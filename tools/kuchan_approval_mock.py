"""承認1回・SIM 保存の UI 案を、本物の画面（filming・モック・偽の音声認識）に重ねて撮る（クーちゃん 11/7）。

    python tools/kuchan_approval_mock.py --out <出力> [--sizes 1920x1080,1440x900,1280x720]

- アプリのコードは変えない。撮るときだけ、ページの中の #dock-actions の見た目を docs/ui-kuchan-1107/approval-save/proposal.html の
  部品に置き換える（押しても何も起きない絵）。承認の状態は本物の流れ（確認表示のボタン）で作ってから重ねる。
- API・実マイク・実機は使わない。出力は一時フォルダの SIM だけ。
- 主なボタン（承認・保存）が画面の中で、ポップアップに切られずに見えるかを測って mock_metrics.json に残す。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "tools")]

import demo_mock as dm  # noqa: E402
import e2e_browser as E  # noqa: E402
from voice_teaching import claude_explain as cx  # noqa: E402
from voice_teaching import sim  # noqa: E402
from voice_teaching.claude_interpreter import MockInterpreter  # noqa: E402
from voice_teaching.web import server  # noqa: E402

PROPOSAL = (REPO / "docs/ui-kuchan-1107/approval-save/proposal.html").read_text(encoding="utf-8")
BLOCK = {m.group(1): m.group(0) for m in re.finditer(r'<div class="vt-step" data-step="(\w+)">.*?\n</div>', PROPOSAL, re.S)}
RESULT = {m.group(1): m.group(0) for m in re.finditer(r'<p class="vt-result (\w+)">.*?</p>', PROPOSAL, re.S)}

INJECT = """([html, extra]) => {
  const box = document.querySelector('#dock-actions');
  box.querySelectorAll(':scope > *:not(.vt-mock)').forEach(e => e.style.display = 'none');
  box.querySelectorAll('.vt-mock').forEach(e => e.remove());
  const d = document.createElement('div'); d.className = 'vt-mock'; d.style.flex = '1 1 100%';
  d.innerHTML = html + (extra || ''); box.append(d);
  // 承認のあとは、候補のカードの中の「承認しました」と3つの状態は今のまま（本物）
}"""

VISIBLE = """(sel) => { const e = document.querySelector(sel); if (!e) return 'none';
  const r = e.getBoundingClientRect(); const p = (e.closest('.cand-card') || document.querySelector('#cand-pop')).getBoundingClientRect();  // 中でスクロールする枠
  const inView = r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth;
  const inPop = r.top >= p.top - 1 && r.bottom <= p.bottom + 1;
  return inView && inPop ? 'visible' : 'cut'; }"""


def serve(tmp: Path):
    cx.PRICES[dm.MOCK_MODEL] = cx.Price(input=0.0, output=0.0, cache_write_5m=0.0, cache_write_1h=0.0, cache_read=0.0)
    sim.DEFAULT_OUT_DIR = tmp / "sim"
    ex = cx.Explainer("mock-no-network", dm.MOCK_MODEL, client=dm.ScriptClient(), usage_log=cx.UsageLog(tmp / "usage.jsonl"))
    srv = server.make_server(port=0, interpreter=MockInterpreter(), updown_config=None, explainer=ex, channel="filming")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def speak(pg, text):
    pg.evaluate("t => { window.__fakeText = t; }", text)
    pg.click("#mic-button")
    if pg.is_visible("#consent-yes"):
        pg.click("#consent-yes")
    E.until(pg, lambda: pg.is_enabled("#voice-stop"))
    pg.click("#voice-stop")
    E.until(pg, lambda: pg.input_value("#text-input") == text)
    pg.click("#text-send")
    E.until(pg, lambda: pg.is_enabled("#text-send") or not pg.is_visible("#text-send"), 40000)
    pg.wait_for_timeout(800)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sizes", default="1920x1080,1440x900,1280x720")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="vt-kuchan-mock-"))
    srv, url = serve(tmp)
    from playwright.sync_api import sync_playwright
    metrics = {}
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for size in a.sizes.split(","):
                w, h = (int(v) for v in size.split("x"))
                pg = br.new_page(viewport={"width": w, "height": h})
                pg.add_init_script(E.FAKE_RECOGNITION)
                pg.add_init_script("try { localStorage.setItem('vt-voice-mode', 'browser'); } catch (_) {}")
                m = metrics.setdefault(size, {})
                shot = lambda name: pg.screenshot(path=str(out / f"{size}_{name}.png"))  # noqa: E731
                pg.goto(url)
                pg.wait_for_timeout(1200)
                pg.set_input_files("#file-input", str(REPO / "samples/dummy/DEMO_RJ_XYZ.JBI"))
                pg.wait_for_selector("#job-area:not([hidden])")
                pg.locator("#position-chips button", has_text="C00004").first.click()
                pg.wait_for_timeout(500)
                speak(pg, "Zプラス方向に5ミリ")
                shot("A0_now_candidate")
                pg.evaluate(INJECT, [BLOCK["approve"], ""])
                pg.wait_for_timeout(300)
                shot("A1_proposed_approve_disabled")
                pg.evaluate("() => { const b = document.querySelector('.vt-mock #approve-one'); b.disabled = false;"
                            " document.querySelector('.vt-mock #approver-name').value = 'UI確認'; }")
                pg.wait_for_timeout(500)  # ボタンの色の切り替え（transition）が終わってから撮る
                m["approve_button"] = pg.evaluate(VISIBLE, ".vt-mock #approve-one")
                m["simonly_note"] = pg.evaluate(VISIBLE, ".vt-mock .vt-simonly")
                m["warnings_before_approve"] = pg.evaluate(VISIBLE, "#candidate-view .cand-warn")
                m["diff_before_approve"] = pg.evaluate(VISIBLE, "#candidate-view .xyz")
                shot("A2_proposed_approve_ready")
                # 本物の承認（今の確認表示のボタン）で、承認の状態を作る
                pg.evaluate("() => document.querySelectorAll('.vt-mock').forEach(e => e.remove())")
                pg.evaluate("() => document.querySelectorAll('#dock-actions > *').forEach(e => e.style.display = '')")
                pg.click("#open-confirm")
                pg.wait_for_timeout(600)
                pg.fill("#approver-name", "UI確認")
                pg.click("#approve-button")
                pg.wait_for_timeout(900)
                shot("B0_now_approved")
                pg.evaluate(INJECT, [BLOCK["save"], ""])
                pg.wait_for_timeout(300)
                m["save_button"] = pg.evaluate(VISIBLE, ".vt-mock #save-sim")
                shot("B1_proposed_save")
                for k in ("ok", "dl", "cancel"):
                    extra = RESULT[k]
                    html = BLOCK["save"] if k == "cancel" else ""
                    pg.evaluate(INJECT, [html.replace("vt-step", "vt-step") if html else "", extra])
                    pg.wait_for_timeout(200)
                    m[f"result_{k}"] = pg.evaluate(VISIBLE, f".vt-mock .vt-result.{k}")
                    shot(f"C_{k}")
                pg.close()
            br.close()
    finally:
        srv.shutdown()
        srv.server_close()
    (out / "mock_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
