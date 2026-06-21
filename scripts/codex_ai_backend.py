#!/usr/bin/env python3
"""Shared Codex CLI JSON backend for local AI scripts."""

from __future__ import annotations

import json
import shutil
import sys
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


class CodexBackendError(RuntimeError):
    """Raised when codex exec cannot produce the expected JSON payload."""


class CodexAuthError(CodexBackendError):
    """Raised when Codex saved authentication is missing, expired, or revoked."""


AUTH_ERROR_MARKERS = (
    "401 Unauthorized",
    "refresh_token_invalidated",
    "access token could not be refreshed",
    "session has ended",
    "Please log out and sign in again",
)


def run_codex_json(prompt: str, schema: dict[str, Any], model: str, timeout: int = 300) -> dict[str, Any]:
    """Run `codex exec` with saved Codex auth and a JSON Schema response contract."""
    if not shutil.which("codex"):
        raise CodexBackendError("Codex CLI was not found on PATH. Run `codex login` after installing Codex.")
    codex_cmd = ["rtk", "codex"] if shutil.which("rtk") else ["codex"]

    with tempfile.TemporaryDirectory(prefix="sss-codex-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        schema_path = tmp_path / "schema.json"
        output_path = tmp_path / "response.json"
        schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")

        cmd = [
            *codex_cmd,
            "exec",
            "-c",
            'model_reasoning_effort="low"',
            "-c",
            'model_reasoning_summary="none"',
            "-c",
            'model_verbosity="low"',
            "--ignore-rules",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "workspace-write",
            "--color",
            "never",
            "--model",
            model,
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "-",
        ]

        started = time.monotonic()
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=tmp_path,
        )
        assert process.stdin is not None
        process.stdin.write(prompt)
        process.stdin.close()

        last_heartbeat = started
        while process.poll() is None:
            now = time.monotonic()
            if now - started > timeout:
                process.kill()
                process.wait()
                raise CodexBackendError(f"codex exec timed out after {timeout}s")
            if now - last_heartbeat >= 20:
                print(f"  codex backend still running ({int(now - started)}s)", file=sys.stderr, flush=True)
                last_heartbeat = now
            time.sleep(1)

        stdout = process.stdout.read() if process.stdout is not None else ""
        stderr = process.stderr.read() if process.stderr is not None else ""

        class Result:
            returncode = process.returncode

        result = Result()
        result.stdout = stdout
        result.stderr = stderr

        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            if any(marker.lower() in stderr.lower() for marker in AUTH_ERROR_MARKERS):
                raise CodexAuthError(
                    "Codex auth failed. Run `codex logout && codex login`, then verify with "
                    "`codex exec --skip-git-repo-check --ephemeral \"Return ok\"`."
                )
            raise CodexBackendError(f"codex exec failed with code {result.returncode}: {stderr[-1200:]}")

        raw = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        if not raw:
            raw = result.stdout.strip()
        if not raw:
            raise CodexBackendError("codex exec returned an empty response")

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CodexBackendError(f"codex exec returned invalid JSON: {raw[:1200]}") from exc
