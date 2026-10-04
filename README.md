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
Node state is stored in the Data Protection Keychain on both macOS and iOS,
scoped by the caller-supplied namespace. Items are device-local and never synchronize
through iCloud Keychain. The host must be signed with the appropriate application
identifier and Keychain access-group entitlements; there is no fallback to the
legacy macOS Keychain. The host app handles login UI, SSH policy, peer metadata,
and application storage.

After closing every node for a profile, call
`Node.eraseState(directory:stateNamespace:)` to remove its local credentials and
state directory without starting a node. Keep a durable reference for retry until
cleanup succeeds. This API does not require network access or revoke other profiles.

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

The Keychain integration test requires an entitled, signed test host. Set
`TAILSCALE_KEYCHAIN_TESTS=1` in that host's test environment to run it; plain
`swift test` skips this test because its runner has no Keychain entitlements.
Consumers should also test profile cleanup from their signed app test targets.

## Releases

Native binaries and Swift package releases are separate, as in libghostty-spm.
The native and package workflows publish from existing source tags. Release
workflows validate the checked-out tag, the binary checksum, and the consumer build.

### Automatic upstream tracking

`Weekly Upstream` runs every Monday at 02:00 UTC (10:00 China time), or through
manual dispatch. It tracks both the default-branch HEAD of `tailscale/libtailscale`
and the latest official stable release of `tailscale/tailscale`, including new
stable minor releases. Drafts, prereleases, odd-minor development versions, and
Tailscale downgrades are rejected. Unchanged pins skip builds and releases.

The workflow regenerates the Go dependency patch, rebases compatibility patches,
and raises `.go-version` if the new module requires a newer toolchain. It tests the
Go bridge, commits a candidate, allocates an unused `tailscale.VERSION-BUILD` tag,
and dispatches Go tests on Linux/macOS, followed by the existing native workflow
to build and test all Apple slices.
It then generates and tests the manifest against the published archive, allocates
the next package patch version, and dispatches the package release workflow.
Only after all workflows succeed does it advance `main`, guarded by a lease so
concurrent maintainer changes cannot be overwritten.

This uses the repository's `GITHUB_TOKEN` with Contents and Actions write access;
no personal access token is needed. Tag pushes made with that token do not trigger
push workflows, so both release workflows are dispatched explicitly on their
immutable tags. The scheduled workflow must be present on the default branch.
Repository rules protecting `main` or tags must permit the workflow's writes.

Failures leave `main` unchanged. A native asset or package already published before
a later failure remains immutable; a retry starts from current `main` and allocates
fresh tags. Inspect failed workflow logs and fix incompatible bridge APIs or source
patches before retrying. Automatic tracking does not update consumers' package pins.

To prepare an update locally without committing or publishing:

```sh
python3 Scripts/upstream.py
python3 Scripts/test-upstream.py
Scripts/test-go.sh
```

`--libtailscale-ref SHA` and `--tailscale-version vX.Y.Z` select explicit pins;
`--refresh` regenerates patches even when the selected pins are unchanged.

### Manual releases

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
