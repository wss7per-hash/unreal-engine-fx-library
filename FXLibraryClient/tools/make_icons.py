# tools/make_icons.py -- generate app/resources/logo.ico and logo.png from the
# in-code logo SVG. Run once (or after changing the logo). Requires Pillow.

import os
import sys

# Make the app package importable.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402

# A QApplication is required to create QPixmap in a headless environment.
_app = QApplication.instance() or QApplication(sys.argv)

# Import the SVG->pixmap renderer from the app.
from app.icons import logo_pixmap  # noqa: E402

from PIL import Image  # noqa: E402

OUT_DIR = os.path.join(ROOT, "app", "resources")
os.makedirs(OUT_DIR, exist_ok=True)

SIZES = [16, 24, 32, 48, 64, 128, 256]


def to_pil(qpm):
    """Convert a QPixmap to a PIL Image (RGBA)."""
    qimg = qpm.toImage().convertToFormat(QImage.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    ptr = qimg.constBits()
    arr = bytes(ptr)
    img = Image.frombytes("RGBA", (w, h), arr, "raw", "RGBA", 0, 1)
    return img


def main():
    pngs = []
    for s in SIZES:
        qpm = logo_pixmap(s)
        img = to_pil(qpm)
        pngs.append(img)
        img.save(os.path.join(OUT_DIR, "logo_%d.png" % s))
        print("wrote logo_%d.png" % s)

    # 256 png as the main logo asset.
    pngs[-1].save(os.path.join(OUT_DIR, "logo.png"))
    print("wrote logo.png")

    # Combine into a multi-resolution .ico.
    # Save the largest first; PIL needs explicit append_images for all smaller sizes.
    largest = pngs[-1].convert("RGBA")
    append = [img.convert("RGBA") for img in pngs[:-1]]
    largest.save(
        os.path.join(OUT_DIR, "logo.ico"),
        format="ICO",
        sizes=[(s, s) for s in reversed(SIZES)],
        append_images=append,
    )
    print("wrote logo.ico")

    # verify
    with Image.open(os.path.join(OUT_DIR, "logo.ico")) as verify:
        print("ico sizes:", verify.info.get("sizes"))


if __name__ == "__main__":
    main()
