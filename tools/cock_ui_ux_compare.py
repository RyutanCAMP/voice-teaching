"""Compare UI audit case names and preserve screenshot/source provenance."""
from __future__ import annotations
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs/ui-ux-1106"
BASE="60f3d2469fe125da3913e950b74f9974d95055f5"

def main():
    before=json.loads((OUT/"before/audit.json").read_text(encoding="utf-8"))
    after=json.loads((OUT/"after/audit.json").read_text(encoding="utf-8"))
    cases=[]
    for data in [before,after]:
        mapped={c["name"]:c["pass"] for c in data["checks"]}
        if len(mapped)!=len(data["checks"]):raise ValueError("Duplicate check names")
        cases.append(mapped)
    a,b=cases
    common=sorted(a.keys()&b.keys())
    missing=sorted(a.keys()-b.keys())
    unexpected_missing=[k for k in missing if "tooltip_blocked: no horizontal page overflow" not in k]
    source="voice_teaching/web/static/style.css"
    source_before=subprocess.check_output(["git","show",f"{BASE}:{source}"],cwd=ROOT)
    source_after=(ROOT/source).read_bytes().replace(b"\r\n",b"\n")
    result={"base_sha":BASE,"common_cases":len(common),
        "before_common_pass":sum(a[k] for k in common),"before_common_fail":sum(not a[k] for k in common),
        "after_common_pass":sum(b[k] for k in common),"after_common_fail":sum(not b[k] for k in common),
        "improved":[k for k in common if not a[k] and b[k]],
        "regressed":[k for k in common if a[k] and not b[k]],
        "before_only_supplemental_checks":missing,"unexpected_missing_cases":unexpected_missing,
        "after_only_checks":sorted(b.keys()-a.keys()),
        "execution_errors":{"before":before.get("execution_error"),"after":after.get("execution_error")},
        "css_before_sha256":hashlib.sha256(source_before).hexdigest(),
        "css_after_sha256_lf":hashlib.sha256(source_after).hexdigest(),
        "mock_only":True,"real_api_calls":0,"microphone_precision_tested":False,
        "screenshots":[],"figure_sizes":[]}
    shots_before={(tuple(s["size"]),s["name"]):s for s in before["screens"]}
    for s in after["screens"]:
        k=(tuple(s["size"]),s["name"])
        if k not in shots_before:continue
        prev=shots_before[k]
        if s["name"] in ["loaded","candidate","long_conversation"]:
            for folder,item in [("before",prev),("after",s)]:
                path=OUT/folder/item["path"]
                result["screenshots"].append({"path":str(path.relative_to(OUT)),
                    "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
        if s["name"] in ["loaded","repeat_candidate"]:
            old=prev["metrics"]["boxes"]["#fig-3d"]
            new=s["metrics"]["boxes"]["#fig-3d"]
            result["figure_sizes"].append({"size":s["size"],"state":s["name"],
                "before":[round(old["width"],1),round(old["height"],1)],
                "after":[round(new["width"],1),round(new["height"],1)]})
    (OUT/"comparison.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# 同解像度のスクリーンショット比較","",
           "[比較ビューを開く](index.html)。すべて合成JOB・モック・Chrome156で撮影。", "",
           f"共通{len(common)}項目：変更前 {result['before_common_pass']} PASS / {result['before_common_fail']} FAIL → "
           f"変更後 {result['after_common_pass']} PASS / {result['after_common_fail']} FAIL。", "",
           "変更前だけの3項目は、不具合発生時に追加した証拠画像の横スクロール検査。共通ケースの比較には含めない。", "",
           "| 解像度 | 場面 | 変更前 | 変更後 |","|---|---|---|---|"]
    for w,h in [(1920,1080),(1440,900),(1280,720)]:
        for state,label in [("loaded","読み込み後"),("candidate","候補・座標差分"),("long_conversation","長い返答")]:
            name=f"{w}x{h}_{state}.png"
            lines.append(f"| {w}×{h} | {label} | [画像](before/{name}) | [画像](after/{name}) |")
    lines += ["","## 3Dの表示領域","","| 解像度・場面 | 前 | 後 |","|---|---:|---:|"]
    for item in result["figure_sizes"]:
        lines.append(f"| {'×'.join(map(str,item['size']))} {item['state']} | {'×'.join(map(str,item['before']))} | {'×'.join(map(str,item['after']))} |")
    lines += ["","安全の最終合格判定、実Claudeの意味理解、実マイクの認識精度をこの数値から主張しない。",
              "比較の元データはbefore/audit.json・after/audit.json、画像とCSSのハッシュはcomparison.json。"]
    (OUT/"COMPARISON.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ["common_cases","before_common_pass","before_common_fail", "after_common_pass","after_common_fail","improved","regressed","unexpected_missing_cases"]},ensure_ascii=False))
    return int(bool(result["regressed"] or unexpected_missing or any(result["execution_errors"].values())))

if __name__=="__main__":raise SystemExit(main())
