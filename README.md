# libtailscale-spm

A Swift package for embedding the official [Tailscale](https://github.com/tailscale/tailscale)
userspace network on macOS 15+ and iOS 18+. The build downloads
[Tailscale’s libtailscale](https://github.com/tailscale/libtailscale) at the exact commit
in `libtailscale.ref` and applies the patches in `Patches/libtailscale/`. Upstream
source and Git history are not part of this repository.

The `TailscaleKit` product wraps a prebuilt `CTailscale.xcframework` with macOS
arm64/x86_64, iOS arm64, and iOS Simulator arm64/x86_64 slices. `Tailscale.version` and `.go-version` pin the
official Tailscale release and Go toolchain; there is no Tailscale fork or system VPN dependency.

```swift
.package(url: "https://github.com/AkinoKaede/libtailscale-spm.git", from: "1.0.0")
```

Add the `TailscaleKit` product to your target. `Node` owns a userspace Tailscale node,
provides cancellable TCP dialing and LocalAPI requests, and exposes the linked
Tailscale version through `Node.version`. The caller owns returned socket descriptors.
Node state is stored in device-local Keychain items, scoped by the caller-supplied
namespace. The host app handles login UI, SSH policy, peer metadata, and application storage.

## Development

Use Xcode with macOS and iOS SDKs, and the Go version in `.go-version`.

```sh
Scripts/test-go.sh
Scripts/build-xcframework.sh
Scripts/test-package.sh --local
```

The consumer check runs Swift tests against the native binary and builds iOS device
and simulator destinations. `Package.local.swift` points at the ignored `Artifacts/`
directory; the validation script stages it under `.build/` without changing the
release manifest. Linux CI checks the upstream C bindings and real userspace
Exit Node routing; the Apple bridge and Keychain implementation build only on Apple platforms.

## Releases

Native binaries and Swift package releases are separate, as in libghostty-spm.
CI publishes from existing source tags and never creates commits. Release
workflows validate the checked-out tag, the binary checksum, and the consumer build.

1. Update the version pins, dependency patch, bridge, or Apple build inputs. Test and commit the changes, then create a native tag such as
   `git tag -a tailscale.1.102.5-1 -m "Tailscale 1.102.5 Apple build 1"`,
   then push the branch and tag. `Build XCFramework` tests all supported targets
   and publishes the XCFramework ZIP, checksum, and toolchain/source metadata.
   Use a new build suffix when rebuilding the same Tailscale version.
2. Download the published ZIP and generate the package manifest:
   ```sh
   gh release download tailscale.1.102.5-1 --pattern CTailscale.xcframework.zip --dir Artifacts
   Scripts/build-manifest.sh Artifacts/CTailscale.xcframework.zip \
     https://github.com/AkinoKaede/libtailscale-spm/releases/download/tailscale.1.102.5-1/CTailscale.xcframework.zip
   Scripts/verify-release.sh
   Scripts/test-package.sh
   ```
3. Commit the manifest and create a semantic package tag, for example `1.0.0`.
   Push them. `Release Swift Package` downloads and
   checks the native asset, tests the published consumer, and publishes the package release.

Both workflows also support manual dispatch with an existing tag. Published
assets and package versions are immutable; failed unpublished runs can be retried.
Swift-only updates may reuse a compatible native binary.

## Source layout

- `Sources/`: Swift wrapper and public API.
- `Bridge/`: Apple Keychain and cancellable LocalAPI/TCP bridge, overlaid at build time.
- `Patches/libtailscale/`: changes to the pinned upstream, including locked Go dependencies.
- `Scripts/`: source preparation, XCFramework builds, consumer verification, and manifest generation.
- `.github/workflows/`: Go/Swift checks, native binary publication, and Swift package releases.

`Scripts/prepare-source.sh` creates a disposable checkout under `.build/libtailscale`,
applies each patch strictly, and overlays the bridge. It fails if the dependency
patch disagrees with `Tailscale.version`. To update upstream, change `libtailscale.ref`
and rebase the patches; do not copy upstream files into this repository.

Report this package’s issues
[here](https://github.com/AkinoKaede/libtailscale-spm/issues); upstream Tailscale issues
belong in [tailscale/tailscale](https://github.com/tailscale/tailscale/issues).

## License

BSD 3-Clause for this wrapper; see [LICENSE](LICENSE). The downloaded upstream
libtailscale retains its original copyright and license; see [NOTICE](NOTICE).
