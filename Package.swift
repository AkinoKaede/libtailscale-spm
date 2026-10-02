// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "TailscaleKit",
    platforms: [.macOS(.v15), .iOS(.v18)],
    products: [.library(name: "TailscaleKit", targets: ["TailscaleKit"])],
    targets: [
        .binaryTarget(
            name: "CTailscale",
            url: "https://github.com/AkinoKaede/libtailscale-spm/releases/download/tailscale.1.102.5-1/CTailscale.xcframework.zip",
            checksum: "98214f20dfcf6eca92ce622c49c062ddf231086181491f2e358db5770239c21f"
        ),
        .target(
            name: "TailscaleKit", dependencies: ["CTailscale"],
            linkerSettings: [
                .linkedFramework("Security"), .linkedFramework("CoreFoundation"), .linkedLibrary("resolv"),
            ]
        ),
        .testTarget(name: "TailscaleKitTests", dependencies: ["TailscaleKit"]),
    ]
)
