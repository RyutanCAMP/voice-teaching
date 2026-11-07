#!/usr/bin/env bash
# 動画の部品（素材に依らないもの）を ffmpeg で作る（クーちゃん 11/7）。アプリ・実機には何もしない。
#   bash tools/video/make_parts.sh <出力フォルダ> [日本語フォントのファイル]
# 作るもの（1920x1080・30fps・H.264・無音の AAC。Clipchamp などにそのまま入れられる）：
#   endroll.mp4  … docs/video/endroll_ja.txt を黒地に白で下から上へ（ENDROLL_SEC 秒・既定 12）
#   title.mp4    … 「VOICE TEACHING」と副題（フェードイン・アウト 9 秒）
#   source_note.png … 出典の文字（透明の背景・画面の下に重ねる用）
# Windows：ffmpeg を入れて Git Bash で動かす。フォントは例 "C:/Windows/Fonts/YuGothB.ttc" を2つ目に渡す。
set -euo pipefail
OUT="${1:?出力フォルダ}"
FONT="${2:-/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf}"
SEC="${ENDROLL_SEC:-12}"
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$OUT"
[ -f "$FONT" ] || { echo "フォントが見つかりません：$FONT" >&2; exit 1; }
# エンドロール：文字の高さを測らず、行の数から動かす距離を決める（1行 54px）
LINES=$(wc -l < "$HERE/docs/video/endroll_ja.txt")
TEXT_H=$((LINES * 54))
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "color=c=black:s=1920x1080:r=30:d=$SEC" \
  -f lavfi -i "anullsrc=r=48000:cl=stereo" -t "$SEC" \
  -vf "drawtext=fontfile='$FONT':textfile='$HERE/docs/video/endroll_ja.txt':fontcolor=white:fontsize=40:line_spacing=14:x=(w-text_w)/2:y=h-(h+$TEXT_H)*t/$SEC" \
  -c:v libx264 -pix_fmt yuv420p -crf 18 -c:a aac -shortest "$OUT/endroll.mp4"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "color=c=black:s=1920x1080:r=30:d=9" \
  -f lavfi -i "anullsrc=r=48000:cl=stereo" -t 9 \
  -vf "drawtext=fontfile='$FONT':text='VOICE TEACHING':fontcolor=white:fontsize=120:x=(w-text_w)/2:y=(h-text_h)/2-40:alpha='if(lt(t,1.5),t/1.5,if(gt(t,7.5),(9-t)/1.5,1))',drawtext=fontfile='$FONT':text='声で、ロボットの動きを変える。':fontcolor=0xC8D6F0:fontsize=44:x=(w-text_w)/2:y=(h)/2+70:alpha='if(lt(t,2.5),max(0,(t-1)/1.5),if(gt(t,7.5),(9-t)/1.5,1))'" \
  -c:v libx264 -pix_fmt yuv420p -crf 18 -c:a aac -shortest "$OUT/title.mp4"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "color=c=black@0.0:s=1920x80,format=rgba" -frames:v 1 \
  -vf "drawtext=fontfile='$FONT':text='出典：IFR World Robotics 2026（2025年末・世界の稼働台数）／関東経済産業局 ロボットSIer人材調査（2017年度）':fontcolor=white@0.85:fontsize=24:x=40:y=(h-text_h)/2" \
  "$OUT/source_note.png"
for f in endroll.mp4 title.mp4; do
  printf '%s  ' "$f"; ffprobe -v error -show_entries format=duration:stream=codec_name,width,height -of csv=p=0 "$OUT/$f" | tr '\n' ' '; echo
done
echo "出力：$OUT"
