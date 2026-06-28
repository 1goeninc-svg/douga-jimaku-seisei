-- macOS ドラッグ&ドロップ用アプリ
-- osacompile でコンパイルして .app にする（Macセットアップ.sh が自動で行います）

on open dropped_items
    set script_dir to do shell script "dirname " & quoted form of POSIX path of (path to me)
    set py_script to script_dir & "/make_subtitle.py"

    -- ドロップされたファイルを順番に処理するコマンドを組み立てる
    set cmd to ""
    repeat with item_ref in dropped_items
        set video_path to POSIX path of item_ref
        if cmd is not "" then
            set cmd to cmd & " && "
        end if
        set cmd to cmd & "python3 " & quoted form of py_script & " " & quoted form of video_path
    end repeat
    set cmd to cmd & " && echo '' && echo '✅ すべて完了しました。このウィンドウは閉じてください。'"

    tell application "Terminal"
        activate
        do script cmd
    end tell
end open

on run
    display dialog "動画ファイルをこのアイコンにドラッグ＆ドロップしてください。" & return & return & "複数ファイルを同時にドロップすることもできます。" buttons {"OK"} default button "OK" with title "動画字幕生成"
end run
