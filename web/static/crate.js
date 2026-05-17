// Crate editor — sample browser + drag-to-pad + form serialization.

const browserEl = document.getElementById('samples-browser');
const formEl    = document.getElementById('crateForm');
const padJsonEl = document.getElementById('pad_json');

// ── Sample browser (folder tree, audition, drag handles) ────────────────────
async function loadFolder(cwd) {
  if (!browserEl) return;
  const r = await fetch('/api/samples?path=' + encodeURIComponent(cwd));
  if (!r.ok) {
    browserEl.textContent = 'error loading samples';
    return;
  }
  const data = await r.json();
  browserEl.dataset.cwd = cwd;
  renderFolder(data);
}

function renderFolder(data) {
  const parts = ['<ul class="files">'];
  if (data.parent !== null) {
    parts.push(`<li class="folder" data-go="${attr(data.parent)}">⬑ up</li>`);
  }
  for (const f of data.folders) {
    const path = data.cwd ? `${data.cwd}/${f}` : f;
    parts.push(`<li class="folder" data-go="${attr(path)}">📁 ${esc(f)}</li>`);
  }
  for (const f of data.files) {
    parts.push(`
      <li draggable="true" data-abs="${attr(f.abs)}">
        <span class="fn">${esc(f.name)}</span>
        <span class="sz">${(f.size / 1024).toFixed(1)} KB</span>
        <audio controls preload="none" src="/audio/sample?path=${encodeURIComponent(f.abs)}"></audio>
      </li>`);
  }
  parts.push('</ul>');
  browserEl.innerHTML = parts.join('');

  browserEl.querySelectorAll('li.folder').forEach(el =>
    el.addEventListener('click', () => loadFolder(el.dataset.go)));

  browserEl.querySelectorAll('li[draggable=true]').forEach(el => {
    el.addEventListener('dragstart', ev => {
      ev.dataTransfer.setData('text/plain', el.dataset.abs);
      ev.dataTransfer.effectAllowed = 'copy';
    });
  });
}

if (browserEl) loadFolder('');

// ── Pad assignment ──────────────────────────────────────────────────────────
function setPadSource(td, abs) {
  const input  = td.querySelector('.src-input');
  const disp   = td.querySelector('.src-display');
  const audio  = td.querySelector('.pad-audio');
  input.value  = abs || '';
  disp.title   = abs || '';
  disp.textContent = abs ? abs.split('/').pop() : '(drop here)';
  if (audio) {
    audio.src = abs ? '/audio/sample?path=' + encodeURIComponent(abs) : '';
    audio.load();
  }
  td.dataset.filled = abs ? '1' : '0';
}

document.querySelectorAll('td.crate-pad').forEach(td => {
  td.addEventListener('dragover', ev => {
    ev.preventDefault();
    td.classList.add('dragover');
  });
  td.addEventListener('dragleave', () => td.classList.remove('dragover'));
  td.addEventListener('drop', ev => {
    ev.preventDefault();
    td.classList.remove('dragover');
    const path = ev.dataTransfer.getData('text/plain');
    if (path) setPadSource(td, path);
  });
  // Sync color when type dropdown changes
  const typeSel = td.querySelector('.type-input');
  if (typeSel) {
    typeSel.addEventListener('change', () => {
      td.className = td.className.split(/\s+/)
        .filter(c => !c.startsWith('pad-')).join(' ');
      td.classList.add('pad-' + (typeSel.value || 'empty'));
    });
  }
});

document.querySelectorAll('.clearbtn').forEach(btn => {
  btn.addEventListener('click', () => {
    const td = btn.closest('td.crate-pad');
    if (td) setPadSource(td, '');
  });
});

// ── Form submit: serialize all pad inputs to a single JSON field ───────────
formEl.addEventListener('submit', ev => {
  const specs = [];
  document.querySelectorAll('.src-input').forEach(input => {
    const pad = parseInt(input.dataset.pad, 10);
    const source = input.value.trim();
    const typeSel = document.querySelector(`.type-input[data-pad="${pad}"]`);
    const type = typeSel ? typeSel.value.trim() : '';
    if (source || type) {
      specs.push({pad, source: source || null, type: type || null});
    }
  });
  padJsonEl.value = JSON.stringify(specs);
});

// ── Helpers ────────────────────────────────────────────────────────────────
function esc(s) {
  return s.replace(/[&<>"']/g, c =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}
function attr(s) { return esc(s); }
