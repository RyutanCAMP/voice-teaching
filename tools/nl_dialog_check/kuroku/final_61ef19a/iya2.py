import sys, json, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T
from voice_teaching import sim
CP = (ROOT / "samples/dummy/DEMO_C_PLACE.JBI").read_bytes()
F = [T.answer("この位置へ動く動作です。", (21,22,23,24,25,26)) for _ in range(10)]
def msg(r):
    h=r.get("hear") or {}; a=r.get("ask") or {}
    return " / ".join(str(x) for x in (h.get("message"), a.get("reply"), r.get("message") if isinstance(r.get("message"),str) else None) if x)
for approved in (True, False):
  for p in ["いやYプラス","いやZマイナス","いやプラス","いやYプラス10ミリ","いやYプラス方向に10ミリ","やっぱりYプラス10ミリ","いやYマイナス5ミリ"]:
    with tempfile.TemporaryDirectory() as d:
        sim.DEFAULT_OUT_DIR = Path(d)/"o"
        w, _ = T.flow(Path(d), *F); sid = w.load(CP)["session_id"]; w.select(sid, "C00003"); w.talk(sid, "Yマイナス10mm")
        g0 = w.candidate_gen_of(sid)
        if approved: w.approve(sid, "QA", candidate_gen=g0)
        r = w.talk(sid, p); s = w.state(sid)["state"]; g = w.candidate_gen_of(sid)
        e0 = w.export(sid, candidate_gen=g)
        a = w.approve(sid, "QA", candidate_gen=g); e = w.export(sid, candidate_gen=g) if a.get("ok") else {}
        body = Path(e["path"]).read_text(encoding="utf-8", errors="replace") if e.get("ok") else ""
        print("承認済" if approved else "未承認", p, "| gen", g0, "->", g, "| 候補", (s.get("candidate") or {}).get("target"), (s.get("candidate") or {}).get("delta"), "| 承認し直さず出力", e0.get("ok"), "| ボタン再承認", a.get("ok"), "→出力", e.get("ok"))
        print("   返事：", msg(r)[:230]); print("   状態：", str(s.get("status_line") or "")[:120])
