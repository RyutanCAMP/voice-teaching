"""SIM の名前（モック）：日本時間・同じ秒・上書きしない・中身の一致・返事のバイト列と sha256。"""
import sys, tempfile, re, hashlib, base64
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); sys.path[:0] = [str(ROOT), str(ROOT / "tests")]; sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T
from voice_teaching import sim
RJ = (ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI").read_bytes()
PAT = re.compile(r"^DEMO_RJ_XYZ_SIM_(\d{10})(_\d\d)?\.JBI$")  # 11/7 夕方：<JOB>_SIM_YYMMDDHHMM.JBI
def run(d, fixed=None):
    sim.DEFAULT_OUT_DIR = Path(d) / "o"
    if fixed: sim.clock = lambda: fixed
    w, _ = T.flow(Path(d), *[T.answer("説明", (24,)) for _ in range(3)])
    sid = w.load(RJ)["session_id"]; w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice")
    w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid)); return w.export(sid, candidate_gen=w.candidate_gen_of(sid))
real_clock = sim.clock
with tempfile.TemporaryDirectory() as d:
    t0 = datetime.now(timezone(timedelta(hours=9))); e = run(d); m = PAT.match(e["file_name"])
    got = datetime.strptime(m.group(1), "%y%m%d%H%M").replace(tzinfo=timezone(timedelta(hours=9)))
    print("S1 形", bool(m), e["file_name"], "| 日本時間の分との差（秒・60未満なら同じ分）", round(abs((got - t0.replace(second=0, microsecond=0)).total_seconds()), 1))
    keys = sorted(k for k in e if k not in ("state",)); print("   返事の項目", keys)
    body = (Path(d) / "o" / e["file_name"]).read_bytes()
    b64 = e.get("content_b64")
    sha = next((e[k] for k in e if "sha" in k), None)
    if isinstance(b64, dict): print("   ", b64.keys())
    print("S4 返事の中身＝ファイル", (base64.b64decode(b64) == body) if isinstance(b64, str) else "項目が見つからない", "| sha256 一致", sha == hashlib.sha256(body).hexdigest() if sha else "項目なし")
    print("   //NAME", [l for l in body.decode('ascii').splitlines() if l.startswith('//NAME')], "| Z", [l for l in body.decode('ascii').splitlines() if l.startswith('C00004=')])
with tempfile.TemporaryDirectory() as d:
    fixed = datetime(2026, 11, 7, 12, 15, 30, tzinfo=timezone.utc)  # UTC で渡しても日本時間で名前にするか
    names = [run(d, fixed).get("file_name") for _ in range(3)]
    print("S2 同じ分に3つ", names, "| 日本時間（2611072115）", all("_SIM_2611072115" in (n or "") for n in names), "| 連番", [n.rsplit("_",1)[-1] for n in names])
    files = sorted(p.name for p in (Path(d) / "o").iterdir()); print("   フォルダの中", files)
sim.clock = real_clock
