// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "TailscaleKit",
    platforms: [.macOS(.v15), .iOS(.v18)],
    products: [.library(name: "TailscaleKit", targets: ["TailscaleKit"])],
    targets: [
        .binaryTarget(
            name: "CTailscale",
            url: "https://github.com/AkinoKaede/libtailscale-spm/releases/download/tailscale.1.102.5-3/CTailscale.xcframework.zip",
            checksum: "8e246684afece748ebcc2d2e5f99367750d0025682b79009f96538f00d270e97"
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
