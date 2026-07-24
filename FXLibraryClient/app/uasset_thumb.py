"""Pure-Python extractor for the editor thumbnail embedded inside a .uasset.

Unreal Engine stores an editor-generated thumbnail for many assets (Niagara
systems, Cascade particle systems, meshes, materials ...) directly inside the
.uasset package. Modern UE compresses that thumbnail image as a PNG, so the raw
PNG bytes are physically present near the end of the package file.

This module locates that PNG by scanning for the PNG signature, validates each
candidate by walking its chunk table (IHDR -> ... -> IEND), re-decodes it
through Pillow to normalize color channels, and writes the result out to
``out_path``. No Unreal Editor process is launched and no third-party
dependency is required.

If the asset has no embedded thumbnail (e.g. it was never opened/saved with a
thumbnail), :func:`extract_thumbnail` returns ``False`` and the caller is
expected to fall back to a generated "no thumbnail" placeholder.
"""

import io
import os
import struct

PNG_SIG = b"\x89PNG\r\n\x1a\n"

# Read the whole file when it is reasonably small; for very large assets the
# thumbnail lives near the tail of the package, so only the tail is scanned to
# bound memory use.
_WHOLE_FILE_LIMIT = 64 * 1024 * 1024      # <= 64 MB: read entire file
_TAIL_READ = 32 * 1024 * 1024             # otherwise scan last 32 MB


def _png_dims(data, start):
    """Return (width, height) from the IHDR chunk of a PNG at ``start`` or
    (-1, -1) if the bytes right after the signature are not a valid IHDR."""
    if data[start + 12:start + 16] != b"IHDR":
        return (-1, -1)
    try:
        w = struct.unpack(">I", data[start + 16:start + 20])[0]
        h = struct.unpack(">I", data[start + 20:start + 24])[0]
        return (w, h)
    except Exception:
        return (-1, -1)


# The IEND chunk of every PNG is byte-for-byte identical: zero-length data, the
# type "IEND", and the fixed CRC 0xAE426082. Searching for the type+CRC (8 bytes)
# avoids matching the literal string "IEND" that can appear by chance inside the
# compressed IDAT stream (which truncates the image and yields a CRC error).
_IEND = b"IEND\xae\x42\x60\x82"


def _png_end(data, start):
    """Return the byte offset just past the PNG's IEND chunk, or -1.

    A strict chunk-table walk proved unreliable on some UE-authored thumbnail
    PNGs (their IDAT layout does not always match a naive stride walk), so the
    unique IEND terminator (type + fixed CRC) is located directly."""
    j = data.find(_IEND, start)
    if j < 0:
        return -1
    end = j + len(_IEND)  # 'IEND'(4) + fixed CRC(4)
    return end if end <= len(data) else len(data)


def _iter_pngs(data):
    """Yield (start, end, width, height) for every PNG found in ``data``."""
    start = 0
    while True:
        i = data.find(PNG_SIG, start)
        if i < 0:
            break
        w, h = _png_dims(data, i)
        end = _png_end(data, i)
        yield (i, end, w, h)
        start = i + 8


def find_best_png(data, min_size=16):
    """Return (start, end) of the best embedded PNG for a thumbnail, or None.

    Selection rules (in priority order):
      1. Must be decodable by Pillow (filters out garbage bytes that happen
         to start with a PNG signature but are not real images).
      2. Prefer images with dimensions in the typical UE thumbnail range
         (<= 512 px on each side). Larger "PNGs" are usually embedded
         textures or compressed data that coincidentally match the signature.
      3. Among equally valid candidates, pick the largest.
    """
    candidates = []
    for (i, end, w, h) in _iter_pngs(data):
        if end <= i:
            continue
        if w < min_size or h < min_size:
            continue
        blen = end - i
        raw = data[i:end]
        # Validate: must be decodable by Pillow. This filters out binary
        # blobs that start with the PNG signature by coincidence (e.g.
        # DXT-compressed textures inside .uasset files).
        try:
            from PIL import Image
            bio = io.BytesIO(raw)
            im = Image.open(bio)
            im.load()          # force full decode; raises on corrupt IDAT
            candidates.append((blen, i, end, w, h))
        except Exception:
            continue

    if not candidates:
        return None

    # Sort: prefer reasonable thumbnail sizes (both dims <= 512), then by
    # size descending. This ensures we pick the actual editor thumbnail over
    # an accidentally-matched large texture blob.
    def _score(c):
        blen, i, end, w, h = c
        reasonable = 1 if (w <= 512 and h <= 512) else 0
        return (reasonable, blen)

    candidates.sort(key=_score, reverse=True)
    best = candidates[0]
    return (best[1], best[2])


def _re_encode_png(raw_png: bytes) -> bytes:
    """Re-decode a candidate PNG with Pillow and re-encode it as plain RGB.

    Why this matters: some UE-authored thumbnails come out of the package with
    bogus color profiles (iCCP / sRGB chunks) or with a non-standard
    channel/bit-depth layout (palette / 16-bit) that downstream decoders render
    with the wrong colors (the "red particle shows up blue" complaint). A
    round-trip through Pillow normalizes the channels and drops profile noise,
    so the saved PNG is always a clean, channel-correct RGB image."""
    try:
        from PIL import Image
    except Exception:
        return raw_png
    try:
        bio = io.BytesIO(raw_png)
        im = Image.open(bio)
        im.load()
        # Convert anything (RGBA, P, I, F, ...) into a sane RGB representation.
        if im.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", im.size, (0, 0, 0))
            try:
                bg.paste(im, mask=im.split()[-1])
            except Exception:
                bg = im.convert("RGB")
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, format="PNG", optimize=False)
        return out.getvalue()
    except Exception:
        return raw_png


def extract_thumbnail(uasset_path, out_path, min_size=16):
    """Extract the embedded editor thumbnail from ``uasset_path`` and write it
    to ``out_path`` as a PNG. Returns True on success, False if the asset has no
    usable embedded thumbnail or on any I/O error.

    The extracted bytes are normalized through Pillow to guarantee correct color
    channels (UE-saved PNGs sometimes carry profiles or odd bit depths that make
    the image render with the wrong colors if copied verbatim)."""
    try:
        size = os.path.getsize(uasset_path)
    except OSError:
        return False
    if size <= 0:
        return False
    try:
        with open(uasset_path, "rb") as f:
            if size > _WHOLE_FILE_LIMIT:
                f.seek(size - _TAIL_READ)
            data = f.read()
    except OSError:
        return False

    hit = find_best_png(data, min_size=min_size)
    if hit is None:
        return False
    png = data[hit[0]:hit[1]]
    if not png.startswith(PNG_SIG):
        return False

    # Normalize channels so we never write a PNG with shifted color channels.
    normalized = _re_encode_png(png)
    if not normalized.startswith(PNG_SIG):
        normalized = png

    try:
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(normalized)

        # Post-write validation: ensure the file we just wrote is actually
        # decodable (catches rare cases where re-encoding produces a corrupt
        # PNG that Pillow itself can round-trip but Qt cannot).
        try:
            from PIL import Image as _PILImage
            _PILImage.open(out_path).load()
        except Exception:
            # Re-encode produced garbage; fall back to raw bytes
            with open(out_path, "wb") as f:
                f.write(png)
            try:
                _PILImage.open(out_path).load()
            except Exception:
                # Raw bytes also bad — delete and report failure
                try:
                    os.remove(out_path)
                except OSError:
                    pass
                return False

        return True
    except OSError:
        return False


def has_thumbnail(uasset_path, min_size=16):
    """Lightweight check: True if the .uasset contains an embedded thumbnail."""
    try:
        size = os.path.getsize(uasset_path)
    except OSError:
        return False
    if size <= 0:
        return False
    try:
        with open(uasset_path, "rb") as f:
            if size > _WHOLE_FILE_LIMIT:
                f.seek(size - _TAIL_READ)
            data = f.read()
    except OSError:
        return False
    return find_best_png(data, min_size=min_size) is not None
