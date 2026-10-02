#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
archive="${1:?Usage: build-manifest.sh ARCHIVE URL}"
url="${2:?A release asset URL is required}"
checksum=$(swift package compute-checksum "$archive")
python3 - "$url" "$checksum" <<'PYTHON'
import pathlib, re, sys
url, checksum = sys.argv[1:]
if not re.fullmatch(r"https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/download/[A-Za-z0-9_.-]+/CTailscale\.xcframework\.zip", url):
    raise SystemExit("Expected a GitHub release URL for CTailscale.xcframework.zip")
template = pathlib.Path("Package.swift.template").read_text()
pathlib.Path("Package.swift").write_text(template.replace("__BINARY_URL__", url).replace("__BINARY_CHECKSUM__", checksum))
PYTHON
