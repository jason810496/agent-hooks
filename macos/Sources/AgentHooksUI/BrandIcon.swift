import AppKit

/// The Agent Hooks pixel-art mark, drawn programmatically so it ships with the executable
/// without an asset catalog. Mirrors `docs/assets/agent-hooks-logo.svg` on a 20x20 grid.
enum BrandIcon {
    enum ExportError: Error { case bitmap, encode }

    /// Palette indices: 0 = light, 1 = mid, 2 = dark. Matches the SVG's three teal shades.
    private static let palette: [NSColor] = [
        NSColor(srgbRed: 0x53 / 255.0, green: 0xab / 255.0, blue: 0xad / 255.0, alpha: 1),
        NSColor(srgbRed: 0x22 / 255.0, green: 0x8b / 255.0, blue: 0x8d / 255.0, alpha: 1),
        NSColor(srgbRed: 0x1d / 255.0, green: 0x74 / 255.0, blue: 0x76 / 255.0, alpha: 1),
    ]

    /// Dark tile behind the mark in the app icon (matches `agent-hooks-logo-mark.svg`).
    private static let iconBackground = NSColor(
        srgbRed: 0x10 / 255.0, green: 0x2E / 255.0, blue: 0x32 / 255.0, alpha: 1
    )

    /// (x, y, paletteIndex) on a 20x20 grid, y increasing downward (SVG coordinates).
    private static let pixels: [(x: Int, y: Int, color: Int)] = [
        (11, 2, 0), (12, 2, 1), (13, 2, 2),
        (10, 3, 1), (11, 3, 0), (12, 3, 0), (13, 3, 1), (14, 3, 2),
        (9, 4, 0), (10, 4, 0), (11, 4, 1), (14, 4, 1), (15, 4, 2),
        (9, 5, 0), (10, 5, 0), (11, 5, 1), (14, 5, 1), (15, 5, 2),
        (10, 6, 0), (11, 6, 1), (12, 6, 2), (13, 6, 2), (14, 6, 1),
        (11, 7, 0), (12, 7, 1), (13, 7, 2),
        (11, 8, 0), (12, 8, 1), (13, 8, 2),
        (11, 9, 0), (12, 9, 1), (13, 9, 2),
        (11, 10, 0), (12, 10, 1), (13, 10, 2),
        (11, 11, 0), (12, 11, 1), (13, 11, 2),
        (6, 12, 2), (11, 12, 0), (12, 12, 1), (13, 12, 2),
        (6, 13, 2), (7, 13, 1), (11, 13, 0), (12, 13, 1), (13, 13, 2),
        (6, 14, 2), (7, 14, 0), (8, 14, 1), (11, 14, 0), (12, 14, 1), (13, 14, 2),
        (6, 15, 2), (7, 15, 0), (8, 15, 0), (9, 15, 1), (10, 15, 1), (11, 15, 2), (12, 15, 2), (13, 15, 0),
        (7, 16, 1), (8, 16, 0), (9, 16, 0), (10, 16, 1), (11, 16, 1), (12, 16, 0),
        (8, 17, 2), (9, 17, 1), (10, 17, 1), (11, 17, 1), (12, 17, 0),
    ]

    /// Renders the mark into a square `size`×`size` image. When `template` is true the shape is
    /// flattened to a single-color silhouette the menu bar tints for light/dark; otherwise the
    /// full teal palette is used. The art is trimmed to its bounding box and centered so it fills
    /// the square evenly rather than sitting low-right as in the raw 20x20 grid.
    static func image(size: CGFloat, template: Bool, inset: CGFloat = 0) -> NSImage {
        let image = NSImage(size: NSSize(width: size, height: size), flipped: true) { _ in
            NSGraphicsContext.current?.shouldAntialias = false

            let minX = pixels.map(\.x).min() ?? 0
            let maxX = pixels.map(\.x).max() ?? 20
            let minY = pixels.map(\.y).min() ?? 0
            let maxY = pixels.map(\.y).max() ?? 20
            let cols = CGFloat(maxX - minX + 1)
            let rows = CGFloat(maxY - minY + 1)
            let scale = (size - inset * 2) / max(cols, rows)
            let offsetX = (size - cols * scale) / 2
            let offsetY = (size - rows * scale) / 2

            for pixel in pixels {
                (template ? NSColor.black : palette[pixel.color]).setFill()
                NSBezierPath(
                    rect: NSRect(
                        x: offsetX + CGFloat(pixel.x - minX) * scale,
                        y: offsetY + CGFloat(pixel.y - minY) * scale,
                        width: scale,
                        height: scale
                    )
                ).fill()
            }
            return true
        }
        image.isTemplate = template
        return image
    }

    /// The app/Spotlight icon: the teal hook on a dark rounded tile, with transparent margin so
    /// it reads as a standard macOS icon. Mirrors `docs/assets/agent-hooks-logo-mark.svg`.
    static func appIcon(size: CGFloat) -> NSImage {
        NSImage(size: NSSize(width: size, height: size), flipped: true) { _ in
            // Rounded tile, inset from the canvas edges like the macOS icon grid.
            NSGraphicsContext.current?.shouldAntialias = true
            let margin = (size * 0.1).rounded()
            let tile = NSRect(
                x: margin, y: margin, width: size - margin * 2, height: size - margin * 2
            )
            let radius = tile.width * 0.2237
            iconBackground.setFill()
            NSBezierPath(roundedRect: tile, xRadius: radius, yRadius: radius).fill()

            // The 20x20 art grid centered in the tile (mirrors the SVG's translate(2,2) on 24).
            NSGraphicsContext.current?.shouldAntialias = false
            let gridSide = tile.width * (20.0 / 24.0)
            let scale = gridSide / 20.0
            let originX = tile.minX + (tile.width - gridSide) / 2
            let originY = tile.minY + (tile.height - gridSide) / 2
            for pixel in pixels {
                palette[pixel.color].setFill()
                NSBezierPath(
                    rect: NSRect(
                        x: originX + CGFloat(pixel.x) * scale,
                        y: originY + CGFloat(pixel.y) * scale,
                        width: scale,
                        height: scale
                    )
                ).fill()
            }
            return true
        }
    }

    /// Writes a macOS `.iconset` directory (every required size) for `iconutil` to compile into
    /// an `.icns`. Called from the `--write-iconset` build step so the app bundle ships an icon.
    static func writeIconset(to directory: String) throws {
        try FileManager.default.createDirectory(
            atPath: directory, withIntermediateDirectories: true
        )
        let entries: [(name: String, dimension: Int)] = [
            ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
            ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
            ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
            ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
            ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
        ]
        let base = URL(fileURLWithPath: directory)
        for entry in entries {
            let data = try pngData(dimension: entry.dimension)
            try data.write(to: base.appendingPathComponent(entry.name))
        }
    }

    private static func pngData(dimension: Int) throws -> Data {
        guard
            let rep = NSBitmapImageRep(
                bitmapDataPlanes: nil, pixelsWide: dimension, pixelsHigh: dimension,
                bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
            )
        else { throw ExportError.bitmap }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
        appIcon(size: CGFloat(dimension))
            .draw(in: NSRect(x: 0, y: 0, width: dimension, height: dimension))
        NSGraphicsContext.restoreGraphicsState()
        guard let data = rep.representation(using: .png, properties: [:]) else {
            throw ExportError.encode
        }
        return data
    }
}
