"""設計書 7-1 の NLR の文と、既存の言い方の集まりの重複（API 0回）。"""
import json, re, sys, unicodedata, difflib
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
C = Path(sys.argv[1])
def norm(s):
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"[\s、。,.!?！？「」『』（）()・…ー〜~]", "", s)
# NLR：設計書 7-1 の表に書かれた具体的な文（クロークが手で写した。O04 は文が無い）
NLR = [(i, t, "") for i, t in [
 ("S01","C00003 を Yプラス に5ミリ動かして"),("S02","C00003、Yプラス方向へ5mm移動"),("S03","C00003 の Y を 5ミリ増やして"),
 ("S04","5ミリ Y のプラスにずらしてほしいんだけど"),("S05","Yを+5で"),("S06","ワイプラス五ミリ"),
 ("U01","0.5センチ Yプラス"),("U02","Yプラス 1センチ"),("U03","十ミリ下げて"),("U04","ミリで言うと3、Zマイナス"),("U05","3mmです、Zマイナスに"),
 ("R01","さっきと同じだけ C00004 も"),("R02","同じだけ反対に"),("R03","さっきと同じ"),
 ("C01","もう少し右に寄せて"),("C01b","5ミリ"),("C03","上に"),("C04","C00003"),("C04b","Zプラス"),("C04c","3ミリ"),("C05","右に3ミリ"),
 ("A01","ちょっとだけ右"),("A02","少し動かして"),("A03","いい感じにして"),("A04","もう少し"),("A05","5くらい上"),
 ("K01","Zプラス10ミリ、いや5ミリ"),("K02","やっぱり3ミリ"),("K03","Zプラス方向に3ミリ"),("K04","うーん"),
 ("L01","Yプラス25ミリ"),("L02","2センチ5ミリ"),("L03","あと10ミリ"),("L04","C00000 を Yプラス3ミリ"),
 ("P01","Yプラス5ミリ"),("P02","C00099 を"),("P03","さっきの所"),("P04","置くところを上に"),
 ("N01","今日は寒いね"),("N02","このロボット何してるの？"),("N03","承認して"),("N04","出力して"),
 ("O01","3ミリにして"),("O02","もうちょっと上"),("O03","だめ"),("O05","4回にして"),("O06","大丈夫？"),("O07","ノー")]]
print("NLR の文", len(NLR))
SRC = {}
def add(src, i, t):
    if isinstance(t, str) and t.strip(): SRC.setdefault(src, []).append((i, t))
for r in json.load(open(C/"c243.json", encoding="utf-8"))["results"]:
    add("243", r["id"], r.get("said"))
    for k, l in enumerate(r.get("log") or []): 
        if k: add("243", f"{r['id']}#{k}", l.get("said"))
for r in json.load(open(C/"f47.json", encoding="utf-8"))["results"]:
    add("focus47", r["id"], r.get("said"))
for f in ("natural_cases_v1", "natural_extra_v1", "context_supplement_v1", "fraction_boundary_v1"):
    for r in json.load(open(C/f"{f}.json", encoding="utf-8")).get("cases", []):
        add("169", f"{f.split('_')[0]}:{r['id']}", r.get("text"))
        for k, s in enumerate(r.get("setup") or []):
            add("169", f"{f.split('_')[0]}:{r['id']}#s{k}", s.get("text") if isinstance(s, dict) else s)
for r in json.load(open(C/"microphone_matrix.json", encoding="utf-8"))["cases"]:
    add("mic36", r["id"], r.get("intended_utterance"))
for k, l in enumerate((C/"stop.txt").read_text(encoding="utf-8").splitlines()):
    if l.strip() and not l.startswith("#"): add("stop", f"L{k+1}", l.split("\t")[0])
for m in re.finditer(r"\"([^\"\n]*[ぁ-んァ-ン一-龥][^\"\n]*)\"", (C/"kc_accept.py").read_text(encoding="utf-8")):
    if len(m.group(1)) <= 40: add("クロクラウド", f"q{m.start()}", m.group(1))
print({k: len(v) for k, v in SRC.items()})
exact, near = [], []
for nid, t, ctx in NLR:
    n = norm(t)
    for src, items in SRC.items():
        for i, u in items:
            m = norm(u)
            if not m: continue
            if m == n: exact.append((nid, t, src, i, u))
            elif difflib.SequenceMatcher(None, n, m).ratio() >= 0.85:
                near.append((nid, t, src, i, u))
print("\n## 同じ文"); [print(f"{a}「{b}」 = {c}:{d}「{e}」") for a, b, c, d, e in exact]
print("\n## ほぼ同じ文"); [print(f"{a}「{b}」 ≈ {c}:{d}「{e}」") for a, b, c, d, e in near]
hit = {x[0] for x in exact + near}
print("\n## 重複なし", len([x for x in NLR if x[0] not in hit]), "件:", " ".join(f"{a}「{b}」" for a, b, _ in NLR if a not in hit))
json.dump({"nlr": NLR, "exact": exact, "near": near, "sources": {k: len(v) for k, v in SRC.items()}}, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
