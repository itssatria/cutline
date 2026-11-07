"""Duplicate detection: exact (SHA-256) + near-duplicate (256-bit difference hash)."""
import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

from .files import load_rgb
from .ordering import color_hist


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _dhash(im, size=16):
    g = im.convert("L").resize((size + 1, size), Image.LANCZOS)
    a = np.asarray(g, dtype=np.int16)
    return (a[:, 1:] > a[:, :-1]).flatten().astype(np.float32)


def find_duplicates(paths, tolerance=10, progress=lambda f, m: None):
    """Return groups of duplicate files; each group lists the best copy first
    (highest resolution, then largest file)."""
    paths = [Path(p) for p in paths]
    n = len(paths)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    seen = {}
    for i, p in enumerate(paths):
        progress(0.4 * i / max(n, 1), f"Checking exact copies: {p.name}")
        try:
            d = _sha256(p)
        except OSError:
            continue
        if d in seen:
            union(seen[d], i)
        else:
            seen[d] = i

    bits, hists, ok = [], [], []
    for i, p in enumerate(paths):
        progress(0.4 + 0.55 * i / max(n, 1), f"Fingerprinting: {p.name}")
        try:
            im = load_rgb(p, 256)
            bits.append(_dhash(im))
            hists.append(color_hist(im))
            ok.append(i)
        except Exception:
            pass
    if len(bits) > 1 and tolerance >= 0:
        B = np.stack(bits)
        ham = B @ (1 - B).T + (1 - B) @ B.T
        ii, jj = np.where(np.triu(ham <= tolerance, k=1))
        if len(ii):
            # The hash only sees brightness, so also require similar colours: a recoloured
            # variant of the same layout is not a duplicate.
            H = np.stack(hists)
            col = 0.5 * np.abs(H[ii] - H[jj]).sum(1)
            for a, b, c in zip(ii, jj, col):
                if c <= 0.12 + 0.01 * tolerance:
                    union(ok[a], ok[b])

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(paths[i])

    def quality(p):
        try:
            w, h = Image.open(p).size
        except Exception:
            w = h = 0
        return (w * h, p.stat().st_size)

    out = [sorted(g, key=quality, reverse=True) for g in groups.values() if len(g) > 1]
    progress(1.0, "Done")
    return out
