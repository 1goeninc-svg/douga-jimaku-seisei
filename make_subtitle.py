# -*- coding: utf-8 -*-
"""
動画字幕（テロップ）自動生成ツール
==================================
動画ファイルを渡すと、音声を AI（Whisper）で文字起こしして
字幕ファイル（.srt）を作り、必要なら動画にテロップを焼き込みます。

使い方:
    python make_subtitle.py 動画.mp4                # 字幕(.srt)だけ作る
    python make_subtitle.py 動画.mp4 --burn         # 字幕を焼き込んだ動画も作る
    python make_subtitle.py 動画.mp4 --model large-v3   # 精度重視（遅い）
    python make_subtitle.py 動画.mp4 --lang en       # 英語の動画

ドラッグ&ドロップ:
    動画ファイルを「字幕をつける.bat」にドロップするだけでもOK。

モデルの目安（精度↑ ＝ 速度↓・メモリ↑）:
    tiny < base < small < medium < large-v3
    日本語は medium 以上を推奨。初回はモデルを自動ダウンロードします。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ---- 設定（ここを変えればデフォルト動作を調整できます）---------------------
DEFAULT_MODEL = "medium"      # 精度を上げたいなら "large-v3"
DEFAULT_LANG = "ja"           # 日本語。英語なら "en"
MAX_CHARS = 22                # 1つのテロップに入れる最大文字数（これ以上は分割）
MAX_DURATION = 6.0            # 1つのテロップの最大秒数
# 焼き込み時のテロップ見た目（libass の force_style 形式）
SUBTITLE_STYLE = (
    "FontName=Yu Gothic,FontSize=20,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,"
    "Alignment=2,MarginV=30"
)
# ---------------------------------------------------------------------------


def find_ffmpeg():
    """ffmpeg の実行ファイルを探す。PATH → macOS Homebrew → Windows winget の順。"""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    # macOS: Homebrew (Apple Silicon / Intel)
    for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if Path(p).exists():
            return p
    # Windows: winget(Gyan.FFmpeg) の標準的な場所を探索
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if base.exists():
        for p in base.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"):
            return str(p)
    return None


def format_timestamp(seconds: float) -> str:
    """秒数を SRT 形式のタイムコード (HH:MM:SS,mmm) に変換。"""
    if seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def split_into_telop(segments):
    """
    Whisper のセグメントを、テロップ向けの短いブロックに整える。
    単語ごとのタイムスタンプ(word_timestamps)を使い、文字数・秒数で区切る。
    """
    blocks = []
    cur_words = []
    cur_text = ""
    cur_start = None

    def flush():
        nonlocal cur_words, cur_text, cur_start
        if cur_words:
            blocks.append({
                "start": cur_start,
                "end": cur_words[-1]["end"],
                "text": cur_text.strip(),
            })
        cur_words = []
        cur_text = ""
        cur_start = None

    for seg in segments:
        words = seg.words or []
        if not words:
            # 単語情報が無い場合はセグメントをそのまま使う
            text = seg.text.strip()
            if text:
                blocks.append({"start": seg.start, "end": seg.end, "text": text})
            continue
        for w in words:
            word = w.word
            if cur_start is None:
                cur_start = w.start
            tentative = (cur_text + word).strip()
            too_long = len(tentative) > MAX_CHARS
            too_far = (w.end - cur_start) > MAX_DURATION
            if cur_words and (too_long or too_far):
                flush()
                cur_start = w.start
            cur_words.append({"start": w.start, "end": w.end})
            cur_text += word
            # 句読点で区切るとテロップとして自然
            if word.strip().endswith(("。", "！", "？", ".", "!", "?")):
                flush()
        flush()
    return [b for b in blocks if b["text"]]


def write_srt(blocks, srt_path: Path):
    lines = []
    for i, b in enumerate(blocks, 1):
        lines.append(str(i))
        lines.append(f"{format_timestamp(b['start'])} --> {format_timestamp(b['end'])}")
        lines.append(b["text"])
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def transcribe(video: Path, model_name: str, lang: str, word_ts: bool = True):
    from faster_whisper import WhisperModel

    print(f"[1/2] モデル '{model_name}' を読み込み中（初回はダウンロードします）...")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")

    print(f"[2/2] 音声を文字起こし中: {video.name}")
    segments, info = model.transcribe(
        str(video),
        language=lang,
        word_timestamps=word_ts,
        vad_filter=True,
    )
    print(f"      検出言語: {info.language} (確度 {info.language_probability:.0%})")
    seg_list = []
    for seg in segments:
        seg_list.append(seg)
        text = seg.text.strip()
        if text:
            print(f"SEGMENT:{text}")
    return seg_list


def burn_subtitles(video: Path, srt_path: Path, ffmpeg: str) -> Path:
    """字幕を動画に焼き込む。Windows のパス問題を避けるため作業ディレクトリを移動。"""
    out_path = video.with_name(f"{video.stem}_字幕付き{video.suffix}")
    workdir = video.parent
    # subtitles フィルタはパスのコロン/バックスラッシュに弱いので相対名で渡す
    srt_rel = srt_path.name.replace("'", r"\'")
    vf = f"subtitles='{srt_rel}':force_style='{SUBTITLE_STYLE}'"
    cmd = [
        ffmpeg, "-y",
        "-i", video.name,
        "-vf", vf,
        "-c:a", "copy",
        out_path.name,
    ]
    print(f"[3/3] テロップを焼き込み中 -> {out_path.name}")
    result = subprocess.run(cmd, cwd=str(workdir), capture_output=True, text=True)
    if result.returncode != 0:
        print("  ffmpeg エラー:\n" + result.stderr[-2000:], file=sys.stderr)
        raise RuntimeError("字幕の焼き込みに失敗しました。")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="動画に自動でテロップ(字幕)をつけます")
    parser.add_argument("video", help="動画ファイルのパス")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Whisper モデル (既定: {DEFAULT_MODEL})")
    parser.add_argument("--lang", default=DEFAULT_LANG,
                        help=f"言語コード (既定: {DEFAULT_LANG})")
    parser.add_argument("--burn", action="store_true",
                        help="字幕を動画に焼き込んだファイルも作成する")
    parser.add_argument("--text-only", action="store_true",
                        help="テキスト出力のみ（SRT不要・高速）")
    args = parser.parse_args()

    video = Path(args.video).expanduser().resolve()
    if not video.exists():
        print(f"エラー: ファイルが見つかりません: {video}", file=sys.stderr)
        sys.exit(1)

    if args.text_only:
        # word_timestamps 不要なので高速
        transcribe(video, args.model, args.lang, word_ts=False)
        print("\n完了しました。")
        return

    seg_list = transcribe(video, args.model, args.lang)
    blocks = split_into_telop(seg_list)
    if not blocks:
        print("音声から文字起こしできる内容が見つかりませんでした。", file=sys.stderr)
        sys.exit(1)

    srt_path = video.with_suffix(".srt")
    write_srt(blocks, srt_path)
    print(f"\n字幕ファイルを作成しました: {srt_path}")

    if args.burn:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            print("ffmpeg が見つからないため焼き込みをスキップしました。", file=sys.stderr)
        else:
            out = burn_subtitles(video, srt_path, ffmpeg)
            print(f"テロップ入り動画を作成しました: {out}")

    print("\n完了しました。")


if __name__ == "__main__":
    main()
