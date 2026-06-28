# -*- coding: utf-8 -*-
"""
動画字幕生成 Web アプリケーション — 高速テキスト抽出モード
  - faster_whisper をサーバープロセス内で直接呼び出す（サブプロセスなし）
  - モデルはメモリにキャッシュ（2回目以降はロード時間ゼロ）
  - beam_size=1 / temperature=0 でグリーディーデコード（最速）
"""
import sys
import uuid
import queue
import threading
import socket
from pathlib import Path
from flask import (
    Flask, request, jsonify,
    render_template, Response, stream_with_context,
)

SCRIPT_DIR        = Path(__file__).parent
UPLOAD_DIR        = SCRIPT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DEFAULT_MODEL     = "small"   # 起動時にプリロードするモデル
TRANSCRIBE_PARAMS = dict(
    word_timestamps           = False,  # 単語タイムスタンプ不要 → 高速
    vad_filter                = True,   # 無音区間をスキップ
    beam_size                 = 1,      # グリーディーデコード（最速）
    temperature               = 0,      # 温度 0 ＝ 再試行なし
    condition_on_previous_text= False,  # 前文脈を使わない → 速い
    no_speech_threshold       = 0.6,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024 * 1024  # 4 GB

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


# ── モデルキャッシュ ───────────────────────────────────
_model_cache: dict = {}         # model_name → WhisperModel
_warmed_up:   set  = set()      # ロード＋JITウォームアップ完了済みモデル名
_model_lock   = threading.Lock()
_transcribe_sem = threading.Semaphore(1)   # 同時転写は 1 件のみ（CPU 競合防止）


def _get_model(model_name: str):
    """モデルが未ロードなら読み込む。以降はキャッシュを返す。"""
    if model_name not in _model_cache:
        with _model_lock:
            if model_name not in _model_cache:
                from faster_whisper import WhisperModel
                _model_cache[model_name] = WhisperModel(
                    model_name, device="cpu", compute_type="int8"
                )
    return _model_cache[model_name]


def _preload(model_name: str):
    """ロード＋JIT ウォームアップをバックグラウンドで完了させる。
    _warmed_up に追加されるまで /model_ready は False を返す。"""
    try:
        import numpy as np
        model = _get_model(model_name)

        # CTranslate2 の JIT コンパイルを事前に済ませる。
        # 1 秒の無音を vad_filter=False で流す（VAD 処理を挟まず純粋にデコードを温める）。
        dummy = np.zeros(16000, dtype=np.float32)
        segs, _ = model.transcribe(
            dummy, language="ja",
            beam_size=1, temperature=0,
            word_timestamps=False, vad_filter=False,
        )
        list(segs)   # ジェネレータを消費して初回コンパイルを完了させる

        _warmed_up.add(model_name)
        print(f"  ✅ モデル '{model_name}' 準備完了（ロード＋ウォームアップ済み）")
    except Exception as exc:
        print(f"  ⚠️  モデル準備失敗: {exc}")


# ---------------------------------------------------------------------------
# ルーティング
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/model_ready")
def model_ready():
    """ロード＋JIT ウォームアップが完了しているかを返す。"""
    model_name = request.args.get("model", DEFAULT_MODEL)
    return jsonify({"ready": model_name in _warmed_up})


@app.route("/upload", methods=["POST"])
def upload():
    if "video" not in request.files:
        return jsonify({"error": "ファイルがありません"}), 400

    f = request.files["video"]
    if not f.filename:
        return jsonify({"error": "ファイル名が空です"}), 400

    model = request.form.get("model", DEFAULT_MODEL)
    lang  = request.form.get("lang",  "ja")

    if model not in {"tiny", "base", "small", "medium", "large-v3"}:
        return jsonify({"error": "Invalid model"}), 400
    if not lang.replace("-", "").isalpha() or len(lang) > 5:
        return jsonify({"error": "Invalid lang"}), 400

    job_id     = str(uuid.uuid4())
    safe_name  = Path(f.filename).name
    video_path = UPLOAD_DIR / f"{job_id}_{safe_name}"
    f.save(str(video_path))

    q: "queue.Queue[tuple[str, str]]" = queue.Queue()
    with jobs_lock:
        jobs[job_id] = {
            "id":       job_id,
            "filename": safe_name,
            "model":    model,
            "lang":     lang,
            "status":   "queued",
            "queue":    q,
            "result":   [],
        }

    threading.Thread(
        target=_run_job,
        args=(job_id, str(video_path), model, lang),
        daemon=True,
    ).start()

    return jsonify({"job_id": job_id, "filename": safe_name})


@app.route("/stream/<job_id>")
def stream(job_id: str):
    """SSE — 認識テキストをリアルタイムでストリーミングする。"""
    def generate():
        with jobs_lock:
            job = jobs.get(job_id)
        if not job:
            yield "event: error\ndata: ジョブが見つかりません\n\n"
            return

        q: queue.Queue = job["queue"]
        while True:
            try:
                event_type, data = q.get(timeout=30)
                safe = data.replace("\\", "\\\\").replace("\n", "\\n")
                yield f"event: {event_type}\ndata: {safe}\n\n"
                if event_type in ("done", "error"):
                    break
            except queue.Empty:
                yield ": keepalive\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/jobs")
def list_jobs():
    with jobs_lock:
        result = [
            {
                "id":       j["id"],
                "filename": j["filename"],
                "model":    j["model"],
                "lang":     j["lang"],
                "status":   j["status"],
                "result":   j["result"],
            }
            for j in jobs.values()
        ]
    return jsonify(result[::-1])


# ---------------------------------------------------------------------------
# バックグラウンドジョブ実行（サブプロセスなし・直接 faster_whisper を呼ぶ）
# ---------------------------------------------------------------------------

def _run_job(job_id: str, video_path: str, model_name: str, lang: str):
    q: queue.Queue = jobs[job_id]["queue"]

    try:
        with jobs_lock:
            jobs[job_id]["status"] = "processing"

        # モデルがキャッシュ済みなら即座に取得、未ロードなら読み込む
        cached = model_name in _model_cache
        if not cached:
            q.put(("log", f"モデル '{model_name}' を読み込み中（初回のみ）…"))
        model = _get_model(model_name)
        if not cached:
            q.put(("log", "読み込み完了"))

        q.put(("log", f"文字起こしを開始します（言語: {lang}）…"))

        with _transcribe_sem:
            segments, info = model.transcribe(
                video_path,
                language=lang,
                **TRANSCRIBE_PARAMS,
            )
            q.put(("log", f"検出言語: {info.language} ({info.language_probability:.0%})"))

            # segments はジェネレータ — 1セグメント認識されるたびに即座に送信
            for seg in segments:
                text = seg.text.strip()
                if text:
                    with jobs_lock:
                        jobs[job_id]["result"].append(text)
                    q.put(("segment", text))

        with jobs_lock:
            jobs[job_id]["status"] = "done"
        q.put(("done", ""))

    except Exception as exc:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
        q.put(("error", str(exc)))
    finally:
        # アップロードファイルを削除して空き容量を確保
        try:
            Path(video_path).unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ip = get_local_ip()
    print("=" * 54)
    print("  動画字幕生成 Web アプリ（高速テキスト抽出モード）")
    print("=" * 54)
    print(f"\n  Mac ブラウザ : http://localhost:8080")
    print(f"  iPhone/iPad  : http://{ip}:8080")
    print(f"\n  ※ iPhone は Mac と同じ Wi-Fi に接続してください")
    print(f"  モデル '{DEFAULT_MODEL}' を起動時にプリロードします…")
    print("  Ctrl+C で停止\n")

    # サーバー起動と並行してモデルをバックグラウンドでロード
    threading.Thread(target=_preload, args=(DEFAULT_MODEL,), daemon=True).start()

    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
