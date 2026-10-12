// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "TailscaleKit",
    platforms: [.macOS(.v15), .iOS(.v18)],
    products: [.library(name: "TailscaleKit", targets: ["TailscaleKit"])],
    targets: [
        .binaryTarget(
            name: "CTailscale",
            url: "https://github.com/AkinoKaede/libtailscale-spm/releases/download/tailscale.1.104.1-1/CTailscale.xcframework.zip",
            checksum: "3d1e3c4abc4027d64a3c9604c10bad5a2bb6fabcaf26f1e55e136871dd1c0e1d"
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
