"""Cutline - clean cuts, clear story.   Run:  python app.py   (opens http://127.0.0.1:7860)"""
import os
from pathlib import Path

import gradio as gr

from cutline import dedupe, files, models, ordering, providers

HEADER = """<div style="display:flex;align-items:baseline;gap:12px">
<span style="font-size:1.7rem;font-weight:700">Cutline</span>
<span style="opacity:.7">Clean cuts. Clear story.</span></div>"""
TOGGLE_JS = "() => { document.body.classList.toggle('dark'); }"


def _check_folder(folder):
    if not folder or not Path(folder.strip().strip('"')).is_dir():
        raise gr.Error("Enter a valid folder path.")
    return Path(folder.strip().strip('"'))


def _prog(progress):
    return lambda f, m: progress(f, desc=m)


# ----------------------------------------------------------- duplicates
def scan(folder, recursive, tolerance, progress=gr.Progress()):
    folder = _check_folder(folder)
    paths = files.list_images(folder, recursive)
    if len(paths) < 2:
        raise gr.Error("Need at least two images in that folder.")
    groups = dedupe.find_duplicates(paths, int(tolerance), _prog(progress))
    items, choices, marked, saving = [], [], [], 0
    for gi, g in enumerate(groups, 1):
        for k, p in enumerate(g):
            w, h, size = files.describe(p)
            keep = k == 0
            tag = "KEEP" if keep else "DELETE"
            label = f"G{gi} · {tag} · {p.name} · {w}×{h} · {files.human_size(size)}"
            items.append((files.make_thumb(p), label))
            choices.append((f"G{gi} · {p.name} · {w}×{h}", str(p)))
            if not keep:
                marked.append(str(p))
                saving += size
    if not groups:
        summary = f"No duplicates found in {len(paths)} images."
    else:
        summary = (f"**{len(groups)} groups** · {len(marked)} files marked for the Recycle Bin "
                   f"(frees {files.human_size(saving)}). Untick any file you want to keep.")
    return (items, gr.CheckboxGroup(choices=choices, value=marked), summary,
            [[str(p) for p in g] for g in groups])


def delete_marked(selected, groups):
    selected = set(selected or [])
    if not selected:
        raise gr.Error("Nothing is selected.")
    for g in groups:
        if all(p in selected for p in g):
            raise gr.Error(f"Every copy in the group containing {Path(g[0]).name} is selected. Keep at least one.")
    try:
        files.to_trash(sorted(selected))
    except Exception as e:
        raise gr.Error(str(e))
    return [], gr.CheckboxGroup(choices=[], value=[]), f"Moved {len(selected)} files to the Recycle Bin.", []


# ----------------------------------------------------------- storyboard
def _gallery(paths, order):
    return [(files.make_thumb(paths[i]), f"{k + 1:03d} · {Path(paths[i]).name}") for k, i in enumerate(order)]


def on_nsfw(nsfw, engine):
    choices = providers.PRIVATE_ENGINES if nsfw else providers.ENGINES
    return gr.Dropdown(choices=choices, value=engine if engine in choices else providers.LOCAL_ONLY)


def on_engine(engine):
    local = engine == providers.LOCAL_ONLY
    needs_key = engine in providers.CLOUD
    return (gr.Textbox(visible=needs_key, label=f"{engine} API key (or set {providers.ENV_KEYS.get(engine, '')})"),
            gr.Textbox(visible=not local, value=providers.DEFAULT_MODELS.get(engine, "")))


def sort_story(folder, recursive, engine, key, model_name, vmodel, nsfw, progress=gr.Progress()):
    folder = _check_folder(folder)
    if nsfw and engine not in providers.PRIVATE_ENGINES:
        raise gr.Error("NSFW mode is on: cloud engines are disabled. Choose Local only or Ollama.")
    paths = files.list_images(folder, recursive)
    if len(paths) < 2:
        raise gr.Error("Need at least two images in that folder.")
    p = _prog(progress)
    try:
        order, note = ordering.local_order(paths, vmodel, p)
        if engine != providers.LOCAL_ONLY:
            order = providers.refine(engine, key, model_name, paths, order, p)
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(str(e))
    msg = f"Sorted {len(paths)} images with {engine}. Click a frame, then use Move left/right if needed. {note}"
    return _gallery(paths, order), [str(x) for x in paths], order, None, msg


def pick(evt: gr.SelectData):
    return evt.index


def _selected_text(paths, order, sel):
    return "" if sel is None else f"Selected frame {sel + 1:03d}: {Path(paths[order[sel]]).name}"


def move(paths, order, sel, delta):
    if not order:
        raise gr.Error("Sort first.")
    if sel is None:
        raise gr.Error("Click a frame first.")
    j = sel + delta
    if 0 <= j < len(order):
        order[sel], order[j] = order[j], order[sel]
        sel = j
    return _gallery(paths, order), order, sel, _selected_text(paths, order, sel)


def reverse(paths, order):
    if not order:
        raise gr.Error("Sort first.")
    order = order[::-1]
    return _gallery(paths, order), order, None, ""


def apply(folder, paths, order, rename):
    if not order:
        raise gr.Error("Sort first.")
    folder = _check_folder(folder)
    try:
        return files.apply_order([paths[i] for i in order], folder, rename == "Rename originals")
    except Exception as e:
        raise gr.Error(str(e))


# ----------------------------------------------------------- UI
def build():
    with gr.Blocks(title="Cutline", theme=gr.themes.Soft(primary_hue="orange", neutral_hue="zinc")) as demo:
        with gr.Row():
            gr.HTML(HEADER)
            theme_btn = gr.Button("Light / Dark", scale=0, min_width=130)
        theme_btn.click(None, None, None, js=TOGGLE_JS)

        with gr.Tab("1 · Duplicates"):
            with gr.Row():
                with gr.Column(scale=1):
                    d_folder = gr.Textbox(label="Image folder", placeholder=r"D:\Shots\Project01")
                    d_rec = gr.Checkbox(label="Include subfolders")
                    d_tol = gr.Slider(0, 40, value=10, step=1, label="Similarity tolerance",
                                      info="0 = exact copies only · 10 = default · 40 = very loose")
                    d_scan = gr.Button("Scan for duplicates", variant="primary")
                    d_msg = gr.Markdown()
                with gr.Column(scale=3):
                    d_gal = gr.Gallery(label="Duplicate groups (first in each group is kept)", columns=5,
                                       height=480, object_fit="cover", allow_preview=False)
                    d_marked = gr.CheckboxGroup(label="Files to move to the Recycle Bin", choices=[])
                    d_del = gr.Button("Move selected files to Recycle Bin", variant="stop")
            d_groups = gr.State([])
            d_scan.click(scan, [d_folder, d_rec, d_tol], [d_gal, d_marked, d_msg, d_groups])
            d_del.click(delete_marked, [d_marked, d_groups], [d_gal, d_marked, d_msg, d_groups])

        with gr.Tab("2 · Storyboard"):
            with gr.Row():
                with gr.Column(scale=1):
                    s_folder = gr.Textbox(label="Image folder", placeholder=r"D:\Shots\Project01")
                    s_rec = gr.Checkbox(label="Include subfolders")
                    s_nsfw = gr.Checkbox(label="My photos contain NSFW content",
                                         info="Turns off cloud engines. Nothing leaves your PC.")
                    s_vmodel = gr.Dropdown(choices=models.choices(), value=models.DEFAULT_MODEL,
                                           label="Vision model (downloads automatically on first use)")
                    s_engine = gr.Dropdown(choices=providers.ENGINES, value=providers.LOCAL_ONLY,
                                           label="Sorting engine",
                                           info="Local = visual flow only. Others add story logic.")
                    s_key = gr.Textbox(type="password", visible=False, label="API key")
                    s_mname = gr.Textbox(visible=False, label="Model name (change if outdated)")
                    s_sort = gr.Button("Sort as storyboard", variant="primary")
                    s_msg = gr.Markdown()
                with gr.Column(scale=3):
                    s_gal = gr.Gallery(label="Storyboard order", columns=5, height=520,
                                       object_fit="cover", allow_preview=False)
                    s_sel_txt = gr.Markdown()
                    with gr.Row():
                        b_rev = gr.Button("Reverse")
                        b_left = gr.Button("Move left")
                        b_right = gr.Button("Move right")
                    with gr.Row():
                        s_apply_mode = gr.Radio(["Copy to _storyboard folder", "Rename originals"],
                                                value="Copy to _storyboard folder", label="Apply as")
                        b_apply = gr.Button("Apply order", variant="primary")
                    s_apply_msg = gr.Markdown()
            st_paths, st_order, st_sel = gr.State([]), gr.State([]), gr.State(None)

            s_nsfw.change(on_nsfw, [s_nsfw, s_engine], s_engine)
            s_engine.change(on_engine, s_engine, [s_key, s_mname])
            s_sort.click(sort_story, [s_folder, s_rec, s_engine, s_key, s_mname, s_vmodel, s_nsfw],
                         [s_gal, st_paths, st_order, st_sel, s_msg])
            s_gal.select(pick, None, st_sel).then(_selected_text, [st_paths, st_order, st_sel], s_sel_txt)
            b_left.click(lambda p, o, s: move(p, o, s, -1), [st_paths, st_order, st_sel],
                         [s_gal, st_order, st_sel, s_sel_txt])
            b_right.click(lambda p, o, s: move(p, o, s, 1), [st_paths, st_order, st_sel],
                          [s_gal, st_order, st_sel, s_sel_txt])
            b_rev.click(reverse, [st_paths, st_order], [s_gal, st_order, st_sel, s_sel_txt])
            b_apply.click(apply, [s_folder, st_paths, st_order, s_apply_mode], s_apply_msg)
    return demo


if __name__ == "__main__":
    build().queue().launch(server_name="127.0.0.1", inbrowser=True)
