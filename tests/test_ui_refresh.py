"""画面の仕上げ（feat/ui-refresh）：テーマ・効果音・読み込みの演出の、画面のファイルの決まり。

ブラウザーでの動き（OS に合わせる・切り替えを覚える・既定 OFF・reduced-motion で演出なし・名前の重なり）は
tools/e2e_browser.py の check_ui_refresh、色のコントラストと鳴らす条件は tests/theme.test.mjs で確かめる。
"""
import http.client
import re
import threading
from pathlib import Path

from voice_teaching.web import server

STATIC = Path(__file__).resolve().parent.parent / "voice_teaching" / "web" / "static"


def text(name):
    return (STATIC / name).read_text(encoding="utf-8")


def test_server_serves_theme_and_sound_modules():
    srv = server.make_server(port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for path in ["/static/theme.js", "/static/sfx.js"]:
            c = http.client.HTTPConnection(*srv.server_address[:2], timeout=5)
            c.request("GET", path)
            r = c.getresponse()
            body = r.read()
            assert r.status == 200 and r.getheader("Content-Type").startswith("text/javascript"), path
            assert body
            c.close()
    finally:
        srv.shutdown()
        srv.server_close()


def test_no_sound_files_are_shipped():
    # 音は Web Audio で作る（音のファイルは入れない）
    for p in STATIC.iterdir():
        assert p.suffix.lower() not in {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".webm"}, p.name


def test_sound_is_off_by_default_and_silent_while_mic_is_on():
    s = text("sfx.js")
    assert '=== "on"' in s                     # "on" と覚えているときだけ ON
    assert "fetch(" not in s and "/api/" not in s  # 音は合図だけ（承認・出力を呼ばない）
    a = text("app.js")
    assert "new Sfx(() => recording() || state.live)" in a  # マイクが ON の間は鳴らさない
    # 鳴らすのは読み込み・候補・承認の3か所だけ。止まった候補では鳴らさない
    assert sorted(re.findall(r'sfx\.play\("(\w+)"\)', a)) == ["approve", "candidate", "candidate", "load"]
    assert a.count('if (state.st.can_approve) sfx.play("candidate")') == 2


def test_theme_and_sound_switches_live_in_the_help_popover():
    h = text("index.html")
    pop = re.search(r'<div id="help-pop".*?<!-- /help-pop -->', h, re.S).group(0)
    for w in ['data-theme-pref="auto"', 'data-theme-pref="light"', 'data-theme-pref="dark"', 'id="sound-on"', 'id="sound-off"']:
        assert w in pop, w
    assert re.search(r'id="sound-off" aria-pressed="true"', pop)  # 既定 OFF
    assert "approve" not in pop  # 小窓から承認しない


def test_reveal_is_skipped_with_reduced_motion_and_short():
    v = text("view3d.js")
    assert "prefers-reduced-motion: reduce" in v
    assert re.search(r"REVEAL_MS = (\d+)", v) and int(re.search(r"REVEAL_MS = (\d+)", v).group(1)) <= 1000
    css = text("style.css")
    # 演出の指定は、動きを減らす設定でないときだけ
    i = css.index("@media (prefers-reduced-motion: no-preference)")
    assert css.index("svg.revealing line.seg.draw") > i


def test_dark_theme_keeps_safety_colours_distinct():
    css = text("style.css")
    dark = re.search(r':root\[data-theme="dark"\] \{([^}]*)\}', css).group(1)
    for var in ["--red", "--danger-bg", "--warn-bg", "--primary-bg", "--primary-fg"]:
        assert var + ":" in dark, var
    # 承認できない帯・承認ボタン・注意の文は、テーマの変数で色を付ける（テーマを変えても消えない）
    assert re.search(r"\.confirm-blocked \{[^}]*background: var\(--danger-bg\)", css)
    assert re.search(r"button\.approve:not\(\[disabled\]\) \{[^}]*background: var\(--primary-bg\)", css)
    assert re.search(r"\.confirm-warnings \{[^}]*background: var\(--warn-bg\)", css)
