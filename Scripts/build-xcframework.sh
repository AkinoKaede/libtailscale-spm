#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
export GOTOOLCHAIN="${GOTOOLCHAIN:-go$(tr -d '[:space:]' < .go-version)}"
root="$PWD"
Scripts/prepare-source.sh
source_dir="$root/.build/libtailscale"
build_dir="$PWD/.build/apple"
mkdir -p "$build_dir" Artifacts
for target in macos-arm64 macos-amd64 ios-arm64 simulator-arm64 simulator-amd64; do
    case "$target" in
        macos-*) sdk=macosx; goos=darwin; minflag=-mmacosx-version-min=15.0 ;;
        ios-*) sdk=iphoneos; goos=ios; minflag=-miphoneos-version-min=18.0 ;;
        simulator-*) sdk=iphonesimulator; goos=ios; minflag=-mios-simulator-version-min=18.0 ;;
    esac
    arch="${target##*-}"
    clangarch="$arch"
    [ "$arch" != amd64 ] || clangarch=x86_64
    mkdir -p "$build_dir/$target"
    sdkpath="$(xcrun --sdk "$sdk" --show-sdk-path)"
    CGO_ENABLED=1 GOOS="$goos" GOARCH="$arch" CC="$(xcrun --sdk "$sdk" --find clang)" \
        CGO_CFLAGS="-isysroot $sdkpath -arch $clangarch $minflag" \
        CGO_LDFLAGS="-isysroot $sdkpath -arch $clangarch $minflag" \
        go -C "$source_dir" build -trimpath -buildmode=c-archive -o "$build_dir/$target/libtailscale.a" .
done
mkdir -p "$build_dir/macos" "$build_dir/simulator"
lipo -create "$build_dir/macos-arm64/libtailscale.a" "$build_dir/macos-amd64/libtailscale.a" -output "$build_dir/macos/libtailscale.a"
lipo -create "$build_dir/simulator-arm64/libtailscale.a" "$build_dir/simulator-amd64/libtailscale.a" -output "$build_dir/simulator/libtailscale.a"
for slice in macos ios-arm64 simulator; do
    framework="$build_dir/$slice/CTailscale.framework"
    mkdir -p "$framework/Headers" "$framework/Modules"
    cp "$build_dir/$slice/libtailscale.a" "$framework/CTailscale"
    cp "$source_dir/tailscale.h" "$source_dir/spm_bridge.h" "$framework/Headers/"
    echo 'framework module CTailscale { umbrella header "spm_bridge.h" export * }' > "$framework/Modules/module.modulemap"
    cat > "$framework/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>CFBundleIdentifier</key><string>com.tailscale.CTailscale</string><key>CFBundleExecutable</key><string>CTailscale</string><key>CFBundlePackageType</key><string>FMWK</string></dict></plist>
EOF
done
rm -rf Artifacts/CTailscale.xcframework
xcodebuild -create-xcframework \
    -framework "$build_dir/macos/CTailscale.framework" \
    -framework "$build_dir/ios-arm64/CTailscale.framework" \
    -framework "$build_dir/simulator/CTailscale.framework" \
    -output "$PWD/Artifacts/CTailscale.xcframework"
