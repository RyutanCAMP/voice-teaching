"""21時の仕上げ（UI-1700-1／XC-26・UI-1700-2）の確かめ。偽の Claude・偽の保存の窓・API 0回。シクロの道具とは別に書いた。
使い方：python -I ui_polish_check.py <worktree> <出力フォルダ>
V：［承認して保存］のあと、3つの大きさで候補の窓（.cand-pop）が 3D の C00003〜C00005 の点・線と重なるか（四角の重なりで測る）
   ［承認して保存］のボタン・承認の表示が見えるか（承認の前）
W：保存の結果の言い方（窓を自動で開く経路。navigator.webdriver を false にして、本物と同じ流れにする）
   成功／取りやめ／権限なし／書けない／読み戻しが違う／窓の無いブラウザー（ダウンロード）
   期待：保存していないのに「保存しました」を出さない・成功の ✓ が2つ出ない・アプリの記録とブラウザーの保存を言い分ける
OS の本物の保存の窓ではない。
"""
from __future__ import annotations
import json, sys, threading
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
sys.stdout.reconfigure(encoding="utf-8")
import e2e_browser as E  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from voice_teaching import sim  # noqa: E402
from voice_teaching.claude_interpreter import MockInterpreter  # noqa: E402
from voice_teaching.web import server  # noqa: E402

sim.DEFAULT_OUT_DIR = OUT / "sim_out"
srv = server.make_server(port=0, interpreter=MockInterpreter(), updown_config=None)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}/?opening=0"
RJ = str(ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI")
RES = []
PICKER = """
window.__mode = window.__mode || 'ok'; window.__pickerCalls = 0;
window.showSaveFilePicker = async (opts) => {
  window.__pickerCalls += 1; const m = window.__mode;
  if (m === 'abort') { const e = new Error('cancel'); e.name = 'AbortError'; throw e; }
  if (m === 'notallowed') { const e = new Error('denied'); e.name = 'NotAllowedError'; throw e; }
  let buf = null;
  return { name: opts.suggestedName,
    async createWritable() { return { async write(b) { if (m === 'writefail') throw new Error('disk full'); buf = new Uint8Array(b); }, async close() {} }; },
    async getFile() { let b = buf || new Uint8Array(); if (m === 'tamper') { b = new Uint8Array(b); b[0] = (b[0] + 1) % 256; } return new Blob([b]); } };
};
"""
NOWEBDRIVER = "Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => false });"


def rec(cid, verdict, what, **kw):
    RES.append({"id": cid, "verdict": verdict, "what": what, **kw})
    print(cid, verdict, what, json.dumps(kw, ensure_ascii=False)[:600], flush=True)


def vis(pg, s):
    return pg.locator(s).count() > 0 and pg.locator(s).first.is_visible()


def to_candidate(br, w, h, init=""):
    pg = br.new_page(viewport={"width": w, "height": h}, accept_downloads=True)
    pg.add_init_script(E.FAKE_RECOGNITION)
    if init: pg.add_init_script(init)
    pg.goto(URL)
    pg.set_input_files("#file-input", RJ); pg.wait_for_selector("#job-area:not([hidden])")
    pg.locator("#position-chips button", has_text="C00004").first.click(); pg.wait_for_timeout(200)
    E.fill_text(pg, "Zプラス方向に5ミリ動かして"); pg.click("#text-send")
    E.until(pg, lambda: vis(pg, "#quick-approve-button"), 10000); pg.wait_for_timeout(500)
    return pg


def approve_save(pg):
    pg.fill("#quick-approver", "QA"); pg.click("#quick-approve-button")
    E.until(pg, lambda: vis(pg, "#export-result"), 10000); pg.wait_for_timeout(1200)


OVERLAP_JS = """() => {
  const pop = document.querySelector('.cand-pop');
  const pr = pop && getComputedStyle(pop).display !== 'none' ? pop.getBoundingClientRect() : null;
  const inter = (a, b) => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  const want = ['C00003', 'C00004', 'C00005'];
  const out = { pop: pr && { l: pr.left, t: pr.top, r: pr.right, b: pr.bottom }, pts: [], segs: [] };
  for (const g of document.querySelectorAll('g.pt3')) {
    const names = (g.dataset.names || '').split(' ');
    if (!names.some((n) => want.includes(n))) continue;
    const c = [...g.querySelectorAll('circle')].pop().getBoundingClientRect();
    out.pts.push({ names: names.join(' '), cx: (c.left + c.right) / 2, cy: (c.top + c.bottom) / 2, hidden: pr ? inter(c, pr) > 0 : false });
  }
  for (const s of document.querySelectorAll('line.seg, path.seg, polyline.seg')) {
    if (!(want.includes(s.dataset.from) || want.includes(s.dataset.to))) continue;
    const r = s.getBoundingClientRect();
    out.segs.push({ k: s.dataset.from + '>' + s.dataset.to + ':' + (s.dataset.kind || ''), hidden_area: pr ? Math.round(inter(r, pr)) : 0, area: Math.round(r.width * r.height) });
  }
  return out;
}"""

with sync_playwright() as p:
    br = p.chromium.launch()
    # V：3つの大きさ
    for w, h in [(1920, 1080), (1440, 900), (1280, 720)]:
        pg = to_candidate(br, w, h, PICKER)
        before = {"approve_btn": vis(pg, "#quick-approve-button"), "approver": vis(pg, "#quick-approver")}
        approve_save(pg)
        ov = pg.evaluate(OVERLAP_JS)
        pg.screenshot(path=str(OUT / f"V_{w}x{h}_after_save.png"))
        hidden_pts = [q["names"] for q in ov["pts"] if q["hidden"]]
        rec(f"V-{w}", "PASS" if not hidden_pts and before["approve_btn"] else "FAIL",
            "承認して保存のあと、候補の窓が C00003〜C00005 の点を隠さない（承認の前はボタンが見える）",
            hidden_points=hidden_pts, segs_hidden=[s for s in ov["segs"] if s["hidden_area"] > 0], pop=ov["pop"], before=before)
        pg.close()
    # V2：承認して保存のあとに話しかける（返事の欄が出る）→ 候補の窓が右下に戻る例外で、変更の点が隠れないか（1920 だけ）
    for say in ["どこが変わったの？", "ありがとう", "Zプラス方向に3ミリ動かして"]:
        pg = to_candidate(br, 1920, 1080, PICKER)
        approve_save(pg)
        E.fill_text(pg, say); pg.click("#text-send"); pg.wait_for_timeout(2500)
        ov = pg.evaluate(OVERLAP_JS)
        reply = vis(pg, "#reply-message")
        hidden_pts = [q["names"] for q in ov["pts"] if q["hidden"]]
        pg.screenshot(path=str(OUT / f"V2_1920_after_save_say_{len(RES)}.png"))
        rec(f"V2-{say}", "PASS" if not hidden_pts else "FAIL", "承認して保存のあと話しかけても、候補の窓が C00003〜C00005 の点を隠さない",
            reply_shown=reply, hidden_points=hidden_pts, pop=ov["pop"], segs_hidden=[x for x in ov["segs"] if x["hidden_area"] > 0][:3])
        pg.close()
    # W：保存の結果の言い方（窓を自動で開く経路）
    for mode in ["ok", "abort", "notallowed", "writefail", "tamper", "none"]:
        init = NOWEBDRIVER + (f"window.__mode = {json.dumps(mode)};" + PICKER if mode != "none"
                              else "delete window.showSaveFilePicker; window.showSaveFilePicker = undefined;")
        pg = to_candidate(br, 1920, 1080, init)
        approve_save(pg)
        if mode == "none" and vis(pg, ".save-as-download"):
            with pg.expect_download() as dl: pg.click(".save-as-download")
            pg.wait_for_timeout(300)
        txt = pg.inner_text("#export-result")
        head = pg.inner_text("#next-action") if pg.locator("#next-action").count() else ""
        ovw = pg.evaluate(OVERLAP_JS); hid_w = [q["names"] for q in ovw["pts"] if q["hidden"]]
        calls = pg.evaluate("window.__pickerCalls || 0")
        checks = txt.count("✓"); saved_word = "保存しました" in txt
        really_saved = mode == "ok"
        problems = []
        if saved_word and not really_saved: problems.append("保存していないのに「保存しました」")
        if ("保存しました" in head) and not really_saved: problems.append("見出しが「保存しました」（保存していない）")
        if hid_w: problems.append(f"候補の窓が {hid_w} を隠す")
        if checks > 1: problems.append(f"✓ が {checks} 個")
        warn = []
        if (not really_saved) and checks >= 1: warn.append("選んだ場所には保存していないのに ✓（アプリの記録の ✓）が目立つ")
        if (not really_saved) and not (vis(pg, ".save-as-pick") or vis(pg, ".save-as-download")):
            warn.append("保存していないのに、保存し直しのボタンが無い")
        if "アプリの記録" not in txt: problems.append("アプリの記録の行が無い")
        pg.screenshot(path=str(OUT / f"W_{mode}.png"))
        rec(f"W-{mode}", "FAIL" if problems else ("WARN" if warn else "PASS"), "保存の結果の言い方", picker_calls=calls, problems=problems, warn=warn, head=head,
            text=txt.replace("\n", " ／ ")[:400])
        pg.close()
    br.close()
(OUT / "ui_polish_check.json").write_text(json.dumps(RES, ensure_ascii=False, indent=1), encoding="utf-8")
print("合計", len(RES), "FAIL", sum(r["verdict"] == "FAIL" for r in RES))
