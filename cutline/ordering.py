"""Storyboard ordering: visual embeddings + colour -> smoothest path through all images."""
import numpy as np

from .files import load_rgb


def color_hist(im, levels=4):
    """Coarse colour histogram (used by duplicate detection)."""
    a = np.asarray(im.resize((64, 64)), dtype=np.uint8).astype(np.int32) // (256 // levels)
    idx = a[..., 0] * levels * levels + a[..., 1] * levels + a[..., 2]
    h = np.bincount(idx.flatten(), minlength=levels ** 3).astype(np.float32)
    return h / h.sum()


def tiny(im):
    """8x8 colour thumbnail. Unlike a histogram, nearby colours give nearby values, so smooth
    lighting / colour changes between shots read as 'similar'."""
    return (np.asarray(im.resize((8, 8)), dtype=np.float32) / 255.0).flatten()


def build_distance(feats, tinies, color_weight=0.3):
    T = np.stack(tinies)
    sq = (T ** 2).sum(1)
    col = np.sqrt(np.maximum(sq[:, None] + sq[None, :] - 2 * T @ T.T, 0) / T.shape[1])
    D = col if feats is None else (1 - feats @ feats.T) + color_weight * col
    np.fill_diagonal(D, 0)
    return D


def path_length(order, D):
    return float(sum(D[order[i], order[i + 1]] for i in range(len(order) - 1)))


def nearest_neighbour(D, start):
    n = len(D)
    order, left = [start], np.ones(n, bool)
    left[start] = False
    while left.any():
        cand = np.where(left)[0]
        nxt = int(cand[np.argmin(D[order[-1], cand])])
        order.append(nxt)
        left[nxt] = False
    return order


def two_opt(order, D, max_passes=50):
    n = len(order)
    for _ in range(max_passes):
        improved = False
        for i in range(0, n - 1):
            for j in range(i + 1, n):
                old = new = 0.0
                if i > 0:
                    old += D[order[i - 1], order[i]]
                    new += D[order[i - 1], order[j]]
                if j < n - 1:
                    old += D[order[j], order[j + 1]]
                    new += D[order[i], order[j + 1]]
                if new < old - 1e-9:
                    order[i:j + 1] = order[i:j + 1][::-1]
                    improved = True
        if not improved:
            break
    return order


def storyboard_order(D):
    n = len(D)
    if n < 3:
        return list(range(n))
    starts = range(n) if n <= 40 else np.random.choice(n, 40, replace=False)
    best = min((nearest_neighbour(D, int(s)) for s in starts), key=lambda o: path_length(o, D))
    return two_opt(best, D, max_passes=50 if n <= 300 else 4)


def _edge(D, o, i):
    return D[o[i], o[i + 1]] if 0 <= i < len(o) - 1 else 0.0


def _improve_locked(order, D, free_slots, max_passes):
    """Swap / reverse free frames while pinned frames stay put."""
    runs, run = [], []
    for s in free_slots:
        if run and s != run[-1] + 1:
            runs.append(run)
            run = []
        run.append(s)
    if run:
        runs.append(run)
    for _ in range(max_passes):
        improved = False
        for a in range(len(free_slots) - 1):
            i = free_slots[a]
            for b in range(a + 1, len(free_slots)):
                j = free_slots[b]
                edges = {i - 1, i, j - 1, j}
                old = sum(_edge(D, order, k) for k in edges)
                order[i], order[j] = order[j], order[i]
                if sum(_edge(D, order, k) for k in edges) < old - 1e-9:
                    improved = True
                else:
                    order[i], order[j] = order[j], order[i]
        for run in runs:
            for x in range(len(run) - 1):
                for y in range(x + 1, len(run)):
                    i, j = run[x], run[y]
                    old = _edge(D, order, i - 1) + _edge(D, order, j)
                    order[i:j + 1] = order[i:j + 1][::-1]
                    if _edge(D, order, i - 1) + _edge(D, order, j) < old - 1e-9:
                        improved = True
                    else:
                        order[i:j + 1] = order[i:j + 1][::-1]
        if not improved:
            break
    return order


def constrained_order(D, locked):
    """Smoothest order in which the pinned frames keep their positions.
    locked: {position: image_index}. Pinning the first and last frame fixes the story's start and end."""
    n = len(D)
    locked = {int(s): int(i) for s, i in locked.items() if 0 <= int(s) < n}
    if not locked:
        return storyboard_order(D)
    pinned = set(locked.values())
    free_imgs = [i for i in range(n) if i not in pinned]
    free_slots = [s for s in range(n) if s not in locked]
    if not free_slots:
        return [locked[s] for s in range(n)]
    base = [free_imgs[k] for k in storyboard_order(D[np.ix_(free_imgs, free_imgs)])]

    def build(seq):
        out = [None] * n
        for s, img in locked.items():
            out[s] = img
        for s, img in zip(free_slots, seq):
            out[s] = img
        return out

    order = min((build(base), build(base[::-1])), key=lambda o: path_length(o, D))
    passes = 30 if n <= 150 else (8 if n <= 300 else 3)
    return _improve_locked(order, D, free_slots, passes)


def enforce_locks(order, locked):
    """Put pinned images back at their positions, keeping the rest in the given order."""
    if not locked:
        return list(order)
    pinned = set(locked.values())
    rest = iter(i for i in order if i not in pinned)
    return [locked[s] if s in locked else next(rest) for s in range(len(order))]


def local_order(paths, model_key, progress=lambda f, m: None, locked=None):
    """Returns (order, note). Falls back to colour-only if PyTorch/open_clip are missing.
    locked: {position: image_index} frames that must keep their position."""
    from . import models

    note = ""
    try:
        embed = models.load(model_key, progress)
    except ImportError as e:
        embed = None
        note = (f"Python package '{e.name}' is not installed, so only colour was used (weak story flow). "
                "Run: pip install -r requirements.txt")
    n, B = len(paths), 16
    hists, feats = [], []
    for s in range(0, n, B):
        progress(0.1 + 0.75 * s / n, f"Looking at images {s + 1}-{min(s + B, n)} of {n}")
        batch = [load_rgb(p, 512) for p in paths[s:s + B]]
        hists += [tiny(im) for im in batch]
        if embed:
            feats.append(embed(batch))
    D = build_distance(np.concatenate(feats) if embed else None, hists)
    progress(0.9, "Finding the smoothest sequence...")
    return (constrained_order(D, locked) if locked else storyboard_order(D)), note
