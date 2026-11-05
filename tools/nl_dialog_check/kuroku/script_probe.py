import sys, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1]); sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T
from voice_teaching import sim
CP = (ROOT / "samples/dummy/DEMO_C_PLACE.JBI").read_bytes()
EXP = [T.answer("この位置へ動く動作です。", (21,22,23,24,25,26)) for _ in range(3)]
V5 = ["Zプラス方向に5mm","Zプラス方向に5ミリ","Zプラス方向に5㎜","Zプラス方向に５ｍｍ","zプラス方向に5mm","Z+方向に5mm","Z＋方向に5mm",
      "ゼットプラス方向に5ミリ","ぜっとぷらす方向に5ミリ","Zプラスほうこうに5ミリ","Zプラス方向に5mm。","Zプラス方向に 5 mm","Z プラス 方向に 5mm",
      "Zプラス方向へ5mm","Zプラス方向に5mm動かして","Zプラス方向に5mm動かしてください","Zプラスに5mm","Zプラス5mm","Zプラス方向5mm",
      "C00005をZプラス方向に5mm","えーとZプラス方向に5mm","Zプラス方向に5mmです","Zプラス方向に5ミリメートル","Zプラス方向に五ミリ","Zプラス方向に5",
      "Zプラス方向に5センチ","Zプラス方向に0.5mm","Zプラス方向に5.0mm","Zプラス方向に15mm","Zぷらす方向に5ミリ","ジープラス方向に5ミリ"]
V30 = ["Zプラス方向に30mm","Zプラス方向に30ミリ","Zプラス方向に３０ｍｍ","ゼットプラス方向に30ミリ","Zプラス方向に三十ミリ","Zプラス方向に20mm","Zプラス方向に21mm","Zプラス方向に20.001mm"]
def one(t):
    with tempfile.TemporaryDirectory() as d:
        sim.DEFAULT_OUT_DIR = Path(d)/"out"
        w, f = T.flow(Path(d), *EXP)
        sid = w.load(CP)["session_id"]; w.select(sid, "C00005")
        r = w.talk(sid, t); st = w.state(sid)["state"]; c = st.get("candidate")
        m = ((r.get("hear") or {}).get("message") or (r.get("ask") or {}).get("reply") or r.get("message") or "")
        return (c and (c.get("summary") or c.get("target"))), st.get("can_approve"), r.get("via"), len(f.requests), m[:110]
for t in V5 + V30:
    c, a, via, api, m = one(t)
    print(f"{t!r:42} cand={'Y' if c else '-'} appr={a} via={via} api={api} | {m}")
