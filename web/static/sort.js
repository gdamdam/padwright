// Click-to-sort for any <table class="sortable"> with a <thead>.
// Cell sort key: data-sort attr if present (parsed as number when numeric),
// otherwise textContent. Click toggles asc/desc; arrow shows current state.
// Sort is persisted per-table via localStorage so it survives navigation.

(function () {
  function cellKey(td) {
    const raw = td.dataset.sort ?? td.textContent.trim();
    const num = parseFloat(raw);
    return (!isNaN(num) && raw.match(/^-?\d/)) ? num : raw.toLowerCase();
  }

  function applySort(table, colIdx, dir) {
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const rows = Array.from(tbody.rows);
    rows.sort((a, b) => {
      const ka = cellKey(a.cells[colIdx]);
      const kb = cellKey(b.cells[colIdx]);
      if (ka < kb) return -dir;
      if (ka > kb) return dir;
      return 0;
    });
    for (const r of rows) tbody.appendChild(r);

    // Update header arrows.
    for (const th of table.tHead.rows[0].cells) {
      th.classList.remove('sort-asc', 'sort-desc');
    }
    const th = table.tHead.rows[0].cells[colIdx];
    th.classList.add(dir > 0 ? 'sort-asc' : 'sort-desc');
  }

  function init(table) {
    const id = table.id || table.className;
    const key = `sort:${location.pathname}:${id}`;
    const saved = JSON.parse(localStorage.getItem(key) || 'null');

    for (const [i, th] of Array.from(table.tHead.rows[0].cells).entries()) {
      if (th.dataset.nosort !== undefined) continue;
      th.classList.add('sortable-th');
      th.addEventListener('click', () => {
        const cur = th.classList.contains('sort-asc') ? 1
                  : th.classList.contains('sort-desc') ? -1 : 0;
        const dir = cur === 1 ? -1 : 1;
        applySort(table, i, dir);
        localStorage.setItem(key, JSON.stringify({ col: i, dir }));
      });
    }
    if (saved) applySort(table, saved.col, saved.dir);
  }

  document.querySelectorAll('table.sortable').forEach(init);
})();
