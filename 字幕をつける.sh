#!/bin/bash
# Mac ターミナル用：動画ファイルを引数に渡すか、このスクリプトに D&D（Automator経由）で使う
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/make_subtitle.py"

if [ $# -eq 0 ]; then
    echo "使い方:"
    echo "  bash 字幕をつける.sh 動画.mp4"
    echo "  bash 字幕をつける.sh 動画.mp4 --burn   # 字幕を動画に焼き込む"
    echo ""
    echo "または「字幕をつける.app」に動画ファイルをドラッグ＆ドロップ"
    exit 1
fi

for video_file in "$@"; do
    # --burn など追加引数は除外してファイルパスのみ処理
    case "$video_file" in
        --*) continue ;;
    esac
    echo "==================================="
    echo "処理中: $video_file"
    echo "==================================="
    python3 "$PY_SCRIPT" "$video_file" "${@:2}"
    echo ""
done

echo "すべて完了しました。"
