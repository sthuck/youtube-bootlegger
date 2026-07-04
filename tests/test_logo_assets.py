import struct
import xml.etree.ElementTree as ET

from src.youtube_bootlegger.resources import APP_LOGO_PNG, APP_LOGO_SVG


def test_logo_assets_exist_and_have_expected_dimensions():
    assert APP_LOGO_SVG.is_file()
    assert APP_LOGO_PNG.is_file()

    root = ET.parse(APP_LOGO_SVG).getroot()
    assert root.attrib["viewBox"] == "0 0 144.5 144"

    with APP_LOGO_PNG.open("rb") as png_file:
        assert png_file.read(8) == b"\x89PNG\r\n\x1a\n"
        png_file.read(8)
        width, height = struct.unpack(">II", png_file.read(8))

    assert (width, height) == (1024, 1024)
