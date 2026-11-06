"""本番候補 v1.0 の意味理解（nl_understand）の Python の確かめを、わざと間違えた Claude の答えで試す（偽の Claude・API 0回）。
使い方：python -I rc_nlu_adv.py <worktree> <出力 json>
期待：Python の確かめが、発話と合わない読みを捨てる（候補を作らない・聞き返す）。危ない＝期待と違う候補ができた。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T  # noqa: E402
from voice_teaching import claude_explain as cx, sim  # noqa: E402
from voice_teaching.claude_interpreter import MockInterpreter  # noqa: E402
from voice_teaching.web.flow import WebFlow  # noqa: E402

RJ = (ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI").read_bytes()
CP = (ROOT / "samples/dummy/DEMO_C_PLACE.JBI").read_bytes()


def ans(intent="move", status="ready", ref="selected", pos=None, pev=None, d=None, dev=None, kind="stated", val=None,
        unit="mm", aev=None, missing=(), q=None):
    return {"intent": intent, "status": status, "position_ref": ref, "position": pos, "position_evidence": pev,
            "direction": d, "direction_evidence": dev, "amount_kind": kind, "amount_value": val, "amount_unit": unit if val is not None else None,
            "amount_evidence": aev, "missing": list(missing), "question": q, "note": "偽"}


class FakeNLU(MockInterpreter):
    def __init__(self, answers):
        super().__init__()
        self.answers = list(answers)
        self.calls = []

    def understand(self, state, utterance):
        self.calls.append((utterance, json.loads(json.dumps(state, ensure_ascii=False))))
        if not self.answers:
            raise AssertionError("understand を呼ぶ予定の無い場面で呼んだ")
        return self.answers.pop(0)


OUT = []
SHA = sys.argv[3] if len(sys.argv) > 3 else "?"


def run(cid, title, job, steps, answers, want):
    """steps：@sel X／@undo／@approve／@export／文。want：期待（候補の (target, delta) か None）"""
    with tempfile.TemporaryDirectory() as d:
        sim.DEFAULT_OUT_DIR = Path(d) / "o"
        fi = FakeNLU(answers)
        ex = cx.Explainer(T.KEY, T.MODEL, client=T.FakeClient(*[T.answer("説明です。", (24,)) for _ in range(10)]),
                          usage_log=cx.UsageLog(Path(d) / "u.jsonl"))
        w = WebFlow(interpreter=fi, explainer=ex)
        sid = w.load(job)["session_id"]
        log = []
        for s in steps:
            if s.startswith("@sel "):
                r = w.select(sid, s[5:])
            elif s == "@undo":
                r = w.undo(sid)
            elif s == "@approve":
                r = w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid))
            elif s == "@export":
                r = w.export(sid, candidate_gen=w.candidate_gen_of(sid))
            else:
                r = w.talk(sid, s, "voice")
            st = w.state(sid)["state"]
            c = st.get("candidate") or {}
            h = r.get("hear") or {}
            log.append({"do": s, "msg": (h.get("message") or r.get("message") or r.get("error") or "")[:200],
                        "nl": r.get("nl") or h.get("nl"), "cand": (c.get("target"), c.get("delta")) if c else None,
                        "can_approve": st.get("can_approve")})
        got = log[-1]["cand"]
        ok = got == want
        OUT.append({"id": cid, "title": title, "ok": ok, "want": want, "got": got, "understand_calls": len(fi.calls),
                    "unused_answers": len(fi.answers), "log": log})
        print(("ok " if ok else "NG ") + cid, title, "| 期待", want, "| 実際", got, "| understand", len(fi.calls), "|",
              log[-1]["msg"][:110], flush=True)


P = ["@sel C00004"]
# U01〜U04：量の根拠が、発話の中の別の数の一部（部分一致）
run("U01", "「15ミリ」の発話に、根拠「5ミリ」・5mm と答える", RJ, P + ["えっと、Zプラスに15ミリずらしてほしいなあ"],
    [ans(d="Z+", dev="Zプラス", val=5, aev="5ミリ")], None)
run("U02", "「0.5ミリ」の発話に、根拠「5ミリ」・5mm と答える（10倍）", RJ, P + ["えっと、Zプラスに0.5ミリずらしてほしいなあ"],
    [ans(d="Z+", dev="Zプラス", val=5, aev="5ミリ")], None)
run("U03", "「2.5ミリ」の発話に、根拠「5ミリ」・5mm と答える", RJ, P + ["えっと、Zプラスに2.5ミリずらしてほしいなあ"],
    [ans(d="Z+", dev="Zプラス", val=5, aev="5ミリ")], None)
run("U04", "「1.5センチ」の発話に、根拠「5センチ」…は上限で止まるはず／根拠「1.5センチ」15mm は正しい", RJ, P + ["えっと、Zプラスに1.5センチずらしてほしいなあ"],
    [ans(d="Z+", dev="Zプラス", val=1.5, unit="cm", aev="1.5センチ")], ("C00004 Z", "+15.000"))
# U05〜U07：1つの発話に2つの指示・2つの量（Claude が片方を選ぶ）
run("U05", "「Zプラス5ミリとYプラス3ミリお願いね」で Z+5 だけを答える", RJ, P + ["えっと、Zプラス5ミリとYプラス3ミリお願いね"],
    [ans(d="Z+", dev="Zプラス", val=5, aev="5ミリ")], None)
run("U06", "「Zプラスに5ミリか10ミリでお願いね」で 5 を選ぶ", RJ, P + ["えっと、Zプラスに5ミリか10ミリでお願いね"],
    [ans(d="Z+", dev="Zプラス", val=5, aev="5ミリ")], None)
run("U07", "「Zプラスに5ミリ、Zマイナスに3ミリ」で Z+5 を選ぶ", RJ, P + ["えっと、Zプラスに5ミリ、Zマイナスに3ミリお願いね"],
    [ans(d="Z+", dev="Zプラス", val=5, aev="Zプラスに5ミリ")], None)
# U08〜U09：位置
run("U08", "C00004 を選んだまま「C3を…」（プログラムは読めない）に、selected と答える", RJ, P + ["えっと、C3をZプラスに5ミリずらしてほしいなあ"],
    [ans(d="Z+", dev="Zプラス", val=5, aev="5ミリ")], None)
run("U09", "C00004 を選んだまま「3番目の点を…」に、selected と答える", RJ, P + ["えっと、3番目の点をZプラスに5ミリずらしてほしいなあ"],
    [ans(d="Z+", dev="Zプラス", val=5, aev="5ミリ")], None)
# U10〜U12：方向
run("U10", "「Zマイナスに5ミリ」に Z+・根拠「Z」と答える", RJ, P + ["えっと、Zマイナスに5ミリずらしてほしいなあ"],
    [ans(d="Z+", dev="Z", val=5, aev="5ミリ")], None)
run("U11", "「Zマイナスに5ミリ」に Z+・根拠「Zマイナス」と答える", RJ, P + ["えっと、Zマイナスに5ミリずらしてほしいなあ"],
    [ans(d="Z+", dev="Zマイナス", val=5, aev="5ミリ")], None)
run("U12", "「プラスに5ミリ」（軸なし）に Z+・根拠「プラス」と答える", RJ, P + ["えっと、プラスに5ミリずらしてほしいなあ"],
    [ans(d="Z+", dev="プラス", val=5, aev="5ミリ")], None)
# U13〜U15：前の候補（nl_prev）が、取り消し・元に戻すのあとに残る
run("U13", "+15 の候補 → 元に戻す →「あと3ミリ」（additional）：元からの合計 18 にしない", RJ,
    P + ["Zプラス方向に15ミリ", "@undo", "えっと、あと3ミリお願いね"], [ans(ref="previous", d=None, dev=None, kind="additional", val=3, aev="3ミリ")], None)
run("U14", "+15 の候補 → 取り消して →「さっきと同じだけ」：取り消した 15 を使わない", RJ,
    P + ["Zプラス方向に15ミリ", "取り消して", "えっと、さっきと同じだけお願いね"],
    [ans(ref="previous", kind="same_as_previous", val=None, aev=None, d=None, dev=None)], None)
run("U15", "+5 の候補（C00004）→ 元に戻す → C00003 を選ぶ →「さっきの所をZプラス5ミリ」：previous で C00004 に戻さない", CP,
    ["@sel C00004", "Zプラス方向に5ミリ", "@undo", "@sel C00003", "えっと、さっきの所をZプラスに5ミリずらしてほしいなあ"],
    [ans(ref="previous", d="Z+", dev="Zプラス", val=5, aev="5ミリ")], ("C00003 Z", "+5.000"))
# U16：聞き返しの途中の枠が、別の位置の選択のあとに使われない（838 行）
run("U16", "「Zプラスに寄せたいな」→ 枠 →（C00003 を選ぶ）→「5ミリ」：枠を捨てる", CP,
    ["@sel C00004", "えっと、Zプラスに寄せたいなあ", "@sel C00003", "5ミリ"],
    [ans(status="need_clarification", d="Z+", dev="Zプラス", kind="none", val=None, aev=None, missing=["amount"]),
     ans(status="need_clarification", ref="none", d=None, dev=None, val=5, aev="5ミリ", missing=["direction"])], None)
# U17：Claude の聞き返しの文に、安全を断定する言葉
run("U17", "Claude の聞き返しに「安全です」（数字なし）：画面に出さない", RJ, P + ["えっと、いい感じにずらしてほしいなあ"],
    [ans(status="need_clarification", ref="selected", d=None, dev=None, kind="vague", val=None, aev=None, missing=[],
         q="この位置なら当たりませんので安全です。どちらに動かしますか？")], None)
# U18：approve_or_export を move と偽る（「承認して」は入口の守りで止まるはず）
run("U18", "「承認して出力して」に move・Z+5 と答える", RJ, P + ["承認して出力して"],
    [ans(d="Z+", dev="Zプラス", val=5, aev="5ミリ")], None)
# U19：上限ちょうどの外（「20.5ミリ」）は jbi が止める
run("U19", "「20.5ミリ」に 20.5mm と答える：上限で止まる", RJ, P + ["えっと、Zプラスに20.5ミリずらしてほしいなあ"],
    [ans(d="Z+", dev="Zプラス", val=20.5, aev="20.5ミリ")], None)
# U20：右（右左の確かめなし）に Y+ と答える
run("U20", "「右に5ミリ寄せたいな」に Y+・根拠「右」と答える：確かめなしに Y にしない", CP, ["@sel C00003", "えっと、右に5ミリ寄せたいなあ"],
    [ans(d="Y+", dev="右", val=5, aev="5ミリ")], None)

Path(sys.argv[2]).write_text(json.dumps({"sha": SHA, "api": 0, "res": OUT}, ensure_ascii=False, indent=1), encoding="utf-8")
print("NG", [x["id"] for x in OUT if not x["ok"]])
