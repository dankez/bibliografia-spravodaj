#!/usr/bin/env python3
"""Confirm selected cave-to-SMOPaJ matches through a direct Codex decision loop.

This is a narrow recovery/helper script for cases where the bulk matcher is too
fragile for long-running Codex subprocess batches. It reuses the same candidate
shortlist, prompt, validation, and JSON output format as ai_match_smopaj_caves.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import ai_match_smopaj_caves as matcher


BASE_DIR = Path(__file__).resolve().parents[1]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caves", type=Path, default=matcher.DEFAULT_CAVES_PATH)
    parser.add_argument("--register", type=Path, default=matcher.DEFAULT_REGISTER_PATH)
    parser.add_argument("--output", type=Path, default=matcher.DEFAULT_OUTPUT_PATH)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--max-candidates", type=int, default=5)
    parser.add_argument("--min-confidence", type=float, default=0.82)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--slug", action="append", required=True)
    return parser.parse_args()


def run_codex_text_decision(
    cave: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    model: str,
    timeout: int,
) -> dict[str, Any]:
    codex_cmd = ["rtk", "codex"] if shutil.which("rtk") else ["codex"]
    prompt = matcher.ai_prompt(cave, candidates, matcher.cave_summary_context(cave))
    prompt += "\n\nReturn only one valid JSON object."
    with tempfile.TemporaryDirectory(prefix="sss-codex-text-") as tmp_dir:
        output_path = Path(tmp_dir) / "response.json"
        cmd = [
            *codex_cmd,
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "workspace-write",
            "--color",
            "never",
            "--model",
            model,
            "-o",
            str(output_path),
            prompt,
        ]
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"codex text exec failed with code {result.returncode}: {error[-1200:]}")
        raw = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else result.stdout.strip()
        return matcher.extract_json_object(raw)


def main() -> int:
    args = parse_args()
    caves = load_json(args.caves, [])
    register = load_json(args.register, {})
    output = load_json(
        args.output,
        {
            "schema_version": "smopaj-cave-ai-matches/v1",
            "matches": [],
            "deferred": [],
            "stats": {},
        },
    )
    entries = [entry for entry in register.get("entries", []) if isinstance(entry, dict)]
    caves_by_slug = {str(cave.get("slug") or ""): cave for cave in caves if isinstance(cave, dict)}
    processed = {
        str(item.get("cave_slug") or "")
        for item in [*(output.get("matches") or []), *(output.get("deferred") or [])]
        if str(item.get("cave_slug") or "")
    }

    for slug in args.slug:
        if slug in processed:
            print(f"skip {slug}", flush=True)
            continue
        cave = caves_by_slug.get(slug)
        if not cave:
            raise SystemExit(f"Unknown cave slug: {slug}")

        started = time.monotonic()
        candidates = matcher.shortlist_smopaj_candidates(cave, entries, max_candidates=args.max_candidates)
        decision = {"decision": "defer", "cave_number": "", "confidence": 0.0, "reason": "no candidates"}
        status = "defer"
        if candidates:
            try:
                decision = run_codex_text_decision(
                    cave,
                    candidates,
                    model=args.model,
                    timeout=args.timeout,
                )
                decision = matcher.validate_decision(decision, candidates, args.min_confidence)
            except Exception as exc:  # noqa: BLE001 - error is preserved in generated audit data.
                decision = {
                    "decision": "defer",
                    "cave_number": "",
                    "confidence": 0.0,
                    "reason": f"AI backend error: {str(exc)[:500]}",
                }

        if decision["decision"] == "match":
            output.setdefault("matches", []).append(
                matcher.decision_to_match(cave, decision, candidates, backend="codex", model=args.model)
            )
            status = "match"
        else:
            output.setdefault("deferred", []).append(
                {
                    "cave_slug": slug,
                    "cave_name": cave.get("name", ""),
                    "reason": decision.get("reason") or "AI nevybrala dostatočne istý SMOPaJ záznam",
                    "candidate_numbers": [item["cave_number"] for item in candidates[:5]],
                }
            )

        output["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        stats = output.setdefault("stats", {})
        stats["matched"] = len(output.get("matches") or [])
        stats["deferred"] = len(output.get("deferred") or [])
        matcher.write_json(args.output, output)
        print(
            f"{status} {slug} candidates={len(candidates)} time={time.monotonic() - started:.1f}s",
            flush=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
