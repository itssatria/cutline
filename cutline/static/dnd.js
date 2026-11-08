() => {
  // Default theme is always dark.
  document.body.classList.add('dark');
  if (window.__cutlineReady) return;
  window.__cutlineReady = true;

  // ---------- helpers ----------
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const bridge = (sel) => $(sel + ' textarea') || $(sel + ' input');
  const post = (sel, value) => {
    const ta = bridge(sel);
    if (!ta) return;
    ta.value = value + '|' + Date.now();          // timestamp so repeated actions always register
    ta.dispatchEvent(new Event('input', { bubbles: true }));
  };
  const setText = (el, t) => { if (el && el.textContent !== t) el.textContent = t; };
  const fmtSize = (n) => (n >= 1e6 ? (n / 1e6).toFixed(1) + ' MB' : Math.round(n / 1e3) + ' KB');
  const vis = (el) => !!(el && el.isConnected && el.offsetParent);

  // ---------- right-hand panel: preview (Space) and compare ----------
  let hover = null, lastActive = null, current = null;
  const panel = () => $('#pv-panel');
  const pvOpen = () => document.body.classList.contains('pv-open');
  const clearPreviewing = () => $$('.previewing').forEach((x) => x.classList.remove('previewing'));
  const setOpen = (on) => {
    document.body.classList.toggle('pv-open', on);
    if (!on) {
      clearPreviewing();
      window.__pvWant = null;
      const p = panel();
      if (p) p.classList.remove('loading');
    }
  };
  const want = (key) => {
    window.__pvWant = key;
    const p = panel();
    if (p) p.classList.add('loading');
  };
  const isFrame = (el) => el.classList.contains('sb-frame');
  const cardsOf = (el) => $$(isFrame(el) ? '#sb-grid .sb-frame' : '#dup-scroll .dp-card');
  const requestPreview = (el) => {
    if (!vis(el)) return;
    const list = cardsOf(el);
    const key = (isFrame(el) ? 'story' : 'dup') + ':' + el.dataset.idx + ':' + (list.indexOf(el) + 1) + ':' + list.length;
    clearPreviewing();
    el.classList.add('previewing');
    current = el;
    want(key);
    post('#preview-bridge', key);
  };
  const requestCompare = (g, a, b) => {
    clearPreviewing();
    want('cmp:' + g + ':' + a + ':' + b);
    post('#compare-bridge', JSON.stringify({ g: g, a: a, b: b }));
    setOpen(true);
  };
  const compareGroup = (group, prefer) => {
    if (!group) return;
    const cards = Array.from(group.querySelectorAll('.dp-card'));
    if (cards.length < 2) return;
    const b = prefer && prefer !== cards[0] ? prefer : cards[1];
    requestCompare(Number(group.dataset.g), Number(cards[0].dataset.idx), Number(b.dataset.idx));
  };

  document.addEventListener('mouseover', (e) => {
    const el = e.target.closest ? e.target.closest('.sb-frame, .dp-card') : null;
    if (el) hover = el;
  });
  document.addEventListener('mouseout', (e) => {
    const el = e.target.closest ? e.target.closest('.sb-frame, .dp-card') : null;
    if (el && hover === el && !el.contains(e.relatedTarget)) hover = null;
  });

  // compare slider: drag on the image, or use the range input underneath
  let sliding = null;
  const setPos = (stage, clientX) => {
    const r = stage.getBoundingClientRect();
    const p = Math.min(100, Math.max(0, ((clientX - r.left) / r.width) * 100));
    stage.style.setProperty('--pos', p + '%');
    const rg = stage.parentElement.querySelector('.cmp-range');
    if (rg) rg.value = Math.round(p);
  };
  document.addEventListener('pointerdown', (e) => {
    const st = e.target.closest ? e.target.closest('.cmp-stage') : null;
    if (!st) return;
    sliding = st;
    setPos(st, e.clientX);
    e.preventDefault();
  });
  document.addEventListener('pointermove', (e) => { if (sliding) setPos(sliding, e.clientX); });
  document.addEventListener('pointerup', () => { sliding = null; });

  // ---------- storyboard multi-select ----------
  let anchor = null;
  const grid = () => $('#sb-grid');
  const frames = (g) => Array.from((g || grid() || document).querySelectorAll('.sb-frame'));
  const selectedFrames = () => frames().filter((f) => f.classList.contains('sel'));
  const clearSel = () => selectedFrames().forEach((f) => f.classList.remove('sel'));

  const frameClick = (e, f) => {
    if (e.shiftKey && anchor && anchor.isConnected) {
      const list = frames();
      const a = list.indexOf(anchor), b = list.indexOf(f);
      if (!e.ctrlKey && !e.metaKey) clearSel();
      list.slice(Math.min(a, b), Math.max(a, b) + 1).forEach((x) => x.classList.add('sel'));
    } else if (e.ctrlKey || e.metaKey) {
      f.classList.toggle('sel');
      anchor = f;
    } else {
      clearSel();
      f.classList.add('sel');
      anchor = f;
    }
    lastActive = f;
    if (pvOpen() && !String(window.__pvWant || '').startsWith('cmp')) requestPreview(f);
  };

  // ---------- live status (thumbnail sliders, mode, duplicate counts, panel offset) ----------
  const syncUi = () => {
    const mode = window.__mode || 'copy';
    $$('.sb-mode').forEach((b) => b.classList.toggle('active', b.dataset.mode === mode));
    const v = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--thumb'), 10);
    $$('.thumb-slider').forEach((sl) => { if (v && parseInt(sl.value, 10) !== v) sl.value = v; });
    const marked = $$('#dup-scroll .dp-card.del');
    let size = 0;
    marked.forEach((c) => { size += Number(c.dataset.size) || 0; });
    setText($('#dp-count'), marked.length ? marked.length + ' files marked \u00b7 frees ' + fmtSize(size) : 'Nothing marked');
    const del = $('[data-act="dup-delete"]');
    if (del) {
      setText(del, marked.length ? 'Move ' + marked.length + ' to Recycle Bin' : 'Move to Recycle Bin');
      if (del.disabled !== (marked.length === 0)) del.disabled = marked.length === 0;
    }
    const p = panel(), inner = $('#pv-panel .pv-inner');
    if (p && window.__pvWant && inner && inner.dataset.key === window.__pvWant) p.classList.remove('loading');
    const tb = $('#tabbar');
    if (tb) {
      const top = Math.round(tb.getBoundingClientRect().bottom) + 'px';
      if (window.__pvTop !== top) { window.__pvTop = top; document.documentElement.style.setProperty('--pv-top', top); }
    }
  };

  document.addEventListener('input', (e) => {
    const t = e.target;
    if (!t || !t.classList) return;
    if (t.classList.contains('thumb-slider')) {
      document.documentElement.style.setProperty('--thumb', t.value + 'px');
      syncUi();
    } else if (t.classList.contains('cmp-range')) {
      const st = t.parentElement.querySelector('.cmp-stage');
      if (st) st.style.setProperty('--pos', t.value + '%');
    }
  });

  // ---------- clicks ----------
  document.addEventListener('click', (e) => {
    const t = e.target;
    if (!t || !t.closest) return;

    const b = t.closest('[data-act], [data-mode]');
    if (b && !b.disabled) {
      if (b.dataset.mode) { window.__mode = b.dataset.mode; syncUi(); return; }
      const act = b.dataset.act;
      if (act === 'pv-close') { setOpen(false); return; }
      if (act === 'compare') { compareGroup(b.closest('.dp-group'), null); return; }
      if (act === 'cmp-a' || act === 'cmp-b') {
        const root = $('#pv-panel .cmp-root');
        if (!root) return;
        let a = Number(root.dataset.a), c = Number(root.dataset.b);
        const idx = Number(b.dataset.idx);
        if (act === 'cmp-a') { if (idx === c) c = a; a = idx; } else { if (idx === a) a = c; c = idx; }
        requestCompare(Number(root.dataset.g), a, c);
        return;
      }
      if (act === 'reverse' || act === 'undo') post('#action-bridge', act);
      if (act === 'apply') post('#apply-bridge', window.__mode || 'copy');
      if (act === 'dup-reset') {
        $$('#dup-scroll .dp-card').forEach((c) => {
          const del = c.dataset.def === 'del';
          c.classList.toggle('del', del);
          c.querySelector('.dp-badge').textContent = del ? 'DELETE' : 'KEEP';
        });
        syncUi();
      }
      if (act === 'dup-delete') {
        const idx = $$('#dup-scroll .dp-card.del').map((c) => Number(c.dataset.idx));
        if (idx.length) post('#del-bridge', JSON.stringify(idx));
      }
      return;
    }

    const card = t.closest('.dp-card');
    if (card) {
      lastActive = card;
      const group = card.closest('.dp-group');
      const badge = card.querySelector('.dp-badge');
      if (!card.classList.contains('del')) {
        if (group.querySelectorAll('.dp-card:not(.del)').length <= 1) {   // always keep one copy
          card.classList.add('nope');
          setTimeout(() => card.classList.remove('nope'), 500);
          return;
        }
        card.classList.add('del');
        badge.textContent = 'DELETE';
      } else {
        card.classList.remove('del');
        badge.textContent = 'KEEP';
      }
      syncUi();
      if (pvOpen() && !String(window.__pvWant || '').startsWith('cmp')) requestPreview(card);
      return;
    }

    const f = t.closest('.sb-frame');
    if (f) { frameClick(e, f); return; }
    if (t.closest('#sb-scroll')) clearSel();            // click on empty space clears the selection
  });

  // ---------- keyboard ----------
  document.addEventListener('keydown', (e) => {
    const tg = e.target;
    if (tg && (/^(INPUT|TEXTAREA|SELECT)$/.test(tg.tagName) || tg.isContentEditable)) return;
    const open = pvOpen();
    const previewing = open && !String(window.__pvWant || '').startsWith('cmp');

    if (e.code === 'Space') {
      if (tg && tg.closest && tg.closest('button')) return;
      if (open) { e.preventDefault(); setOpen(false); return; }
      const el = vis(hover) ? hover : (vis(lastActive) ? lastActive : null);
      if (el) { e.preventDefault(); setOpen(true); requestPreview(el); }
    } else if (e.key === 'Escape') {
      if (open) setOpen(false);
      else clearSel();
    } else if (previewing && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) {
      const list = current && vis(current) ? cardsOf(current) : [];
      const n = list[list.indexOf(current) + (e.key === 'ArrowRight' ? 1 : -1)];
      if (n) {
        e.preventDefault();
        n.scrollIntoView({ block: 'nearest' });
        lastActive = n;
        if (isFrame(n)) { clearSel(); n.classList.add('sel'); anchor = n; }
        requestPreview(n);
      }
    } else if ((e.key === 'c' || e.key === 'C') && !e.ctrlKey && !e.metaKey) {
      if (vis(hover) && hover.classList.contains('dp-card')) {
        e.preventDefault();
        compareGroup(hover.closest('.dp-group'), hover);
      }
    } else if ((e.ctrlKey || e.metaKey) && (e.key === 'a' || e.key === 'A')) {
      if (vis(grid())) { e.preventDefault(); frames().forEach((f) => f.classList.add('sel')); }
    }
  });

  // ---------- size the working area to the real window height ----------
  const layout = () => {
    const vh = window.innerHeight;
    const narrow = window.innerWidth < 900;
    $$('.page').forEach((pg) => {
      if (!pg.offsetParent) return;
      const h = narrow ? 'auto' : Math.max(320, vh - pg.getBoundingClientRect().top - 8) + 'px';
      if (pg.style.height !== h) pg.style.height = h;
    });
    [['#sb-scroll', '#sb-bottom'], ['#dup-scroll', '#dp-bottom']].forEach(([s, b]) => {
      const sc = $(s);
      if (!sc || !sc.offsetParent) return;
      const bar = $(b);
      const bh = bar ? bar.offsetHeight : 0;
      const h = narrow ? '60vh' : Math.max(160, vh - sc.getBoundingClientRect().top - bh - 24) + 'px';
      if (sc.style.height !== h) sc.style.height = h;
    });
  };
  const tick = () => { layout(); syncUi(); };
  window.addEventListener('resize', tick);
  new MutationObserver(() => requestAnimationFrame(tick)).observe(document.body, { childList: true, subtree: true });
  setInterval(tick, 500);
  tick();

  // ---------- drag and drop (storyboard, moves every selected frame together) ----------
  let dragSet = [];
  const frameOf = (t) => (t && t.closest) ? t.closest('.sb-frame') : null;
  const gridOf = (t) => (t && t.closest) ? t.closest('#sb-grid') : null;
  const clearOver = () => $$('.sb-frame.over').forEach((x) => x.classList.remove('over'));
  const renumber = (g) => frames(g).forEach((f, i) => {
    f.querySelector('.sb-num').textContent = String(i + 1).padStart(3, '0');
  });
  const send = (g) => {
    const ta = bridge('#order-bridge');
    if (!ta) return;
    ta.value = frames(g).map((f) => f.dataset.idx).join(',');
    ta.dispatchEvent(new Event('input', { bubbles: true }));
  };
  const endDrag = () => {
    dragSet.forEach((f) => f.classList.remove('dragging'));
    dragSet = [];
    clearOver();
  };

  document.addEventListener('dragstart', (e) => {
    const f = frameOf(e.target);
    if (!f) return;
    if (!f.classList.contains('sel')) { clearSel(); f.classList.add('sel'); anchor = f; }
    dragSet = selectedFrames();                          // DOM order
    dragSet.forEach((x) => x.classList.add('dragging'));
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', f.dataset.idx);
    if (dragSet.length > 1) {
      const ghost = document.createElement('div');
      ghost.className = 'drag-ghost';
      ghost.textContent = dragSet.length + ' frames';
      document.body.appendChild(ghost);
      e.dataTransfer.setDragImage(ghost, 20, 20);
      setTimeout(() => ghost.remove(), 0);
    }
  });
  document.addEventListener('dragend', endDrag);
  document.addEventListener('dragover', (e) => {
    if (!dragSet.length) return;
    const g = gridOf(e.target);
    if (!g) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    clearOver();
    const f = frameOf(e.target);
    if (f && !dragSet.includes(f)) f.classList.add('over');
    const sc = $('#sb-scroll');
    if (sc) {
      const r = sc.getBoundingClientRect();
      if (e.clientY < r.top + 60) sc.scrollTop -= 18;
      else if (e.clientY > r.bottom - 60) sc.scrollTop += 18;
    }
  });
  document.addEventListener('drop', (e) => {
    if (!dragSet.length) return;
    const g = gridOf(e.target);
    if (!g) return;
    e.preventDefault();
    const target = frameOf(e.target);
    if (target && dragSet.includes(target)) { endDrag(); return; }
    const before = frames(g).map((f) => f.dataset.idx).join(',');
    const moved = dragSet.slice();
    if (target) {
      const kids = frames(g);
      const forward = kids.indexOf(moved[0]) < kids.indexOf(target);
      const frag = document.createDocumentFragment();
      moved.forEach((x) => frag.appendChild(x));
      if (forward) target.after(frag); else target.before(frag);
    } else {
      moved.forEach((x) => g.appendChild(x));
    }
    endDrag();
    renumber(g);
    moved.forEach((x) => x.classList.add('dropped'));
    setTimeout(() => moved.forEach((x) => x.classList.remove('dropped')), 700);
    if (frames(g).map((f) => f.dataset.idx).join(',') !== before) send(g);
  });
}
