"""本番候補の画面を、本物の Claude のサーバー（クロークが自分の作業フォルダで立てたもの・8896 ではない）で確かめる。
使い方：python -I rc_ui_real.py <URL> <JOB のフォルダ> <出力フォルダ>
計画書 6章の確かめ：開発の印が出ない・30mm を止める・あいまいな量を聞き返す・上の確かめ・候補の数と 3D・確認表示・承認・出力・
「だめ」・空の送信・3つの画面の大きさでボタンが隠れない・候補の窓が会話に重ならない。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL, JD, OUT = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
OUT.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding="utf-8")
RES = []
log_hidden = []
DEV = re.compile(r"TEST|filming|DEBUG|MOCK|\b[0-9a-f]{7,40}\b|v1\.00|開発者")


def vis(pg, s):
    return pg.locator(s).count() > 0 and pg.locator(s).first.is_visible()


def wait_idle(pg, ms=60000):
    pg.wait_for_function("() => !document.getElementById('text-send').disabled", timeout=ms)
    pg.wait_for_timeout(500)


def say(pg, text):
    if not pg.is_visible("#text-input") and pg.is_visible("#kbd-button"):
        pg.click("#kbd-button")
    if not pg.is_visible("#text-input"):
        log_hidden.append(text)
        pg.wait_for_selector("#text-input", state="visible", timeout=40000)
    pg.fill("#text-input", text)
    pg.click("#text-send")
    pg.wait_for_timeout(300)
    wait_idle(pg)


def last_app(pg):
    t = pg.locator("#ask-turns li").all_inner_texts()
    return (t[-1] if t else "")[:300]


def box(pg, sel):
    if not vis(pg, sel):
        return None
    return pg.locator(sel).first.bounding_box()


def overlap(a, b):
    if not a or not b:
        return 0
    x = max(0, min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"]))
    y = max(0, min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"]))
    return int(x * y)


def in_view(pg, sel):
    b = box(pg, sel)
    if not b:
        return "hidden"
    pg.locator(sel).first.scroll_into_view_if_needed()
    b = pg.locator(sel).first.bounding_box()
    v = pg.viewport_size
    return "ok" if 0 <= b["y"] and b["y"] + b["height"] <= v["height"] and 0 <= b["x"] and b["x"] + b["width"] <= v["width"] else "outside"


def run(w, h):
    pg = BR.new_page(viewport={"width": w, "height": h})
    log = {}
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)[:200]))
    pg.goto(URL + "?opening=0")
    pg.wait_for_timeout(800)
    header = pg.inner_text("header") if vis(pg, "header") else pg.inner_text("body")[:400]
    log["dev_marks_in_header"] = sorted(set(DEV.findall(header)))
    pg.set_input_files("#file-input", str(JD / "DEMO_RJ_XYZ.JBI"))
    pg.wait_for_selector("#job-area:not([hidden])")
    pg.wait_for_timeout(500)
    pg.locator("#position-chips button", has_text="C00004").first.click()
    pg.wait_for_timeout(400)
    log["selected_readout"] = pg.inner_text("#play-status") if vis(pg, "#play-status") else ""
    # 空の送信
    if not pg.is_visible("#text-input") and pg.is_visible("#kbd-button"):
        pg.click("#kbd-button")
    pg.fill("#text-input", "")
    log["empty_send_enabled"] = pg.is_enabled("#text-send")
    say(pg, "Zプラス方向に30ミリ動かして")
    log["r30"] = last_app(pg); log["open_confirm_after_30"] = vis(pg, "#open-confirm") and pg.is_enabled("#open-confirm")
    pg.screenshot(path=str(OUT / f"{w}x{h}_1_30mm.png"))
    say(pg, "もう少し上に寄せたいな")
    log["r_vague"] = last_app(pg)
    say(pg, "5ミリ")
    log["r_5"] = last_app(pg)
    pg.screenshot(path=str(OUT / f"{w}x{h}_2_updown.png"))
    yes = pg.locator("button", has_text="合っている")
    log["updown_button"] = yes.count() > 0
    if yes.count():
        yes.last.click()
        try:
            pg.wait_for_selector("#quick-approve-button", state="visible", timeout=40000)  # 候補は Claude の解釈のあと（数秒）
        except Exception:  # noqa: BLE001
            log["cand_wait_timeout"] = True
        pg.wait_for_timeout(800)
    log["cand"] = (pg.inner_text("#candidate-view") if vis(pg, "#candidate-view") else "")[:200]
    log["cand_has_185"] = "185.000" in log["cand"] and "180.000" in log["cand"]
    log["cand_over_chat_px"] = overlap(box(pg, "#cand-pop"), box(pg, "#ask-turns"))
    log["open_confirm"] = in_view(pg, "#open-confirm")
    log["icon"] = pg.get_attribute("#approval-icon", "data-appr")
    pg.screenshot(path=str(OUT / f"{w}x{h}_3_candidate.png"))
    # 未承認の候補のあいだは、文字の欄とマイクが出ない（60f3d24 と同じ作り）。承認 → 出力 → 続けて話す
    log["text_input_visible_with_candidate"] = vis(pg, "#text-input") or vis(pg, "#kbd-button")
    log["approve_btn"] = in_view(pg, "#quick-approve-button")
    if vis(pg, "#quick-approve-button"):
        clicks = 0
        pg.fill("#quick-approver", "クローク確認"); pg.click("#quick-approve-button"); clicks += 1
        pg.wait_for_timeout(1000)
        log["approve_clicks"] = clicks
        log["confirm_overlay_opened"] = vis(pg, "#confirm-overlay")
        log["icon_approved"] = pg.get_attribute("#approval-icon", "data-appr")
        log["export_in_view"] = in_view(pg, "#export-button")
        pg.click("#export-button"); pg.wait_for_timeout(1200)
        log["export_result"] = (pg.inner_text("#export-result") if vis(pg, "#export-result") else "")[:200]
        log["export_enabled_after"] = pg.is_enabled("#export-button") if vis(pg, "#export-button") else False
        pg.screenshot(path=str(OUT / f"{w}x{h}_4_exported.png"))
        say(pg, "3ミリに訂正して")
        log["r_teisei"] = last_app(pg)
        log["icon_after_teisei"] = pg.get_attribute("#approval-icon", "data-appr")
        log["export_enabled_after_teisei"] = pg.is_enabled("#export-button") if vis(pg, "#export-button") else False
        pg.screenshot(path=str(OUT / f"{w}x{h}_5_teisei.png"))
    body = pg.inner_text("body")
    log["dev_marks_in_body"] = sorted(set(m for m in DEV.findall(body) if not re.fullmatch(r"[0-9a-f]{7,40}", m) or m.isdigit() is False))[:10]
    log["page_errors"] = errors
    log["text_input_hidden_before"] = list(log_hidden); log_hidden.clear()
    RES.append({"size": f"{w}x{h}", **log})
    print(json.dumps(RES[-1], ensure_ascii=False)[:1500], flush=True)
    pg.close()


with sync_playwright() as p:
    BR = p.chromium.launch()
    for w, h in ((1920, 1080), (1440, 900), (1280, 720)):
        try:
            run(w, h)
        except Exception as ex:  # noqa: BLE001
            RES.append({"size": f"{w}x{h}", "error": repr(ex)[:300]}); print(w, h, "ERROR", repr(ex)[:300])
    BR.close()
(OUT / "rc_ui_real.json").write_text(json.dumps({"sha": "36ca898", "res": RES}, ensure_ascii=False, indent=1), encoding="utf-8")
