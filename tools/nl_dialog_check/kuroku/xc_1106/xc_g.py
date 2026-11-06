import json,sys
from collections import defaultdict, Counter
sys.stdout.reconfigure(encoding="utf-8")
names=["60f","c77b049","b361565"]
def cls(x):
    s=x["state"]; sc=x["scene"]
    if sc=="none":
        if s["cand"]: return "候補ができた!"
        return "説明(Claude)" if x.get("claude") else "Python の文"
    if s["cand"] is None: return "取消"
    if s["hold"]: return "保留(承認なし)" if not s["approval"] else "保留(承認の記録あり)"
    if s["approval"] and s["can_export"]: return "承認が残る(出力可)"
    if s["can_approve"]: return "承認できるまま" if sc=="unapproved" else "承認だけ取消・候補は承認できる"
    return "?"
out={}
for n in names:
    for x in json.load(open(f"out/xc/xc_{n}.json",encoding="utf-8"))["res"]:
        if not x["id"].startswith("G-") or "state" not in x: continue
        out.setdefault((x["grp"],x["scene"],x["word"]),{})[n]=cls(x)+("" if not x.get("old_export") else " 古い出力可!")
words={}
for (g,sc,w),v in out.items(): words.setdefault(g,[]); words[g].append(w) if w not in words[g] else None
for g in words:
    for sc in ("none","unapproved","approved"):
        print(f"### {g} / {sc}")
        for n in names:
            c=Counter(out[(g,sc,w)][n] for w in words[g]); print(f"  {n:8}", dict(c))
        diff=[w for w in words[g] if len({out[(g,sc,w)][n] for n in names})>1 or True]
        print("   各語:", "; ".join(f"{w}={'/'.join(out[(g,sc,w)][n][:8] for n in names)}" for w in words[g]))
