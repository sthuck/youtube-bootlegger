"""Package resource paths."""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
ASSETS_DIR = PACKAGE_ROOT / "assets"
APP_LOGO_PNG = ASSETS_DIR / "logo.png"
APP_LOGO_SVG = ASSETS_DIR / "logo.svg"
