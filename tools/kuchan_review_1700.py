"""17時の見え方の確かめ（クーちゃん 11/7）：最新の本番候補の［承認］→［保存］・3D の差分・繰り返しの案内・保存の結果の表示を、
3つの大きさで撮って、大事な部品が画面の中で切れずに見えるかを測る。

    python tools/kuchan_review_1700.py --repo <撮るコードのフォルダ> --out <出力>

- filming の見せ方・モックの解釈・偽の音声なし（文字で入力）。API・実マイク・実機は使わない。出力は一時フォルダ。
- OS の保存の窓は自動で操作できないので、showSaveFilePicker を偽の窓に差し替える（シクロの tools/check_approve_save.py と同じ形）：
  保存できた（ok）／取りやめた（abort）／窓が無い（ダウンロードへ）の3つ。本物の窓は人の手で確かめる。
- アプリのコードは変えない。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--sizes", default="1920x1080,1440x900,1280x720")
A = ap.parse_args()
REPO = Path(A.repo).resolve()
sys.path[:0] = [str(REPO), str(REPO / "tools")]

import demo_mock as dm  # noqa: E402
from voice_teaching import claude_explain as cx  # noqa: E402
from voice_teaching import sim  # noqa: E402
from voice_teaching.claude_interpreter import MockInterpreter  # noqa: E402
from voice_teaching.web import server  # noqa: E402

FAKE_PICKER = """
window.__pickerMode = 'ok';
Object.defineProperty(navigator, 'webdriver', { get: () => false });
window.showSaveFilePicker = async (opts) => {
  window.__lastName = opts.suggestedName;
  if (window.__pickerMode === 'abort') { const e = new Error('cancel'); e.name = 'AbortError'; throw e; }
  let data = new Uint8Array();
  return { name: opts.suggestedName,
    async createWritable() { return { async write(b) { data = new Uint8Array(b); }, async close() {} }; },
    async getFile() { return new Blob([data]); } };
};
"""

# 見えるか：画面の中で、スクロールする枠（候補の窓のカード・ポップアップ）に切られていない
SEEN = """(sels) => Object.fromEntries(sels.map(s => {
  const e = document.querySelector(s);
  if (!e || e.offsetParent === null || e.closest('[hidden]')) return [s, 'none'];
  const r = e.getBoundingClientRect(); if (r.width === 0) return [s, 'none'];
  if (r.top < 0 || r.bottom > innerHeight + 0.5 || r.left < 0 || r.right > innerWidth + 0.5) return [s, 'off-screen'];
  for (let p = e.parentElement; p; p = p.parentElement) {
    const cs = getComputedStyle(p);
    if (/(auto|scroll|hidden)/.test(cs.overflowY)) { const q = p.getBoundingClientRect();
      if (r.top < q.top - 1 || r.bottom > q.bottom + 1) return [s, 'cut']; }
  }
  // ほかの部品が上に重なっていないか（真ん中の点）
  const t = document.elementFromPoint(r.left + r.width / 2, r.top + Math.min(r.height / 2, 10));
  if (t && !e.contains(t) && !t.contains(e)) return [s, 'covered'];
  return [s, 'visible'];
}))"""

PTS = """() => { const pop = document.querySelector('#cand-pop'); if (!pop || pop.offsetParent === null) return [];
  const p = pop.getBoundingClientRect(); const out = [];
  document.querySelectorAll('#fig-3d .pt3').forEach(g => { const r = g.getBoundingClientRect();
    const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
    if (cx >= p.x && cx <= p.right && cy >= p.y && cy <= p.bottom) out.push(g.getAttribute('data-names')); });
  return out; }"""

KEYS_BEFORE = ["#quick-approve-button", "#quick-approver", "#candidate-view .cand-warn", "#candidate-view .cand-job",
               "#candidate-view .cand-big", "#undo-button"]
KEYS_AFTER = ["#approval-status", "#export-button", "#approval-states"]
KEYS_SAVED = ["#export-result"]


def serve(tmp: Path):
    cx.PRICES[dm.MOCK_MODEL] = cx.Price(input=0.0, output=0.0, cache_write_5m=0.0, cache_write_1h=0.0, cache_read=0.0)
    sim.DEFAULT_OUT_DIR = tmp / "sim"
    ex = cx.Explainer("mock-no-network", dm.MOCK_MODEL, client=dm.ScriptClient(), usage_log=cx.UsageLog(tmp / "usage.jsonl"))
    srv = server.make_server(port=0, interpreter=MockInterpreter(), updown_config=None, explainer=ex, channel="filming")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def type_text(pg, text):
    if pg.is_visible("#kbd-button") and not pg.is_visible("#text-input"):
        pg.click("#kbd-button")
    pg.fill("#text-input", text)
    pg.click("#text-send")
    pg.wait_for_timeout(1500)


def main() -> int:
    out = Path(A.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="vt-kuchan-1700-"))
    srv, url = serve(tmp)
    from playwright.sync_api import sync_playwright
    res = {}
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for size in A.sizes.split(","):
                w, h = (int(v) for v in size.split("x"))
                m = res.setdefault(size, {})
                for mode in ("ok", "abort", "download"):
                    pg = br.new_page(viewport={"width": w, "height": h}, accept_downloads=True)
                    errs = []
                    pg.on("pageerror", lambda e: errs.append(str(e)))
                    pg.add_init_script(FAKE_PICKER)
                    if mode == "download":
                        pg.add_init_script("delete window.showSaveFilePicker;")
                    pg.goto(url)
                    pg.wait_for_timeout(800)
                    pg.set_input_files("#file-input", str(REPO / "samples/dummy/DEMO_RJ_XYZ.JBI"))
                    pg.wait_for_selector("#job-area:not([hidden])")
                    pg.locator("#position-chips .chip", has_text="C00004").first.click()
                    pg.wait_for_timeout(400)
                    type_text(pg, "Zプラス方向に5ミリ動かして")
                    pg.wait_for_selector("#quick-approve-button", state="visible", timeout=20000)
                    pg.wait_for_timeout(500)
                    if mode == "ok":
                        pg.screenshot(path=str(out / f"{size}_1_before_approve.png"))
                        m["before_approve"] = pg.evaluate(SEEN, KEYS_BEFORE)
                        m["points_under_popup_before"] = pg.evaluate(PTS)
                    # 17時の版（563dca2〜）：［承認して保存］1回で、承認 → 保存の窓（または ダウンロードの案内）まで進む。
                    # 窓の結果（できた・取りやめ）は押す前に決めておく
                    pg.evaluate(f"() => {{ window.__pickerMode = '{'abort' if mode == 'abort' else 'ok'}'; }}")
                    pg.fill("#quick-approver", "UI確認")
                    pg.click("#quick-approve-button")
                    pg.wait_for_selector("#approval-status:not([hidden])", timeout=10000)
                    pg.wait_for_timeout(1800)
                    pg.screenshot(path=str(out / f"{size}_2_approved_saved_{mode}.png"))
                    m[f"after_{mode}"] = pg.evaluate(SEEN, KEYS_AFTER + KEYS_SAVED)
                    m[f"points_under_popup_after_{mode}"] = pg.evaluate(PTS)
                    m[f"suggested_name_{mode}"] = pg.evaluate("() => window.__lastName || null")
                    m[f"result_{mode}_text"] = pg.inner_text("#export-result")[:300] if pg.is_visible("#export-result") else "(表示なし)"
                    m[f"retry_button_{mode}"] = pg.inner_text("#export-button") if pg.is_visible("#export-button") else "(なし)"
                    m[f"errors_{mode}"] = errs
                    pg.close()
            br.close()
    finally:
        srv.shutdown()
        srv.server_close()
    (out / "review_1700.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
