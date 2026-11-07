"""上限 20mm と元の JOB が変わらないことの確かめ（偽の Claude・API 0回）。
使い方：python -I cap_orig.py <worktree> <出力 json> [SHA]
- 正直な Claude の答え（発話の量・単位・根拠をそのまま返す）で、上限の内と外を試す
- 1回の変更の上限は 20mm（jbi.DEFAULT_MAX_SHIFT_MM）。20 までは候補、20 を超えたら候補を作らない、を期待とする
- 承認・書き出しのあと、samples の元の JOB のバイトが変わらないこと、書き出しの名前が元の名前と違うこと
"""
from __future__ import annotations
import hashlib, json, sys, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T  # noqa: E402
from voice_teaching import claude_explain as cx, sim  # noqa: E402
from voice_teaching.claude_interpreter import MockInterpreter  # noqa: E402
from voice_teaching.web.flow import WebFlow  # noqa: E402

SAMPLES = {p.name: p for p in (ROOT / "samples/dummy").glob("*.JBI")}
BEFORE = {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in SAMPLES.items()}
RJ = SAMPLES["DEMO_RJ_XYZ.JBI"].read_bytes()

def ans(d, dev, val, unit, aev):
    return {"intent": "move", "status": "ready", "position_ref": "selected", "position": None, "position_evidence": None,
            "direction": d, "direction_evidence": dev, "amount_kind": "stated", "amount_value": val, "amount_unit": unit,
            "amount_evidence": aev, "missing": [], "question": None, "note": "偽"}

class FakeNLU(MockInterpreter):
    def __init__(self, answers): super().__init__(); self.answers = list(answers); self.calls = 0
    def understand(self, state, utterance):
        self.calls += 1
        return self.answers.pop(0) if self.answers else ans(None, None, None, None, None) | {"status": "need_clarification", "amount_kind": "none"}

OUT = []
def run(cid, utt, answer, want, fake=True):
    with tempfile.TemporaryDirectory() as d:
        sim.DEFAULT_OUT_DIR = Path(d) / "o"
        ex = cx.Explainer(T.KEY, T.MODEL, client=T.FakeClient(*[T.answer("説明です。", (24,)) for _ in range(10)]),
                          usage_log=cx.UsageLog(Path(d) / "u.jsonl"))
        w = WebFlow(interpreter=FakeNLU([answer] if answer else []) if fake else MockInterpreter(), explainer=ex)
        sid = w.load(RJ)["session_id"]; w.select(sid, "C00004")
        r = w.talk(sid, utt, "voice")
        st = w.state(sid)["state"]; c = st.get("candidate") or {}
        got = (c.get("target"), c.get("delta")) if c else None
        exp_name = None; exp_ok = None
        if got:
            w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid))
            e = w.export(sid, candidate_gen=w.candidate_gen_of(sid))
            exp_name = e.get("file_name")
            exp_ok = bool(exp_name) and exp_name != "DEMO_RJ_XYZ.JBI" and exp_name.startswith("DEMO_RJ_XYZ_SIM_")
        msg = ((r.get("hear") or {}).get("message") or r.get("message") or r.get("error") or "")[:140]
        ok = (got == want) and (exp_ok in (None, True))
        OUT.append({"id": cid, "utt": utt, "fake_nlu": fake, "want": want, "got": got, "export": exp_name, "ok": ok, "msg": msg})
        print(("ok " if ok else "NG ") + cid, utt, "| 期待", want, "| 実際", got, "| 出力", exp_name, "|", msg[:90], flush=True)

Z = "C00004 Z"
run("C01", "Zプラスに19.9ミリずらして", ans("Z+", "Zプラス", 19.9, "mm", "19.9ミリ"), (Z, "+19.900"))
run("C02", "Zプラスに20ミリずらして", ans("Z+", "Zプラス", 20, "mm", "20ミリ"), (Z, "+20.000"))
run("C03", "Zプラスに20.001ミリずらして", ans("Z+", "Zプラス", 20.001, "mm", "20.001ミリ"), None)
run("C04", "Zプラスに20.1ミリずらして", ans("Z+", "Zプラス", 20.1, "mm", "20.1ミリ"), None)
run("C05", "Zプラスに21ミリずらして", ans("Z+", "Zプラス", 21, "mm", "21ミリ"), None)
run("C06", "Zマイナスに21ミリずらして", ans("Z-", "Zマイナス", 21, "mm", "21ミリ"), None)
run("C07", "Zプラスに2センチずらして", ans("Z+", "Zプラス", 2, "cm", "2センチ"), (Z, "+20.000"))
run("C08", "Zプラスに2.1センチずらして", ans("Z+", "Zプラス", 2.1, "cm", "2.1センチ"), None)
run("C09", "Zプラスに0.03メートルずらして", ans("Z+", "Zプラス", 0.03, "m", "0.03メートル"), None)
run("C10", "Zプラスに二十一ミリずらして", ans("Z+", "Zプラス", 21, "mm", "二十一ミリ"), None)
run("C11", "Zプラスに２１ミリずらして", ans("Z+", "Zプラス", 21, "mm", "２１ミリ"), None)
run("C12", "Zプラスに100ミリずらして", ans("Z+", "Zプラス", 100, "mm", "100ミリ"), None)
run("C13", "Zプラスに1e2ミリずらして", ans("Z+", "Zプラス", 100, "mm", "1e2ミリ"), None)
# Claude が上限の外の量を、上限の中に縮めて答える（発話は 30）
run("C14", "Zプラスに30ミリずらして", ans("Z+", "Zプラス", 20, "mm", "30ミリ"), None)
run("C15", "Zプラスに30ミリずらして", ans("Z+", "Zプラス", 20, "mm", "20ミリ"), None)
# 決まった言い方（Claude を使わない経路）
for i, (u, want) in enumerate([("Zプラス方向に20ミリ", (Z, "+20.000")), ("Zプラス方向に21ミリ", None), ("Zマイナス方向に20.5ミリ", None),
                                ("Zプラス方向に30ミリ", None), ("Xプラス方向に25ミリ", None), ("Yマイナス方向に20ミリ", ("C00004 Y", "-20.000"))], 1):
    run(f"M{i:02d}", u, None, want, fake=False)

AFTER = {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in SAMPLES.items()}
same = BEFORE == AFTER
print(("ok " if same else "NG ") + "元の JOB（samples/dummy の", len(SAMPLES), "個）のバイトが変わらない")
Path(sys.argv[2]).write_text(json.dumps({"sha": sys.argv[3] if len(sys.argv) > 3 else "?", "api": 0, "orig_unchanged": same,
                                         "res": OUT}, ensure_ascii=False, indent=1), encoding="utf-8")
