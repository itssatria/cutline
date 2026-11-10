"""Cutline - clean cuts, clear story.   Run:  python app.py   (opens http://127.0.0.1:7860)"""
import base64
import html
import json
import os
import subprocess
import sys
from pathlib import Path

import gradio as gr

from cutline import config, dedupe, files, models, ordering, providers, updater
from cutline.gridhtml import (EMPTY, EMPTY_DUP, SIDE_HIDE, compare_panel, footer_bar, header_html, preview_panel,
                              render_animatic, render_dupes, render_grid)

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
STATIC = ROOT / "cutline" / "static"
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
FAVICON = "data:image/png;base64," + base64.b64encode((ASSETS / "favicon.png").read_bytes()).decode()
DND_JS = (STATIC / "dnd.js").read_text(encoding="utf-8").replace("__FAVICON__", FAVICON)


def _logo_uri():
    return "data:image/png;base64," + base64.b64encode((ASSETS / "logo_mark.png").read_bytes()).decode()


HEADER = header_html(_logo_uri())


def _nav_js(name):
    return ("() => { document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));"
            " document.querySelector('#tab-%s').classList.add('active'); window.scrollTo(0, 0); }" % name)


_DIALOG = ("import sys, tkinter as tk\nfrom tkinter import filedialog\n"
           "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
           "print(filedialog.askdirectory(initialdir=sys.argv[1] or None) or '')")


def _modal(title, msg):
    return gr.Group(visible=True), f"### {title}\n\n{msg}"


def _folder_path(folder):
    folder = (folder or "").strip().strip('"')
    return Path(folder) if folder and Path(folder).is_dir() else None


def _check_folder(folder):
    p = _folder_path(folder)
    if p is None:
        raise gr.Error("Enter a valid folder path, or use Browse.")
    return p


def _prog(progress):
    return lambda f, m: progress(f, desc=m)


def _page(which):
    return tuple(gr.Row(visible=which == w) for w in ("dup", "story", "anim"))


# ----------------------------------------------------------- shared
def browse(current):
    """Native folder picker. Cutline runs on your PC, so the dialog opens on your desktop."""
    start = current if current and Path(current).is_dir() else str(Path.home())
    try:
        res = subprocess.run([sys.executable, "-c", _DIALOG, start], capture_output=True, text=True, timeout=900)
    except Exception as e:
        raise gr.Error(f"Could not open the folder dialog: {e}")
    out = res.stdout.strip()
    if res.returncode != 0 and not out:
        raise gr.Error("Folder dialog unavailable (tkinter missing). Paste the folder path instead.")
    chosen = str(Path(out)) if out else (current or "")
    return chosen, chosen


# ----------------------------------------------------------- duplicates
def scan(folder, recursive, tolerance, progress=gr.Progress()):
    folder = _check_folder(folder)
    paths = files.list_images(folder, recursive)
    note = files.skipped_note(folder, recursive)
    if len(paths) < 2:
        raise gr.Error("Need at least two supported images in that folder." + note)
    groups = dedupe.find_duplicates(paths, int(tolerance), _prog(progress))
    flat, gidx, marked, saving = [], [], 0, 0
    for g in groups:
        idx = []
        for k, p in enumerate(g):
            idx.append(len(flat))
            flat.append(str(p))
            if k:
                marked += 1
                saving += files.describe(p)[2]
        gidx.append(idx)
    if groups:
        summary = (f"**{len(groups)} groups** · {marked} files marked for the Recycle Bin "
                   f"(frees {files.human_size(saving)}). Click a card to keep or delete it." + note)
        gr.Info(f"Found {len(groups)} duplicate groups.")
    else:
        summary = f"No duplicates found in {len(paths)} images." + note
        gr.Info("No duplicates found.")
    return render_dupes(gidx, flat), flat, gidx, summary


def on_scan_btn(_text, folder, recursive, tolerance, progress=gr.Progress()):
    return scan(folder, recursive, tolerance, progress)


def on_delete(text, flat, groups):
    """The Move-to-Recycle-Bin button posts a JSON list of file indexes + a timestamp."""
    try:
        chosen = {int(i) for i in json.loads((text or "").rsplit("|", 1)[0])}
    except Exception:
        raise gr.Error("Could not read the selection. Scan again and retry.")
    chosen = {i for i in chosen if 0 <= i < len(flat)}
    if not chosen:
        raise gr.Error("Nothing is marked for deletion.")
    for g in groups:
        if all(i in chosen for i in g):
            raise gr.Error(f"Every copy in the group containing {Path(flat[g[0]]).name} is marked. Keep at least one.")
    try:
        files.to_trash([flat[i] for i in sorted(chosen)])
    except Exception as e:
        raise gr.Error(str(e))
    msg = f"Moved {len(chosen)} files to the Recycle Bin. You can restore them from there."
    return EMPTY_DUP, [], [], msg, *_modal("Duplicates removed", msg)


# ----------------------------------------------------------- preview / compare panel
def on_preview(text, st_paths, d_files):
    """Space / double-click: the page posts "story:<idx>:<pos>:<total>" or "dup:..." plus a timestamp."""
    try:
        kind, idx, pos, total = (text or "").rsplit("|", 1)[0].split(":")
        idx, pos, total = int(idx), int(pos), int(total)
        path = (st_paths if kind == "story" else d_files)[idx]
    except Exception:
        return gr.skip()
    try:
        return preview_panel(kind, idx, path, pos, total)
    except Exception as e:
        raise gr.Error(f"Could not open the image: {e}")


def on_compare(text, d_files, d_groups):
    """Compare button / C key: JSON {"g": group, "a": file index, "b": file index}."""
    try:
        d = json.loads((text or "").rsplit("|", 1)[0])
        g, a, b = int(d["g"]), int(d["a"]), int(d["b"])
        group = d_groups[g]
        if a == b or a not in group or b not in group:
            return gr.skip()
    except Exception:
        return gr.skip()
    try:
        return compare_panel(g, d_files, group, a, b)
    except Exception as e:
        raise gr.Error(f"Could not open the images: {e}")


# ----------------------------------------------------------- storyboard
def on_nsfw(nsfw, engine, blur):
    choices = providers.PRIVATE_ENGINES if nsfw else providers.ENGINES
    return (gr.Dropdown(choices=choices, value=engine if engine in choices else providers.LOCAL_ONLY),
            gr.Checkbox(visible=bool(nsfw), value=bool(blur) and bool(nsfw)))


def _ollama_dropdown():
    """Dropdown filled from the local Ollama (vision models first)."""
    label = "Ollama model (installed on this PC)"
    try:
        found = providers.list_ollama_models()
    except ConnectionError as e:
        gr.Warning(f"{e} Start Ollama, then click 'Refresh Ollama models'.")
        d = providers.DEFAULT_MODELS[providers.OLLAMA]
        return gr.Dropdown(label=label, choices=[d], value=d, visible=True, allow_custom_value=True)
    if not found:
        gr.Warning("Ollama is running but has no models. Run: ollama pull " + providers.DEFAULT_MODELS[providers.OLLAMA])
    rank = {True: 0, None: 1, False: 2}
    found.sort(key=lambda x: (rank[x[1]], x[0]))
    if found and not any(v is not False for _, v in found):
        gr.Warning("No vision-capable model found in Ollama. Run: ollama pull " + providers.DEFAULT_MODELS[providers.OLLAMA])
    tag = {True: " · vision", None: "", False: " · text only"}
    choices = [(n + tag[v], n) for n, v in found] or [providers.DEFAULT_MODELS[providers.OLLAMA]]
    value = next((n for n, v in found if v is not False), found[0][0] if found else choices[0])
    return gr.Dropdown(label=label, choices=choices, value=value, visible=True, allow_custom_value=True)


def on_engine(engine):
    needs_key = engine in providers.CLOUD
    key = gr.Textbox(visible=needs_key, label=f"{engine} API key (or set {providers.ENV_KEYS.get(engine, '')})")
    prompt = gr.Textbox(visible=engine != providers.LOCAL_ONLY)
    vmodel = gr.Dropdown(visible=engine == providers.LOCAL_ONLY)       # the AI engine does the work: hide it
    if engine == providers.OLLAMA:
        return key, _ollama_dropdown(), gr.Button(visible=True), prompt, vmodel
    default = providers.DEFAULT_MODELS.get(engine, "")
    model = gr.Dropdown(label="Model name (change if outdated)", choices=[default] if default else [],
                        value=default or None, visible=engine != providers.LOCAL_ONLY, allow_custom_value=True)
    return key, model, gr.Button(visible=False), prompt, vmodel


def on_refresh():
    return _ollama_dropdown()


def _load_outputs(n):
    return (gr.skip(),) * n


def load_folder(folder, recursive, loaded, progress=gr.Progress()):
    """Show every image of the folder right away (name order), without sorting."""
    p = _folder_path(folder)
    if p is None:
        return _load_outputs(8)
    key = [str(p), bool(recursive)]
    if loaded == key:
        return _load_outputs(8)
    paths = files.list_images(p, recursive)
    note = files.skipped_note(p, recursive)
    if not paths:
        gr.Warning("No supported images in that folder." + note)
        return EMPTY, [], [], [], [], {}, key, "No supported images found." + note
    order = list(range(len(paths)))
    grid = render_grid(paths, order, (), _prog(progress))
    gr.Info(f"Loaded {len(paths)} images.")
    return (grid, [str(x) for x in paths], order, [], [], {}, key,
            f"Loaded {len(paths)} images in name order. Drag them into place, pin frames with the lock icon, "
            f"or press Sort.{note}")


def sort_story(folder, recursive, engine, key, model_name, vmodel, nsfw, prompt, st_paths, st_order, st_locked,
               st_texts, loaded, progress=gr.Progress()):
    folder = _check_folder(folder)
    if nsfw and engine not in providers.PRIVATE_ENGINES:
        raise gr.Error("NSFW mode is on: cloud engines are disabled. Choose Local only or Ollama.")
    same = bool(st_paths) and loaded == [str(folder), bool(recursive)]
    if same:
        paths = [Path(x) for x in st_paths]
        cur = list(st_order) if sorted(st_order) == list(range(len(paths))) else list(range(len(paths)))
        pinned = set(st_locked or [])
        texts = st_texts or {}
    else:
        paths = files.list_images(folder, recursive)
        cur, pinned, texts = list(range(len(paths))), set(), {}
    note = files.skipped_note(folder, recursive)
    if len(paths) < 2:
        raise gr.Error("Need at least two supported images in that folder." + note)
    slots = {pos: idx for pos, idx in enumerate(cur) if idx in pinned}      # pinned frames keep their positions
    p = _prog(progress)
    try:
        order, local_note = ordering.local_order(paths, vmodel, p, locked=slots)
        if engine != providers.LOCAL_ONLY:
            order = providers.refine(engine, key, model_name, paths, order, p, story_prompt=prompt, locked=slots)
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(str(e))
    if local_note:
        gr.Warning(local_note)
    gr.Info(f"Sorted {len(paths)} images" + (f" around {len(slots)} pinned frame(s)." if slots else ".")
            + " Drag frames to rearrange.")
    pin_txt = f" Kept {len(slots)} pinned frame(s) in place." if slots else ""
    msg = f"Sorted {len(paths)} images with {engine}.{pin_txt} {local_note}{note}"
    return (render_grid(paths, order, pinned), [str(x) for x in paths], order, [], sorted(pinned), texts,
            [str(folder), bool(recursive)], msg)


def on_sort_btn(_text, folder, recursive, engine, key, model_name, vmodel, nsfw, prompt, st_paths, st_order,
                st_locked, st_texts, loaded, progress=gr.Progress()):
    return sort_story(folder, recursive, engine, key, model_name, vmodel, nsfw, prompt, st_paths, st_order,
                      st_locked, st_texts, loaded, progress)


def on_drag(text, order, hist):
    """The drag-and-drop script posts the new order (comma-separated indexes) through a hidden box."""
    new = files.parse_perm(text, len(order))
    if new is None or new == order:
        return order, hist
    return new, (hist + [order])[-50:]


def on_lock(text, _old):
    try:
        return sorted({int(i) for i in json.loads((text or "").rsplit("|", 1)[0])})
    except Exception:
        return gr.skip()


def reverse(paths, order, hist, locked):
    if not order:
        raise gr.Error("Load a folder first.")
    gr.Info("Order reversed.")
    new = order[::-1]
    return render_grid(paths, new, locked), new, (hist + [order])[-50:]


def undo(paths, order, hist, locked):
    if not hist:
        raise gr.Error("Nothing to undo.")
    gr.Info("Undid the last change.")
    new = hist[-1]
    return render_grid(paths, new, locked), new, hist[:-1]


def on_action(text, paths, order, hist, locked):
    """Reverse / Undo buttons (HTML) post "reverse|timestamp" or "undo|timestamp" here."""
    act = (text or "").split("|")[0]
    if act == "reverse":
        return reverse(paths, order, hist, locked)
    if act == "undo":
        return undo(paths, order, hist, locked)
    return gr.skip(), gr.skip(), gr.skip()


def apply(folder, recursive, paths, order, mode, progress=gr.Progress()):
    if not order:
        raise gr.Error("Load a folder first.")
    folder = _check_folder(folder)
    rename = mode.startswith("Rename")
    try:
        msg = files.apply_order([paths[i] for i in order], folder, rename)
    except Exception as e:
        raise gr.Error(str(e))
    if rename:   # file names changed on disk: reload the folder (it now sorts in storyboard order)
        new = files.list_images(folder, recursive)
        o = list(range(len(new)))
        return (*_modal("Storyboard order applied", msg), render_grid(new, o, (), _prog(progress)),
                [str(x) for x in new], o, [], [], {}, [str(folder), bool(recursive)])
    return (*_modal("Storyboard order applied", msg),) + (gr.skip(),) * 7


def on_apply(text, folder, recursive, paths, order, progress=gr.Progress()):
    """Apply order button posts "copy|timestamp" or "rename|timestamp"."""
    mode = (text or "").split("|")[0]
    return apply(folder, recursive, paths, order, "Rename originals" if mode == "rename" else "Copy", progress)


# ----------------------------------------------------------- animatic
def show_animatic(paths, order, texts, secs, engine):
    return render_animatic(paths, order, texts, secs, engine)


def on_animatic(text, paths, order, texts, secs, folder, engine, key, model, prompt, nsfw,
                progress=gr.Progress()):
    """All animatic buttons post JSON {act, i, secs, texts:{idx: text}} (the current text boxes) + a timestamp."""
    try:
        d = json.loads((text or "").rsplit("|", 1)[0])
    except Exception:
        return (gr.skip(),) * 5
    texts = dict(texts or {})
    for k, v in (d.get("texts") or {}).items():
        try:
            texts[int(k)] = str(v)
        except ValueError:
            pass
    try:
        secs = float(d.get("secs") or secs or 3)
    except (TypeError, ValueError):
        secs = secs or 3.0
    act = d.get("act")
    if act == "save":
        return gr.skip(), texts, secs, gr.skip(), gr.skip()
    if not order:
        raise gr.Error("Load a folder on the Storyboard tab first.")
    paths = [Path(x) for x in paths]
    if act in ("gen", "fill", "regen"):
        if engine == providers.LOCAL_ONLY:
            raise gr.Error("Pick an AI engine (Ollama, Gemini, ...) on the Storyboard tab first.")
        if nsfw and engine not in providers.PRIVATE_ENGINES:
            raise gr.Error("NSFW mode is on: cloud engines are disabled. Choose Ollama.")
        if act == "regen":
            targets = [int(d["i"])]
        elif act == "fill":
            targets = [i for i in order if not (texts.get(i) or "").strip()]
        else:
            targets = list(order)
        if not targets:
            gr.Info("Every frame already has text.")
        else:
            try:
                texts.update(providers.write_story(engine, key, model, paths, order, texts, targets, prompt,
                                                   _prog(progress)))
            except Exception as e:
                raise gr.Error(str(e))
            gr.Info(f"Wrote story text for {len(targets)} frame(s).")
        return render_animatic(paths, order, texts, secs, engine), texts, secs, gr.skip(), gr.skip()
    if act == "export":
        f = _folder_path(folder)
        if f is None:
            raise gr.Error("Enter a valid folder path first.")
        try:
            md, cs = files.export_animatic(f, [(paths[i], texts.get(i, "")) for i in order], secs)
        except Exception as e:
            raise gr.Error(str(e))
        return (render_animatic(paths, order, texts, secs, engine), texts, secs,
                *_modal("Story exported", f"Saved:\n\n- `{md}`\n- `{cs}`"))
    return (gr.skip(),) * 5


# ----------------------------------------------------------- footer: build, updates, about
def footer_html(res=None):
    badge = ""
    if res and res.get("state") == "update":
        rv = f" · v{html.escape(res['remote_version'])}" if res.get("remote_version") else ""
        badge = f'<span class="ft-badge">&#9679; Update available{rv}</span>'
    return footer_bar(html.escape(updater.build_label()), badge)


def _link(url, text, cls=""):
    return f'<a class="{cls}" href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">{text}</a>'


def about_html():
    i = updater.local_info()
    repo_url = f"https://github.com/{config.GITHUB_REPO}"
    coffee = ""
    if config.BUY_ME_A_COFFEE_URL:
        coffee = f'<div class="ab-coffee">{_link(config.BUY_ME_A_COFFEE_URL, "&#9749; Buy me a coffee", "ab-btn")}</div>'
    return f"""<div class="about">
<img src="{_logo_uri()}" alt="Cutline" class="ab-logo">
<div class="ab-name"><span style="color:#D9541E">Cut</span>line</div>
<div class="ab-tag">Clean cuts. Clear story.</div>
<div class="ab-build">{html.escape(updater.build_label())}</div>
<p>Cutline finds duplicate photos and arranges a folder of images into storyboard order.
It runs on your PC; nothing is uploaded unless you pick a cloud engine.</p>
<div class="ab-author"><b>{html.escape(config.AUTHOR_NAME)}</b> · {html.escape(config.AUTHOR_TAGLINE)}<br>
{_link(config.AUTHOR_URL, "Profile")} · {_link(repo_url, "Source on GitHub")} · {_link(repo_url + "/issues", "Report an issue")}</div>
{coffee}
<div class="ab-small">MIT licensed · version {html.escape(i["version"])}</div></div>"""


def _update_html(res):
    icon = {"update": "&#11014;", "current": "&#10003;", "ahead": "&#8505;", "error": "&#9888;"}[res["state"]]
    out = f'<div class="about"><div class="ab-name">{icon} {html.escape(res["title"])}</div><p>{html.escape(res["detail"])}</p>'
    if res["state"] == "update":
        repo_url = f"https://github.com/{config.GITHUB_REPO}"
        if res["can_pull"]:
            out += "<p>Click <b>Update now</b> to pull the latest version from GitHub.</p>"
        else:
            out += (f"<p>{_link(repo_url + '/releases/latest', 'Open the latest release')} or "
                    f"{_link(repo_url + '/archive/refs/heads/' + config.DEFAULT_BRANCH + '.zip', 'download the zip')}, "
                    "then replace the app files (your <code>.venv</code> can stay).<br>"
                    "Tip: install with <code>git clone</code> to get one-click updates.</p>")
    return out + "</div>"


def auto_check():
    if os.environ.get("CUTLINE_NO_UPDATE_CHECK"):
        return gr.skip()
    return footer_html(updater.cached_check())


def on_footer(text):
    """Footer icon buttons post "check|timestamp" or "about|timestamp"."""
    act = (text or "").split("|")[0]
    if act == "about":
        return gr.Group(visible=True), about_html(), gr.Button(visible=False), gr.skip()
    if act == "check":
        gr.Info("Checking for updates...")
        res = updater.check_update()
        pull = res["state"] == "update" and res["can_pull"]
        return gr.Group(visible=True), _update_html(res), gr.Button(visible=pull), footer_html(res)
    return (gr.skip(),) * 4


def on_update():
    ok, out = updater.pull_latest()
    if ok:
        body = ('<div class="about"><div class="ab-name">&#10003; Updated</div>'
                "<p>Close Cutline and run <b>run.bat</b> again. It installs any new packages automatically.</p>"
                f"<pre class='ab-pre'>{html.escape(out[-600:])}</pre></div>")
    else:
        body = ('<div class="about"><div class="ab-name">&#9888; Update failed</div>'
                f"<pre class='ab-pre'>{html.escape(out[-800:])}</pre>"
                "<p>If you edited files locally, commit or stash your changes and try again.</p></div>")
    return body, gr.Button(visible=False)


# ----------------------------------------------------------- UI
def _folder_field():
    """Folder box with the Browse button inside the same bordered field (see .folder-field in style.css)."""
    gr.HTML('<span class="field-label">Image folder</span>')
    with gr.Row(elem_classes="folder-field"):
        box = gr.Textbox(show_label=False, container=False, placeholder=r"D:\Shots\Project01",
                         lines=1, max_lines=1, scale=1, min_width=0)
        btn = gr.Button("Browse…", elem_classes="browse-btn", size="sm", scale=0, min_width=0)
    return box, btn


def _bridge(elem_id, label):
    return gr.Textbox(elem_id=elem_id, elem_classes="bridge", label=label)


def build():
    with gr.Blocks(title="Cutline", theme=gr.themes.Soft(primary_hue="orange", neutral_hue="zinc"),
                   css=CSS, js=DND_JS) as demo:
        with gr.Row(elem_id="app-header"):
            gr.HTML(HEADER)
        with gr.Row(elem_id="tabbar"):
            tab_dup = gr.Button("1 · Duplicates", elem_id="tab-dup", elem_classes=["tab-btn", "active"], scale=0)
            tab_story = gr.Button("2 · Storyboard", elem_id="tab-story", elem_classes=["tab-btn"], scale=0)
            tab_anim = gr.Button("3 · Animatic", elem_id="tab-anim", elem_classes=["tab-btn"], scale=0)

        # ---------------- page 1: duplicates
        with gr.Row(elem_classes="page", visible=True) as page_dup:
            with gr.Column(elem_classes="side", scale=0):
                gr.HTML(SIDE_HIDE)
                d_folder, d_browse = _folder_field()
                d_rec = gr.Checkbox(label="Include subfolders")
                d_tol = gr.Slider(0, 40, value=10, step=1, label="Similarity tolerance",
                                  info="0 = exact copies only · 10 = default · 40 = very loose")
                d_scan = gr.Button("Scan for duplicates", variant="primary")
                d_msg = gr.Markdown()
            with gr.Column(elem_classes=["mainc", "panel"]):
                d_html = gr.HTML(EMPTY_DUP)
                d_bridge = _bridge("del-bridge", "delete bridge")
                d_scan_bridge = _bridge("scan-bridge", "scan bridge")
        d_files, d_groups = gr.State([]), gr.State([])

        # ---------------- page 2: storyboard
        with gr.Row(elem_classes="page", visible=False) as page_story:
            with gr.Column(elem_classes="side", scale=0):
                gr.HTML(SIDE_HIDE)
                s_folder, s_browse = _folder_field()
                s_rec = gr.Checkbox(label="Include subfolders")
                s_nsfw = gr.Checkbox(label="My photos contain NSFW content",
                                     info="Turns off cloud engines. Nothing leaves your PC.")
                s_blur = gr.Checkbox(label="Blur thumbnails (hover to reveal)", visible=False)
                s_vmodel = gr.Dropdown(choices=models.choices(), value=models.DEFAULT_MODEL,
                                       label="Vision model", info="Downloads automatically on first use.")
                s_engine = gr.Dropdown(choices=providers.ENGINES, value=providers.LOCAL_ONLY,
                                       label="Sorting engine", info="Local = visual flow only. Others add story logic.")
                s_key = gr.Textbox(type="password", visible=False, label="API key")
                s_mname = gr.Dropdown(choices=[], allow_custom_value=True, visible=False,
                                      label="Model name (change if outdated)")
                s_refresh = gr.Button("Refresh Ollama models", size="sm", visible=False)
                s_prompt = gr.Textbox(label="Story prompt (optional)", lines=3, visible=False,
                                      info="Tell the AI what story you want, e.g. 'a day in the life of a lighthouse keeper'. "
                                           "Used for sorting and for the Animatic text.")
                s_sort = gr.Button("Sort as storyboard", variant="primary")
                s_msg = gr.Markdown()
            with gr.Column(elem_classes=["mainc", "panel"]):
                s_grid = gr.HTML(EMPTY)      # toolbar + scrolling grid + bottom buttons, all in one block
                s_bridge = _bridge("order-bridge", "drag bridge")
                s_act = _bridge("action-bridge", "action bridge")
                s_apply = _bridge("apply-bridge", "apply bridge")
                s_lock = _bridge("lock-bridge", "lock bridge")
                s_sort_bridge = _bridge("sort-bridge", "sort bridge")
        (st_paths, st_order, st_hist, st_locked, st_texts,
         st_loaded, st_secs) = (gr.State([]), gr.State([]), gr.State([]), gr.State([]), gr.State({}),
                                gr.State(None), gr.State(3.0))

        # ---------------- page 3: animatic
        with gr.Row(elem_classes="page", visible=False) as page_anim:
            with gr.Column(elem_classes=["mainc", "panel"]):
                a_html = gr.HTML(render_animatic([], [], {}, 3.0, ""))
                a_bridge = _bridge("am-bridge", "animatic bridge")

        # ---------------- popup
        with gr.Group(visible=False, elem_id="modal") as modal:
            modal_md = gr.Markdown()
            modal_ok = gr.Button("OK", variant="primary")
        modal_ok.click(lambda: gr.Group(visible=False), None, modal)

        # ---------------- footer (build number, update check, about)
        with gr.Row(elem_id="app-footer"):
            ft_html = gr.HTML(footer_html())
            ft_bridge = _bridge("ft-bridge", "footer bridge")
        with gr.Group(visible=False, elem_id="modal2") as modal2:
            ab_html = gr.HTML()
            with gr.Row():
                ab_action = gr.Button("Update now", variant="primary", visible=False)
                ab_close = gr.Button("Close")
        ab_close.click(lambda: gr.Group(visible=False), None, modal2)
        ft_bridge.input(on_footer, ft_bridge, [modal2, ab_html, ab_action, ft_html])
        ab_action.click(on_update, None, [ab_html, ab_action])
        demo.load(auto_check, None, ft_html)

        # ---------------- right-hand panel data (the page script copies it into the sliding panel)
        pv_data = gr.HTML("", elem_id="pv-data", elem_classes="bridge")
        pv_bridge = _bridge("preview-bridge", "preview bridge")
        cmp_bridge = _bridge("compare-bridge", "compare bridge")

        # ---------------- wiring: tabs
        pages = [page_dup, page_story, page_anim]
        tab_dup.click(lambda: _page("dup"), None, pages, js=_nav_js("dup"))
        tab_story.click(lambda: _page("story"), None, pages, js=_nav_js("story"))
        tab_anim.click(lambda: _page("anim"), None, pages, js=_nav_js("anim")).then(
            show_animatic, [st_paths, st_order, st_texts, st_secs, s_engine], a_html)

        # ---------------- wiring: folder boxes (storyboard loads automatically)
        load_outs = [s_grid, st_paths, st_order, st_hist, st_locked, st_texts, st_loaded, s_msg]
        load_in = lambda box: [box, s_rec, st_loaded]  # noqa: E731
        d_browse.click(browse, d_folder, [d_folder, s_folder]).then(load_folder, load_in(d_folder), load_outs)
        s_browse.click(browse, s_folder, [d_folder, s_folder]).then(load_folder, load_in(s_folder), load_outs)
        d_folder.input(lambda x: x, d_folder, s_folder)
        s_folder.input(lambda x: x, s_folder, d_folder)
        for box in (d_folder, s_folder):
            box.submit(load_folder, load_in(box), load_outs)
            box.blur(load_folder, load_in(box), load_outs)
        s_rec.change(load_folder, load_in(s_folder), load_outs)

        # ---------------- wiring: duplicates
        d_scan.click(scan, [d_folder, d_rec, d_tol], [d_html, d_files, d_groups, d_msg])
        d_scan_bridge.input(on_scan_btn, [d_scan_bridge, d_folder, d_rec, d_tol], [d_html, d_files, d_groups, d_msg])
        d_bridge.input(on_delete, [d_bridge, d_files, d_groups], [d_html, d_files, d_groups, d_msg, modal, modal_md])

        # ---------------- wiring: storyboard
        s_nsfw.change(on_nsfw, [s_nsfw, s_engine, s_blur], [s_engine, s_blur])
        s_blur.change(None, s_blur, None, js="(v) => { document.body.classList.toggle('blur-thumbs', !!v); }")
        s_engine.change(on_engine, s_engine, [s_key, s_mname, s_refresh, s_prompt, s_vmodel])
        s_refresh.click(on_refresh, None, s_mname)
        sort_in = [s_folder, s_rec, s_engine, s_key, s_mname, s_vmodel, s_nsfw, s_prompt, st_paths, st_order,
                   st_locked, st_texts, st_loaded]
        s_sort.click(sort_story, sort_in, load_outs)
        s_sort_bridge.input(on_sort_btn, [s_sort_bridge, *sort_in], load_outs)
        s_bridge.input(on_drag, [s_bridge, st_order, st_hist], [st_order, st_hist])
        s_lock.input(on_lock, [s_lock, st_locked], st_locked)
        s_act.input(on_action, [s_act, st_paths, st_order, st_hist, st_locked], [s_grid, st_order, st_hist])
        s_apply.input(on_apply, [s_apply, s_folder, s_rec, st_paths, st_order],
                      [modal, modal_md, s_grid, st_paths, st_order, st_hist, st_locked, st_texts, st_loaded])

        # ---------------- wiring: animatic
        a_bridge.input(on_animatic, [a_bridge, st_paths, st_order, st_texts, st_secs, s_folder, s_engine, s_key,
                                     s_mname, s_prompt, s_nsfw],
                       [a_html, st_texts, st_secs, modal, modal_md])

        # ---------------- wiring: side panel
        pv_bridge.input(on_preview, [pv_bridge, st_paths, d_files], pv_data)
        cmp_bridge.input(on_compare, [cmp_bridge, d_files, d_groups], pv_data)
    return demo


if __name__ == "__main__":
    build().queue().launch(server_name="127.0.0.1", inbrowser=True,
                           favicon_path=str(ASSETS / "favicon.png"))
