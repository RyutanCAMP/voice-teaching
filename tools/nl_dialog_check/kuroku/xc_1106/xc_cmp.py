import json,sys
sys.stdout.reconfigure(encoding="utf-8")
names=["60f","c77b049","b361565"]; D={n:{x["id"]:x for x in json.load(open(f"out/xc/xc_{n}.json",encoding="utf-8"))["res"]} for n in names}
pre=sys.argv[1]
def short(x):
    s=x.get("state") or x.get("state3") or x.get("s2") or {}
    c=s.get("cand"); 
    t=f"cand={c[1] if c else '-'} appr={int(s.get('approval',0))} hold={int(s.get('hold',0))} canA={int(s.get('can_approve',0))} canE={int(s.get('can_export',0))}"
    if "gen_changed" in x: t+=f" gen+={int(x['gen_changed'])}"
    if "old_export" in x: t+=f" OLD:exp={int(x['old_export'])},reapp={int(x['old_reapprove'])}"
    for k in ("asked_again","dead_end","claude"):
        if k in x: t+=f" {k}={x[k]}"
    return t
for i in D["60f"]:
    if not i.startswith(pre): continue
    print("##",i)
    for n in names:
        x=D[n].get(i,{}); m=x.get("msg") or x.get("msg3") or x.get("msg2") or ""
        print(f"  {n:8} {short(x)} | {m[:150]}")
