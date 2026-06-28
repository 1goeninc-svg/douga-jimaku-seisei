'use strict';

const MAX_MB = 25;

const fileInput    = document.getElementById('file-input');
const dropzone     = document.getElementById('dropzone');
const filePill     = document.getElementById('file-pill');
const filePillName = document.getElementById('file-pill-name');
const fileSizeEl   = document.getElementById('file-size');
const submitBtn    = document.getElementById('submit-btn');
const processCard  = document.getElementById('process-card');
const resultWrap   = document.getElementById('result-wrap');
const segmentList  = document.getElementById('segment-list');

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
  filePill.hidden    = false;
  submitBtn.disabled = false;
}

function clearFile() {
  selectedFile = null;
  fileInput.value    = '';
  filePill.hidden    = true;
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

// ── 音声前処理（16 kHz モノラル WAV に変換） ─────────
async function preprocessToWav(file) {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return null;

  const SAMPLE_RATE = 16000;
  try {
    const ctx = new AudioCtx({ sampleRate: SAMPLE_RATE });
    const buf = await ctx.decodeAudioData(await file.arrayBuffer());
    await ctx.close();

    const numCh = buf.numberOfChannels;
    const len   = buf.length;
    const mono  = new Float32Array(len);
    for (let c = 0; c < numCh; c++) {
      const ch = buf.getChannelData(c);
      for (let i = 0; i < len; i++) mono[i] += ch[i] / numCh;
    }

    const wavBuf = new ArrayBuffer(44 + len * 2);
    const view   = new DataView(wavBuf);
    const str    = (off, s) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };
    str(0, 'RIFF');
    view.setUint32(4,  36 + len * 2,     true);
    str(8, 'WAVE');
    str(12, 'fmt ');
    view.setUint32(16, 16,               true);
    view.setUint16(20, 1,                true);
    view.setUint16(22, 1,                true);
    view.setUint32(24, SAMPLE_RATE,      true);
    view.setUint32(28, SAMPLE_RATE * 2,  true);
    view.setUint16(32, 2,                true);
    view.setUint16(34, 16,               true);
    str(36, 'data');
    view.setUint32(40, len * 2,          true);
    let off = 44;
    for (let i = 0; i < len; i++) {
      const s = Math.max(-1, Math.min(1, mono[i]));
      view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
      off += 2;
    }

    const blob = new Blob([wavBuf], { type: 'audio/wav' });
    if (blob.size > 24 * 1024 * 1024) return null;
    return blob;
  } catch (_) {
    return null;
  }
}

// ── セグメント描画 ────────────────────────────────────
const CIRCLES = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟';

function circledNum(n) {
  return n <= CIRCLES.length ? CIRCLES[n - 1] : `${n}.`;
}

function renderSegments(text) {
  segmentList.innerHTML = '';
  const lines = text.split('\n').filter(l => l.trim());

  if (!lines.length) {
    const empty = document.createElement('p');
    empty.className = 'segment-empty';
    empty.textContent = '（テキストが認識されませんでした）';
    segmentList.appendChild(empty);
    return;
  }

  lines.forEach((line, i) => {
    const item = document.createElement('div');
    item.className = 'segment-item';
    item.innerHTML = `
      <span class="segment-num">${circledNum(i + 1)}</span>
      <p class="segment-text">${escHtml(line)}</p>
      <button class="segment-copy-btn" data-text="${escAttr(line)}">コピー</button>
    `;
    item.querySelector('.segment-copy-btn').addEventListener('click', function () {
      navigator.clipboard.writeText(this.dataset.text).then(() => {
        this.textContent = '✓';
        this.classList.add('copied');
        setTimeout(() => { this.textContent = 'コピー'; this.classList.remove('copied'); }, 1500);
      });
    });
    segmentList.appendChild(item);
  });
}

// ── 全てコピー ────────────────────────────────────────
function copyAll() {
  const lines = Array.from(segmentList.querySelectorAll('.segment-text')).map(el => el.textContent);
  if (!lines.length) return;
  navigator.clipboard.writeText(lines.join('\n')).then(() => {
    const btn = document.getElementById('copy-btn');
    btn.textContent = 'コピーしました！';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '全てコピー'; btn.classList.remove('copied'); }, 2000);
  });
}

// ── 処理開始 ──────────────────────────────────────────
async function startProcess() {
  if (!selectedFile) return;

  submitBtn.disabled = true;
  segmentList.innerHTML = '';
  resultWrap.hidden  = true;
  processCard.hidden = false;
  document.getElementById('process-filename').textContent = selectedFile.name;
  setStatus('processing', '音声を最適化中…');

  const wav = await preprocessToWav(selectedFile);
  const uploadFile = wav
    ? new File([wav], selectedFile.name.replace(/\.[^.]+$/, '') + '_audio.wav', { type: 'audio/wav' })
    : selectedFile;

  setStatus('processing', 'アップロード中…');

  const form = new FormData();
  form.append('audio', uploadFile);
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
      renderSegments(text || '');
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

// ── ユーティリティ ────────────────────────────────────
function setStatus(type, text) {
  const badge   = document.getElementById('status-badge');
  const spinner = type === 'processing' ? '<span class="spinner"></span>' : '';
  badge.innerHTML = `<span class="badge badge-${type}">${spinner}${escHtml(text)}</span>`;
}

function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escAttr(s) {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}
