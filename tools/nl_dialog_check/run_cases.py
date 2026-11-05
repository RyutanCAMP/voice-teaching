"""自然な日本語の会話テスト（クロクラウドの独立検証 2026-11-05）。

- 普段ロボットを扱う人が話しそうな言い方を、単発と2〜4ターンの会話で確かめる
- **モックだけ**：解釈の係は MockInterpreter、Claude に聞く係は tests/test_claude_talk.py の偽の client
  （決めた答えを返す）。**実 Claude・実マイクは使っていない**。Claude の答えの中身の良し悪しは確かめていない
- ジョブは samples/dummy/ の合成ジョブだけ。出力先は一時フォルダ
- 判定：PASS（期待どおり）／FAIL（期待と違う）／ERROR（実行できなかった）。期待は「安全側を崩さずに、会話が成り立つこと」

実行：python tools/nl_dialog_check/run_cases.py [--json 出力先] [--md 出力先]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import test_claude_talk as T  # noqa: E402
from voice_teaching import jbi, sim, updown  # noqa: E402

BR = T.demo_bytes()  # DEMO_BUTTON_REPEAT.JBI（C00001〜C00003 を2回くり返す）
CP = (ROOT / "samples" / "dummy" / "DEMO_C_PLACE.JBI").read_bytes()  # C00003 = 400,-150,300
BLOCK = (21, 22, 23, 24, 25, 26)


def explain(text="同じ動きをくり返しています。" + T.ASKED):
    return T.answer(text, BLOCK)


def count(to=3, frm=2):
    return T.answer("回数のご希望ですね。", BLOCK, "change_request", {"kind": "repeat", "from_count": frm, "to_count": to})


# 1ケース：id・題・ジョブ・選ぶ位置・上下の向き（確認済みか）・ターン・偽の Claude の答え・期待
# ターン：("talk", 文) / ("press",)＝「この動きです」ボタン / ("range_yes",)＝［この範囲を繰り返す］
#         ("reload",)＝同じジョブを previous 付きで読み直す / ("approve_old",)＝読み直す前の番号で承認
#         ("repeat3",)＝回数の候補 2回→3回 を作る（準備） / ("select", 位置)
CASES = [
    # ---- 説明・質問 ----
    dict(id="N01", title="今何してる？", job=BR, turns=[("talk", "このロボット、今何してる？")], fake=[explain()],
         expect=dict(no_candidate=True, via="ask", reply_by="claude")),
    dict(id="N02", title="何回繰り返してるの？（数はプログラムが答えるべき）", job=BR,
         turns=[("talk", "何回繰り返してるの？")], fake=[explain("同じ動きを2回くり返しています。")],
         expect=dict(no_candidate=True, reply_has="2回")),
    dict(id="N03", title="変更するとどう動くの？（候補あり）", job=BR, turns=[("repeat3",), ("talk", "変更するとどう動くの？")],
         fake=[explain("くり返しが1回増え、同じ動きを続けます。")],
         expect=dict(candidate_kept=True, approvable=True, not_hidden=True)),
    dict(id="N04", title="何回から何回にする提案なの？（候補あり）", job=BR,
         turns=[("repeat3",), ("talk", "何回から何回にする提案なの？")], fake=[explain("承認待ちの変更候補は、くり返しの回数の変更です。")],
         expect=dict(candidate_kept=True, reply_has="3回")),
    # ---- 回数 ----
    dict(id="N05", title="3回にして", job=BR, turns=[("talk", "3回にして")], fake=[count()],
         expect=dict(range_total=3, no_candidate=True)),
    dict(id="N06", title="説明 → 教える → じゃあ3回にして（4ターン）", job=BR,
         turns=[("talk", "このロボット、何してる？"), ("talk", "ボタンを押してるんだよ"), ("press",), ("talk", "じゃあ3回にして")],
         fake=[explain(), count()], expect=dict(range_total=3, no_candidate=True)),
    dict(id="N07", title="じゃあ3回にして → ［この範囲を繰り返す］", job=BR,
         turns=[("talk", "じゃあ3回にして"), ("range_yes",)], fake=[count()],
         expect=dict(candidate_kind="repeat", approvable=True, not_approved=True)),
    dict(id="N08", title="あと1回増やして", job=BR, turns=[("talk", "あと1回増やして")], fake=[count()],
         expect=dict(range_total=3)),
    dict(id="N09", title="あと1回押して（合計を確かめる）", job=BR, turns=[("talk", "あと1回押して")], fake=[],
         expect=dict(no_range=True, reply_has="合計3回", api=0)),
    dict(id="N10", title="2.3回にして", job=BR, turns=[("talk", "2.3回にして")], fake=[],
         expect=dict(no_range=True, reply_has="整数", api=0)),
    dict(id="N11", title="3回くらいにして → はい", job=BR, turns=[("talk", "3回くらいにして"), ("talk", "はい")], fake=[],
         expect=dict(no_range=True, no_candidate=True)),
    # ---- 取消・言い直し（候補 2回→3回 があるとき） ----
    dict(id="N12", title="やっぱり元に戻して", job=BR, turns=[("repeat3",), ("talk", "やっぱり元に戻して")], fake=[],
         expect=dict(not_approvable=True)),
    dict(id="N13", title="今の変更はやめて", job=BR, turns=[("repeat3",), ("talk", "今の変更はやめて")], fake=[],
         expect=dict(not_approvable=True)),
    dict(id="N14", title="やっぱり2回でいいや", job=BR, turns=[("repeat3",), ("talk", "やっぱり2回でいいや")], fake=[],
         expect=dict(not_approvable=True)),
    dict(id="N15", title="3回じゃなくて4回（H02 の形）", job=BR, turns=[("repeat3",), ("talk", "3回じゃなくて4回")], fake=[],
         expect=dict(not_approvable=True)),
    dict(id="N16", title="取り消して、何してるか教えて（H16 の形）", job=BR,
         turns=[("repeat3",), ("talk", "変更は取り消して、何してるか教えて")], fake=[explain()],
         expect=dict(not_approvable=True)),
    dict(id="N17", title="やっぱり → 4回（2ターンに分けた言い直し）", job=BR,
         turns=[("repeat3",), ("talk", "やっぱり"), ("talk", "4回")], fake=[explain()],
         expect=dict(not_approvable=True)),
    dict(id="N18", title="いや4回（読点なし。音声認識の形）", job=BR, turns=[("repeat3",), ("talk", "いや4回")], fake=[],
         expect=dict(not_approvable=True)),
    dict(id="N19", title="取り消して説明して（候補あり。読点なし）", job=BR,
         turns=[("repeat3",), ("talk", "説明してあと取り消して")], fake=[explain()], expect=dict(not_approvable=True)),
    # ---- 位置の移動（DEMO_C_PLACE・C00003 を選んでいる） ----
    dict(id="N20", title="もう少し右に動かしたい", job=CP, select="C00003", turns=[("talk", "もう少し右に動かしたい")], fake=[],
         expect=dict(no_candidate=True)),
    dict(id="N21", title="さっきの位置を3ミリ下げて（上下の向き 確認済み）", job=CP, select="C00003", updown=True,
         turns=[("talk", "さっきの位置を3ミリ下げて")], fake=[], expect=dict(no_guess_other_than="C00003 Z")),
    dict(id="N22", title="Y方向に10ミリ（向きを聞き返す）", job=CP, select="C00003", turns=[("talk", "Y方向に10ミリ")], fake=[],
         expect=dict(no_candidate=True, reply_has="プラスですか、マイナスですか")),
    dict(id="N23", title="Y方向に10ミリ → マイナスで", job=CP, select="C00003",
         turns=[("talk", "Y方向に10ミリ"), ("talk", "マイナスで")], fake=[],
         expect=dict(candidate_target="C00003 Y", reply_has="-150.000 → -160.000", not_approved=True, api=0)),
    dict(id="N24", title="Y方向に10ミリ → マイナス → ちがう、プラス", job=CP, select="C00003",
         turns=[("talk", "Y方向に10ミリ"), ("talk", "マイナス"), ("talk", "ちがう、プラス")], fake=[],
         expect=dict(not_approvable_or_target_value="-140.000")),
    dict(id="N25", title="10mm動かして → Yマイナス（量を覚えている）", job=CP, select="C00003",
         turns=[("talk", "10mm動かして"), ("talk", "Yマイナス")], fake=[],
         expect=dict(candidate_target="C00003 Y", reply_has="-160.000")),
    dict(id="N26", title="Yマイナスの方向に10mm", job=CP, select="C00003", turns=[("talk", "Yマイナスの方向に10mm")], fake=[],
         expect=dict(candidate_target="C00003 Y")),
    dict(id="N27", title="上に3mm（上下の向き 確認済み）", job=CP, select="C00003", updown=True,
         turns=[("talk", "上に3mm")], fake=[], expect=dict(candidate_target="C00003 Z", reply_has="300.000 → 303.000")),
    dict(id="N28", title="上に3mm（上下の向き 未確認）", job=CP, select="C00003", turns=[("talk", "上に3mm")], fake=[],
         expect=dict(no_candidate=True)),
    dict(id="N29", title="Zプラス → 3ミリ", job=CP, select="C00003", turns=[("talk", "Zプラス"), ("talk", "3ミリ")], fake=[],
         expect=dict(candidate_target="C00003 Z", reply_has="303.000")),
    dict(id="N30", title="ちょっと下げて（上下 確認済み）", job=CP, select="C00003", updown=True,
         turns=[("talk", "ちょっと下げて")], fake=[], expect=dict(no_candidate=True)),
    dict(id="N31", title="Zマイナス30ミリ（上限）", job=CP, select="C00003", turns=[("talk", "Zマイナス30ミリ")], fake=[],
         expect=dict(no_candidate=True, reply_has="20mm")),
    dict(id="N32", title="Zマイナス3ミリ → やっぱり5ミリ", job=CP, select="C00003",
         turns=[("talk", "Zマイナス3ミリ"), ("talk", "やっぱり5ミリ")], fake=[], expect=dict(not_approvable=True)),
    dict(id="N33", title="Zマイナス3ミリ → いいね、承認して（声では承認しない）", job=CP, select="C00003",
         turns=[("talk", "Zマイナス3ミリ"), ("talk", "いいね、承認して")], fake=[], expect=dict(not_approved=True, approvable=True)),
    dict(id="N34", title="Yに10mm → この位置は何？ → マイナス（間に会話）", job=CP, select="C00003",
         turns=[("talk", "Yに10mm"), ("talk", "この位置は何をするところ？"), ("talk", "マイナス")],
         fake=[explain("物を置くあたりの位置です。")], expect=dict(no_candidate=True)),
    dict(id="N35", title="Zマイナス3ミリ → JOB を読み直す → 前の画面で承認", job=CP, select="C00003",
         turns=[("talk", "Zマイナス3ミリ"), ("reload",), ("approve_old",)], fake=[], expect=dict(old_approve_refused=True)),
]


def run_case(c, tmp: Path) -> dict:
    cfg = None
    if c.get("updown"):
        obj = updown.build_config(jbi.parse_bytes(c["job"]), updown.DEFAULT_ROBOT, "QA", "probe evidence",
                                  confirmed_at="2026-11-05T00:00:00+09:00")
        cfg = updown.write_config(obj, tmp / "updown.json", overwrite=True)
    w, fake = T.flow(tmp, *c.get("fake", []), updown_config=cfg)
    sid = w.load(c["job"])["session_id"]
    first_sid = sid
    if c.get("select"):
        w.select(sid, c["select"])
    log, r, old_approve = [], {}, None
    for step in c["turns"]:
        k = step[0]
        if k == "talk":
            r = w.talk(sid, step[1])
        elif k == "press":
            r = T.press(w, sid)
        elif k == "range_yes":
            r = w.repeat_choose(sid, "yes", w.state(sid)["state"]["repeat_range"]["turn"])
        elif k == "repeat3":
            r = T.repeat_to_three(w, sid)
        elif k == "reload":
            sid = w.load(c["job"], previous=sid)["session_id"]
            r = w.state(sid)
        elif k == "approve_old":
            old_approve = w.approve(first_sid, "QA")
            r = w.state(sid)
        st = (r.get("state") if isinstance(r, dict) else None) or w.state(sid)["state"]
        hear = (r.get("hear") or {}) if isinstance(r, dict) else {}
        ask = (r.get("ask") or {}) if isinstance(r, dict) else {}
        msg = " ".join(x for x in (ask.get("reply"), " ".join(ask.get("notes") or []), hear.get("message"),
                                    (r.get("message") if isinstance(r, dict) else None)) if x)
        cand = st.get("candidate")
        log.append({"turn": " ".join(step[1:]) if len(step) > 1 else f"［{k}］", "via": r.get("via") if isinstance(r, dict) else None,
                    "reply_by": ask.get("reply_by"), "message": msg,
                    "candidate": (cand.get("target") or cand.get("kind")) if cand else None,
                    "can_approve": st.get("can_approve"), "approval": bool(st.get("approval")),
                    "range": (st.get("repeat_range") or {}).get("total")})
    st = w.state(sid)["state"]
    last = log[-1]
    e = c["expect"]
    fails = []
    cand = st.get("candidate")

    def need(ok, why):
        if not ok:
            fails.append(why)

    if e.get("no_candidate"):
        need(not cand, "候補ができた")
    if e.get("candidate_kept"):
        need(bool(cand), "候補が消えた")
    if e.get("approvable"):
        need(bool(st.get("can_approve")), "承認できる状態でない")
    if e.get("not_approvable"):
        need(not st.get("can_approve") and not w.approve(sid, "QA")["ok"], "古い候補が承認できるまま残る")
    if e.get("not_approved"):
        need(not st.get("approval"), "承認されている")
    if "via" in e:
        need(last["via"] == [e["via"]], f"道が {last['via']}")
    if "reply_by" in e:
        need(last["reply_by"] == e["reply_by"], f"答えたのが {last['reply_by']}")
    if "reply_has" in e:
        need(e["reply_has"] in last["message"], f"返事に「{e['reply_has']}」が無い")
    if e.get("not_hidden"):
        need("表示しません" not in last["message"], "Claude の答えを隠した")
    if "range_total" in e:
        need((st.get("repeat_range") or {}).get("total") == e["range_total"], "範囲の確認に進まない")
    if e.get("no_range"):
        need(not st.get("repeat_range"), "範囲の確認に進んだ")
    if "api" in e:
        need(len(fake.requests) == e["api"], f"Claude の呼び出し {len(fake.requests)} 回")
    if "candidate_target" in e:
        need(bool(cand) and cand.get("target") == e["candidate_target"], "期待の候補にならない")
    if "candidate_kind" in e:
        need(bool(cand) and cand.get("kind") == e["candidate_kind"], "期待の候補にならない")
    if "no_guess_other_than" in e:
        need(not cand or cand.get("target") == e["no_guess_other_than"], "別の位置・軸の候補")
    if "not_approvable_or_target_value" in e:
        v = e["not_approvable_or_target_value"]
        need(not st.get("can_approve") or v in last["message"], "前の候補（逆の向き）が承認できるまま残る")
    if e.get("old_approve_refused"):
        need(old_approve is not None and not old_approve.get("ok"), "前の画面の番号で承認できた")
    return {"id": c["id"], "title": c["title"], "verdict": "FAIL" if fails else "PASS", "why": fails,
            "api_calls": len(fake.requests), "turns": log}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--md")
    a = ap.parse_args()
    results = []
    for c in CASES:
        with tempfile.TemporaryDirectory() as d:
            old = sim.DEFAULT_OUT_DIR
            sim.DEFAULT_OUT_DIR = Path(d) / "out"
            try:
                results.append(run_case(c, Path(d)))
            except Exception as ex:  # noqa: BLE001
                results.append({"id": c["id"], "title": c["title"], "verdict": "ERROR", "why": [repr(ex)], "turns": []})
            finally:
                sim.DEFAULT_OUT_DIR = old
    n = {k: sum(r["verdict"] == k for r in results) for k in ("PASS", "FAIL", "ERROR")}
    print(json.dumps(n, ensure_ascii=False))
    for r in results:
        print(r["id"], r["verdict"], r["title"], "／".join(r["why"]))
    if a.json:
        Path(a.json).write_text(json.dumps({"summary": n, "mode": "mock（偽の Claude・MockInterpreter）。実 Claude・実マイクは未使用",
                                            "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.md:
        lines = ["| ID | 会話 | 判定 | 最後の返事（要約） | 理由 |", "|---|---|---|---|---|"]
        for r in results:
            conv = " → ".join(t["turn"] for t in r["turns"])
            last = (r["turns"][-1]["message"] if r["turns"] else "")[:90].replace("|", "｜")
            lines.append(f"| {r['id']} | {conv} | {r['verdict']} | {last} | {'／'.join(r['why'])} |")
        Path(a.md).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
