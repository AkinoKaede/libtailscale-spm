#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .build/release
swift package dump-package > .build/release/package.json
python3 - <<'PYTHON'
import json, pathlib, re, urllib.request, hashlib
package = json.loads(pathlib.Path(".build/release/package.json").read_text())
target = next(t for t in package["targets"] if t["name"] == "CTailscale")
url, expected = target.get("url", ""), target.get("checksum", "")
if not re.fullmatch(r"https://github.com/AkinoKaede/libtailscale-spm/releases/download/tailscale\.[0-9]+\.[0-9]+\.[0-9]+-[0-9]+/CTailscale\.xcframework\.zip", url):
    raise SystemExit("Manifest must reference a published native release")
archive = pathlib.Path(".build/release/CTailscale.xcframework.zip")
with urllib.request.urlopen(url) as source, archive.open("wb") as destination:
    while chunk := source.read(1024 * 1024):
        destination.write(chunk)
with archive.open("rb") as source:
    actual = hashlib.file_digest(source, "sha256").hexdigest()
if actual != expected:
    raise SystemExit(f"Binary checksum mismatch: expected {expected}, got {actual}")
print(f"Verified {url}: {actual}")
PYTHON
