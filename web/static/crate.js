// Crate editor: sample browser + drag-to-pad + form serialization.

const browserEl = document.getElementById('samples-browser');
const formEl = document.getElementById('crateForm');
const padJsonEl = document.getElementById('pad_json');

// ── Sample browser ────────────────────────────────────────────────────────
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
    parts.push(`<li class="folder" data-go="${escapeAttr(data.parent)}">⬑ up</li>`);
  }
  for (const f of data.folders) {
    const path = data.cwd ? `${data.cwd}/${f}` : f;
    parts.push(`<li class="folder" data-go="${escapeAttr(path)}">📁 ${escapeHtml(f)}</li>`);
  }
  for (const f of data.files) {
    parts.push(`
      <li draggable="true" data-abs="${escapeAttr(f.abs)}">
        <span class="fn">${escapeHtml(f.name)}</span>
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

// ── Drag onto pad ─────────────────────────────────────────────────────────
document.querySelectorAll('td.pad').forEach(td => {
  td.addEventListener('dragover', ev => {
    ev.preventDefault();
    td.classList.add('dragover');
  });
  td.addEventListener('dragleave', () => td.classList.remove('dragover'));
  td.addEventListener('drop', ev => {
    ev.preventDefault();
    td.classList.remove('dragover');
    const path = ev.dataTransfer.getData('text/plain');
    const input = td.querySelector('.src-input');
    if (input) input.value = path;
  });
});

// ── Clear buttons ────────────────────────────────────────────────────────
document.querySelectorAll('.clearbtn').forEach(btn => {
  btn.addEventListener('click', () => {
    const pad = btn.dataset.pad;
    document.querySelector(`.src-input[data-pad="${pad}"]`).value = '';
  });
});

// ── Serialize form ────────────────────────────────────────────────────────
formEl.addEventListener('submit', ev => {
  const specs = [];
  document.querySelectorAll('.src-input').forEach(input => {
    const pad = parseInt(input.dataset.pad, 10);
    const source = input.value.trim();
    const typeInput = document.querySelector(`.type-input[data-pad="${pad}"]`);
    const type = typeInput ? typeInput.value.trim() : '';
    if (source || type) {
      specs.push({pad, source: source || null, type: type || null});
    }
  });
  padJsonEl.value = JSON.stringify(specs);
});

// ── Helpers ───────────────────────────────────────────────────────────────
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}
function escapeAttr(s) { return escapeHtml(s); }
