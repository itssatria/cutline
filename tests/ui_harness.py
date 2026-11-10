"""Static page mimicking the Cutline DOM (Gradio-like flex defaults) so the real CSS + JS can be tested in Chromium."""
import base64
import sys
import types
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.modules.setdefault('send2trash', types.ModuleType('send2trash'))
sys.modules['send2trash'].send2trash = lambda p: None
from cutline import gridhtml as G  # noqa: E402

BASE = """*{box-sizing:border-box} body{margin:0;font-family:sans-serif;background:#0b0f19;color:#e5e7eb}
.gradio-container{display:flex;flex-direction:column;width:100%}
.row{display:flex;flex-direction:row;gap:16px} .column{display:flex;flex-direction:column;gap:16px;min-width:min(320px,100%)}
.block{padding:0;width:100%} button{font:inherit}
:root{--background-fill-primary:#0b0f19;--background-fill-secondary:#1f2937;--border-color-primary:#374151;--body-text-color:#e5e7eb;--input-background-fill:#1f2937;}"""
SIZES = [(200, 320), (320, 200), (240, 240)]          # portrait, landscape, square


def make_images(d, n=10):
    d = Path(d)
    d.mkdir(exist_ok=True)
    out = []
    for i in range(n):
        im = Image.new('RGB', SIZES[i % 3], ((i * 30) % 255, 120, 255 - (i * 25) % 255))
        p = d / f'img_{i:02d}.png'
        im.save(p)
        out.append(str(p))
    return out


def bridge(i):
    return f'<div id="{i}" class="bridge"><textarea></textarea></div>'


def build(out_html, imgs, locked=()):
    css = (ROOT / 'cutline/static/style.css').read_text()
    fav = "data:image/png;base64," + base64.b64encode((ROOT / 'assets/favicon.png').read_bytes()).decode()
    js = (ROOT / 'cutline/static/dnd.js').read_text().replace('__FAVICON__', fav)
    logo = "data:image/png;base64," + base64.b64encode((ROOT / 'assets/logo_mark.png').read_bytes()).decode()
    n = len(imgs)
    grid = G.render_grid(imgs, list(range(n)), locked)
    dup = G.render_dupes([[0, 1, 2], [3, 4]], imgs)
    am = G.render_animatic(imgs, list(range(n)), {2: 'The hero wakes.'}, 3.0, 'Ollama')
    tall = ''.join(f'<div class="block" style="height:64px;border:1px solid #374151">option row {i}</div>' for i in range(14))
    side = lambda extra: f'<div class="column side"><div class="block">{G.SIDE_HIDE}</div><div class="block">Folder</div>{tall}{extra}</div>'  # noqa: E731
    html = f"""<!doctype html><html><head><meta charset=utf-8><title>gradio</title><link rel="icon" href="gradio-default.ico">
<style>{BASE}\n{css}</style></head>
<body class="dark"><div class="gradio-container">
<div id="app-header" class="row"><div class="block">{G.header_html(logo)}</div></div>
<div id="tabbar" class="row"><button id="tab-dup" class="tab-btn active">1 · Duplicates</button><button id="tab-story" class="tab-btn">2 · Storyboard</button><button id="tab-anim" class="tab-btn">3 · Animatic</button></div>
<div class="row page" id="page-dup">{side('<button id="scan-btn">Scan</button>')}
 <div class="column mainc panel"><div class="block">{dup}</div>{bridge('del-bridge')}{bridge('scan-bridge')}</div></div>
<div class="row page" id="page-story" style="display:none">{side('<button id="sort-btn">Sort as storyboard</button>')}
 <div class="column mainc panel"><div class="block">{grid}</div>{bridge('order-bridge')}{bridge('action-bridge')}{bridge('apply-bridge')}{bridge('lock-bridge')}{bridge('sort-bridge')}</div></div>
<div class="row page" id="page-anim" style="display:none"><div class="column mainc panel"><div class="block">{am}</div>{bridge('am-bridge')}</div></div>
<div id="app-footer" class="row"><div class="block">{G.footer_bar('Cutline v0.6.0 · build 1')}</div>{bridge('ft-bridge')}</div>
<div id="pv-data" class="block bridge"></div>{bridge('preview-bridge')}{bridge('compare-bridge')}
</div>
<script>const __f = {js}; __f();
const show = (w) => {{ for (const p of ['dup','story','anim']) document.getElementById('page-'+p).style.display = p===w ? '' : 'none';
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active')); document.getElementById('tab-'+w).classList.add('active'); }};
for (const w of ['dup','story','anim']) document.getElementById('tab-'+w).addEventListener('click', () => show(w));
</script></body></html>"""
    Path(out_html).write_text(html)
