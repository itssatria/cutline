() => {
  // Default theme is always dark.
  document.body.classList.add('dark');
  if (window.__cutlineReady) return;
  window.__cutlineReady = true;

  // ---------- helpers ----------
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const on = (type, fn, opts) => document.addEventListener(type, function () {
    try { return fn.apply(this, arguments); } catch (err) { console.error('[Cutline]', err); }
  }, opts);
  const bridge = (sel) => $(sel + ' textarea') || $(sel + ' input');
  const post = (sel, value) => {
    const ta = bridge(sel);
    if (!ta) { console.warn('[Cutline] bridge not found:', sel); return; }
    ta.value = value + '|' + Date.now();          // timestamp so repeated actions always register
    ta.dispatchEvent(new Event('input', { bubbles: true }));
  };
  const setText = (el, t) => { if (el && el.textContent !== t) el.textContent = t; };
  const fmtSize = (n) => (n >= 1e6 ? (n / 1e6).toFixed(1) + ' MB' : Math.round(n / 1e3) + ' KB');
  const vis = (el) => !!(el && el.isConnected && el.offsetParent);
  const vars = {};
  const setVar = (name, v) => {
    if (vars[name] !== v) { vars[name] = v; document.documentElement.style.setProperty(name, v); }
  };
  const FAVICON = '__FAVICON__';
  const ITEM = '.sb-frame, .dp-card, .am-row';
  const isFrame = (el) => el.classList.contains('sb-frame');
  const isDupCard = (el) => el.classList.contains('dp-card');
  const itemsOf = (el) => $$(isDupCard(el) ? '#dup-scroll .dp-card' : (el.classList.contains('am-row') ? '#am-scroll .am-row' : '#sb-grid .sb-frame'));

  // ---------- right-hand preview / compare panel (owned by this script) ----------
  const PV_EMPTY = '<div class="pv-inner" data-key=""><div class="pv-head"><b class="pv-title">Preview</b>' +
    '<button type="button" class="pv-close" data-act="pv-close" aria-label="Close panel">\u2715</button></div>' +
    '<div class="pv-empty">Hover an image and press Space (or double-click it).<br>On the Duplicates tab, press C to compare.</div></div>';
  const panel = () => {
    let p = $('#cutline-pv');
    if (!p) {
      p = document.createElement('div');
      p.id = 'cutline-pv';
      p.innerHTML = PV_EMPTY;
      document.body.appendChild(p);
    }
    return p;
  };
  const pvKey = () => { const i = panel().querySelector('.pv-inner'); return i ? i.dataset.key : ''; };
  const pvOpen = () => document.body.classList.contains('pv-open');
  const wantsCompare = () => String(window.__pvWant || '').startsWith('cmp');
  let current = null, lastActive = null, mx = 0, my = 0;
  const clearPreviewing = () => $$('.previewing').forEach((x) => x.classList.remove('previewing'));
  const setOpen = (on) => {
    panel();
    document.body.classList.toggle('pv-open', on);
    if (!on) { clearPreviewing(); window.__pvWant = null; panel().classList.remove('loading'); }
  };
  const want = (key) => {
    const p = panel();
    window.__pvWant = key;
    p.classList.remove('pv-error');
    if (pvKey() !== key) p.classList.add('loading'); else p.classList.remove('loading');
    clearTimeout(window.__pvTimer);
    window.__pvTimer = setTimeout(() => {          // no answer from Python: say so instead of hanging
      if (window.__pvWant === key && pvKey() !== key) {
        p.classList.remove('loading');
        p.classList.add('pv-error');
        const t = p.querySelector('.pv-title');
        if (t) t.textContent = 'Could not load this image (see the terminal for the error)';
      }
    }, 12000);
  };
  const requestPreview = (el) => {
    if (!vis(el)) return;
    const list = itemsOf(el);
    const key = (isDupCard(el) ? 'dup' : 'story') + ':' + el.dataset.idx + ':' + (list.indexOf(el) + 1) + ':' + list.length;
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
  const openPreview = (el) => { setOpen(true); requestPreview(el); };
  const syncPanel = () => {                         // copy Python's answer (hidden #pv-data) into the panel
    const p = panel();
    const src = $('#pv-data .pv-inner');
    if (src && src.dataset.key && window.__pvWant && src.dataset.key === window.__pvWant && pvKey() !== src.dataset.key) {
      p.innerHTML = src.outerHTML;
    }
    if (window.__pvWant && pvKey() === window.__pvWant) p.classList.remove('loading');
  };

  const itemUnderMouse = () => {
    const e = document.elementFromPoint(mx, my);
    return e && e.closest ? e.closest(ITEM) : null;
  };
  on('mousemove', (e) => { mx = e.clientX; my = e.clientY; }, { passive: true });

  // compare slider: drag on the image, or use the range input underneath
  let sliding = null;
  const setPos = (stage, clientX) => {
    const r = stage.getBoundingClientRect();
    const p = Math.min(100, Math.max(0, ((clientX - r.left) / r.width) * 100));
    stage.style.setProperty('--pos', p + '%');
    const rg = stage.parentElement.querySelector('.cmp-range');
    if (rg) rg.value = Math.round(p);
  };
  on('pointerdown', (e) => {
    const st = e.target.closest ? e.target.closest('.cmp-stage') : null;
    if (!st) return;
    sliding = st;
    setPos(st, e.clientX);
    e.preventDefault();
  });
  on('pointermove', (e) => { if (sliding) setPos(sliding, e.clientX); });
  on('pointerup', () => { sliding = null; });

  // ---------- storyboard: multi-select and pinned (locked) frames ----------
  let anchor = null;
  const grid = () => $('#sb-grid');
  const frames = (g) => Array.from((g || grid() || document).querySelectorAll('.sb-frame'));
  const selectedFrames = () => frames().filter((f) => f.classList.contains('sel'));
  const clearSel = () => selectedFrames().forEach((f) => f.classList.remove('sel'));
  const sendLocks = () => post('#lock-bridge', JSON.stringify(
    frames().filter((f) => f.classList.contains('locked')).map((f) => Number(f.dataset.idx))));

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
    if (pvOpen() && !wantsCompare()) requestPreview(f);
  };
  const lockSelected = () => {
    const sel = selectedFrames();
    if (!sel.length) return;
    const allLocked = sel.every((f) => f.classList.contains('locked'));
    sel.forEach((f) => f.classList.toggle('locked', !allLocked));
    sendLocks();
  };

  // ---------- animatic ----------
  const amSnapshot = () => {
    const t = {};
    $$('#am-scroll .am-ta').forEach((ta) => { t[ta.dataset.idx] = ta.value; });
    return t;
  };
  const amPost = (act, idx) => {
    const secs = Number(($('.am-secs') || {}).value) || 3;
    post('#am-bridge', JSON.stringify({ act: act, i: idx === undefined ? null : idx, secs: secs, texts: amSnapshot() }));
  };

  // ---------- live status ----------
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
    const info = $('#am-info');
    if (info) {
      const n = $$('#am-scroll .am-row').length;
      const secs = Number(($('.am-secs') || {}).value) || 3;
      const total = Math.round(n * secs);
      setText(info, n + ' frames \u00b7 ' + secs + ' s each \u00b7 ' + Math.floor(total / 60) + ':' + String(total % 60).padStart(2, '0') + ' total');
    }
    syncPanel();
  };

  on('input', (e) => {
    const t = e.target;
    if (!t || !t.classList) return;
    if (t.classList.contains('thumb-slider')) {
      setVar('--thumb', t.value + 'px');
      document.documentElement.style.setProperty('--thumb', t.value + 'px');
      syncUi();
    } else if (t.classList.contains('cmp-range')) {
      const st = t.parentElement.querySelector('.cmp-stage');
      if (st) st.style.setProperty('--pos', t.value + '%');
    } else if (t.classList.contains('am-secs')) {
      syncUi();
    }
  });
  on('change', (e) => {                              // keep typed story text in Python
    if (e.target && e.target.classList && e.target.classList.contains('am-ta')) amPost('save');
  });

  // ---------- clicks ----------
  on('click', (e) => {
    const t = e.target;
    if (!t || !t.closest) return;

    const b = t.closest('[data-act], [data-mode]');
    if (b && !b.disabled) {
      if (b.dataset.mode) { window.__mode = b.dataset.mode; syncUi(); return; }
      const act = b.dataset.act;
      switch (act) {
        case 'pv-close': setOpen(false); return;
        case 'toggle-side': document.body.classList.toggle('side-hidden'); return;
        case 'theme': document.body.classList.toggle('dark'); return;
        case 'ft-check':
          post('#ft-bridge', 'check');
          b.classList.add('busy');
          setTimeout(() => b.classList.remove('busy'), 6000);
          return;
        case 'ft-about': post('#ft-bridge', 'about'); return;
        case 'compare': compareGroup(b.closest('.dp-group'), null); return;
        case 'cmp-a':
        case 'cmp-b': {
          const root = $('#cutline-pv .cmp-root');
          if (!root) return;
          let a = Number(root.dataset.a), c = Number(root.dataset.b);
          const idx = Number(b.dataset.idx);
          if (act === 'cmp-a') { if (idx === c) c = a; a = idx; } else { if (idx === a) a = c; c = idx; }
          requestCompare(Number(root.dataset.g), a, c);
          return;
        }
        case 'sort': post('#sort-bridge', 'go'); return;
        case 'scan': post('#scan-bridge', 'go'); return;
        case 'reverse':
        case 'undo': post('#action-bridge', act); return;
        case 'apply': post('#apply-bridge', window.__mode || 'copy'); return;
        case 'lock': { const f = b.closest('.sb-frame'); if (f) { f.classList.toggle('locked'); sendLocks(); } return; }
        case 'lock-sel': lockSelected(); return;
        case 'pin-ends': {
          const list = frames();
          if (list.length) { list[0].classList.add('locked'); list[list.length - 1].classList.add('locked'); sendLocks(); }
          return;
        }
        case 'unlock-all': frames().forEach((f) => f.classList.remove('locked')); sendLocks(); return;
        case 'am-gen': amPost('gen'); return;
        case 'am-fill': amPost('fill'); return;
        case 'am-export': amPost('export'); return;
        case 'am-regen': amPost('regen', Number(b.dataset.idx)); return;
        case 'dup-reset':
          $$('#dup-scroll .dp-card').forEach((c) => {
            const d = c.dataset.def === 'del';
            c.classList.toggle('del', d);
            c.querySelector('.dp-badge').textContent = d ? 'DELETE' : 'KEEP';
          });
          syncUi();
          return;
        case 'dup-delete': {
          const idx = $$('#dup-scroll .dp-card.del').map((c) => Number(c.dataset.idx));
          if (idx.length) post('#del-bridge', JSON.stringify(idx));
          return;
        }
        default: return;
      }
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
      if (pvOpen() && !wantsCompare()) requestPreview(card);
      return;
    }

    const f = t.closest('.sb-frame');
    if (f) { frameClick(e, f); return; }
    const row = t.closest('.am-row');
    if (row) { lastActive = row; if (pvOpen() && !wantsCompare() && !/^(TEXTAREA|BUTTON)$/.test(t.tagName)) requestPreview(row); return; }
    if (t.closest('#sb-scroll')) clearSel();            // click on empty space clears the selection
  });

  on('dblclick', (e) => {                              // double-click = full preview
    const t = e.target;
    if (!t || !t.closest || t.closest('[data-act], textarea')) return;
    const el = t.closest(ITEM);
    if (el) { e.preventDefault(); openPreview(el); }
  });

  // ---------- keyboard ----------
  on('keydown', (e) => {
    const tg = e.target;
    if (tg && (/^(INPUT|TEXTAREA|SELECT)$/.test(tg.tagName) || tg.isContentEditable)) return;
    const open = pvOpen();
    const previewing = open && !wantsCompare();
    const item = itemUnderMouse();

    if (e.code === 'Space') {
      const onButton = tg && tg.closest && tg.closest('button');
      if (onButton && !item && !open) return;          // a focused button keeps its normal Space behaviour
      if (open) { e.preventDefault(); setOpen(false); return; }
      const el = item || (vis(lastActive) ? lastActive : null);
      if (el) {
        e.preventDefault();
        if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();
        openPreview(el);
      }
    } else if (e.key === 'Escape') {
      if (open) setOpen(false); else clearSel();
    } else if (previewing && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) {
      const list = current && vis(current) ? itemsOf(current) : [];
      const n = list[list.indexOf(current) + (e.key === 'ArrowRight' ? 1 : -1)];
      if (n) {
        e.preventDefault();
        n.scrollIntoView({ block: 'nearest' });
        lastActive = n;
        if (isFrame(n)) { clearSel(); n.classList.add('sel'); anchor = n; }
        requestPreview(n);
      }
    } else if ((e.key === 'c' || e.key === 'C') && !e.ctrlKey && !e.metaKey) {
      if (item && isDupCard(item)) { e.preventDefault(); compareGroup(item.closest('.dp-group'), item); }
    } else if ((e.key === 'l' || e.key === 'L') && !e.ctrlKey && !e.metaKey) {
      if (vis(grid())) { e.preventDefault(); lockSelected(); }
    } else if ((e.ctrlKey || e.metaKey) && (e.key === 'a' || e.key === 'A')) {
      if (vis(grid())) { e.preventDefault(); frames().forEach((f) => f.classList.add('sel')); }
    }
  });

  // ---------- layout: pin the gallery panel under the header, fit its scroll area to the window ----------
  const layout = () => {
    const vh = window.innerHeight;
    const narrow = window.innerWidth < 900;
    const hdr = $('#app-header'), tb = $('#tabbar'), ft = $('#app-footer');
    const hh = hdr ? hdr.offsetHeight : 0;
    const th = tb ? tb.offsetHeight : 0;
    const fh = ft && !narrow ? ft.offsetHeight : 0;
    setVar('--hdr-h', hh + 'px');
    setVar('--tab-h', th + 'px');
    setVar('--ft-h', fh + 'px');
    setVar('--pv-top', (narrow ? 0 : hh + th) + 'px');
    const avail = Math.max(300, vh - hh - th - fh - 24);
    setVar('--avail', avail + 'px');
    $$('.page .mainc').forEach((m) => {
      if (!m.offsetParent) return;
      const h = narrow ? 'auto' : avail + 'px';
      if (m.style.height !== h) m.style.height = h;
      const sc = m.querySelector('[data-scroll]');
      if (!sc) return;
      const tbar = m.querySelector('.sb-toolbar'), bar = m.querySelector('.sb-bottom');
      const sh = narrow ? '60vh' : Math.max(140, avail - (tbar ? tbar.offsetHeight : 0) - (bar ? bar.offsetHeight : 0) - 6) + 'px';
      if (sc.style.height !== sh) sc.style.height = sh;
    });
  };
  const fixHead = () => {                          // always show the Cutline logo as the tab icon
    let ours = $('#cutline-icon');
    if (!ours && FAVICON.indexOf('data:') === 0) {
      ours = document.createElement('link');
      ours.id = 'cutline-icon';
      ours.rel = 'icon';
      ours.type = 'image/png';
      ours.href = FAVICON;
      document.head.appendChild(ours);
    }
    $$('link[rel~="icon"]').forEach((l) => { if (l !== ours) l.remove(); });
    if (document.title !== 'Cutline') document.title = 'Cutline';
  };
  const tick = () => { layout(); syncUi(); fixHead(); };
  window.addEventListener('resize', tick);
  new MutationObserver(() => requestAnimationFrame(tick)).observe(document.body, { childList: true, subtree: true });
  setInterval(tick, 500);
  panel();
  tick();

  // ---------- drag and drop (storyboard, moves every selected frame together) ----------
  let dragSet = [];
  const frameOf = (t) => (t && t.closest) ? t.closest('.sb-frame') : null;
  const gridOf = (t) => (t && t.closest) ? t.closest('#sb-grid') : null;
  const clearOver = () => $$('.sb-frame.over').forEach((x) => x.classList.remove('over'));
  const renumber = (g) => frames(g).forEach((f, i) => {
    f.querySelector('.sb-num').textContent = String(i + 1).padStart(3, '0');
  });
  const sendOrder = (g) => {
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

  on('dragstart', (e) => {
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
  on('dragend', endDrag);
  on('dragover', (e) => {
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
  on('drop', (e) => {
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
    if (frames(g).map((f) => f.dataset.idx).join(',') !== before) sendOrder(g);
  });
}
