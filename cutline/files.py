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

EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
OUT_DIR_NAME = "_storyboard"
THUMBS = Path(tempfile.gettempdir()) / "cutline_thumbs"


def list_images(folder, recursive=False):
    folder = Path(folder)
    it = folder.rglob("*") if recursive else folder.glob("*")
    return sorted(p for p in it
                  if p.is_file() and p.suffix.lower() in EXTS and OUT_DIR_NAME not in p.parts)


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
