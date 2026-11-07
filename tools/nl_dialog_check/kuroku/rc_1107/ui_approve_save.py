"""承認1回化と保存の場所（クロークの独立の道具・偽の Claude・偽の保存の窓）。シクロの tools/check_approve_save.py とは別に書いた。
使い方：python -I ui_approve_save.py <worktree> <出力フォルダ>
- A：承認の操作の数・名前なし・Enter・二重クリック・承認前の出力ボタン・3つの画面の大きさで見えるか・隠れていないか
- P：保存の窓の差し替え（成功・取りやめ・権限なし・書けない・読み戻しが違う・窓が無い→ダウンロード）
OS の本物の保存の窓ではない（自動で操作できない）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import threading
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

# 偽の保存の窓。mode：ok／abort／notallowed／writefail／tamper
PICKER = """
window.__saved = null; window.__pickerCalls = 0;
window.__mode = window.__mode || 'ok';
window.showSaveFilePicker = async (opts) => {
  window.__pickerCalls += 1; window.__pickerOpts = JSON.stringify(opts);
  const m = window.__mode;
  if (m === 'abort') { const e = new Error('cancel'); e.name = 'AbortError'; throw e; }
  if (m === 'notallowed') { const e = new Error('denied'); e.name = 'NotAllowedError'; throw e; }
  let buf = null;
  return {
    name: opts.suggestedName,
    async createWritable() {
      return { async write(b) { if (m === 'writefail') throw new Error('disk full'); buf = new Uint8Array(b); },
               async close() { window.__saved = buf ? Array.from(buf) : null; } };
    },
    async getFile() {
      let b = buf || new Uint8Array();
      if (m === 'tamper') { b = new Uint8Array(b); b[0] = (b[0] + 1) % 256; }
      return new Blob([b]);
    },
  };
};
"""


def rec(cid, ok, what, **kw):
    RES.append({"id": cid, "verdict": "PASS" if ok else "FAIL", "what": what, **kw})
    print(cid, "PASS" if ok else "FAIL", what, json.dumps(kw, ensure_ascii=False)[:420], flush=True)


def vis(pg, s):
    return pg.locator(s).count() > 0 and pg.locator(s).first.is_visible()


def setup(br, w=1920, h=1080, picker=True, mode="ok"):
    pg = br.new_page(viewport={"width": w, "height": h}, accept_downloads=True)
    pg.add_init_script(E.FAKE_RECOGNITION)
    if picker:
        pg.add_init_script(f"window.__mode = {json.dumps(mode)};" + PICKER)
    else:
        pg.add_init_script("delete window.showSaveFilePicker; window.showSaveFilePicker = undefined;")
    pg.goto(URL)
    pg.set_input_files("#file-input", RJ); pg.wait_for_selector("#job-area:not([hidden])")
    pg.locator("#position-chips button", has_text="C00004").first.click(); pg.wait_for_timeout(200)
    E.fill_text(pg, "Zプラス方向に5ミリ動かして"); pg.click("#text-send")
    E.until(pg, lambda: vis(pg, "#quick-approve-button"), 10000); pg.wait_for_timeout(500)
    return pg


def approved(pg):
    return pg.get_attribute("#approval-icon", "data-appr") == "ok"


def covered(pg, sel):
    loc = pg.locator(sel).first
    loc.scroll_into_view_if_needed()
    b = loc.bounding_box(); v = pg.viewport_size
    if not b:
        return "nobox"
    cx, cy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    if not (0 <= cx <= v["width"] and 0 <= cy <= v["height"]):
        return "outside"
    return loc.evaluate("(t,[x,y]) => { const e = document.elementFromPoint(x,y); return e && (t===e||t.contains(e)) ? 'ok' : (e ? (e.id||e.className||e.tagName) : 'none'); }", [cx, cy])


def server_file(name):
    p = OUT / "sim_out" / name
    return p.read_bytes() if p.exists() else None


with sync_playwright() as p:
    br = p.chromium.launch()
    # A1〜A3：3つの大きさ・承認の前に見えるもの・1回で承認
    for w, h in ((1920, 1080), (1440, 900), (1280, 720)):
        pg = setup(br, w, h)
        cand = pg.inner_text("#cand-pop") if vis(pg, "#cand-pop") else ""
        need = {"C00004": "C00004" in cand, "DEMO_RJ_XYZ": "DEMO_RJ_XYZ" in cand, "Z": "Z" in cand, "+5": "+5.000" in cand,
                "180→185": "180.000" in cand and "185.000" in cand, "SIM専用": ("シミュレーション" in cand or "SIM" in cand),
                "実機に送らない": ("実機" in cand)}
        btn = covered(pg, "#quick-approve-button")
        pre_export = vis(pg, "#export-button") and pg.is_enabled("#export-button")
        before_name = pg.is_enabled("#quick-approve-button")
        pg.click("#quick-approve-button", force=True); pg.wait_for_timeout(400)
        no_name_approved = approved(pg)
        pg.fill("#quick-approver", "クローク確認")
        pg.press("#quick-approver", "Enter"); pg.wait_for_timeout(500)
        enter_approved = approved(pg)
        clicks = 0
        if not approved(pg):
            pg.click("#quick-approve-button"); clicks = 1
            E.until(pg, lambda: approved(pg), 10000)
        overlay_opened = vis(pg, "#confirm-overlay")
        pg.screenshot(path=str(OUT / f"A_{w}x{h}_approved.png"))
        why = [k for k, v in need.items() if not v]
        if btn != "ok": why.append(f"承認のボタンが隠れている：{btn}")
        if pre_export: why.append("承認の前に出力ボタンが押せる")
        if no_name_approved: why.append("名前が空で承認された")
        if enter_approved: why.append("名前の欄の Enter で承認された（承認の操作が増えた・減った）")
        if overlay_opened: why.append("確認表示が開いた（2段のまま）")
        if not approved(pg): why.append("1回押しても承認にならない")
        rec(f"A-{w}x{h}", not why, "承認の前に見えるもの・1回で承認", why=why, button=btn, enabled_before_name=before_name, clicks=clicks)
        pg.close()

    # A4：二重クリック（すばやく2回）→ 承認の送信は1回
    pg = setup(br)
    reqs = []
    pg.on("request", lambda r: reqs.append(r.url) if r.url.endswith("/api/approve") else None)
    pg.fill("#quick-approver", "クローク確認")
    pg.dblclick("#quick-approve-button"); pg.wait_for_timeout(1500)
    rec("A4", len(reqs) == 1 and approved(pg), "二重クリックで承認の送信は1回", approve_requests=len(reqs))
    # A5：出力を2回（すばやく）→ ファイルは1つ
    ex = []
    pg.on("request", lambda r: ex.append(r.url) if r.url.endswith("/api/export") else None)
    pg.dblclick("#export-button"); pg.wait_for_timeout(1500)
    files = sorted(x.name for x in (OUT / "sim_out").iterdir())
    rec("A5", len(files) == 1, "出力ボタンの二重クリックでファイルは1つ", export_requests=len(ex), files=files)
    pg.close()

    # P1〜P5：保存の窓
    for mode, cid in (("ok", "P1"), ("abort", "P2"), ("notallowed", "P3"), ("writefail", "P5a"), ("tamper", "P5b")):
        for f in (OUT / "sim_out").glob("*"):
            f.unlink()
        pg = setup(br, mode=mode)
        pg.fill("#quick-approver", "クローク確認"); pg.click("#quick-approve-button"); E.until(pg, lambda: approved(pg), 10000)
        pg.click("#export-button"); E.until(pg, lambda: vis(pg, "#export-result"), 10000); pg.wait_for_timeout(600)
        auto_calls = pg.evaluate("window.__pickerCalls")
        if vis(pg, ".save-as-pick"):
            pg.click(".save-as-pick"); pg.wait_for_timeout(1200)
        area = pg.inner_text("#save-as-area") if vis(pg, "#save-as-area") else ""
        result = pg.inner_text("#export-result")
        name = next(iter(x.name for x in (OUT / "sim_out").iterdir()), None)
        srv_bytes = server_file(name) if name else None
        saved = pg.evaluate("window.__saved")
        opts = json.loads(pg.evaluate("window.__pickerOpts") or "{}")
        says_saved = "選んだ場所に保存しました" in area
        why = []
        if mode == "ok":
            if not says_saved: why.append("保存しましたと出ない")
            if saved is None or bytes(saved) != srv_bytes: why.append("保存した中身がサーバーのファイルと違う")
            if opts.get("suggestedName") != name: why.append(f"名前の案がサーバーと違う：{opts.get('suggestedName')} / {name}")
        else:
            if says_saved: why.append("失敗・取りやめなのに保存しましたと出る")
            if mode == "abort" and ("失敗" in area and "失敗ではありません" not in area): why.append("取りやめを失敗と書いている")
            if not vis(pg, ".save-as-download"): why.append("ダウンロードのボタンが出ない")
        pg.screenshot(path=str(OUT / f"{cid}_{mode}.png"))
        rec(cid, not why, f"保存の窓：{mode}", why=why, area=area[:160], auto_picker_calls=auto_calls,
            server_file=name, result=result[:120])
        pg.close()

    # P4：窓が無いブラウザー → ダウンロード（中身と名前）
    for f in (OUT / "sim_out").glob("*"):
        f.unlink()
    pg = setup(br, picker=False)
    pg.fill("#quick-approver", "クローク確認"); pg.click("#quick-approve-button"); E.until(pg, lambda: approved(pg), 10000)
    pg.click("#export-button"); E.until(pg, lambda: vis(pg, "#export-result"), 10000); pg.wait_for_timeout(600)
    has_pick = vis(pg, ".save-as-pick")
    with pg.expect_download(timeout=10000) as dl:
        pg.click(".save-as-download")
    d = dl.value
    path = d.path(); body = Path(path).read_bytes()
    name = next(iter(x.name for x in (OUT / "sim_out").iterdir()), None)
    area = pg.inner_text("#save-as-area")
    why = []
    if has_pick: why.append("窓が無いのに［保存先を選んで保存］が出る")
    if d.suggested_filename != name: why.append(f"ダウンロードの名前が違う：{d.suggested_filename}")
    if body != server_file(name): why.append("ダウンロードの中身がサーバーと違う")
    if "選んだ場所に保存しました" in area: why.append("ダウンロードなのに保存しましたと言う")
    rec("P4", not why, "窓が無い→ダウンロード", why=why, area=area[:200], name=d.suggested_filename)
    pg.close()

    # P6：出力が断られたら保存の窓を開かない（承認のあと「ちょっと待って」で保留 → 出力ボタンは押せないはず）
    pg = setup(br)
    pg.fill("#quick-approver", "クローク確認"); pg.click("#quick-approve-button"); E.until(pg, lambda: approved(pg), 10000)
    E.fill_text(pg, "ちょっと待って"); pg.click("#text-send"); pg.wait_for_timeout(1000)
    en = vis(pg, "#export-button") and pg.is_enabled("#export-button")
    calls = pg.evaluate("window.__pickerCalls")
    rec("P6", (not en) and calls == 0, "保留中は出力・保存の窓を開かない", export_enabled=en, picker_calls=calls)
    pg.close()
    br.close()
srv.shutdown()
(OUT / "ui_approve_save.json").write_text(json.dumps({"root": ROOT.name, "res": RES}, ensure_ascii=False, indent=1), encoding="utf-8")
print("FAIL", [r["id"] for r in RES if r["verdict"] == "FAIL"])
