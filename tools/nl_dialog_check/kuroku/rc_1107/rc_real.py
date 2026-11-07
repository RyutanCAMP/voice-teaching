"""本番候補 v1.0（36ca898）を本物の Claude で少しだけ確かめる（クローク・11/7 朝）。サーバーを起動しない・出力は一時フォルダ。
使い方：python -I rc_real.py <worktree> <.env> <出力 json> [--only A,B] [--rep N]
キーは表示・保存しない。API の回数とトークンを数える。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("root"); ap.add_argument("envfile"); ap.add_argument("out")
ap.add_argument("--only", default=""); ap.add_argument("--rep", type=int, default=1)
A = ap.parse_args()
ROOT = Path(A.root).resolve()
sys.path[:0] = [str(ROOT)]
sys.stdout.reconfigure(encoding="utf-8")
from voice_teaching import claude_explain, claude_interpreter, sim  # noqa: E402
from voice_teaching.web.flow import WebFlow  # noqa: E402

claude_interpreter.load_dotenv(A.envfile)
CALLS = []
import anthropic.resources.messages as _m  # noqa: E402
_orig = _m.Messages.create


def _t(self, *a, **kw):
    r = None
    try:
        r = _orig(self, *a, **kw); return r
    finally:
        u = getattr(r, "usage", None)
        CALLS.append(((getattr(u, "input_tokens", 0) or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0)
                      + (getattr(u, "cache_read_input_tokens", 0) or 0) * 0.1,
                      getattr(u, "output_tokens", 0) or 0, r is None))


_m.Messages.create = _t
JOBS = {"RJ": (ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI").read_bytes(), "CP": (ROOT / "samples/dummy/DEMO_C_PLACE.JBI").read_bytes(),
        "BR": (ROOT / "samples/dummy/DEMO_BUTTON_REPEAT.JBI").read_bytes()}
P = ["@sel C00004"]
SC = {
    # 量・指示が2つ（Claude が片方を選ぶと、Python は通してしまう：偽の Claude で U05〜U07）
    "two_axes": ("RJ", P + ["えっと、Zプラス5ミリとYプラス3ミリお願いね"]),
    "or_amount": ("RJ", P + ["えっと、Zプラスに5ミリか10ミリでお願いね"]),
    "two_dirs": ("RJ", P + ["えっと、Zプラスに5ミリ、Zマイナスに3ミリお願いね"]),
    "up_then_down": ("RJ", P + ["Zプラスに5ミリ上げてから3ミリ戻してほしいな"]),
    # 量の根拠の部分一致（U01〜U03）：本物の Claude が正しく読むか
    "amt_15": ("RJ", P + ["えっと、Zプラスに15ミリずらしてほしいなあ"]),
    "amt_0_5": ("RJ", P + ["えっと、Zプラスに0.5ミリずらしてほしいなあ"]),
    "amt_2_5": ("RJ", P + ["えっと、Zプラスに2.5ミリずらしてほしいなあ"]),
    # 位置の言葉（U09）
    "nth_point": ("RJ", P + ["えっと、3番目の点をZプラスに5ミリずらしてほしいなあ"]),
    # 取り消した候補の量を使う（U13・U14）
    "undo_add": ("RJ", P + ["Zプラス方向に15ミリ", "@undo", "えっと、あと3ミリお願いね"]),
    "cancel_same": ("RJ", P + ["Zプラス方向に15ミリ", "取り消して", "えっと、さっきと同じだけZプラスにお願いね"]),
    # 自然な言い方・聞き返し・訂正（計画書 6章）
    "vague_up": ("RJ", P + ["もう少し上に寄せたいな", "5ミリ"]),
    "cm": ("RJ", P + ["Zプラスに0.5センチ動かしてくれる？"]),
    "polite": ("RJ", P + ["すみません、Zのプラス方向に5ミリだけ動かしてもらえますか"]),
    "dame_unappr": ("RJ", P + ["Zプラス方向に5ミリ", "だめ"]),
    "no_unappr": ("RJ", P + ["Zプラス方向に5ミリ", "ノー"]),
    "doushiyou_appr": ("RJ", P + ["Zプラス方向に5ミリ", "@approve", "どうしよう"]),
    "daijoubu_appr": ("RJ", P + ["Zプラス方向に5ミリ", "@approve", "大丈夫？"]),
    "f2_appr": ("RJ", P + ["Zプラス方向に5ミリ", "@approve", "3ミリに訂正して"]),
    "script": ("RJ", P + ["Zプラス方向に30ミリ動かして", "Zプラス方向に5ミリ動かして", "@approve", "@export"]),
    "repeat23": ("BR", ["2回から3回にして", "@range_yes", "@approve", "@export"]),
    "repeat_kai": ("BR", ["2階から3階にして", "@range_yes", "@approve", "@export"]),
    "kai_rj": ("RJ", P + ["2階から3階にして"]),
    "right_c02": ("CP", ["@sel C00003", "もう少し右に寄せて", "5ミリ", "@yes"]),
}
only = {x for x in A.only.split(",") if x}
res = []
for name, (job, steps) in SC.items():
    if only and name not in only:
        continue
    for rep in range(A.rep):
        with tempfile.TemporaryDirectory() as d:
            sim.DEFAULT_OUT_DIR = Path(d) / "out"
            w = WebFlow(interpreter=claude_interpreter.from_env(),
                        explainer=claude_explain.Explainer.from_env(usage_path=Path(d) / "u.jsonl"))
            sid = w.load(JOBS[job])["session_id"]; log = []; last = {}
            for s in steps:
                n = len(CALLS); t0 = time.time()
                if s.startswith("@sel "):
                    r = w.select(sid, s[5:])
                elif s == "@approve":
                    r = w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid))
                elif s == "@export":
                    r = w.export(sid, candidate_gen=w.candidate_gen_of(sid))
                elif s == "@undo":
                    r = w.undo(sid)
                elif s == "@range_yes":
                    rr = w.state(sid)["state"].get("repeat_range")
                    r = w.repeat_choose(sid, "yes", rr["turn"]) if rr else {"error": "範囲の確認が無い"}
                elif s == "@yes":
                    ch = (last.get("hear") or {}).get("choices") or last.get("choices") or []
                    yes = [c for c in ch if c.get("label") == "合っている"]
                    r = w.hear(sid, yes[0]["text"], "text") if yes else {"error": "［合っている］が無い"}
                else:
                    r = w.talk(sid, s, "voice")
                last = r
                st = w.state(sid)["state"]; c = st.get("candidate") or {}
                h, a = (r.get("hear") or {}), (r.get("ask") or {})
                msg = " ".join(x for x in [a.get("reply"), a.get("error"), h.get("message"),
                                           r.get("message") if isinstance(r.get("message"), str) else None,
                                           r.get("error") if isinstance(r.get("error"), str) else None] if x)
                log.append({"do": s, "msg": msg[:300], "nl": r.get("nl") or h.get("nl"), "file": r.get("file_name"),
                            "cand": (c.get("target"), c.get("delta")) if c else None, "approval": bool(st.get("approval")),
                            "hold": st.get("hold"), "can_approve": st.get("can_approve"), "can_export": st.get("can_export"),
                            "api": len(CALLS) - n, "sec": round(time.time() - t0, 1)})
            res.append({"case": name, "rep": rep, "log": log})
            print("==", name, rep, flush=True)
            for x in log:
                if not x["do"].startswith("@sel"):
                    print("  ", json.dumps(x, ensure_ascii=False)[:420], flush=True)
usd = sum(i * 2.0 + o * 10.0 for i, o, _ in CALLS) / 1e6
print(f"API {len(CALLS)} 回・失敗 {sum(1 for *_, f in CALLS if f)}・推定 {usd:.3f} ドル（sonnet-5-5 の値段で計算）")
Path(A.out).write_text(json.dumps({"sha": ROOT.name, "calls": len(CALLS), "usd": round(usd, 3), "res": res}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
