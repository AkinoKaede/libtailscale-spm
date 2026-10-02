#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
export GOTOOLCHAIN="${GOTOOLCHAIN:-go$(tr -d '[:space:]' < .go-version)}"
Scripts/prepare-source.sh
cd .build/libtailscale
go test ./...
