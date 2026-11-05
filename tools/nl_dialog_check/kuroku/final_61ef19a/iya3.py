import sys, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T
from voice_teaching import sim
CP = (ROOT / "samples/dummy/DEMO_C_PLACE.JBI").read_bytes()
F = [T.answer("この位置へ動く動作です。", (21,22,23,24,25,26)) for _ in range(10)]
P = ["いやYプラス10ミリ","いや Yプラス10ミリ","いや、Yプラス10ミリ","いやいやYプラス10ミリ","あ、いやYプラス10ミリ","違うYプラス10ミリ","ちがうYプラス10ミリ",
     "ごめんYプラス10ミリ","やっぱYプラス10ミリ","じゃなくてYプラス10ミリ","いやC00003をYプラス10ミリ","いやX","いやYプラス","いやプラス10ミリ","いや10ミリプラス",
     "いや、Yプラス","違う、Yプラス","いやいや、プラス","いや上に","いやワイプラス10ミリ","いやYのプラス方向に10ミリ","Yプラス10ミリ、いや","Yプラス10ミリの間違い",
     "Yプラス10ミリだった","プラスだった","プラスの間違い","マイナスやなくてプラス","マイナスじゃないプラス","逆だった","逆やった","符号が逆"]
bad = 0
for p in P:
  for approved in (True, False):
    with tempfile.TemporaryDirectory() as d:
        sim.DEFAULT_OUT_DIR = Path(d)/"o"
        w, _ = T.flow(Path(d), *F); sid = w.load(CP)["session_id"]; w.select(sid, "C00003"); w.talk(sid, "Yマイナス10mm")
        g0 = w.candidate_gen_of(sid)
        if approved: w.approve(sid, "QA", candidate_gen=g0)
        w.talk(sid, p); s = w.state(sid)["state"]; g = w.candidate_gen_of(sid)
        a = w.approve(sid, "QA", candidate_gen=g); e = w.export(sid, candidate_gen=g) if a.get("ok") else {}
        old = (s.get("candidate") or {}).get("delta") == "-10.000"
        flag = old and bool(e.get("ok"))
        bad += flag
        print("NG" if flag else "ok", "承認済" if approved else "未承認", p, "| 世代", g0, "->", g, "| hold", s.get("hold"), "| 古い Y-10 をボタンで再承認→出力", bool(e.get("ok")))
print("NG", bad, "/", 2*len(P))
