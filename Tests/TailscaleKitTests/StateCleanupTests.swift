import CTailscale
import Foundation
import Security
import TailscaleKit
import Testing

// Data Protection Keychain requires a signed test host with Keychain entitlements.
@Test(.enabled(if: ProcessInfo.processInfo.environment["TAILSCALE_KEYCHAIN_TESTS"] == "1"))
func inactiveProfileCleanupIsScopedAndIdempotent() throws {
  let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  let first = root.appendingPathComponent("first")
  let second = root.appendingPathComponent("second")
  let scopes = (0..<2).map { _ in "libtailscale.test.\(UUID())" }
  let profileKey = "profile-\(UUID().uuidString.prefix(4).lowercased())"
  let keys = ["_machinekey", profileKey, "_current-profile", "_profiles"]
  defer {
    // Clean every fixture even when testing an older binary that deletes only one item.
    for scope in scopes {
      for _ in keys { _ = scope.withCString { lt_store_delete_scope($0) } }
    }
    try? FileManager.default.removeItem(at: root)
  }
  for (index, directory) in [first, second].enumerated() {
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    try Data([UInt8(index)]).write(to: directory.appendingPathComponent("state"))
    for key in keys {
      let status = scopes[index].withCString { scope in
        key.withCString { key in
          "synthetic-state-\(index)".withCString { lt_store_write(scope, key, $0, Int32(strlen($0))) }
        }
      }
      #expect(status == errSecSuccess)
    }
  }
  try Node.eraseState(directory: first, stateNamespace: scopes[0])
  #expect(!FileManager.default.fileExists(atPath: first.path))
  #expect(try Data(contentsOf: second.appendingPathComponent("state")) == Data([1]))
  for index in 0..<2 {
    for key in keys {
      var bytes: UnsafeMutableRawPointer?
      var count: Int32 = 0
      let status = scopes[index].withCString { scope in
        key.withCString { lt_store_read(scope, $0, &bytes, &count) }
      }
      defer { free(bytes) }
      #expect(status == (index == 0 ? errSecItemNotFound : errSecSuccess))
      if index == 1, let bytes {
        #expect(Data(bytes: bytes, count: Int(count)) == Data("synthetic-state-1".utf8))
      }
    }
  }
  try Node.eraseState(directory: first, stateNamespace: scopes[0])
  #expect(throws: NodeError.self) { try Node.eraseState(directory: second, stateNamespace: "") }
  #expect(FileManager.default.fileExists(atPath: second.path))
}
