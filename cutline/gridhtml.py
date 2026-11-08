"""HTML for the storyboard panel: toolbar, drag-and-drop grid and the bottom control bar.
Behaviour lives in static/dnd.js; buttons post to hidden Gradio textboxes (the "bridges")."""
import html
from pathlib import Path

from . import files

TOOLBAR = (
    '<div class="sb-toolbar"><div><span class="sb-title">Storyboard</span>'
    '<span class="sb-hint">Drag to reorder · Ctrl/Shift+click to multi-select · Space to preview</span></div>'
    '<label class="sb-size">Thumbnail size'
    '<input type="range" class="thumb-slider" min="90" max="320" step="10" value="160" aria-label="Thumbnail size"></label></div>'
)

BOTTOM = (
    '<div class="sb-bottom" id="sb-bottom">'
    '<button type="button" class="sb-btn" data-act="reverse">Reverse order</button>'
    '<button type="button" class="sb-btn" data-act="undo">Undo</button>'
    '<span class="sb-spacer"></span>'
    '<div class="sb-seg" role="group" aria-label="Apply as">'
    '<button type="button" class="sb-btn sb-mode active" data-mode="copy" '
    'title="Copy the images into a _storyboard folder (originals untouched)">Copy</button>'
    '<button type="button" class="sb-btn sb-mode" data-mode="rename" '
    'title="Rename the original files with 001_, 002_ ... prefixes">Rename</button></div>'
    '<button type="button" class="sb-btn primary" data-act="apply">Apply order</button></div>'
)


def _panel(scroll_inner):
    return f'<div class="sb-panel-inner">{TOOLBAR}<div id="sb-scroll">{scroll_inner}</div>{BOTTOM}</div>'


EMPTY = _panel('<div class="sb-empty">Sort a folder to see your storyboard here.<br>'
               'Then drag frames to rearrange them.</div>')


def render_grid(paths, order):
    if not order:
        return EMPTY
    frames = []
    for k, i in enumerate(order):
        name = html.escape(Path(paths[i]).name)
        frames.append(
            f'<div class="sb-frame" draggable="true" data-idx="{i}" title="{name}">'
            f'<span class="sb-num">{k + 1:03d}</span>'
            f'<img draggable="false" src="{files.thumb_data_uri(paths[i])}" alt="{name}">'
            f'<div class="sb-name">{name}</div></div>')
    return _panel(f'<div id="sb-grid" class="sb-grid">{"".join(frames)}</div>')


# ---------------- duplicates panel ----------------
DUP_TOOLBAR = (
    '<div class="sb-toolbar"><div><span class="sb-title">Duplicate groups</span>'
    '<span class="sb-hint">Click a card to switch Keep / Delete · Space to preview · C to compare</span></div>'
    '<label class="sb-size">Thumbnail size'
    '<input type="range" class="thumb-slider" min="90" max="320" step="10" value="160" aria-label="Thumbnail size"></label></div>'
)
DUP_BOTTOM = (
    '<div class="sb-bottom" id="dp-bottom"><span id="dp-count">Nothing marked</span><span class="sb-spacer"></span>'
    '<button type="button" class="sb-btn" data-act="dup-reset">Reset marks</button>'
    '<button type="button" class="sb-btn danger" data-act="dup-delete" disabled>Move to Recycle Bin</button></div>'
)


def _dup_panel(inner):
    return f'<div class="sb-panel-inner">{DUP_TOOLBAR}<div id="dup-scroll">{inner}</div>{DUP_BOTTOM}</div>'


EMPTY_DUP = _dup_panel('<div class="sb-empty">Scan a folder to see duplicate groups here.</div>')


def render_dupes(groups, files_list):
    """groups: lists of indexes into files_list; the first index of each group is the copy to keep."""
    out = []
    for gi, grp in enumerate(groups, 1):
        cards = []
        for k, i in enumerate(grp):
            p = Path(files_list[i])
            w, h, size = files.describe(p)
            state = "keep" if k == 0 else "del"
            name = html.escape(p.name)
            cards.append(
                f'<div class="dp-card {state}" data-idx="{i}" data-def="{state}" data-size="{size}" title="{name}">'
                f'<img draggable="false" src="{files.thumb_data_uri(p)}" alt="{name}">'
                f'<span class="dp-badge">{"KEEP" if k == 0 else "DELETE"}</span>'
                f'<div class="dp-meta"><b>{name}</b><br>{w}×{h} · {files.human_size(size)}</div></div>')
        out.append(f'<div class="dp-group" data-g="{gi - 1}"><div class="dp-gtitle"><span>Group {gi} · {len(grp)} files</span>'
                   f'<button type="button" class="sb-btn small" data-act="compare">Compare</button></div>'
                   f'<div class="dp-row">{"".join(cards)}</div></div>')
    if not out:
        return _dup_panel('<div class="sb-empty">No duplicates found.</div>')
    return _dup_panel("".join(out))


# ---------------- right-hand preview / compare panel ----------------
_CLOSE = '<button type="button" class="pv-close" data-act="pv-close" aria-label="Close panel">&#10005;</button>'
PV_EMPTY = ('<div class="pv-inner" data-key=""><div class="pv-head"><b class="pv-title">Preview</b>' + _CLOSE +
            '</div><div class="pv-empty">Hover an image and press Space.<br>On the Duplicates tab, press C to compare.</div></div>')


def preview_panel(kind, idx, path, pos, total):
    p = Path(path)
    w, h, size = files.describe(p)
    name = html.escape(p.name)
    return (f'<div class="pv-inner" data-key="{kind}:{idx}:{pos}:{total}">'
            f'<div class="pv-head"><b class="pv-title" title="{name}">{name}</b>{_CLOSE}</div>'
            f'<div class="pv-stage"><img class="pv-img" draggable="false" src="{files.preview_data_uri(p)}" alt="{name}"></div>'
            f'<div class="pv-foot"><span>{w}×{h} · {files.human_size(size)} · {pos} / {total}</span>'
            f'<span class="pv-hint">← → browse · Space close</span></div></div>')


def compare_panel(g, files_list, group, a, b):
    pa, pb = Path(files_list[a]), Path(files_list[b])
    wa, ha, sa = files.describe(pa)
    wb, hb, sb = files.describe(pb)
    na, nb = html.escape(pa.name), html.escape(pb.name)
    chips = []
    for i in group:
        name = html.escape(Path(files_list[i]).name)
        cls = "is-a" if i == a else ("is-b" if i == b else "")
        chips.append(f'<div class="cmp-chip {cls}" title="{name}"><span class="cmp-chip-name">{name}</span>'
                     f'<button type="button" class="cmp-btn" data-act="cmp-a" data-idx="{i}">A</button>'
                     f'<button type="button" class="cmp-btn" data-act="cmp-b" data-idx="{i}">B</button></div>')
    ratio = f"{wa} / {ha}" if wa and ha else "16 / 10"
    return (f'<div class="pv-inner cmp-root" data-key="cmp:{g}:{a}:{b}" data-g="{g}" data-a="{a}" data-b="{b}">'
            f'<div class="pv-head"><b class="pv-title">Compare · Group {g + 1}</b>{_CLOSE}</div>'
            f'<div class="cmp-labels"><span><b class="tagA">A</b> {na}<br>{wa}×{ha} · {files.human_size(sa)}</span>'
            f'<span class="right"><b class="tagB">B</b> {nb}<br>{wb}×{hb} · {files.human_size(sb)}</span></div>'
            f'<div class="cmp-stage" style="--pos:50%;aspect-ratio:{ratio}">'
            f'<img class="cmp-img b" draggable="false" src="{files.preview_data_uri(pb)}" alt="B: {nb}">'
            f'<img class="cmp-img a" draggable="false" src="{files.preview_data_uri(pa)}" alt="A: {na}">'
            f'<div class="cmp-handle"><span>&#8596;</span></div></div>'
            f'<input type="range" class="cmp-range" min="0" max="100" value="50" aria-label="Slide to reveal image A or B">'
            f'<div class="cmp-chips">{"".join(chips)}</div>'
            f'<div class="pv-foot"><span class="pv-hint">Drag the divider · A on the left, B on the right · pick A / B below</span></div></div>')
