"""HTML for the storyboard, duplicates and animatic panels, and for the right-hand preview / compare panel.
Behaviour lives in static/dnd.js; buttons post to hidden Gradio textboxes (the "bridges")."""
import html
from pathlib import Path

from . import files

def _svg(inner, cls=""):
    return (f'<svg class="{cls}" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{inner}</svg>')


ICON_SUN = _svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2'
                'M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>', "ico-sun")
ICON_MOON = _svg('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>', "ico-moon")
ICON_REFRESH = _svg('<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/>')
ICON_INFO = _svg('<circle cx="12" cy="12" r="9"/><path d="M12 16v-4"/><path d="M12 8h.01"/>')


def header_html(logo_uri):
    return (f'<div class="hdr"><div class="brand" style="display:flex;align-items:center;gap:12px">'
            f'<img src="{logo_uri}" alt="Cutline" style="width:42px;height:42px;border-radius:10px">'
            '<div><div style="font-size:1.4rem;font-weight:700;line-height:1.1"><span style="color:#D9541E">Cut</span>line</div>'
            '<div style="font-size:.75rem;opacity:.7">Clean cuts. Clear story.</div></div></div><span class="sb-spacer"></span>'
            '<button type="button" class="icon-btn" data-act="theme" title="Switch light / dark theme" '
            f'aria-label="Switch light / dark theme">{ICON_SUN}{ICON_MOON}</button></div>')


def footer_bar(label, badge=""):
    return (f'<div class="ft-wrap"><div class="ft-info"><span>{label}</span>{badge}</div><span class="sb-spacer"></span>'
            '<button type="button" class="icon-btn small" data-act="ft-check" title="Check for updates" '
            f'aria-label="Check for updates">{ICON_REFRESH}</button>'
            '<button type="button" class="icon-btn small" data-act="ft-about" title="About Cutline" '
            f'aria-label="About Cutline">{ICON_INFO}</button></div>')


# Hide-sidebar button lives at the top of the sidebar; the toolbar shows "Show sidebar" only while it is hidden.
SIDE_HIDE = ('<button type="button" class="sb-btn small side-hide" data-act="toggle-side" '
             'title="Hide this sidebar to give the gallery the full width">&#9664; Hide sidebar</button>')
_SIDE_BTN = ('<button type="button" class="sb-btn small show-side" data-act="toggle-side">&#9654; Show sidebar</button>')
_SLIDER = ('<label class="sb-size">Thumbnail size<input type="range" class="thumb-slider" min="90" max="320" step="10" '
           'value="160" aria-label="Thumbnail size"></label>')


def _toolbar(title, hint, buttons=""):
    return (f'<div class="sb-toolbar"><div class="sb-heading"><span class="sb-title">{title}</span>'
            f'<span class="sb-hint">{hint}</span></div><div class="sb-tools">{buttons}{_SIDE_BTN}{_SLIDER}</div></div>')


def _panel(toolbar, scroll_id, inner, bottom):
    return (f'<div class="sb-panel-inner">{toolbar}<div id="{scroll_id}" data-scroll>{inner}</div>{bottom}</div>')


# ---------------------------------------------------------------- storyboard
TOOLBAR = _toolbar("Storyboard", "Drag to reorder · Ctrl/Shift+click selects · Space previews · lock icon pins a frame",
                   '<button type="button" class="sb-btn small primary" data-act="sort">Sort</button>')

BOTTOM = (
    '<div class="sb-bottom" id="sb-bottom">'
    '<button type="button" class="sb-btn" data-act="reverse">Reverse order</button>'
    '<button type="button" class="sb-btn" data-act="undo">Undo</button>'
    '<button type="button" class="sb-btn" data-act="pin-ends" title="Pin the first and last frame so sorting works around them">Pin ends</button>'
    '<button type="button" class="sb-btn" data-act="lock-sel" title="Pin / unpin the selected frames (L)">Lock selected</button>'
    '<button type="button" class="sb-btn" data-act="unlock-all">Unlock all</button>'
    '<span class="sb-spacer"></span>'
    '<div class="sb-seg" role="group" aria-label="Apply as">'
    '<button type="button" class="sb-btn sb-mode active" data-mode="copy" '
    'title="Copy the images into a _storyboard folder (originals untouched)">Copy</button>'
    '<button type="button" class="sb-btn sb-mode" data-mode="rename" '
    'title="Rename the original files with 001_, 002_ ... prefixes">Rename</button></div>'
    '<button type="button" class="sb-btn primary" data-act="apply">Apply order</button></div>'
)

_LOCK = ('<button type="button" class="sb-lock" data-act="lock" title="Pin this frame: sorting keeps it in place" '
         'aria-label="Pin frame">'
         '<svg class="ico-open" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" '
         'stroke-width="2" stroke-linecap="round"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 7.5-2"/></svg>'
         '<svg class="ico-closed" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" '
         'stroke-width="2" stroke-linecap="round"><rect x="5" y="11" width="14" height="10" rx="2" fill="currentColor"/>'
         '<path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg></button>')

EMPTY = _panel(TOOLBAR, "sb-scroll", '<div class="sb-empty">Pick a folder to see your images here.<br>'
               'Drag them into order, or press Sort.</div>', BOTTOM)


def render_grid(paths, order, locked=(), progress=None):
    if not order:
        return EMPTY
    locked = set(locked or ())
    frames = []
    for k, i in enumerate(order):
        if progress:
            progress(k / len(order), f"Loading thumbnails ({k + 1}/{len(order)})")
        name = html.escape(Path(paths[i]).name)
        cls = "sb-frame locked" if i in locked else "sb-frame"
        frames.append(
            f'<div class="{cls}" draggable="true" data-idx="{i}" title="{name}">'
            f'<span class="sb-num">{k + 1:03d}</span>{_LOCK}'
            f'<img draggable="false" src="{files.thumb_data_uri(paths[i])}" alt="{name}">'
            f'<div class="sb-name">{name}</div></div>')
    return _panel(TOOLBAR, "sb-scroll", f'<div id="sb-grid" class="sb-grid">{"".join(frames)}</div>', BOTTOM)


# ---------------------------------------------------------------- duplicates
DUP_TOOLBAR = _toolbar("Duplicate groups", "Click a card to switch Keep / Delete · Space previews · C compares",
                       '<button type="button" class="sb-btn small primary" data-act="scan">Scan</button>')
DUP_BOTTOM = (
    '<div class="sb-bottom" id="dp-bottom"><span id="dp-count">Nothing marked</span><span class="sb-spacer"></span>'
    '<button type="button" class="sb-btn" data-act="dup-reset">Reset marks</button>'
    '<button type="button" class="sb-btn danger" data-act="dup-delete" disabled>Move to Recycle Bin</button></div>'
)
EMPTY_DUP = _panel(DUP_TOOLBAR, "dup-scroll", '<div class="sb-empty">Scan a folder to see duplicate groups here.</div>',
                   DUP_BOTTOM)


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
        return _panel(DUP_TOOLBAR, "dup-scroll", '<div class="sb-empty">No duplicates found.</div>', DUP_BOTTOM)
    return _panel(DUP_TOOLBAR, "dup-scroll", "".join(out), DUP_BOTTOM)


# ---------------------------------------------------------------- animatic
def _am_toolbar(note, secs):
    btns = ('<button type="button" class="sb-btn small primary" data-act="am-gen">Generate story</button>'
            '<button type="button" class="sb-btn small" data-act="am-fill">Fill empty</button>'
            f'<label class="sb-size">Seconds per frame<input type="number" class="am-secs" min="0.5" max="60" '
            f'step="0.5" value="{secs:g}"></label>')
    return (f'<div class="sb-toolbar"><div class="sb-heading"><span class="sb-title">Animatic</span>'
            f'<span class="sb-hint">{note}</span></div><div class="sb-tools">{btns}{_SLIDER}</div></div>')


AM_BOTTOM = ('<div class="sb-bottom" id="am-bottom"><span id="am-info">0 frames</span><span class="sb-spacer"></span>'
             '<button type="button" class="sb-btn primary" data-act="am-export">Export story</button></div>')


def render_animatic(paths, order, texts, secs=3.0, engine=""):
    note = ("Order comes from the Storyboard tab · uses the engine and story prompt set there"
            + (f" ({html.escape(engine)})" if engine else ""))
    toolbar = _am_toolbar(note, secs)
    if not order:
        return _panel(toolbar, "am-scroll", '<div class="sb-empty">Load a folder on the Storyboard tab first.<br>'
                      'Each image appears here with a box for its story.</div>', AM_BOTTOM)
    texts = texts or {}
    rows = []
    for k, i in enumerate(order):
        name = html.escape(Path(paths[i]).name)
        rows.append(
            f'<div class="am-row" data-idx="{i}" title="{name}"><div class="am-pic"><span class="sb-num">{k + 1:03d}</span>'
            f'<img class="am-img" draggable="false" src="{files.thumb_data_uri(paths[i])}" alt="{name}"></div>'
            f'<div class="am-body"><div class="am-name">{name}</div>'
            f'<textarea class="am-ta" data-idx="{i}" rows="3" placeholder="Story for this shot...">'
            f'{html.escape(texts.get(i, ""))}</textarea>'
            f'<div class="am-actions"><button type="button" class="sb-btn small" data-act="am-regen" data-idx="{i}">'
            f'Regenerate</button></div></div></div>')
    return _panel(toolbar, "am-scroll", "".join(rows), AM_BOTTOM)


# ---------------------------------------------------------------- right-hand preview / compare panel
_CLOSE = '<button type="button" class="pv-close" data-act="pv-close" aria-label="Close panel">&#10005;</button>'


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
