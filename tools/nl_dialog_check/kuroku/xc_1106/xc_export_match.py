"""承認した内容と出力の中身が一致するか（言い直し・回数・読み直しのあと）。モック・API 0回。"""
import sys, tempfile, re
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T
from voice_teaching import sim
RJ = (ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI").read_bytes(); BR = (ROOT / "samples/dummy/DEMO_BUTTON_REPEAT.JBI").read_bytes()
def z4(b): return [l for l in b.decode("ascii").splitlines() if l.startswith("C00004=")][0].split(",")[2]
CASES = [
 ("+5 承認 → Zプラス方向に3ミリ → 承認 → 出力", ["Zプラス方向に5ミリ", "@a", "Zプラス方向に3ミリ", "@a", "@e"], "183.000"),
 ("+5 承認 → Zマイナス方向に5ミリ → 承認 → 出力", ["Zプラス方向に5ミリ", "@a", "Zマイナス方向に5ミリ", "@a", "@e"], "175.000"),
 ("+5 承認 → いやZプラス3ミリ → Zプラス方向に3ミリ → 承認 → 出力", ["Zプラス方向に5ミリ", "@a", "いやZプラス3ミリ", "Zプラス方向に3ミリ", "@a", "@e"], "183.000"),
 ("+5 → 元に戻す → +10 → 承認 → 出力", ["Zプラス方向に5ミリ", "@u", "Zプラス方向に10ミリ", "@a", "@e"], "190.000"),
 ("+5 承認 → ちょっと待って → このままでいい → 承認 → 出力", ["Zプラス方向に5ミリ", "@a", "ちょっと待って", "このままでいい", "@a", "@e"], "185.000"),
 ("+5 承認 → 3ミリにして → Zプラス方向に3ミリ → 承認 → 出力", ["Zプラス方向に5ミリ", "@a", "3ミリにして", "Zプラス方向に3ミリ", "@a", "@e"], "183.000"),
 ("Zプラス10ミリ、いや5ミリ → ボタン → 承認 → 出力", ["Zプラス10ミリ、いや5ミリ", "@b", "@a", "@e"], "185.000"),
]
for title, steps, want in CASES:
    with tempfile.TemporaryDirectory() as d:
        sim.DEFAULT_OUT_DIR = Path(d) / "o"
        w, _ = T.flow(Path(d), *[T.answer("説明です。", (24,)) for _ in range(10)])
        sid = w.load(RJ)["session_id"]; w.select(sid, "C00004"); last = {}; ok = True; note = ""
        for s in steps:
            if s == "@a": last = w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid))
            elif s == "@e": last = w.export(sid, candidate_gen=w.candidate_gen_of(sid))
            elif s == "@u": last = w.undo(sid)
            elif s == "@b":
                ch = (last.get("hear") or {}).get("choices") or []
                last = w.hear(sid, ch[0]["text"], "text") if ch else {"error": "ボタンなし"}
            else: last = w.talk(sid, s, "voice")
        f = last.get("file_name")
        got = z4((Path(d) / "o" / f).read_bytes()) if f else None
        print(("OK " if got == want else "NG ") + title, "| 期待", want, "| 出力", got, "|", "" if f else str(last.get("error") or last.get("message"))[:120])
# 回数 2→3 を承認 → 出力：命令が3つ増える
with tempfile.TemporaryDirectory() as d:
    sim.DEFAULT_OUT_DIR = Path(d) / "o"
    w, _ = T.flow(Path(d), *[T.answer("説明です。", (24,)) for _ in range(10)])
    sid = w.load(BR)["session_id"]; w.talk(sid, "C00001からC00003の作業を2回から3回にして", "voice")
    rr = w.state(sid)["state"]["repeat_range"]; w.repeat_choose(sid, "yes", rr["turn"])
    w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid)); e = w.export(sid, candidate_gen=w.candidate_gen_of(sid))
    b = (Path(d) / "o" / e["file_name"]).read_bytes().decode("ascii")
    n = len([l for l in b.splitlines() if re.match(r"MOVL C0000[123] ", l)])
    print(("OK " if n == 9 else "NG ") + "回数 2→3：MOVL C00001〜C00003 の行", n, "（期待 9）")
