# -*- coding: utf-8 -*-
"""
iPhone / スマートフォン用 字幕生成 Web サーバー
同じ Wi-Fi ネットワーク上のデバイスからブラウザでアクセスできます。
起動後、表示される URL (http://xxx.xxx.xxx.xxx:5000) を iPhone Safari で開いてください。
"""
import os
import sys
import uuid
import subprocess
import threading
import socket
from pathlib import Path
from flask import Flask, request, send_file, jsonify, render_template_string

SCRIPT_DIR = Path(__file__).parent
UPLOAD_DIR = SCRIPT_DIR / "temp_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024 * 1024  # 4GB

jobs: dict = {}
jobs_lock = threading.Lock()


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


# ---------------------------------------------------------------------------
# HTML テンプレート（iPhone フレンドリーなシングルページ）
# ---------------------------------------------------------------------------
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>動画字幕生成</title>
<style>
:root {
  --bg: #0f0f13;
  --card: #1a1a24;
  --accent: #6c63ff;
  --accent2: #ff6584;
  --text: #e8e8f0;
  --text2: #888899;
  --success: #4caf82;
  --error: #ff5c5c;
  --border: #2a2a3a;
  --radius: 16px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, 'Helvetica Neue', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  padding: 24px 16px 80px;
}
h1 {
  font-size: 1.7rem;
  font-weight: 800;
  text-align: center;
  margin-bottom: 4px;
  background: linear-gradient(90deg, var(--accent), var(--accent2));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.sub { text-align: center; color: var(--text2); font-size: 0.85rem; margin-bottom: 28px; }
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 14px;
}
.card-title {
  color: var(--text2);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 14px;
}
.dropzone {
  border: 2px dashed var(--border);
  border-radius: 12px;
  padding: 36px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}
.dropzone:hover, .dropzone.drag {
  border-color: var(--accent);
  background: rgba(108,99,255,0.06);
}
.dropzone-icon { font-size: 2.8rem; margin-bottom: 10px; }
.dropzone p { color: var(--text2); font-size: 0.9rem; line-height: 1.6; }
.dropzone strong { color: var(--text); }
#file-input { display: none; }
.file-name {
  margin-top: 12px;
  background: rgba(108,99,255,0.12);
  border: 1px solid rgba(108,99,255,0.3);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 0.88rem;
  color: var(--accent);
  word-break: break-all;
  display: none;
}
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
label.field-label {
  display: block;
  color: var(--text2);
  font-size: 0.78rem;
  margin-bottom: 6px;
}
select {
  width: 100%;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 11px 12px;
  font-size: 0.9rem;
  -webkit-appearance: none;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='%23888899' d='M6 8L0 0h12z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 32px;
}
.toggle-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
}
.toggle-row span { font-size: 0.92rem; }
.toggle-row small { color: var(--text2); font-size: 0.76rem; display: block; margin-top: 2px; }
.toggle { position: relative; width: 52px; height: 30px; flex-shrink: 0; }
.toggle input { opacity: 0; width: 0; height: 0; }
.toggle-slider {
  position: absolute; inset: 0;
  background: var(--border);
  border-radius: 30px;
  cursor: pointer;
  transition: 0.25s;
}
.toggle-slider::before {
  content: '';
  position: absolute;
  width: 24px; height: 24px;
  left: 3px; bottom: 3px;
  background: white;
  border-radius: 50%;
  transition: 0.25s;
  box-shadow: 0 1px 4px rgba(0,0,0,0.3);
}
.toggle input:checked + .toggle-slider { background: var(--accent); }
.toggle input:checked + .toggle-slider::before { transform: translateX(22px); }
.progress-wrap {
  background: var(--border);
  border-radius: 99px;
  height: 6px;
  overflow: hidden;
  margin: 14px 0 6px;
  display: none;
}
.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent2));
  border-radius: 99px;
  transition: width 0.3s;
  width: 0%;
}
.progress-text { font-size: 0.78rem; color: var(--text2); text-align: right; min-height: 1.2em; }
.btn {
  width: 100%;
  padding: 17px;
  border: none;
  border-radius: 14px;
  font-size: 1.05rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.18s;
  letter-spacing: 0.02em;
}
.btn-primary {
  background: linear-gradient(135deg, var(--accent), #9c8fff);
  color: white;
  box-shadow: 0 4px 20px rgba(108,99,255,0.35);
  margin-top: 6px;
}
.btn-primary:active { transform: scale(0.97); }
.btn-primary:disabled { opacity: 0.38; cursor: not-allowed; box-shadow: none; transform: none; }
.btn-success {
  background: linear-gradient(135deg, var(--success), #6de0a8);
  color: white;
  box-shadow: 0 4px 16px rgba(76,175,130,0.35);
  margin-top: 14px;
}
.btn-success:active { transform: scale(0.97); }
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 99px;
  font-size: 0.8rem;
  font-weight: 600;
  margin-bottom: 14px;
}
.status-processing { background: rgba(108,99,255,0.15); color: var(--accent); }
.status-done       { background: rgba(76,175,130,0.15); color: var(--success); }
.status-error      { background: rgba(255,92,92,0.15);  color: var(--error); }
.spinner {
  width: 13px; height: 13px;
  border: 2px solid rgba(108,99,255,0.3);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.75s linear infinite;
  display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }
.log-box {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  font-family: 'Menlo', 'Courier New', monospace;
  font-size: 0.76rem;
  line-height: 1.65;
  max-height: 220px;
  overflow-y: auto;
  color: #999;
  white-space: pre-wrap;
  word-break: break-all;
}
#result-card { display: none; }
</style>
</head>
<body>

<h1>動画字幕生成</h1>
<p class="sub">AI（Whisper）で字幕ファイルを自動生成します</p>

<div class="card">
  <div class="card-title">動画ファイル</div>
  <div class="dropzone" id="dropzone" onclick="document.getElementById('file-input').click()">
    <div class="dropzone-icon">🎬</div>
    <p><strong>タップしてファイルを選択</strong></p>
    <p>mp4 / mov / m4v / mkv / avi など</p>
  </div>
  <input type="file" id="file-input"
    accept="video/*,.mp4,.mov,.m4v,.mkv,.avi,.wmv,.flv,.webm,.ts,.3gp">
  <div class="file-name" id="file-name"></div>
</div>

<div class="card">
  <div class="card-title">設定</div>
  <div class="settings-grid">
    <div>
      <label class="field-label" for="model">精度モデル</label>
      <select id="model">
        <option value="tiny">tiny（最速）</option>
        <option value="base">base</option>
        <option value="small">small</option>
        <option value="medium" selected>medium（推奨）</option>
        <option value="large-v3">large-v3（高精度）</option>
      </select>
    </div>
    <div>
      <label class="field-label" for="lang">言語</label>
      <select id="lang">
        <option value="ja" selected>日本語</option>
        <option value="en">English</option>
        <option value="zh">中文</option>
        <option value="ko">한국어</option>
      </select>
    </div>
  </div>
  <div class="toggle-row" style="margin-top:14px">
    <div>
      <span>字幕を動画に焼き込む</span>
      <small>ffmpeg が必要・処理時間が増えます</small>
    </div>
    <label class="toggle">
      <input type="checkbox" id="burn">
      <span class="toggle-slider"></span>
    </label>
  </div>
</div>

<div class="progress-wrap" id="progress-wrap">
  <div class="progress-bar" id="progress-bar"></div>
</div>
<div class="progress-text" id="progress-text"></div>

<button class="btn btn-primary" id="submit-btn" onclick="startProcess()" disabled>
  字幕を生成する
</button>

<div class="card" id="result-card" style="margin-top:16px">
  <div id="status-area"></div>
  <div class="log-box" id="log-box"></div>
  <button class="btn btn-success" id="download-btn" onclick="downloadSrt()" style="display:none">
    ⬇️ .srt ファイルをダウンロード
  </button>
</div>

<script>
let selectedFile = null;
let currentJobId = null;
let pollTimer = null;

const fileInput  = document.getElementById('file-input');
const dropzone   = document.getElementById('dropzone');
const fileNameEl = document.getElementById('file-name');
const submitBtn  = document.getElementById('submit-btn');

function onFileSelected(file) {
  selectedFile = file;
  fileNameEl.textContent = '📄 ' + file.name;
  fileNameEl.style.display = 'block';
  submitBtn.disabled = false;
}

fileInput.addEventListener('change', () => {
  if (fileInput.files.length > 0) onFileSelected(fileInput.files[0]);
});

// デスクトップ向けドラッグ&ドロップ
dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('drag'); });
dropzone.addEventListener('dragleave', ()  => dropzone.classList.remove('drag'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('drag');
  if (e.dataTransfer.files.length > 0) onFileSelected(e.dataTransfer.files[0]);
});

function startProcess() {
  if (!selectedFile) return;

  submitBtn.disabled = true;
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }

  const resultCard = document.getElementById('result-card');
  resultCard.style.display = 'block';
  document.getElementById('log-box').textContent = '';
  document.getElementById('download-btn').style.display = 'none';
  setStatus('processing', '送信中...');

  const formData = new FormData();
  formData.append('video', selectedFile);
  formData.append('model', document.getElementById('model').value);
  formData.append('lang',  document.getElementById('lang').value);
  formData.append('burn',  document.getElementById('burn').checked ? '1' : '0');

  const xhr = new XMLHttpRequest();
  const progressWrap = document.getElementById('progress-wrap');
  const progressBar  = document.getElementById('progress-bar');
  const progressText = document.getElementById('progress-text');
  progressWrap.style.display = 'block';

  xhr.upload.addEventListener('progress', e => {
    if (e.lengthComputable) {
      const pct = Math.round(e.loaded / e.total * 100);
      progressBar.style.width = pct + '%';
      progressText.textContent = 'アップロード: ' + pct + '%';
    }
  });

  xhr.addEventListener('load', () => {
    progressWrap.style.display = 'none';
    progressText.textContent = '';
    if (xhr.status === 200) {
      const data = JSON.parse(xhr.responseText);
      currentJobId = data.job_id;
      setStatus('processing', 'AI 処理中...');
      pollTimer = setInterval(pollStatus, 2500);
    } else {
      setStatus('error', 'アップロードに失敗しました (' + xhr.status + ')');
      submitBtn.disabled = false;
    }
  });

  xhr.addEventListener('error', () => {
    progressWrap.style.display = 'none';
    setStatus('error', 'ネットワークエラーが発生しました');
    submitBtn.disabled = false;
  });

  xhr.open('POST', '/upload');
  xhr.send(formData);
}

function setStatus(type, text) {
  const el = document.getElementById('status-area');
  const spinner = type === 'processing'
    ? '<span class="spinner"></span>' : '';
  el.innerHTML = '<div class="status-badge status-' + type + '">' + spinner + text + '</div>';
}

function pollStatus() {
  if (!currentJobId) return;
  fetch('/status/' + currentJobId)
    .then(r => r.json())
    .then(data => {
      const logBox = document.getElementById('log-box');
      logBox.textContent = (data.logs || []).join('\n');
      logBox.scrollTop = logBox.scrollHeight;

      if (data.status === 'done') {
        clearInterval(pollTimer);
        setStatus('done', '✅ 字幕ファイルが完成しました！');
        document.getElementById('download-btn').style.display = 'block';
        submitBtn.disabled = false;
      } else if (data.status === 'error') {
        clearInterval(pollTimer);
        setStatus('error', '❌ エラーが発生しました');
        submitBtn.disabled = false;
      }
    })
    .catch(() => { /* ネットワーク一時切断は無視 */ });
}

function downloadSrt() {
  if (currentJobId) window.location.href = '/download/' + currentJobId;
}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# API エンドポイント
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/upload", methods=["POST"])
def upload():
    if "video" not in request.files:
        return jsonify({"error": "ファイルがありません"}), 400

    f = request.files["video"]
    if not f.filename:
        return jsonify({"error": "ファイル名が空です"}), 400

    model = request.form.get("model", "medium")
    lang  = request.form.get("lang",  "ja")
    burn  = request.form.get("burn",  "0") == "1"

    # 入力検証
    if model not in {"tiny", "base", "small", "medium", "large-v3"}:
        return jsonify({"error": "Invalid model"}), 400
    if not lang.replace("-", "").isalpha() or len(lang) > 5:
        return jsonify({"error": "Invalid lang"}), 400

    job_id = str(uuid.uuid4())

    # ファイル保存（ファイル名は job_id プレフィックス付きで安全に）
    safe_name = Path(f.filename).name
    video_path = UPLOAD_DIR / f"{job_id}_{safe_name}"
    f.save(str(video_path))

    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "logs": [],
            "srt_path": None,
            "video_path": str(video_path),
        }

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, str(video_path), model, lang, burn),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


def _run_job(job_id: str, video_path: str, model: str, lang: str, burn: bool):
    """バックグラウンドで make_subtitle.py を実行してログを収集する。"""
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "make_subtitle.py"),
        video_path,
        "--model", model,
        "--lang",  lang,
    ]
    if burn:
        cmd.append("--burn")

    with jobs_lock:
        jobs[job_id]["status"] = "processing"

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for raw_line in proc.stdout:
            line = raw_line.rstrip()
            if line:
                with jobs_lock:
                    jobs[job_id]["logs"].append(line)

        proc.wait()
        srt_path = Path(video_path).with_suffix(".srt")

        with jobs_lock:
            if proc.returncode == 0 and srt_path.exists():
                jobs[job_id]["status"] = "done"
                jobs[job_id]["srt_path"] = str(srt_path)
            else:
                jobs[job_id]["status"] = "error"

    except Exception as exc:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["logs"].append(f"[サーバーエラー] {exc}")


@app.route("/status/<job_id>")
def status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"status": job["status"], "logs": job["logs"]})


@app.route("/download/<job_id>")
def download(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job["status"] != "done" or not job["srt_path"]:
        return jsonify({"error": "まだ準備できていません"}), 404

    srt_path = Path(job["srt_path"])
    if not srt_path.exists():
        return jsonify({"error": "ファイルが見つかりません"}), 404

    return send_file(
        str(srt_path),
        as_attachment=True,
        download_name=srt_path.name,
        mimetype="text/plain; charset=utf-8",
    )


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    local_ip = get_local_ip()
    print("=" * 52)
    print("  動画字幕生成 iPhone/スマートフォン サーバー")
    print("=" * 52)
    print(f"\n  iPhone や iPad からアクセスするには:")
    print(f"  → http://{local_ip}:5000")
    print(f"\n  ※ Mac と iPhone が同じ Wi-Fi に接続していること")
    print("  ※ Ctrl+C で停止\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
