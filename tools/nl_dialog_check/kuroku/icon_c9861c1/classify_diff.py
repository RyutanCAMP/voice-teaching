"""クローク：stale.classify の判定を2つの版で比べる（API 0回）。python classify_diff.py <前の wt> <後の wt>"""
import sys, subprocess, json
PH = """C00005、Zプラス方向に30ミリ|C00005、Zプラス方向に5ミリ|Zプラス方向に5ミリ|Zプラスに十ミリ|C00005を選んで|これでいい|このままでいい|はい|いいよ|OK|お願いします|出力して|承認したい|いやです|いやだ|いやいや|いや、まあいいか|いやー、いい感じ|いやあ、すごい|いやほんとに|いいや|いえいえ|いえ、大丈夫です|家の前|嫌です|上に5ミリ|下に3ミリ|上がりすぎ？|上ってどっち？|前の位置に戻すの？|後で出力する|右から見せて|左の図|逆方向に5ミリ|Zマイナス方向、つまり逆に5ミリ|反対側から見せて|逆さまに見える|逆光で見えない|反対の意味？|プラスだった？|そうだった|5ミリだったよね？|さっきは何ミリだった？|確認だった|良かった|ありがとうございました|わかった|やった|やったー|できた|C00004も見たい|X方向はどっち|Yの範囲は？|ワイヤーは関係ある？|プラスとマイナスはどっち？|いや上|いやX|いやC00003|いえZプラス3ミリ|あいや|ばいやー|ハイヤー|タイヤ|いやなら取り消して|いやじゃない|やなくて|何をしてるか教えて|ちょっと待って|違くない？|取り消して|やっぱり3ミリ|ごめん、マイナスじゃなくてプラスだった|さっきの3回じゃなくて2回|変更は取り消して、何してるか教えて""".split("|")
code = r'''
import sys, json
sys.path.insert(0, sys.argv[1])
from voice_teaching import stale
out = {}
for p in json.loads(open(sys.argv[2], encoding="utf-8").read()):
    v = stale.classify(p)
    out[p] = [v.kind, getattr(v, "rule", None)]
print(json.dumps(out, ensure_ascii=False))
'''
import tempfile, os
fd, PF = tempfile.mkstemp(suffix=".json"); os.close(fd)
open(PF, "w", encoding="utf-8").write(json.dumps(PH, ensure_ascii=False))
res = []
for wt in sys.argv[1:3]:
    r = subprocess.run([sys.executable, "-I", "-X", "utf8", "-c", code, wt, PF], capture_output=True, text=True, encoding="utf-8")
    if r.returncode: print(r.stderr); sys.exit(1)
    res.append(json.loads(r.stdout))
ch = 0
for p in PH:
    a, b = res[0][p], res[1][p]
    mark = "  変化" if a != b else ""
    ch += a != b
    print(f"{p} | {a[0]}({a[1]}) -> {b[0]}({b[1]}){mark}")
print("変わった数:", ch, "/", len(PH))
