"""クローク：承認したあとに、何気ない一言で保留になるか（サーバーの流れ・モック・API 0回）。python after_approve_words.py <worktree>"""
import sys, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T  # noqa
from voice_teaching import sim  # noqa
CP = (ROOT / "samples" / "dummy" / "DEMO_C_PLACE.JBI").read_bytes()
for p in "やった|やったー|やった！|そうだった|逆光で見えない|ありがとう|はい|すごい|よし".split("|"):
    with tempfile.TemporaryDirectory() as d:
        sim.DEFAULT_OUT_DIR = Path(d) / "out"
        w, fake = T.flow(Path(d), *[T.answer("この位置へ動く動作です。", (21, 22, 23, 24, 25, 26)) for _ in range(10)])
        sid = w.load(CP)["session_id"]; w.select(sid, "C00005"); w.talk(sid, "Zプラス方向に5ミリ")
        g = w.candidate_gen_of(sid); w.approve(sid, "QA", candidate_gen=g)
        w.talk(sid, p)
        s = w.state(sid).get("state") or {}
        print(f"{p} | hold {s.get('hold')} | 承認 {'あり' if s.get('approval') else 'なし'} | can_export {s.get('can_export')} | 出力 {bool(w.export(sid, candidate_gen=w.candidate_gen_of(sid)).get('ok'))}")
