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


def test_parse_perm():
    assert files.parse_perm("2,0,1", 3) == [2, 0, 1]
    assert files.parse_perm("2,2,1", 3) is None
    assert files.parse_perm("abc", 3) is None


def test_avif_and_grid(tmp_path):
    from cutline.gridhtml import render_grid
    im = Image.new("RGB", (64, 40), (200, 60, 20))
    names = []
    for ext in (".png", ".avif"):
        if ext in files.EXTS:
            im.save(tmp_path / f"a{ext}")
            names.append(f"a{ext}")
    found = files.list_images(tmp_path)
    assert [p.name for p in found] == sorted(names)
    html = render_grid(found, list(range(len(found)))[::-1])
    assert 'draggable="true"' in html and html.count("sb-frame") >= len(found)


def test_render_dupes(tmp_path):
    from cutline.gridhtml import render_dupes
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    Image.new("RGB", (80, 50), (10, 120, 200)).save(a)
    shutil.copy(a, b)
    html = render_dupes([[0, 1]], [str(a), str(b)])
    assert html.count("dp-card") >= 2 and 'data-def="keep"' in html and 'data-def="del"' in html
    assert 'data-act="dup-delete"' in html


def test_preview_and_compare_panels(tmp_path):
    from cutline.gridhtml import compare_panel, preview_panel
    a, b = tmp_path / "a.png", tmp_path / "b.jpg"
    Image.new("RGB", (120, 80), (10, 120, 200)).save(a)
    Image.new("RGB", (60, 40), (10, 120, 200)).save(b)
    p = preview_panel("story", 3, str(a), 2, 9)
    assert 'data-key="story:3:2:9"' in p and "data:image/jpeg;base64," in p
    c = compare_panel(1, [str(a), str(b)], [0, 1], 0, 1)
    assert 'data-key="cmp:1:0:1"' in c and 'class="cmp-stage"' in c and 'data-act="cmp-b"' in c


def test_ollama_model_listing(monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send({"models": [{"name": "llama3.2:3b"}, {"name": "qwen2.5vl:7b"}, {"name": "mystery:1b"}]})

        def do_POST(self):
            n = int(self.headers["Content-Length"])
            name = json.loads(self.rfile.read(n))["model"]
            if name.startswith("qwen"):
                self._send({"capabilities": ["completion", "vision"]})
            elif name.startswith("llama"):
                self._send({"capabilities": ["completion"]})
            else:
                self._send({})

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("OLLAMA_HOST", f"127.0.0.1:{srv.server_port}")
    try:
        found = dict(providers.list_ollama_models())
    finally:
        srv.shutdown()
    assert found == {"llama3.2:3b": False, "qwen2.5vl:7b": True, "mystery:1b": None}
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:9")          # nothing listening
    try:
        providers.list_ollama_models(timeout=1)
        assert False, "expected ConnectionError"
    except ConnectionError as e:
        assert "Is it running" in str(e)


def test_ollama_base(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert providers.ollama_base() == "http://127.0.0.1:11434"
    monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0")
    assert providers.ollama_base() == "http://127.0.0.1:11434"
    monkeypatch.setenv("OLLAMA_HOST", "http://box:8080/")
    assert providers.ollama_base() == "http://box:8080"


def test_update_check_and_pull(tmp_path, monkeypatch):
    import subprocess
    from cutline import updater

    def sh(cwd, *a):
        subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                       env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                            "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ["PATH"], "HOME": str(tmp_path)})

    origin, a, b = tmp_path / "origin.git", tmp_path / "a", tmp_path / "b"
    sh(tmp_path, "init", "--bare", "-b", "main", str(origin))
    sh(tmp_path, "clone", str(origin), str(a))
    (a / "f.txt").write_text("1")
    sh(a, "add", "."); sh(a, "commit", "-m", "one"); sh(a, "push", "origin", "HEAD:main")
    sh(tmp_path, "clone", str(origin), str(b))
    (b / "f.txt").write_text("2")
    sh(b, "commit", "-am", "two"); sh(b, "push", "origin", "HEAD:main")

    monkeypatch.setattr(updater, "ROOT", a)
    updater.local_info.cache_clear()
    info = updater.local_info()
    assert info["git"] and info["build"] == 1 and info["sha"]
    ok, out = updater.pull_latest()
    assert ok and (a / "f.txt").read_text() == "2"
    assert updater.local_info()["build"] == 2
    assert updater._vtuple("0.10.2") > updater._vtuple("0.9.9")
    updater.local_info.cache_clear()


def test_pinned_frames_fix_start_and_end():
    import numpy as np
    from cutline import ordering
    rng = np.random.default_rng(1)
    n = 14
    pts = np.cumsum(rng.uniform(0.5, 1.5, size=n))              # points on a line: true story order is 0..n-1
    perm = rng.permutation(n)
    P = pts[perm]
    D = np.abs(P[:, None] - P[None, :])
    start, end = int(np.argmin(P)), int(np.argmax(P))
    order = ordering.constrained_order(D, {0: start, n - 1: end})
    assert order[0] == start and order[-1] == end
    assert sorted(order) == list(range(n))
    assert [int(P[i]) for i in order] == sorted(int(P[i]) for i in order)      # ascending along the line
    mid = ordering.constrained_order(D, {5: int(np.argsort(P)[5])})           # a pinned frame in the middle stays
    assert mid[5] == int(np.argsort(P)[5]) and sorted(mid) == list(range(n))
    assert ordering.enforce_locks([3, 1, 0, 2], {0: 0, 3: 3}) == [0, 1, 2, 3]


def test_story_captions_and_export(tmp_path, monkeypatch):
    import json
    from cutline import providers
    assert providers.parse_captions('Sure: ["a", "b"]', 3) == ["a", "b", ""]
    assert providers.parse_captions("1. first\n2) second", 2) == ["first", "second"]
    imgs = []
    for i in range(5):
        p = tmp_path / f"{i}.png"
        Image.new("RGB", (40, 30), (i * 40, 10, 10)).save(p)
        imgs.append(p)
    seen = []

    def fake(key, model, images, prompt):
        seen.append((len(images), prompt))
        return json.dumps([f"shot {len(seen)}-{k}" for k in range(len(images))])

    monkeypatch.setitem(providers.CALLERS, "Gemini", fake)
    order = [4, 3, 2, 1, 0]
    new = providers.write_story("Gemini", "k", "m", imgs, order, {}, order, "a quiet morning")
    assert set(new) == set(range(5)) and "a quiet morning" in seen[0][1] and seen[0][0] == 5
    only = providers.write_story("Gemini", "k", "m", imgs, order, new, [2])
    assert list(only) == [2] and "Story so far" in seen[-1][1]
    try:
        providers.write_story(providers.LOCAL_ONLY, "", "", imgs, order, {}, order)
        assert False
    except ValueError:
        pass
    md, cs = files.export_animatic(tmp_path, [(imgs[i], new[i]) for i in order], 2.5)
    assert "## 001" in Path(md).read_text(encoding="utf-8") and "shot" in Path(cs).read_text(encoding="utf-8-sig")


def test_locked_and_animatic_html(tmp_path):
    from cutline.gridhtml import render_animatic, render_grid
    imgs = []
    for i in range(3):
        p = tmp_path / f"{i}.png"
        Image.new("RGB", (40, 30), (i * 60, 90, 90)).save(p)
        imgs.append(str(p))
    h = render_grid(imgs, [0, 1, 2], {1})
    assert h.count('class="sb-frame locked"') == 1 and 'data-act="pin-ends"' in h and 'data-act="sort"' in h
    a = render_animatic(imgs, [2, 1, 0], {1: "a <b> & c"}, 4.0, "Ollama")
    assert a.count('class="am-row"') == 3 and "a &lt;b&gt; &amp; c" in a and 'data-act="am-gen"' in a


def test_update_check_via_git(tmp_path, monkeypatch):
    import os
    import subprocess
    from cutline import updater

    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": os.environ["PATH"], "HOME": str(tmp_path)}

    def sh(cwd, *a):
        subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, env=env)

    origin, a, b = tmp_path / "o.git", tmp_path / "a", tmp_path / "b"
    sh(tmp_path, "init", "--bare", "-b", "main", str(origin))
    sh(tmp_path, "clone", str(origin), str(a))
    (a / "cutline").mkdir()
    (a / "cutline" / "__init__.py").write_text('__version__ = "0.1.0"\n__build__ = 1\n')
    sh(a, "add", "."); sh(a, "commit", "-m", "one"); sh(a, "push", "origin", "HEAD:main")
    sh(tmp_path, "clone", str(origin), str(b))
    monkeypatch.setattr(updater, "ROOT", a)
    monkeypatch.setattr(updater, "CACHE_FILE", tmp_path / "cache.json")
    updater.local_info.cache_clear()
    assert updater.check_update()["state"] == "current"
    (b / "cutline" / "__init__.py").write_text('__version__ = "0.2.0"\n__build__ = 1\n')
    sh(b, "commit", "-am", "two"); sh(b, "push", "origin", "HEAD:main")
    res = updater.check_update()
    assert res["state"] == "update" and res["can_pull"] and res["remote_version"] == "0.2.0"
    assert updater.cached_check()["state"] == "update"
    ok, _ = updater.pull_latest()
    assert ok and updater.check_update()["state"] == "current"
    (a / "x.txt").write_text("x")
    sh(a, "add", "."); sh(a, "commit", "-m", "local only")
    updater.local_info.cache_clear()
    assert updater.check_update()["state"] == "ahead"
    updater.local_info.cache_clear()


def test_large_folder_two_step_ordering(tmp_path, monkeypatch):
    import json
    from cutline import providers
    n = 30
    imgs = []
    for i in range(n):
        p = tmp_path / f"{i}.png"
        Image.new("RGB", (30, 20), (i * 8, 40, 40)).save(p)
        imgs.append(p)
    calls = {"image": [], "text": []}

    def fake(key, model, images, prompt):
        if images:
            calls["image"].append(len(images))
            return json.dumps([f"shot description {k}" for k in range(len(images))])
        calls["text"].append(prompt)
        return json.dumps(list(range(n - 1, -1, -1)))               # "story order" = reversed

    monkeypatch.setitem(providers.CALLERS, providers.OLLAMA, fake)
    order = list(range(n))
    out = providers.refine(providers.OLLAMA, "", "m", imgs, order, story_prompt="a long day", locked={0: 0})
    assert sorted(out) == list(range(n)) and out[0] == 0                # pinned frame stayed first
    assert max(calls["image"]) <= 4 and sum(calls["image"]) == n       # described 4 at a time, nothing skipped
    assert len(calls["text"]) == 1 and "a long day" in calls["text"][0] and "pinned" in calls["text"][0]
    assert out[1:] == list(range(n - 1, 0, -1))                          # the rest follows the text answer
    one_request = []

    def fake_small(key, model, images, prompt):
        one_request.append(len(images))
        return json.dumps([5, 4, 3, 2, 1, 0])

    monkeypatch.setitem(providers.CALLERS, providers.OLLAMA, fake_small)
    small = providers.refine(providers.OLLAMA, "", "m", imgs[:6], list(range(6)))
    assert small == [5, 4, 3, 2, 1, 0] and one_request == [6]            # small sets still use ONE request


def test_icon_chrome_html():
    from cutline.gridhtml import SIDE_HIDE, footer_bar, header_html
    h = header_html("data:image/png;base64,AAAA")
    assert 'data-act="theme"' in h and "ico-sun" in h and "ico-moon" in h
    f = footer_bar("Cutline v1 · build 2", '<span class="ft-badge">x</span>')
    assert 'data-act="ft-check"' in f and 'data-act="ft-about"' in f and "<svg" in f and "Check for updates</button>" not in f
    assert 'data-act="toggle-side"' in SIDE_HIDE
