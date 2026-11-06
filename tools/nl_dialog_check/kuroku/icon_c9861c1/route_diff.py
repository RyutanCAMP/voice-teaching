"""クローク：utterance.read_utterance の結果を2つの版で比べる（API 0回）。python route_diff.py <前の wt> <後の wt> 文|文|..."""
import sys, subprocess, json, tempfile, os
PH = sys.argv[3].split("|")
code = r'''
import sys, json
sys.path.insert(0, sys.argv[1])
from voice_teaching import utterance as U
out = {}
for p in json.loads(open(sys.argv[2], encoding="utf-8").read()):
    try:
        r = U.read_utterance(p)
        out[p] = repr(r)[:300]
    except Exception as ex:
        out[p] = "ERR " + repr(ex)[:200]
print(json.dumps(out, ensure_ascii=False))
'''
fd, PF = tempfile.mkstemp(suffix=".json"); os.close(fd)
open(PF, "w", encoding="utf-8").write(json.dumps(PH, ensure_ascii=False))
res = [json.loads(subprocess.run([sys.executable, "-I", "-X", "utf8", "-c", code, wt, PF], capture_output=True, text=True, encoding="utf-8").stdout) for wt in sys.argv[1:3]]
for p in PH:
    print(("同じ " if res[0][p] == res[1][p] else "違う ") + p + "\n  前: " + res[0][p] + ("" if res[0][p] == res[1][p] else "\n  後: " + res[1][p]))
