import sys, json, tempfile
from pathlib import Path
sys.argv = [sys.argv[0], sys.argv[1], sys.argv[2], sys.argv[3], "0"]
exec(open(Path(__file__).with_name("real_recapture.py"), encoding="utf-8").read().split("CASES = [")[0])
out = []
for p in ["いやZプラス3ミリ", "いやZマイナス5ミリ", "いや上に3ミリ", "いやプラス3ミリ", "いや、Zプラス3ミリ"]:
    with tempfile.TemporaryDirectory() as d:
        w = new_flow(Path(d)); sid = w.load(CP)["session_id"]; w.select(sid, "C00005")
        w.talk(sid, "Zプラス方向に5ミリ", "voice"); g0 = w.candidate_gen_of(sid)
        a0 = w.approve(sid, "クローク（テスト）", candidate_gen=g0)
        r = w.talk(sid, p, "voice"); s = w.state(sid)["state"]; g = w.candidate_gen_of(sid)
        e0 = w.export(sid, candidate_gen=g)
        a = w.approve(sid, "クローク（テスト）", candidate_gen=g); e = w.export(sid, candidate_gen=g) if a.get("ok") else {}
        body = Path(e["path"]).read_text(encoding="utf-8", errors="replace") if e.get("ok") else ""
        c = s.get("candidate") or {}
        rec = dict(phrase=p, approved_first=a0.get("ok"), gen=[g0, g], cand_after=c.get("delta"), export_without_reapprove=e0.get("ok"),
                   reapprove=a.get("ok"), export=e.get("ok"), export_has_205=("205.000" in body), reply=msg(r)[:300], status=str(s.get("status_line"))[:160])
        out.append(rec); print(json.dumps(rec, ensure_ascii=False))
tin = sum((c["usage"] or {}).get("in", 0) for c in CALLS); tout = sum((c["usage"] or {}).get("out", 0) for c in CALLS)
summ = dict(calls=len(CALLS), errors=sum(bool(c["error"]) for c in CALLS), tokens_in=tin, tokens_out=tout, usd_est=round(tin*2e-6+tout*10e-6, 4))
print(summ)
Path(sys.argv[3]).write_text(json.dumps(dict(summary=summ, results=out, calls=CALLS), ensure_ascii=False, indent=1), encoding="utf-8")
