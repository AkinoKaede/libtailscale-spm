import CTailscale
import Darwin
import Foundation

public struct NodeError: Error, LocalizedError, Sendable {
  public var message: String
  public var errorDescription: String? { message }
}

/// One userspace node. Persisted private state is device-local Keychain data.
public actor Node {
  public nonisolated static var version: String {
    guard let value = LtVersion() else { return "unknown" }
    defer { free(value) }
    return String(cString: value)
  }

  private let handle: Int32
  private var closed = false
  private let stateNamespace: String
  private let directory: URL

  public init(
    hostname: String, directory: URL, controlURL: String, stateNamespace: String, authKey: String?
  ) throws {
    self.stateNamespace = stateNamespace
    self.directory = directory
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    var resource = URLResourceValues()
    resource.isExcludedFromBackup = true
    var directory = directory
    try directory.setResourceValues(resource)
    let handle = tailscale_new()
    self.handle = handle
    tailscale_set_logfd(handle, -1)
    tailscale_set_dir(handle, directory.path)
    tailscale_set_hostname(handle, hostname)
    tailscale_set_control_url(handle, controlURL)
    let store = stateNamespace.withCString {
      LtConfigureStore(handle, UnsafeMutablePointer(mutating: $0))
    }
    guard store == 0 else {
      tailscale_close(handle)
      throw NodeError(message: "Unable to configure node state")
    }
    if let authKey { tailscale_set_authkey(handle, authKey) }
    guard tailscale_start(handle) == 0 else {
      var buffer = [CChar](repeating: 0, count: 4096)
      tailscale_errmsg(handle, &buffer, buffer.count)
      tailscale_close(handle)
      throw NodeError(
        message: String(
          decoding: buffer.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, as: UTF8.self))
    }
  }

  deinit { if !closed { tailscale_close(handle) } }

  public func close() {
    guard !closed else { return }
    closed = true
    tailscale_close(handle)
  }

  /// Erases only this profile's device-local state after its transport is closed.
  public func eraseState() throws {
    guard closed else { throw NodeError(message: "Close the node before erasing its state") }
    try Self.eraseState(directory: directory, stateNamespace: stateNamespace)
  }

  /// Erases an inactive profile without constructing or starting a node.
  /// The caller must first close every node using this namespace and directory.
  /// Keep a durable cleanup reference until this operation succeeds; retries are safe.
  public nonisolated static func eraseState(directory: URL, stateNamespace: String) throws {
    guard !stateNamespace.isEmpty else { throw NodeError(message: "A state namespace is required") }
    let result = stateNamespace.withCString { lt_store_delete_scope($0) }
    guard result == 0 else { throw NodeError(message: "Unable to erase node state") }
    if FileManager.default.fileExists(atPath: directory.path) {
      try FileManager.default.removeItem(at: directory)
    }
  }

  public func request(method: String = "GET", path: String, body: String = "", timeout: Int32 = 15)
    async throws -> Data
  {
    guard !closed else { throw NodeError(message: "Node is closed") }
    let handle = handle
    let operation = LtNewOperation()
    defer { LtReleaseOperation(operation) }
    return try await withTaskCancellationHandler {
      let data = try await Task.detached {
        var response: UnsafeMutablePointer<CChar>?
        var error: UnsafeMutablePointer<CChar>?
        defer {
          free(response)
          free(error)
        }
        let result = method.withCString { method in
          path.withCString { path in
            body.withCString { body in
              LtRequest(
                handle, UnsafeMutablePointer(mutating: method),
                UnsafeMutablePointer(mutating: path),
                UnsafeMutablePointer(mutating: body), operation, timeout, &response, &error)
            }
          }
        }
        guard result == 0 else {
          throw NodeError(message: error.map { String(cString: $0) } ?? "LocalAPI failed")
        }
        return response.map { Data(bytes: $0, count: strlen($0)) } ?? Data()
      }.value
      try Task.checkCancellation()
      return data
    } onCancel: {
      LtCancelOperation(operation)
    }
  }

  /// The caller owns the returned socket descriptor, including close on cancellation.
  public func dial(host: String, port: Int, timeout: Int32 = 20) async throws -> Int32 {
    guard !closed else { throw NodeError(message: "Node is closed") }
    let handle = handle
    let address = host.contains(":") ? "[\(host)]:\(port)" : "\(host):\(port)"
    let operation = LtNewOperation()
    defer { LtReleaseOperation(operation) }
    return try await withTaskCancellationHandler {
      let fd = try await Task.detached {
        var fd: Int32 = -1
        var error: UnsafeMutablePointer<CChar>?
        defer { free(error) }
        let result = address.withCString {
          LtDial(handle, UnsafeMutablePointer(mutating: $0), operation, timeout, &fd, &error)
        }
        guard result == 0 else {
          throw NodeError(message: error.map { String(cString: $0) } ?? "Dial failed")
        }
        var yes: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &yes, socklen_t(MemoryLayout<Int32>.size))
        return fd
      }.value
      do { try Task.checkCancellation() } catch {
        Darwin.close(fd)
        throw error
      }
      return fd
    } onCancel: {
      LtCancelOperation(operation)
    }
  }
}
