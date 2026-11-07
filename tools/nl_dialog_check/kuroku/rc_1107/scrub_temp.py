import re, sys
B = re.escape(chr(92))
pat = re.compile(r"[A-Za-z]:(?:" + B + r"|/)+Users(?:" + B + r"|/)+User(?:" + B + r"|/)+AppData(?:" + B + r"|/)+Local(?:" + B + r"|/)+Temp")
for p in sys.argv[1:]:
    s = open(p, encoding="utf-8", errors="replace").read()
    n = pat.sub("<temp>", s)
    if n != s:
        open(p, "w", encoding="utf-8", newline="").write(n); print("scrubbed", p, n.count("AppData"))
