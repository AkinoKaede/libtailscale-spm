#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
root="$PWD"
revision=$(tr -d '[:space:]' < libtailscale.ref)
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || { echo "libtailscale.ref must be a full commit SHA" >&2; exit 1; }
source_dir="$root/.build/libtailscale"
if [[ ! -d "$source_dir/.git" ]]; then
    mkdir -p "$source_dir"
    git -C "$source_dir" init --quiet
    git -C "$source_dir" remote add origin https://github.com/tailscale/libtailscale.git
fi
if ! git -C "$source_dir" cat-file -e "$revision^{commit}" 2>/dev/null; then
    git -C "$source_dir" fetch --depth 1 origin "$revision"
fi
# This checkout is disposable build output, never the maintainer's source tree.
git -C "$source_dir" checkout --quiet --detach --force "$revision"
git -C "$source_dir" clean -fdq
for patch in "$root"/Patches/libtailscale/*.patch; do
    git -C "$source_dir" apply --check "$patch"
    git -C "$source_dir" apply "$patch"
done
cp "$root"/Bridge/* "$source_dir/"
expected=$(tr -d '[:space:]' < Tailscale.version)
actual=$(awk '$1 == "tailscale.com" {print $2}' "$source_dir/go.mod")
[[ "$actual" == "$expected" ]] || { echo "Tailscale.version does not match the dependency patch" >&2; exit 1; }
