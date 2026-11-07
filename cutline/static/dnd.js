() => {
  // Default theme is always dark.
  document.body.classList.add('dark');
  if (window.__cutlineReady) return;
  window.__cutlineReady = true;

  // ---------- helpers ----------
  const bridge = (sel) => document.querySelector(sel + ' textarea') || document.querySelector(sel + ' input');
  const post = (sel, value) => {
    const ta = bridge(sel);
    if (!ta) return;
    ta.value = value + '|' + Date.now();          // timestamp so repeated clicks always register
    ta.dispatchEvent(new Event('input', { bubbles: true }));
  };
  const setText = (el, t) => { if (el && el.textContent !== t) el.textContent = t; };
  const fmtSize = (n) => (n >= 1e6 ? (n / 1e6).toFixed(1) + ' MB' : Math.round(n / 1e3) + ' KB');

  const syncUi = () => {
    const mode = window.__mode || 'copy';
    document.querySelectorAll('.sb-mode').forEach((b) => b.classList.toggle('active', b.dataset.mode === mode));
    const v = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--thumb'), 10);
    document.querySelectorAll('.thumb-slider').forEach((sl) => {
      if (v && parseInt(sl.value, 10) !== v) sl.value = v;
    });
    // duplicates: live count + button label
    const marked = document.querySelectorAll('#dup-scroll .dp-card.del');
    let size = 0;
    marked.forEach((c) => { size += Number(c.dataset.size) || 0; });
    setText(document.querySelector('#dp-count'),
      marked.length ? marked.length + ' files marked \u00b7 frees ' + fmtSize(size) : 'Nothing marked');
    const del = document.querySelector('[data-act="dup-delete"]');
    if (del) {
      setText(del, marked.length ? 'Move ' + marked.length + ' to Recycle Bin' : 'Move to Recycle Bin');
      if (del.disabled !== (marked.length === 0)) del.disabled = marked.length === 0;
    }
  };

  document.addEventListener('input', (e) => {
    if (e.target && e.target.classList && e.target.classList.contains('thumb-slider')) {
      document.documentElement.style.setProperty('--thumb', e.target.value + 'px');
      syncUi();
    }
  });

  // ---------- clicks: duplicate cards, bottom-bar buttons ----------
  document.addEventListener('click', (e) => {
    const t = e.target;
    if (!t || !t.closest) return;
    const card = t.closest('.dp-card');
    if (card) {
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
      return;
    }
    const b = t.closest('.sb-btn');
    if (!b || b.disabled) return;
    if (b.dataset.mode) { window.__mode = b.dataset.mode; syncUi(); return; }
    const act = b.dataset.act;
    if (act === 'reverse' || act === 'undo') post('#action-bridge', act);
    if (act === 'apply') post('#apply-bridge', window.__mode || 'copy');
    if (act === 'dup-reset') {
      document.querySelectorAll('#dup-scroll .dp-card').forEach((c) => {
        const del = c.dataset.def === 'del';
        c.classList.toggle('del', del);
        c.querySelector('.dp-badge').textContent = del ? 'DELETE' : 'KEEP';
      });
      syncUi();
    }
    if (act === 'dup-delete') {
      const idx = Array.from(document.querySelectorAll('#dup-scroll .dp-card.del')).map((c) => Number(c.dataset.idx));
      if (idx.length) post('#del-bridge', JSON.stringify(idx));
    }
  });

  // ---------- size the working area to the real window height ----------
  const layout = () => {
    const vh = window.innerHeight;
    const narrow = window.innerWidth < 900;
    document.querySelectorAll('.page').forEach((pg) => {
      if (!pg.offsetParent) return;
      const h = narrow ? 'auto' : Math.max(320, vh - pg.getBoundingClientRect().top - 8) + 'px';
      if (pg.style.height !== h) pg.style.height = h;
    });
    [['#sb-scroll', '#sb-bottom'], ['#dup-scroll', '#dp-bottom']].forEach(([s, b]) => {
      const sc = document.querySelector(s);
      if (!sc || !sc.offsetParent) return;
      const bar = document.querySelector(b);
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

  // ---------- drag and drop (storyboard) ----------
  let dragEl = null;
  const frameOf = (t) => (t && t.closest) ? t.closest('.sb-frame') : null;
  const gridOf = (t) => (t && t.closest) ? t.closest('#sb-grid') : null;
  const clearOver = () => document.querySelectorAll('.sb-frame.over').forEach((x) => x.classList.remove('over'));
  const frames = (grid) => Array.from(grid.querySelectorAll('.sb-frame'));
  const renumber = (grid) => frames(grid).forEach((f, i) => {
    f.querySelector('.sb-num').textContent = String(i + 1).padStart(3, '0');
  });
  const send = (grid) => {
    const ta = bridge('#order-bridge');
    if (!ta) return;
    ta.value = frames(grid).map((f) => f.dataset.idx).join(',');
    ta.dispatchEvent(new Event('input', { bubbles: true }));
  };

  document.addEventListener('dragstart', (e) => {
    const f = frameOf(e.target);
    if (!f) return;
    dragEl = f;
    f.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', f.dataset.idx);
  });
  document.addEventListener('dragend', () => {
    if (dragEl) dragEl.classList.remove('dragging');
    dragEl = null;
    clearOver();
  });
  document.addEventListener('dragover', (e) => {
    if (!dragEl) return;
    const grid = gridOf(e.target);
    if (!grid) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    clearOver();
    const f = frameOf(e.target);
    if (f && f !== dragEl) f.classList.add('over');
    const sc = document.querySelector('#sb-scroll');
    if (sc) {
      const r = sc.getBoundingClientRect();
      if (e.clientY < r.top + 60) sc.scrollTop -= 18;
      else if (e.clientY > r.bottom - 60) sc.scrollTop += 18;
    }
  });
  document.addEventListener('drop', (e) => {
    if (!dragEl) return;
    const grid = gridOf(e.target);
    if (!grid) return;
    e.preventDefault();
    const before = frames(grid).map((f) => f.dataset.idx).join(',');
    const target = frameOf(e.target);
    if (target && target !== dragEl) {
      const kids = frames(grid);
      if (kids.indexOf(dragEl) < kids.indexOf(target)) target.after(dragEl);
      else target.before(dragEl);
    } else if (!target) {
      grid.appendChild(dragEl);
    }
    const moved = dragEl;
    clearOver();
    renumber(grid);
    moved.classList.remove('dragging');
    moved.classList.add('dropped');
    setTimeout(() => moved.classList.remove('dropped'), 700);
    if (frames(grid).map((f) => f.dataset.idx).join(',') !== before) send(grid);
    dragEl = null;
  });
}
