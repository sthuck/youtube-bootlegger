"""Render or resize logo assets for window icons and QML."""

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "src" / "youtube_bootlegger" / "assets"
SVG_PATH = ASSETS_DIR / "logo.svg"
PNG_PATH = ASSETS_DIR / "logo.png"
TARGET_SIZE = 1024


def _render_svg_to_png(target: Path, size: int) -> None:
    renderer = QSvgRenderer(str(SVG_PATH))
    image = QImage(QSize(size, size), QImage.Format.Format_ARGB32)
    image.fill(0)

    painter = QPainter(image)
    renderer.render(painter)
    painter.end()

    if not image.save(str(target), "PNG"):
        raise SystemExit(f"Failed to write {target}")


def _resize_png(source: Path, target: Path, size: int) -> None:
    image = QImage(str(source))
    if image.isNull():
        raise SystemExit(f"Failed to read {source}")

    if image.width() == size and image.height() == size:
        return

    scaled = image.scaled(
        size,
        size,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    if not scaled.save(str(target), "PNG"):
        raise SystemExit(f"Failed to write {target}")


def main() -> None:
    force_svg = "--from-svg" in sys.argv

    if force_svg:
        if not SVG_PATH.is_file():
            raise SystemExit(f"Missing {SVG_PATH}")
        _render_svg_to_png(PNG_PATH, TARGET_SIZE)
        return

    if PNG_PATH.is_file():
        _resize_png(PNG_PATH, PNG_PATH, TARGET_SIZE)
        return

    if SVG_PATH.is_file():
        _render_svg_to_png(PNG_PATH, TARGET_SIZE)
        return

    raise SystemExit(f"Missing logo assets in {ASSETS_DIR}")


if __name__ == "__main__":
    main()
