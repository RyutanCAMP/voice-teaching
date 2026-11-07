"""繰り返しの範囲の案内（FINAL_RC_REPEAT_RANGE_GUIDANCE_20261107）の安全の観点を、今の版で調べる（読むだけ）。
使い方：作業ツリー（固定の SHA）の直下で  python <this> <repo>
モックの解釈（MockInterpreter）・プロセスの中だけ。ネットワーク・ポートは使わない。出力は一時フォルダ。
"""
import json
import sys
import tempfile
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repo))
from voice_teaching import claude_interpreter as ci  # noqa: E402
from voice_teaching import sim  # noqa: E402
from voice_teaching.web.flow import WebFlow  # noqa: E402

sim.DEFAULT_OUT_DIR = Path(tempfile.mkdtemp()) / "sim"
DATA = (repo / "samples/dummy/DEMO_BUTTON_REPEAT.JBI").read_bytes()
NOREP = (repo / "samples/dummy/DEMO_PLACE.JBI").read_bytes()


def new(data=DATA):
    w = WebFlow(interpreter=ci.MockInterpreter(), updown_config=None)
    sid = w.load(data)["session_id"]
    return w, sid


def brief(r):
    st = r.get("state") or {}
    cand = st.get("candidate")
    rp = r.get("repeat") or r.get("repeat_confirm") or st.get("repeat_confirm") or st.get("pending_repeat")
    return {
        "status": r.get("status"),
        "message": (r.get("message") or "")[:220],
        "choices": [c.get("label", c) if isinstance(c, dict) else c for c in (r.get("choices") or [])][:4],
        "candidate": None if not cand else (cand.get("summary") or cand.get("title") or str(cand)[:120]),
        "approval": bool(st.get("approval")),
        "can_export": st.get("can_export"),
        "repeat_pending": None if not rp else str(rp)[:200],
    }


def say(w, sid, text):
    return brief(w.hear(sid, text))


out = {}
CASES = ["C1C4を2回繰り返したい", "C00001からC00004を2回繰り返したい", "2回繰り返したい", "繰り返したい",
         "回数を変えたい", "もう1回", "もう1回増やして", "3回にして", "2回から3回にして", "2回から2回にして",
         "3回から4回にして", "4回にして", "反復を増やして", "C1からC3を3回にして", "C00001からC00003の作業を2回から3回にして"]
for t in CASES:
    w, sid = new()
    out[t] = say(w, sid, t)

w, sid = new(NOREP)
out["[DEMO_PLACE] 3回にして"] = say(w, sid, "3回にして")
w, sid = new(NOREP)
out["[DEMO_PLACE] 繰り返したい"] = say(w, sid, "繰り返したい")

print(json.dumps(out, ensure_ascii=False, indent=1))
