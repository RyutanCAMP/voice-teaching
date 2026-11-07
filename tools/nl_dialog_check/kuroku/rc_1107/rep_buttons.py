"""範囲の案内のボタン（モック）：選ぶ → 範囲の確かめ → 候補（未承認）→ 承認 → 出力。［今回は変更しない］。読み直し後の古いボタン。"""
import sys, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); sys.path[:0] = [str(ROOT), str(ROOT / "tests")]; sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T
from voice_teaching import sim
BR = (ROOT / "samples/dummy/DEMO_BUTTON_REPEAT.JBI").read_bytes()
def st(w, sid):
    s = w.state(sid)["state"]; c = s.get("candidate") or {}
    return f"range={bool(s.get('repeat_range'))} cand={(c.get('target'), c.get('delta')) if c else None} canA={s.get('can_approve')} appr={bool(s.get('approval'))}"
def ch(r): return (r.get("hear") or {}).get("choices") or r.get("choices") or []
for title, mode in (("選ぶ→確かめ→承認→出力", "go"), ("今回は変更しない", "no"), ("読み直し後の古い［選ぶ］", "reload"), ("選ぶだけで承認・出力しない", "onlysel")):
    with tempfile.TemporaryDirectory() as d:
        sim.DEFAULT_OUT_DIR = Path(d) / "o"; w, _ = T.flow(Path(d), *[T.answer("説明です。", (21,)) for _ in range(6)])
        sid = w.load(BR)["session_id"]; r = w.talk(sid, "C1C4を2回繰り返したい", "voice"); c = ch(r)
        labels = [x["label"] for x in c]
        print("==", title, "| ボタン", labels)
        pick = next((x for x in c if "範囲を確かめる" in x["label"]), None); no = next((x for x in c if "変更しない" in x["label"]), None)
        if mode == "no":
            r2 = w.hear(sid, no["text"], "text"); print("  ", st(w, sid), "|", ((r2.get("message") or (r2.get("hear") or {}).get("message") or ""))[:80]); continue
        if mode == "reload":
            sid2 = w.load(BR, previous=sid)["session_id"]
            r2 = w.hear(sid2, pick["text"], "text"); print("  新しい画面に古いボタンの文：", st(w, sid2), "|", (r2.get("message") or "")[:100])
            r3 = w.hear(sid, pick["text"], "text"); print("  前の画面：", (r3.get("message") or r3.get("error") or "")[:80]); continue
        r2 = w.hear(sid, pick["text"], "text"); print("  選んだあと", st(w, sid), "|", (r2.get("message") or "")[:90])
        if mode == "onlysel":
            e = w.export(sid, candidate_gen=w.candidate_gen_of(sid)); print("  承認せずに出力：", e.get("ok"), (e.get("error") or e.get("message") or "")[:70]); continue
        rr = w.state(sid)["state"].get("repeat_range")
        if rr: w.repeat_choose(sid, "yes", rr["turn"])
        print("  範囲の確かめのあと", st(w, sid))
        e0 = w.export(sid, candidate_gen=w.candidate_gen_of(sid)); print("  承認前の出力：", e0.get("ok"))
        w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid)); e = w.export(sid, candidate_gen=w.candidate_gen_of(sid))
        f = Path(d) / "o" / e["file_name"]; b = f.read_text("ascii")
        print("  出力", e["file_name"], "MOVL C0000[123] の行", sum(1 for l in b.splitlines() if l.startswith(("MOVL C00001", "MOVL C00002", "MOVL C00003"))))
