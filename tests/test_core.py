"""Run with:  python -m pytest   (needs pytest; no GPU or network required)"""
import colorsys
import random
import shutil
from pathlib import Path

from PIL import Image

from cutline import dedupe, files, ordering, providers


def _make(tmp: Path):
    names = []
    for i in range(12):                                   # a smooth colour "story"
        r, g, b = [int(255 * c) for c in colorsys.hsv_to_rgb(i / 14, 0.8, 0.9)]
        im = Image.new("RGB", (320, 200), (r, g, b))
        for x in range(0, 320, 20):                       # add some structure so hashes differ
            for y in range(0, 200, 20):
                if (x // 20 + y // 20 + i) % 3 == 0:
                    im.paste((255 - r, 255 - g, 255 - b), (x, y, x + 10, y + 10))
        name = f"img_{random.Random(i).randint(1000, 9999)}_{i}.png"
        im.save(tmp / name)
        names.append(name)
    return names


def test_dedupe_and_order(tmp_path):
    names = _make(tmp_path)
    shutil.copy(tmp_path / names[3], tmp_path / "copy_exact.png")
    Image.open(tmp_path / names[7]).resize((160, 100)).save(tmp_path / "small_version.jpg")
    paths = files.list_images(tmp_path)
    groups = dedupe.find_duplicates(paths, 10)
    assert len(groups) == 2
    assert all(len(g) == 2 for g in groups)
    assert groups[0][0].name in names or groups[1][0].name in names   # best copy listed first

    unique = [p for p in paths if p.name in names]
    hists = [ordering.tiny(files.load_rgb(p, 128)) for p in unique]
    order = ordering.storyboard_order(ordering.build_distance(None, hists))
    ranks = [int(unique[i].stem.split("_")[-1]) for i in order]
    assert ranks in (sorted(ranks), sorted(ranks, reverse=True)) or \
        sum(abs(a - b) == 1 for a, b in zip(ranks, ranks[1:])) >= 9   # mostly neighbours


def test_apply_order(tmp_path):
    names = _make(tmp_path)
    paths = [tmp_path / n for n in names[:3]]
    files.apply_order(paths, tmp_path, rename_in_place=False)
    out = sorted(p.name for p in (tmp_path / "_storyboard").iterdir())
    assert out[0].startswith("001_") and out[2].startswith("003_")
    files.apply_order(paths, tmp_path, rename_in_place=True)
    assert (tmp_path / f"001_{names[0]}").exists()


def test_parse_order_repairs_bad_replies():
    assert providers.parse_order("Sure! [2, 0, 1]", 3) == [2, 0, 1]
    assert providers.parse_order("[1, 1, 7]", 4) == [1, 0, 2, 3]
