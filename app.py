"""Cutline - clean cuts, clear story.   Run:  python app.py   (opens http://127.0.0.1:7860)"""
import base64
import json
import subprocess
import sys
from pathlib import Path

import gradio as gr

from cutline import dedupe, files, models, ordering, providers
from cutline.gridhtml import (EMPTY, EMPTY_DUP, PV_EMPTY, compare_panel, preview_panel, render_dupes,
                              render_grid)

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
STATIC = ROOT / "cutline" / "static"
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
DND_JS = (STATIC / "dnd.js").read_text(encoding="utf-8")


def _logo_uri():
    return "data:image/png;base64," + base64.b64encode((ASSETS / "logo_mark.png").read_bytes()).decode()


HEADER = f"""<div class="brand" style="display:flex;align-items:center;gap:12px">
<img src="{_logo_uri()}" alt="Cutline" style="width:42px;height:42px;border-radius:10px">
<div><div style="font-size:1.4rem;font-weight:700;line-height:1.1"><span style="color:#D9541E">Cut</span>line</div>
<div style="font-size:.75rem;opacity:.7">Clean cuts. Clear story.</div></div></div>"""

THEME_JS = "() => { document.body.classList.toggle('dark'); }"

NAV_JS = """() => {
  document.querySelector('#tab-%s').classList.add('active');
  document.querySelector('#tab-%s').classList.remove('active');
}"""

_DIALOG = ("import sys, tkinter as tk\nfrom tkinter import filedialog\n"
           "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
           "print(filedialog.askdirectory(initialdir=sys.argv[1] or None) or '')")


def _modal(title, msg):
    return gr.Group(visible=True), f"### {title}\n\n{msg}"


def _check_folder(folder):
    folder = (folder or "").strip().strip('"')
    if not folder or not Path(folder).is_dir():
        raise gr.Error("Enter a valid folder path, or use Browse.")
    return Path(folder)


def _page(which):
    return gr.Row(visible=which == "dup"), gr.Row(visible=which == "story")


def _prog(progress):
    return lambda f, m: progress(f, desc=m)


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


# ----------------------------------------------------------- storyboard
def on_nsfw(nsfw, engine):
    choices = providers.PRIVATE_ENGINES if nsfw else providers.ENGINES
    return gr.Dropdown(choices=choices, value=engine if engine in choices else providers.LOCAL_ONLY)


def on_engine(engine):
    needs_key = engine in providers.CLOUD
    return (gr.Textbox(visible=needs_key, label=f"{engine} API key (or set {providers.ENV_KEYS.get(engine, '')})"),
            gr.Textbox(visible=engine != providers.LOCAL_ONLY, value=providers.DEFAULT_MODELS.get(engine, "")))


def sort_story(folder, recursive, engine, key, model_name, vmodel, nsfw, progress=gr.Progress()):
    folder = _check_folder(folder)
    if nsfw and engine not in providers.PRIVATE_ENGINES:
        raise gr.Error("NSFW mode is on: cloud engines are disabled. Choose Local only or Ollama.")
    paths = files.list_images(folder, recursive)
    note = files.skipped_note(folder, recursive)
    if len(paths) < 2:
        raise gr.Error("Need at least two supported images in that folder." + note)
    p = _prog(progress)
    try:
        order, local_note = ordering.local_order(paths, vmodel, p)
        if engine != providers.LOCAL_ONLY:
            order = providers.refine(engine, key, model_name, paths, order, p)
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(str(e))
    if local_note:
        gr.Warning(local_note)
    gr.Info(f"Sorted {len(paths)} images. Drag frames to rearrange.")
    msg = f"Sorted {len(paths)} images with {engine}. {local_note}{note}"
    return render_grid(paths, order), [str(x) for x in paths], order, [], msg


def on_drag(text, order, hist):
    """The drag-and-drop script posts the new order (comma-separated indexes) through a hidden box."""
    new = files.parse_perm(text, len(order))
    if new is None or new == order:
        return order, hist
    return new, (hist + [order])[-50:]


def reverse(paths, order, hist):
    if not order:
        raise gr.Error("Sort first.")
    gr.Info("Order reversed.")
    new = order[::-1]
    return render_grid(paths, new), new, (hist + [order])[-50:]


def undo(paths, order, hist):
    if not hist:
        raise gr.Error("Nothing to undo.")
    gr.Info("Undid the last change.")
    new = hist[-1]
    return render_grid(paths, new), new, hist[:-1]


def on_action(text, paths, order, hist):
    """Reverse / Undo buttons (HTML) post "reverse|timestamp" or "undo|timestamp" here."""
    act = (text or "").split("|")[0]
    if act == "reverse":
        return reverse(paths, order, hist)
    if act == "undo":
        return undo(paths, order, hist)
    return gr.skip(), gr.skip(), gr.skip()


def on_apply(text, folder, paths, order):
    """Apply order button posts "copy|timestamp" or "rename|timestamp"."""
    mode = (text or "").split("|")[0]
    return apply(folder, paths, order, "Rename originals" if mode == "rename" else "Copy")


def apply(folder, paths, order, mode):
    if not order:
        raise gr.Error("Sort first.")
    folder = _check_folder(folder)
    rename = mode.startswith("Rename")
    try:
        msg = files.apply_order([paths[i] for i in order], folder, rename)
    except Exception as e:
        raise gr.Error(str(e))
    if rename:   # file names changed on disk, so the loaded list is stale
        return (*_modal("Storyboard order applied", msg + "\n\nRun Sort again to reload the renamed files."),
                EMPTY, [], [], [])
    return (*_modal("Storyboard order applied", msg), gr.skip(), gr.skip(), gr.skip(), gr.skip())


# ----------------------------------------------------------- preview / compare panel
def on_preview(text, st_paths, d_files):
    """Space key: the page posts "story:<idx>:<pos>:<total>" or "dup:..." plus a timestamp."""
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


# ----------------------------------------------------------- UI
def _folder_field():
    """Folder box with the Browse button inside the same bordered field (see .folder-field in style.css)."""
    gr.HTML('<span class="field-label">Image folder</span>')
    with gr.Row(elem_classes="folder-field"):
        box = gr.Textbox(show_label=False, container=False, placeholder=r"D:\Shots\Project01",
                         lines=1, max_lines=1, scale=1, min_width=0)
        btn = gr.Button("Browse…", elem_classes="browse-btn", size="sm", scale=0, min_width=0)
    return box, btn


def build():
    with gr.Blocks(title="Cutline", theme=gr.themes.Soft(primary_hue="orange", neutral_hue="zinc"),
                   css=CSS, js=DND_JS) as demo:
        with gr.Row(elem_id="app-header"):
            gr.HTML(HEADER)
            theme_btn = gr.Button("", elem_id="theme-btn", scale=0, min_width=46)
        theme_btn.click(None, None, None, js=THEME_JS)
        with gr.Row(elem_id="tabbar"):
            tab_dup = gr.Button("1 · Duplicates", elem_id="tab-dup", elem_classes=["tab-btn", "active"], scale=0)
            tab_story = gr.Button("2 · Storyboard", elem_id="tab-story", elem_classes=["tab-btn"], scale=0)

        # ---------------- page 1: duplicates
        with gr.Row(elem_classes="page", visible=True) as page_dup:
            with gr.Column(elem_classes="side", scale=0):
                d_folder, d_browse = _folder_field()
                d_rec = gr.Checkbox(label="Include subfolders")
                d_tol = gr.Slider(0, 40, value=10, step=1, label="Similarity tolerance",
                                  info="0 = exact copies only · 10 = default · 40 = very loose")
                d_scan = gr.Button("Scan for duplicates", variant="primary")
                d_msg = gr.Markdown()
            with gr.Column(elem_classes=["mainc", "panel"]):
                d_html = gr.HTML(EMPTY_DUP)   # toolbar + scrolling groups + bottom bar with the delete button
                d_bridge = gr.Textbox(elem_id="del-bridge", elem_classes="bridge", label="delete bridge")
        d_files, d_groups = gr.State([]), gr.State([])

        # ---------------- page 2: storyboard
        with gr.Row(elem_classes="page", visible=False) as page_story:
            with gr.Column(elem_classes="side", scale=0):
                s_folder, s_browse = _folder_field()
                s_rec = gr.Checkbox(label="Include subfolders")
                s_nsfw = gr.Checkbox(label="My photos contain NSFW content",
                                     info="Turns off cloud engines. Nothing leaves your PC.")
                s_vmodel = gr.Dropdown(choices=models.choices(), value=models.DEFAULT_MODEL,
                                       label="Vision model", info="Downloads automatically on first use.")
                s_engine = gr.Dropdown(choices=providers.ENGINES, value=providers.LOCAL_ONLY,
                                       label="Sorting engine", info="Local = visual flow only. Others add story logic.")
                s_key = gr.Textbox(type="password", visible=False, label="API key")
                s_mname = gr.Textbox(visible=False, label="Model name (change if outdated)")
                s_sort = gr.Button("Sort as storyboard", variant="primary")
                s_msg = gr.Markdown()
            with gr.Column(elem_classes=["mainc", "panel"]):
                s_grid = gr.HTML(EMPTY)      # toolbar + scrolling grid + bottom buttons, all in one block
                s_bridge = gr.Textbox(elem_id="order-bridge", elem_classes="bridge", label="drag bridge")
                s_act = gr.Textbox(elem_id="action-bridge", elem_classes="bridge", label="action bridge")
                s_apply = gr.Textbox(elem_id="apply-bridge", elem_classes="bridge", label="apply bridge")
        st_paths, st_order, st_hist = gr.State([]), gr.State([]), gr.State([])

        # ---------------- popup
        with gr.Group(visible=False, elem_id="modal") as modal:
            modal_md = gr.Markdown()
            modal_ok = gr.Button("OK", variant="primary")
        modal_ok.click(lambda: gr.Group(visible=False), None, modal)

        # ---------------- right-hand panel (preview on Space, compare on the Duplicates tab)
        pv_html = gr.HTML(PV_EMPTY, elem_id="pv-panel")
        pv_bridge = gr.Textbox(elem_id="preview-bridge", elem_classes="bridge", label="preview bridge")
        cmp_bridge = gr.Textbox(elem_id="compare-bridge", elem_classes="bridge", label="compare bridge")

        # ---------------- wiring
        pv_bridge.input(on_preview, [pv_bridge, st_paths, d_files], pv_html)
        cmp_bridge.input(on_compare, [cmp_bridge, d_files, d_groups], pv_html)

        tab_dup.click(lambda: _page("dup"), None, [page_dup, page_story], js=NAV_JS % ("dup", "story"))
        tab_story.click(lambda: _page("story"), None, [page_dup, page_story], js=NAV_JS % ("story", "dup"))

        d_browse.click(browse, d_folder, [d_folder, s_folder])
        s_browse.click(browse, s_folder, [d_folder, s_folder])
        d_folder.input(lambda x: x, d_folder, s_folder)
        s_folder.input(lambda x: x, s_folder, d_folder)

        d_scan.click(scan, [d_folder, d_rec, d_tol], [d_html, d_files, d_groups, d_msg])
        d_bridge.input(on_delete, [d_bridge, d_files, d_groups], [d_html, d_files, d_groups, d_msg, modal, modal_md])

        s_nsfw.change(on_nsfw, [s_nsfw, s_engine], s_engine)
        s_engine.change(on_engine, s_engine, [s_key, s_mname])
        s_sort.click(sort_story, [s_folder, s_rec, s_engine, s_key, s_mname, s_vmodel, s_nsfw],
                     [s_grid, st_paths, st_order, st_hist, s_msg])
        s_bridge.input(on_drag, [s_bridge, st_order, st_hist], [st_order, st_hist])
        s_act.input(on_action, [s_act, st_paths, st_order, st_hist], [s_grid, st_order, st_hist])
        s_apply.input(on_apply, [s_apply, s_folder, st_paths, st_order],
                      [modal, modal_md, s_grid, st_paths, st_order, st_hist])
    return demo


if __name__ == "__main__":
    build().queue().launch(server_name="127.0.0.1", inbrowser=True,
                           favicon_path=str(ASSETS / "favicon.png"))
