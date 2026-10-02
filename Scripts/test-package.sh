#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
root="$PWD"
if [[ "${1:-}" == --local ]]; then
    stage="$root/.build/package-validation"
    mkdir -p "$stage"
    cp Package.local.swift "$stage/Package.swift"
    for entry in Sources Tests Artifacts; do
        ln -sfn "$root/$entry" "$stage/$entry"
    done
    cd "$stage"
fi
# The release asset is public; validation must not prompt for Keychain access.
swift test --disable-keychain
for destination in 'generic/platform=iOS' 'generic/platform=iOS Simulator'; do
    xcodebuild -scheme TailscaleKit -destination "$destination" \
        -derivedDataPath "$root/.build/package-xcode" \
        -onlyUsePackageVersionsFromResolvedFile -packageAuthorizationProvider netrc CODE_SIGNING_ALLOWED=NO build
done
