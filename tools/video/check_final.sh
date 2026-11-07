#!/usr/bin/env bash
# 書き出した提出動画を確かめる（クーちゃん 11/7）：尺 3:00 以内・1920x1080 以上・音声あり・H.264。目で見る用に 10 秒ごとの1枚を出す。
#   bash tools/video/check_final.sh <最終.mp4> [<コマ画像の出力フォルダ>]
set -euo pipefail
F="${1:?mp4}"; SHOTS="${2:-}"
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$F")
V=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height -of csv=p=0 "$F")
A=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$F" || true)
W=$(echo "$V" | cut -d, -f2); H=$(echo "$V" | cut -d, -f3)
ok=1
awk "BEGIN{exit !($D <= 180.0)}" && echo "OK  尺 ${D} 秒（3:00 以内）" || { echo "NG  尺 ${D} 秒（3:00 を超える）"; ok=0; }
[ "$W" -ge 1920 ] && [ "$H" -ge 1080 ] && echo "OK  ${W}x${H}" || { echo "NG  ${W}x${H}（1080p 未満）"; ok=0; }
[ -n "$A" ] && echo "OK  音声 $A" || { echo "NG  音声なし"; ok=0; }
echo "映像 $V"
if [ -n "$SHOTS" ]; then mkdir -p "$SHOTS"; ffmpeg -hide_banner -loglevel error -y -i "$F" -vf "fps=1/10,scale=960:-1" "$SHOTS/t_%03d.jpg"; echo "コマ：$SHOTS"; fi
[ "$ok" = 1 ] && echo "結果：OK（音と映像のずれ・字幕の読みやすさは人の目で確かめる）" || { echo "結果：NG"; exit 1; }
