# -*- coding: utf-8 -*-
"""
動画字幕生成 — Vercel 版（Groq Whisper API）
faster_whisper の代わりに Groq API で文字起こしを行う。
"""
import os
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_from_directory
from groq import Groq

ROOT = Path(__file__).parent.parent

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
    static_url_path="/static",
)

# Groq が受け付けるファイルサイズ上限
MAX_BYTES = 25 * 1024 * 1024  # 25 MB

GROQ_MODELS = {
    "turbo":  "whisper-large-v3-turbo",   # 速い・高精度（推奨）
    "large":  "whisper-large-v3",          # 最高精度
}

# 言語別プロンプト：Whisper に語彙・文体のヒントを与えて精度向上
PROMPTS = {
    "ja": "以下は日本語の音声です。句読点を正しく使用してください。",
    "en": "The following is English audio. Please use correct punctuation.",
    "zh": "以下是中文音频。",
    "ko": "다음은 한국어 오디오입니다.",
}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/transcribe", methods=["POST"])
def transcribe():
    if "audio" not in request.files:
        return jsonify({"error": "ファイルがありません"}), 400

    f = request.files["audio"]
    if not f.filename:
        return jsonify({"error": "ファイル名が空です"}), 400

    model_key = request.form.get("model", "turbo")
    lang      = request.form.get("lang", "ja")
    groq_model = GROQ_MODELS.get(model_key, GROQ_MODELS["turbo"])

    data = f.read()
    size_mb = len(data) / 1024 / 1024
    if len(data) > MAX_BYTES:
        return jsonify({
            "error": f"ファイルが大きすぎます（{size_mb:.0f} MB）。25 MB 以下にしてください。"
        }), 413

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return jsonify({"error": "GROQ_API_KEY が設定されていません"}), 500

    suffix = Path(f.filename).suffix or ".mp4"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(data)
        tmp.close()

        prompt = PROMPTS.get(lang, "") if lang != "auto" else ""

        client = Groq(api_key=api_key)
        with open(tmp.name, "rb") as audio_file:
            result = client.audio.transcriptions.create(
                file=(f.filename, audio_file.read()),
                model=groq_model,
                language=lang if lang != "auto" else None,
                response_format="verbose_json",
                prompt=prompt or None,
            )
        # セグメントごとに改行して読みやすくする
        # SDK のバージョンによって dict / object どちらでも動くように対応
        lines = []
        for seg in result.segments:
            t = (seg["text"] if isinstance(seg, dict) else seg.text).strip()
            if t:
                lines.append(t)
        text = "\n".join(lines)
        return jsonify({"text": text})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
