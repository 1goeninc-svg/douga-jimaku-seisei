#!/bin/bash
# Finder でダブルクリックするだけで iPhone 用サーバーを起動します

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== 動画字幕生成 iPhone サーバー ==="
echo ""

# Flask がなければインストール
if ! python3 -c "import flask" 2>/dev/null; then
    echo "Flask をインストールしています..."
    python3 -m pip install flask
    echo ""
fi

# ローカル IP を取得して表示
LOCAL_IP=$(python3 -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    print(s.getsockname()[0])
    s.close()
except:
    print('localhost')
" 2>/dev/null)

echo "============================================"
echo "  iPhone / iPad からアクセスするには:"
echo ""
echo "  http://$LOCAL_IP:8080"
echo ""
echo "  ※ Mac と iPhone が同じ Wi-Fi に接続していること"
echo "============================================"
echo ""
echo "停止するには Ctrl+C を押してください"
echo ""

cd "$SCRIPT_DIR"
python3 app.py
