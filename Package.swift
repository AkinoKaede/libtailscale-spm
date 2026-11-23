// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "TailscaleKit",
    platforms: [.macOS(.v15), .iOS(.v18)],
    products: [.library(name: "TailscaleKit", targets: ["TailscaleKit"])],
    targets: [
        .binaryTarget(
            name: "CTailscale",
            url: "https://github.com/AkinoKaede/libtailscale-spm/releases/download/tailscale.1.104.7-2/CTailscale.xcframework.zip",
            checksum: "02f5aa062109f369b727c6d7cd28c7c291acbb83d720cc86da55b42d2fe383b5"
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
