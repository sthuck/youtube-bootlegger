"""Render logo.svg to logo.png for window icons and QML."""

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
SVG_PATH = ROOT / "src" / "youtube_bootlegger" / "assets" / "logo.svg"
PNG_PATH = ROOT / "src" / "youtube_bootlegger" / "assets" / "logo.png"
SIZE = 1024


def main() -> None:
    renderer = QSvgRenderer(str(SVG_PATH))
    image = QImage(QSize(SIZE, SIZE), QImage.Format.Format_ARGB32)
    image.fill(0)

    painter = QPainter(image)
    renderer.render(painter)
    painter.end()

    if not image.save(str(PNG_PATH), "PNG"):
        raise SystemExit(f"Failed to write {PNG_PATH}")


if __name__ == "__main__":
    main()
