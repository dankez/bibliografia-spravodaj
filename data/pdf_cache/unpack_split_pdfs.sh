#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

for zip_file in *.pdf.zip; do
  [ -e "$zip_file" ] || continue
  pdf_file="${zip_file%.zip}"
  if [ -f "$pdf_file" ]; then
    echo "Skipping $pdf_file (already exists)"
    continue
  fi
  echo "Unpacking $zip_file -> $pdf_file ..."
  7z x -y "$zip_file" >/dev/null
done
echo "Done."
