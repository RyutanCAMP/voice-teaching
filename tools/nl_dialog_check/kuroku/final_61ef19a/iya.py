import sys, json, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T
from voice_teaching import sim, stale
CP = (ROOT / "samples/dummy/DEMO_C_PLACE.JBI").read_bytes()
F = [T.answer("この位置へ動く動作です。", (21,22,23,24,25,26)) for _ in range(10)]
for make in ("Yマイナス10mm", "Zプラス方向に5ミリ"):
  for p in ["いやプラス","いや、プラス","いやマイナス","いやYプラス","やっぱりプラス","ちがう、プラス","プラスで","いやプラスで","いや逆","いやZマイナス","ごめんプラス","じゃなくてプラス","マイナスじゃなくてプラス","いや上","いや下"]:
    for approved in (False, True):
      with tempfile.TemporaryDirectory() as d:
        sim.DEFAULT_OUT_DIR = Path(d)/"o"
        w, _ = T.flow(Path(d), *F); sid = w.load(CP)["session_id"]; w.select(sid, "C00003"); w.talk(sid, make)
        g0 = w.candidate_gen_of(sid); c0 = (w.state(sid)["state"].get("candidate") or {}).get("delta")
        if approved: w.approve(sid, "QA", candidate_gen=g0)
        r = w.talk(sid, p); s = w.state(sid)["state"]; g = w.candidate_gen_of(sid)
        a = w.approve(sid, "QA", candidate_gen=g); e = w.export(sid, candidate_gen=g) if a.get("ok") else {}
        cls = None
        for fn in ("classify", "judge", "check"):
          if hasattr(stale, fn):
            try: cls = getattr(stale, fn)(p); break
            except Exception as ex: cls = repr(ex)[:40]
        print(make, "承認済" if approved else "未承認", p, "| 候補", c0, "→", (s.get("candidate") or {}).get("delta"), "hold", s.get("hold"), "| ボタン承認", a.get("ok"), "出力", e.get("ok"), "|", str(cls)[:60])
