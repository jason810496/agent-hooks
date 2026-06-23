import Foundation

/// User-tunable thresholds, persisted in the shared `settings` table so both sides agree.
struct Settings {
    var surfaceThresholdCount: Int
    var surfaceQuietSeconds: Int
    var pollIntervalMs: Int
    /// 0...3 step; mapped to a SwiftUI `DynamicTypeSize` by ``TextSizeOption``.
    var textSizeLevel: Int

    static let keyThreshold = "surface_threshold_count"
    static let keyQuiet = "surface_quiet_seconds"
    static let keyPoll = "poll_interval_ms"
    static let keyTextSize = "ui_text_size_level"

    static let defaults: [String: String] = [
        keyThreshold: "5",
        keyQuiet: "20",
        keyPoll: "400",
        keyTextSize: "1",
    ]

    static func load(from db: Database) -> Settings {
        Settings(
            surfaceThresholdCount: intSetting(db, keyThreshold, 5, min: 1, max: 99),
            surfaceQuietSeconds: intSetting(db, keyQuiet, 20, min: 1, max: 600),
            pollIntervalMs: intSetting(db, keyPoll, 400, min: 100, max: 5000),
            textSizeLevel: intSetting(db, keyTextSize, 1, min: 0, max: 3)
        )
    }

    private static func intSetting(
        _ db: Database, _ key: String, _ fallback: Int, min lower: Int, max upper: Int
    ) -> Int {
        guard let raw = db.settingValue(key), let value = Int(raw) else { return fallback }
        return Swift.min(Swift.max(value, lower), upper)
    }
}
