"""同時の操作（モック・API 0回）：出力2つ同時・出力と取り消し・出力と読み直し・承認と言い直し。各 40 回。"""
import sys, tempfile, threading
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T
from voice_teaching import sim
RJ = (ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI").read_bytes(); BR = (ROOT / "samples/dummy/DEMO_BUTTON_REPEAT.JBI").read_bytes()
F = lambda: [T.answer("この位置へ動く動作です。", (24,)) for _ in range(20)]
def prep(d):
    sim.DEFAULT_OUT_DIR = Path(d) / "o"
    w, _ = T.flow(Path(d), *F()); sid = w.load(RJ)["session_id"]; w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice")
    return w, sid
def race(a, b):
    res = [None, None]; bar = threading.Barrier(2)
    def run(i, f):
        bar.wait()
        try: res[i] = f()
        except Exception as e: res[i] = {"CRASH": repr(e)[:120]}
    ts = [threading.Thread(target=run, args=(0, a)), threading.Thread(target=run, args=(1, b))]
    [t.start() for t in ts]; [t.join() for t in ts]; return res
stats = {}
def bump(k): stats[k] = stats.get(k, 0) + 1
for i in range(40):
    # R1 出力2つ同時
    with tempfile.TemporaryDirectory() as d:
        w, sid = prep(d); g = w.candidate_gen_of(sid); w.approve(sid, "QA", candidate_gen=g)
        r = race(lambda: w.export(sid, candidate_gen=g), lambda: w.export(sid, candidate_gen=g))
        n = sum(1 for x in r if x.get("ok")); bump(f"R1 ok={n} crash={any('CRASH' in x for x in r)}")
    # R2 出力と「取り消して」：出力できたなら、取り消しの返事より前（ファイルの中身は 185）。取り消しのあとの状態で出力できない
    with tempfile.TemporaryDirectory() as d:
        w, sid = prep(d); g = w.candidate_gen_of(sid); w.approve(sid, "QA", candidate_gen=g)
        r = race(lambda: w.export(sid, candidate_gen=g), lambda: w.talk(sid, "取り消して", "voice"))
        st = w.state(sid)["state"]; e2 = w.export(sid, candidate_gen=g)
        bump(f"R2 export={bool(r[0].get('ok'))} cand_after={bool(st.get('candidate'))} export_after={bool(e2.get('ok'))} crash={any('CRASH' in x for x in r)}")
    # R3 出力と、別の JOB の読み込み（previous）
    with tempfile.TemporaryDirectory() as d:
        w, sid = prep(d); g = w.candidate_gen_of(sid); w.approve(sid, "QA", candidate_gen=g)
        r = race(lambda: w.export(sid, candidate_gen=g), lambda: w.load(BR, previous=sid))
        e2 = w.export(sid, candidate_gen=g)
        bump(f"R3 export={bool(r[0].get('ok'))} export_after={bool(e2.get('ok'))} crash={any('CRASH' in x for x in r)}")
    # R4 承認と言い直し（いやZプラス3ミリ）：あとで古い Z+5 が出力できない
    with tempfile.TemporaryDirectory() as d:
        w, sid = prep(d); g = w.candidate_gen_of(sid)
        r = race(lambda: w.approve(sid, "QA", candidate_gen=g), lambda: w.talk(sid, "いやZプラス3ミリ", "voice"))
        e = w.export(sid, candidate_gen=g); st = w.state(sid)["state"]
        bump(f"R4 approve={bool(r[0].get('ok'))} old_export={bool(e.get('ok'))} approval_after={bool(st.get('approval'))} crash={any('CRASH' in x for x in r)}")
    # R5 承認と「ちょっと待って」：保留なのに承認が残って出力できる、が無いか
    with tempfile.TemporaryDirectory() as d:
        w, sid = prep(d); g = w.candidate_gen_of(sid)
        r = race(lambda: w.approve(sid, "QA", candidate_gen=g), lambda: w.talk(sid, "ちょっと待って", "voice"))
        st = w.state(sid)["state"]; e = w.export(sid, candidate_gen=g)
        bump(f"R5 approve={bool(r[0].get('ok'))} hold={st.get('hold')} export={bool(e.get('ok'))} crash={any('CRASH' in x for x in r)}")
for k in sorted(stats): print(k, stats[k])
