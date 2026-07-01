'use strict';

const MAX_MB = 500; // 動画は変換後 WAV がずっと小さくなるため元ファイルは 500MB まで許可

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
    alert(`ファイルが大きすぎます（${mb.toFixed(0)} MB）。\n${MAX_MB} MB 以下のファイルを選択してください。\n（音声の長さは約 13 分まで対応）`);
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
// iOS Safari では AudioContext({ sampleRate }) が不安定なため
// OfflineAudioContext でリサンプリングする方式を使用する。
async function preprocessToWav(file) {
  const AudioCtx   = window.AudioContext   || window.webkitAudioContext;
  const OfflineCtx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  if (!AudioCtx || !OfflineCtx) return null;

  const TARGET_RATE = 16000;
  try {
    // Step 1: ネイティブレートでデコード（sampleRate 指定なし → iOS 互換）
    const tempCtx = new AudioCtx();
    const audioBuffer = await tempCtx.decodeAudioData(await file.arrayBuffer());

    // Step 2: 全チャンネルをモノラルに混合
    const numCh     = audioBuffer.numberOfChannels;
    const nativeLen = audioBuffer.length;
    const nativeRate= audioBuffer.sampleRate;
    const mono      = new Float32Array(nativeLen);
    for (let c = 0; c < numCh; c++) {
      const ch = audioBuffer.getChannelData(c);
      for (let i = 0; i < nativeLen; i++) mono[i] += ch[i] / numCh;
    }

    // Step 3: モノラル AudioBuffer を生成
    const monoBuf = tempCtx.createBuffer(1, nativeLen, nativeRate);
    monoBuf.copyToChannel(mono, 0);
    await tempCtx.close();

    // Step 4: OfflineAudioContext で 16 kHz にリサンプリング
    const targetLen = Math.ceil(audioBuffer.duration * TARGET_RATE);
    const offCtx    = new OfflineCtx(1, targetLen, TARGET_RATE);
    const src       = offCtx.createBufferSource();
    src.buffer      = monoBuf;
    src.connect(offCtx.destination);
    src.start();
    const resampled = await offCtx.startRendering();
    const samples   = resampled.getChannelData(0);

    // Step 5: 16-bit PCM WAV にエンコード
    const len    = samples.length;
    const wavBuf = new ArrayBuffer(44 + len * 2);
    const view   = new DataView(wavBuf);
    const str    = (off, s) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };
    str(0, 'RIFF');
    view.setUint32(4,  36 + len * 2,       true);
    str(8, 'WAVE');
    str(12, 'fmt ');
    view.setUint32(16, 16,                  true);
    view.setUint16(20, 1,                   true);  // PCM
    view.setUint16(22, 1,                   true);  // mono
    view.setUint32(24, TARGET_RATE,         true);
    view.setUint32(28, TARGET_RATE * 2,     true);
    view.setUint16(32, 2,                   true);
    view.setUint16(34, 16,                  true);
    str(36, 'data');
    view.setUint32(40, len * 2,             true);
    let off = 44;
    for (let i = 0; i < len; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
      off += 2;
    }

    const blob = new Blob([wavBuf], { type: 'audio/wav' });
    if (blob.size > 24 * 1024 * 1024) return { blob: null, reason: 'too_long' };
    return { blob, reason: null };
  } catch (_) {
    return { blob: null, reason: 'decode_failed' };
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

  const { blob: wav, reason } = await preprocessToWav(selectedFile);

  if (!wav) {
    if (reason === 'too_long') {
      setStatus('error', '❌ 音声が長すぎます（約 13 分まで対応）。動画を分割してアップロードしてください。');
    } else {
      // デコード失敗：Groq 非対応形式のまま送ると確実に失敗する拡張子はガード
      const GROQ_UNSUPPORTED = /\.(avi|wmv|flv)$/i;
      if (GROQ_UNSUPPORTED.test(selectedFile.name)) {
        setStatus('error', '❌ この形式は処理できません。MP4 または M4A に変換してください。');
        submitBtn.disabled = false;
        return;
      }
      // .mov / その他：Groq がそのまま受け付ける可能性があるので一旦送る
    }
    if (reason === 'too_long') { submitBtn.disabled = false; return; }
  }

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
