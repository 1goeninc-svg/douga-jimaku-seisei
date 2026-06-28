#!/bin/bash
# Mac 初回セットアップ：依存関係の確認と字幕をつける.app の作成

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== 動画字幕生成ツール Mac セットアップ ==="
echo ""

# ---- 実行権限 ----
chmod +x "$SCRIPT_DIR/字幕をつける.sh"
echo "✅ 字幕をつける.sh を実行可能にしました"

# ---- Python ----
if ! command -v python3 &>/dev/null; then
    echo "❌ Python3 が見つかりません。https://www.python.org/ からインストールしてください。"
    exit 1
fi
echo "✅ Python3: $(python3 --version)"

# ---- faster-whisper ----
if ! python3 -c "import faster_whisper" 2>/dev/null; then
    echo ""
    echo "faster-whisper をインストールしています..."
    python3 -m pip install faster-whisper
fi
echo "✅ faster-whisper インストール済み"

# ---- ffmpeg (--burn オプション用・任意) ----
if command -v ffmpeg &>/dev/null; then
    echo "✅ ffmpeg: $(ffmpeg -version 2>&1 | head -1)"
else
    echo "⚠️  ffmpeg が見つかりません（字幕の「焼き込み」機能に必要です）"
    if command -v brew &>/dev/null; then
        read -r -p "   Homebrew で今すぐインストールしますか？ [y/N]: " ans
        if [[ "$ans" =~ ^[Yy]$ ]]; then
            brew install ffmpeg
            echo "✅ ffmpeg をインストールしました"
        fi
    else
        echo "   → Homebrew (https://brew.sh) をインストール後、brew install ffmpeg で追加できます"
    fi
fi

# ---- .app コンパイル ----
APP_PATH="$SCRIPT_DIR/字幕をつける.app"
echo ""
echo "ドラッグ＆ドロップ用アプリを作成中..."

osacompile -o "$APP_PATH" "$SCRIPT_DIR/字幕をつける.applescript"

if [ -d "$APP_PATH" ]; then
    echo "✅ 字幕をつける.app を作成しました"
    # Gatekeeper でブロックされないよう拡張属性を削除
    xattr -cr "$APP_PATH" 2>/dev/null || true
    echo ""
    echo "========================================"
    echo "  セットアップ完了！"
    echo ""
    echo "  【使い方 — ドラッグ＆ドロップ】"
    echo "  動画ファイルを「字幕をつける.app」に"
    echo "  ドラッグ＆ドロップするだけ"
    echo ""
    echo "  【使い方 — ターミナル】"
    echo "  bash 字幕をつける.sh 動画.mp4"
    echo "========================================"
else
    echo "❌ アプリの作成に失敗しました"
    exit 1
fi
