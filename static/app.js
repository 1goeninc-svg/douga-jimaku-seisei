'use strict';

const MAX_MB = 25;

const fileInput     = document.getElementById('file-input');
const dropzone      = document.getElementById('dropzone');
const filePill      = document.getElementById('file-pill');
const filePillName  = document.getElementById('file-pill-name');
const fileSizeEl    = document.getElementById('file-size');
const submitBtn     = document.getElementById('submit-btn');
const processCard   = document.getElementById('process-card');
const resultWrap    = document.getElementById('result-wrap');
const resultArea    = document.getElementById('result-area');

let selectedFile = null;

// ── ファイル選択 ──────────────────────────────────────
function onFileSelected(file) {
  const mb = file.size / 1024 / 1024;
  if (mb > MAX_MB) {
    alert(`ファイルが大きすぎます（${mb.toFixed(0)} MB）。\n${MAX_MB} MB 以下のファイルを選択してください。`);
    return;
  }
  selectedFile = file;
  filePillName.textContent = file.name;
  fileSizeEl.textContent   = mb.toFixed(1) + ' MB';
  filePill.hidden   = false;
  submitBtn.disabled = false;
}

function clearFile() {
  selectedFile = null;
  fileInput.value = '';
  filePill.hidden   = true;
  submitBtn.disabled = true;
}

fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) onFileSelected(fileInput.files[0]);
});
dropzone.addEventListener('click',   () => fileInput.click());
dropzone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });
dropzone.addEventListener('dragover',  e => { e.preventDefault(); dropzone.classList.add('drag-over'); });
dropzone.addEventListener('dragleave', ()  => dropzone.classList.remove('drag-over'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) onFileSelected(e.dataTransfer.files[0]);
});

// ── 処理開始 ──────────────────────────────────────────
function startProcess() {
  if (!selectedFile) return;

  submitBtn.disabled  = true;
  resultArea.value    = '';
  resultWrap.hidden   = true;
  processCard.hidden  = false;
  document.getElementById('process-filename').textContent = selectedFile.name;
  setStatus('processing', 'アップロード中…');

  const form = new FormData();
  form.append('audio', selectedFile);
  form.append('model', document.getElementById('model').value);
  form.append('lang',  document.getElementById('lang').value);

  const progressWrap  = document.getElementById('upload-progress');
  const progressFill  = document.getElementById('progress-fill');
  const progressLabel = document.getElementById('progress-label');
  progressWrap.hidden = false;

  const xhr = new XMLHttpRequest();

  xhr.upload.addEventListener('progress', e => {
    if (!e.lengthComputable) return;
    const pct = Math.round(e.loaded / e.total * 100);
    progressFill.style.width  = pct + '%';
    progressLabel.textContent = `アップロード中… ${pct}%`;
    if (pct === 100) {
      progressLabel.textContent = 'AI が文字起こし中…';
      setStatus('processing', 'AI が文字起こし中…');
    }
  });

  xhr.addEventListener('load', () => {
    progressWrap.hidden = true;
    if (xhr.status === 200) {
      const { text } = JSON.parse(xhr.responseText);
      resultArea.value  = text || '（テキストが認識されませんでした）';
      resultWrap.hidden = false;
      setStatus('done', '✅ 完了！');
    } else {
      let msg = 'エラーが発生しました';
      try { msg = JSON.parse(xhr.responseText).error || msg; } catch (_) {}
      setStatus('error', '❌ ' + msg);
    }
    submitBtn.disabled = false;
  });

  xhr.addEventListener('error', () => {
    progressWrap.hidden = true;
    setStatus('error', '❌ ネットワークエラーが発生しました');
    submitBtn.disabled = false;
  });

  xhr.open('POST', '/transcribe');
  xhr.send(form);
}

// ── コピー ────────────────────────────────────────────
function copyResult() {
  if (!resultArea.value) return;
  navigator.clipboard.writeText(resultArea.value).then(() => {
    const btn = document.getElementById('copy-btn');
    btn.textContent = 'コピーしました！';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'コピー'; btn.classList.remove('copied'); }, 2000);
  });
}

// ── ステータスバッジ ──────────────────────────────────
function setStatus(type, text) {
  const badge   = document.getElementById('status-badge');
  const spinner = type === 'processing' ? '<span class="spinner"></span>' : '';
  badge.innerHTML = `<span class="badge badge-${type}">${spinner}${escHtml(text)}</span>`;
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
