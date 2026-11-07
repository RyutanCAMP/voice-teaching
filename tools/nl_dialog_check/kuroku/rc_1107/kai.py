import sys, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); sys.path[:0] = [str(ROOT), str(ROOT / "tests")]; sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T
from voice_teaching import sim
for job, t in (("DEMO_BUTTON_REPEAT.JBI", "2階から3階にして"), ("DEMO_BUTTON_REPEAT.JBI", "C00001からC00003の作業を2階から3階にして"), ("DEMO_RJ_XYZ.JBI", "2階から3階にして"), ("DEMO_BUTTON_REPEAT.JBI", "3階に上げて")):
    with tempfile.TemporaryDirectory() as d:
        sim.DEFAULT_OUT_DIR = Path(d) / "o"; w, _ = T.flow(Path(d), *[T.answer("C00001〜C00003のくり返しを2回から3回にするご希望として受け取りました。", (21,)) for _ in range(5)])
        sid = w.load((ROOT / "samples/dummy" / job).read_bytes())["session_id"]; r = w.talk(sid, t, "voice"); st = w.state(sid)["state"]
        h = r.get("hear") or {}; a = r.get("ask") or {}
        print(job, t, "| range", bool(st.get("repeat_range")), "cand", (st.get("candidate") or {}).get("delta"), "|", (a.get("reply") or h.get("message") or r.get("error") or "")[:100])
