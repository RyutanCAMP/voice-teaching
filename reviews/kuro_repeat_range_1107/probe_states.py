"""範囲の確認と承認の状態の移り変わり（無断の範囲の置き換え・古い確認の再利用）を、今の版で調べる（読むだけ・モック・プロセスの中）。
使い方：python -I <this> <repo>
"""
import json
import sys
import tempfile
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repo))
from voice_teaching import claude_interpreter as ci  # noqa: E402
from voice_teaching import sim  # noqa: E402
from voice_teaching.web.flow import WebFlow  # noqa: E402

OUT = Path(tempfile.mkdtemp()) / "sim"
sim.DEFAULT_OUT_DIR = OUT
DATA = (repo / "samples/dummy/DEMO_BUTTON_REPEAT.JBI").read_bytes()
res = []


def rec(name, ok, detail):
    res.append({"id": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + " :: " + detail)


def new():
    w = WebFlow(interpreter=ci.MockInterpreter(), updown_config=None)
    return w, w.load(DATA)["session_id"]


def rr(r):
    return (r.get("state") or {}).get("repeat_range")


def turn_of(r):
    x = rr(r)
    if isinstance(x, dict):
        for k in ("turn", "id", "token"):
            if k in x:
                return x[k]
    return None


# 1. 明示した別の範囲：無断の置き換えが無いか
for text in ["C1からC4を3回にして", "C00001からC00004の作業を2回から3回にして", "C2からC3を3回にして",
             "C1とC4の動きを3回にして", "C00001を3回にして", "C4からC1を3回にして"]:
    w, sid = new()
    r = w.hear(sid, text)
    x = rr(r)
    msg = r.get("message") or ""
    shows13 = "C00001" in msg and "C00003" in msg or (isinstance(x, dict) and "C00001" in json.dumps(x))
    says_diff = any(k in msg for k in ("違", "異な", "合いません", "ではなく", "合う区間"))
    rec(f"範囲の不一致「{text}」：候補を作らない", not r.get("candidate_made") and not r["state"].get("candidate"),
        f"status={r.get('status')}・範囲の確認={'あり' if x else 'なし'}・違いの説明={'あり' if says_diff else 'なし'}・文「{msg[:150]}」")
    if x and shows13 and not says_diff:
        rec(f"範囲の不一致「{text}」：違いを言わずに C00001〜C00003 を示していない", False, "範囲の確認は C00001〜C00003、違いの説明が無い")

# 2. 範囲の確認 → 古い確認の再利用
w, sid = new()
r = w.hear(sid, "3回にして")
t = turn_of(r)
print("repeat_range の形：", json.dumps(rr(r), ensure_ascii=False)[:400])
for label, act in [("位置の選び直し", lambda: w.select(sid, "C00002")), ("元に戻す", lambda: w.undo(sid)),
                   ("新しい指示", lambda: w.hear(sid, "Zプラス方向に5mm")), ("否定", lambda: w.hear(sid, "違う"))]:
    w, sid = new()
    r = w.hear(sid, "3回にして")
    t = turn_of(r)
    act()
    r2 = w.repeat_choose(sid, "yes", t)
    rec(f"古い範囲の確認（{label}のあと）：候補を作らない", not r2.get("candidate_made") and not r2["state"].get("candidate"),
        f"turn={t}・文「{(r2.get('message') or '')[:120]}」")

# JOB の読み直し：新しいセッション。古いセッションの turn で押しても候補ができない
w, sid = new()
r = w.hear(sid, "3回にして")
t = turn_of(r)
sid2 = w.load(DATA, previous=sid)["session_id"]
r2 = w.repeat_choose(sid2, "yes", t)
r3 = w.repeat_choose(sid, "yes", t)
rec("JOB の読み直しのあと、古い範囲の確認：候補を作らない",
    not r2.get("candidate_made") and not (r3.get("ok") and r3.get("candidate_made")),
    f"新しい sid：{(r2.get('message') or '')[:80]}／古い sid：ok={r3.get('ok')}・{(r3.get('message') or '')[:80]}")

# 3. 範囲の確認は承認ではない
w, sid = new()
r = w.hear(sid, "3回にして")
r2 = w.repeat_choose(sid, "yes", turn_of(r))
st = r2["state"]
rec("範囲の確定は承認ではない（承認なし・出力できない）", st.get("candidate") and not st.get("approval") and not st.get("can_export"),
    f"候補={'あり' if st.get('candidate') else 'なし'}・承認={st.get('approval')}・can_export={st.get('can_export')}")
e = w.export(sid, candidate_gen=w.candidate_gen_of(sid))
rec("承認の前の出力は断る", not e.get("ok"), f"文「{(e.get('message') or '')[:100]}」")
# 承認 → 回数の別の指示 → 古い承認・候補で出力できない
gen = w.candidate_gen_of(sid)
a = w.approve(sid, "QA", candidate_gen=gen)
r4 = w.hear(sid, "4回にして")
e2 = w.export(sid, candidate_gen=gen)
rec("承認のあと「4回にして」：古い承認で出力できない", not e2.get("ok") and not r4["state"].get("can_export"),
    f"承認={a.get('ok')}・返事「{(r4.get('message') or '')[:100]}」・出力={e2.get('ok')}")
# あいまいな「2回繰り返したい」：2→3 を確定しない
for text in ["2回繰り返したい", "2回にして", "もう1回", "繰り返して"]:
    w, sid = new()
    r = w.hear(sid, text)
    rec(f"あいまいな「{text}」：2→3 の候補を作らない", not r.get("candidate_made") and not r["state"].get("candidate"),
        f"範囲の確認={'あり' if rr(r) else 'なし'}・文「{(r.get('message') or '')[:110]}」")

print(json.dumps({"pass": sum(r["pass"] for r in res), "total": len(res)}, ensure_ascii=False))
Path(sys.argv[2] if len(sys.argv) > 2 else "states.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
