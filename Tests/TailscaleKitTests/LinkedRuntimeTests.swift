import TailscaleKit
import Testing

@Test func binaryExportsTheLinkedTailscaleVersion() {
  // This crosses Swift, C, and Go; a source-only Swift build cannot prove it.
  let version = Node.version
  #expect(version.hasPrefix("v"))
  #expect(version.dropFirst().split(separator: ".").count == 3)
}
