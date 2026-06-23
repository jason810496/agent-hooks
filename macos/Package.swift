// swift-tools-version: 5.9
import PackageDescription

// Swift 5 language mode (tools-version 5.9) keeps AppKit/SwiftUI glue free of Swift 6
// strict-concurrency churn. `import SQLite3` resolves to the system libsqlite3 module on
// macOS, so no third-party dependency is needed to speak the shared IPC database.
let package = Package(
    name: "AgentHooksUI",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "agent-hooks-ui", targets: ["AgentHooksUI"]),
    ],
    targets: [
        .executableTarget(
            name: "AgentHooksUI",
            path: "Sources/AgentHooksUI"
        )
    ]
)
