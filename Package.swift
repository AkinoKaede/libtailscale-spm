// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "TailscaleKit",
    platforms: [.macOS(.v15), .iOS(.v18)],
    products: [.library(name: "TailscaleKit", targets: ["TailscaleKit"])],
    targets: [
        .binaryTarget(
            name: "CTailscale",
            url: "https://github.com/AkinoKaede/libtailscale-spm/releases/download/tailscale.1.104.1-2/CTailscale.xcframework.zip",
            checksum: "bc87a07142422edc90a0f9e0cc4a870ef295ac6329bd04f1a5e5b8118b331010"
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
