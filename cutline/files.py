"""File helpers: listing, thumbnails, Recycle Bin, applying the final order."""
import hashlib
import re
import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

try:
    from send2trash import send2trash
except ImportError:  # pragma: no cover
    send2trash = None

# Optional format plugins: HEIC/HEIF/AVIF (pillow-heif) and JPEG XL (pillow-jxl-plugin).
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    try:
        pillow_heif.register_avif_opener()
    except Exception:
        pass
except Exception:
    pass
try:
    import pillow_jxl  # noqa: F401
except Exception:
    pass

WANTED = {".jpg", ".jpeg", ".jfif", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff",
          ".avif", ".heic", ".heif", ".jxl"}
_registered = Image.registered_extensions()
EXTS = {e for e in WANTED if e in _registered}        # only formats this install can really open
OUT_DIR_NAME = "_storyboard"
THUMBS = Path(tempfile.gettempdir()) / "cutline_thumbs"


def list_images(folder, recursive=False):
    folder = Path(folder)
    it = folder.rglob("*") if recursive else folder.glob("*")
    return sorted(p for p in it
                  if p.is_file() and p.suffix.lower() in EXTS and OUT_DIR_NAME not in p.parts)


def unsupported_exts(folder, recursive=False):
    """Extensions of image files we recognise but cannot open (plugin missing)."""
    folder = Path(folder)
    it = folder.rglob("*") if recursive else folder.glob("*")
    return sorted({p.suffix.lower() for p in it
                   if p.is_file() and p.suffix.lower() in WANTED - EXTS and OUT_DIR_NAME not in p.parts})


def skipped_note(folder, recursive=False):
    ex = unsupported_exts(folder, recursive)
    return (f" Skipped unsupported files ({', '.join(ex)}): run `pip install pillow-heif` "
            "(HEIC/AVIF) or `pillow-jxl-plugin` (JXL).") if ex else ""


def parse_perm(text, n):
    """'3,0,2,1' -> [3, 0, 2, 1] if it is a permutation of range(n), else None."""
    try:
        v = [int(x) for x in str(text).split(",") if x.strip() != ""]
    except ValueError:
        return None
    return v if sorted(v) == list(range(n)) else None


_URI_CACHE = {}


def thumb_data_uri(path, size=256):
    """Tiny inline JPEG for the drag-and-drop grid (no file serving needed)."""
    import base64
    import io
    path = Path(path)
    key = (str(path), path.stat().st_mtime_ns, size)
    if key not in _URI_CACHE:
        buf = io.BytesIO()
        load_rgb(path, size).save(buf, "JPEG", quality=72)
        _URI_CACHE[key] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return _URI_CACHE[key]


def load_rgb(path, max_side=None):
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if max_side:
        im.thumbnail((max_side, max_side))
    return im


def make_thumb(path, size=384):
    """Small cached JPEG. Gradio can only serve files it is allowed to, so we show thumbnails."""
    path = Path(path)
    THUMBS.mkdir(exist_ok=True)
    key = hashlib.sha1(f"{path}|{path.stat().st_mtime_ns}|{size}".encode()).hexdigest()
    out = THUMBS / f"{key}.jpg"
    if not out.exists():
        load_rgb(path, size).save(out, "JPEG", quality=80)
    return str(out)


def describe(path):
    path = Path(path)
    try:
        w, h = Image.open(path).size
    except Exception:
        w = h = 0
    return w, h, path.stat().st_size


def human_size(n):
    return f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{n / 1e3:.0f} KB"


def to_trash(paths):
    """Move to the Recycle Bin. Refuses to delete permanently."""
    if send2trash is None:
        raise RuntimeError("send2trash is not installed, so Cutline will not delete anything. "
                           "Run: pip install send2trash")
    for p in paths:
        send2trash(str(Path(p)))


_PREFIX = re.compile(r"^\d{3,}_")


def apply_order(ordered_paths, folder, rename_in_place=False):
    """Write the storyboard order. Returns a message for the UI."""
    ordered_paths = [Path(p) for p in ordered_paths]
    width = max(3, len(str(len(ordered_paths))))
    if rename_in_place:
        tmp = []
        for k, p in enumerate(ordered_paths, 1):
            t = p.with_name(f"__cutline_tmp_{k}{p.suffix}")
            p.rename(t)
            tmp.append((t, p, k))
        for t, p, k in tmp:
            t.rename(p.with_name(f"{k:0{width}d}_{_PREFIX.sub('', p.name)}"))
        return f"Renamed {len(tmp)} files in place (001_, 002_, ...)."
    out = Path(folder) / OUT_DIR_NAME
    out.mkdir(exist_ok=True)
    for k, p in enumerate(ordered_paths, 1):
        shutil.copy2(p, out / f"{k:0{width}d}_{_PREFIX.sub('', p.name)}")
    return f"Copied {len(ordered_paths)} files to {out}"
