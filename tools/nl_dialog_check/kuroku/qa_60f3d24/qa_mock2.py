"""qa_mock の続き（モック・API 0回）：JOB の形の深掘りと、SIM 出力を読み直す連鎖。
使い方：python -I qa_mock2.py <worktree>
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T  # noqa: E402
from voice_teaching import sim  # noqa: E402

RJ = (ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI").read_bytes()
F = lambda: [T.answer("この位置へ動く動作です。", (24, 25)) for _ in range(30)]  # noqa: E731


def try_job(name, data, d):
    sim.DEFAULT_OUT_DIR = Path(d) / "out"
    w, _ = T.flow(Path(d), *F())
    r = w.load(data)
    sid = r.get("session_id")
    if not sid:
        print(name, "refused", (r.get("error") or "")[:80]); return None
    w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice")
    st = w.state(sid)["state"]
    out = None
    if st.get("can_approve"):
        w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid))
        e = w.export(sid, candidate_gen=w.candidate_gen_of(sid))
        out = e.get("file_name") or e.get("error") or e.get("message")
        if e.get("file_name"):
            body = (Path(d) / "out" / e["file_name"]).read_bytes()
            out = (e["file_name"], len(body), body.count(b"/JOB"), body.count(b"\r\nEND"), body[-40:])
    print(name, "loaded", "can_approve", st.get("can_approve"), "export", out)
    return w, sid


with tempfile.TemporaryDirectory() as d:
    try_job("noEND", RJ.replace(b"\r\nEND\r\n", b"\r\n"), d)
with tempfile.TemporaryDirectory() as d:
    try_job("noNOP", RJ.replace(b"NOP\r\n", b""), d)
with tempfile.TemporaryDirectory() as d:
    try_job("twoJOB", RJ + RJ, d)
with tempfile.TemporaryDirectory() as d:
    try_job("trailing_garbage", RJ + b"MOVL C00004 V=60.0\r\n", d)
with tempfile.TemporaryDirectory() as d:
    try_job("after_END_instr", RJ.replace(b"END\r\n", b"END\r\nMOVL C00001 V=150.0\r\n"), d)
with tempfile.TemporaryDirectory() as d:
    try_job("tool1", RJ.replace(b"///TOOL 0", b"///TOOL 1"), d)
with tempfile.TemporaryDirectory() as d:
    try_job("V_huge", RJ.replace(b"MOVL C00004 V=60.0", b"MOVL C00004 V=99999.0"), d)
with tempfile.TemporaryDirectory() as d:
    try_job("V_zero", RJ.replace(b"MOVL C00004 V=60.0", b"MOVL C00004 V=0.0"), d)
with tempfile.TemporaryDirectory() as d:
    try_job("NPOS_wrong", RJ.replace(b"///NPOS 7", b"///NPOS 3"), d)
with tempfile.TemporaryDirectory() as d:
    try_job("posfar", RJ.replace(b"C00004=680.000,240.000,180.000", b"C00004=99999.000,240.000,180.000"), d)

# SIM 出力を読み直して重ねる：+15 → 出力 → 読み直し → +15 → 出力（元から 30mm）
with tempfile.TemporaryDirectory() as d:
    sim.DEFAULT_OUT_DIR = Path(d) / "out"
    w, _ = T.flow(Path(d), *F())
    data = RJ
    for i in range(3):
        sid = w.load(data)["session_id"]
        w.select(sid, "C00004"); r = w.talk(sid, "Zプラス方向に15ミリ", "voice")
        st = w.state(sid)["state"]
        if not st.get("can_approve"):
            print("chain", i, "can_approve False", (r.get("hear") or {}).get("message", "")[:120]); break
        w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid))
        e = w.export(sid, candidate_gen=w.candidate_gen_of(sid))
        if not e.get("file_name"):
            print("chain", i, "export refused", e.get("error") or e.get("message")); break
        data = (Path(d) / "out" / e["file_name"]).read_bytes()
        z = [l for l in data.decode("ascii").splitlines() if l.startswith("C00004=")]
        print("chain", i, e["file_name"], z)
