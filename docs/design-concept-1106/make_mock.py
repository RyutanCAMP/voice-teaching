"""Voice Teaching 新デザインの完成イメージ（1920×1080・3画面）。アプリのコードとは別の見本。値は合成デモ JOB DEMO_C_PLACE。"""
from pathlib import Path

OUT = Path(__file__).resolve().parent

PTS = {  # DEMO_C_PLACE の位置（X は全部 400 なので、Y を横・Z を縦に描く）
    "C00000": (0, 400), "C00001": (-150, 300), "C00002": (-150, 200), "C00003": (-150, 300),
    "C00004": (150, 300), "C00005": (150, 200), "C00006": (150, 300), "C00007": (0, 400),
}
ORDER = ["C00000", "C00001", "C00002", "C00003", "C00004", "C00005", "C00006", "C00007"]
LABEL = {(0, 400): "C00000 · C00007", (-150, 300): "C00001 · C00003", (-150, 200): "C00002",
         (150, 300): "C00004 · C00006", (150, 200): "C00005"}
CX, CY, K = 690, 470, 2.35  # 3D の画面の中の位置（3D の枠の左上が 0,0）


def P(y, z):
    # 少し斜めから見下ろす形（奥行きは床の格子だけで出す）
    return CX + y * K, CY - (z - 290) * K


def grid():
    # 床（Z=150）の格子。奥の線ほど詰まって薄くなる透視の見え方（見た目だけ）
    out = []
    hx = CX
    base = P(0, 150)[1]
    for i in range(-9, 10):
        x = CX + i * 120
        out.append(f'<line x1="{x:.0f}" y1="{base + 70:.0f}" x2="{hx + (x - hx) * 0.42:.0f}" y2="{base - 26:.0f}" class="grid"/>')
    for t in (0, 0.25, 0.47, 0.66, 0.82, 0.95):
        y = base + 70 - t * 96
        w = 1100 * (1 - t * 0.58)
        out.append(f'<line x1="{CX - w:.0f}" y1="{y:.0f}" x2="{CX + w:.0f}" y2="{y:.0f}" class="grid" opacity="{1 - t * 0.6:.2f}"/>')
    return "\n".join(out)


def path(points, cls):
    d = " ".join(("M" if i == 0 else "L") + f"{P(*points[n])[0]:.1f},{P(*points[n])[1]:.1f}" for i, n in enumerate(ORDER))
    return f'<path d="{d}" class="{cls}"/>'


def scene(mode):
    pts = dict(PTS)
    after = dict(PTS)
    after["C00005"] = (150, 205)
    parts = [f'<svg viewBox="0 0 1380 940" class="scene">', '<defs><radialGradient id="g"><stop offset="0" stop-color="#5aa2ff" stop-opacity=".9"/>'
             '<stop offset="1" stop-color="#5aa2ff" stop-opacity="0"/></radialGradient>'
             '<filter id="blur"><feGaussianBlur stdDeviation="6"/></filter></defs>', grid()]
    # 床への落とし線（高さが分かるように）
    for n, (y, z) in {k: v for k, v in pts.items() if k in ("C00002", "C00005", "C00000")}.items():
        a, b = P(y, z), P(y, 150)
        parts.append(f'<line x1="{a[0]:.0f}" y1="{a[1]:.0f}" x2="{b[0]:.0f}" y2="{b[1]:.0f}" class="drop"/>')
    parts.append(path(pts, "route"))
    if mode != "idle":  # 変わる区間（入る区間・出る区間）だけを青く光らせる
        seg = " ".join(("M" if i == 0 else "L") + f"{P(*after[n])[0]:.1f},{P(*after[n])[1]:.1f}"
                       for i, n in enumerate(["C00004", "C00005", "C00006"]))
        parts.append(f'<path d="{seg}" class="route after"/>')
    for (y, z), lab in LABEL.items():
        x, yy = P(y, z)
        sel = lab == "C00005"
        if sel and mode != "idle":
            ax, ay = P(150, 205)
            parts.append(f'<circle cx="{x:.0f}" cy="{yy:.0f}" r="9" class="pt-before"/>')
            parts.append(f'<circle cx="{ax:.0f}" cy="{ay:.0f}" r="46" fill="url(#g)" opacity=".55"/>')
            parts.append(f'<circle cx="{ax:.0f}" cy="{ay:.0f}" r="11" class="pt-after"/>')
            parts.append(f'<line x1="{x:.0f}" y1="{yy - 14:.0f}" x2="{ax:.0f}" y2="{ay + 16:.0f}" class="arrow"/>')
            parts.append(f'<text x="{ax + 62:.0f}" y="{ay - 2:.0f}" class="lab sel">C00005</text>')
            parts.append(f'<text x="{ax + 62:.0f}" y="{ay + 22:.0f}" class="lab delta">Z +5.000 mm</text>')
            continue
        if sel:
            parts.append(f'<circle cx="{x:.0f}" cy="{yy:.0f}" r="52" fill="url(#g)" opacity=".7"/>')
            parts.append(f'<circle cx="{x:.0f}" cy="{yy:.0f}" r="22" class="ring"/>')
        parts.append(f'<circle cx="{x:.0f}" cy="{yy:.0f}" r="{10 if sel else 7}" class="{"pt sel" if sel else "pt"}"/>')
        if sel:
            parts.append(f'<text x="{x + 66:.0f}" y="{yy + 6:.0f}" class="lab sel">{lab}</text>')
        elif y < 0:
            parts.append(f'<text x="{x - 20:.0f}" y="{yy - 14:.0f}" class="lab" text-anchor="end">{lab}</text>')
        else:
            parts.append(f'<text x="{x + 20:.0f}" y="{yy - 14:.0f}" class="lab">{lab}</text>')
    # 軸の小さな目印
    ox, oy = 90, 860
    parts.append(f'<g class="axes"><line x1="{ox}" y1="{oy}" x2="{ox + 46}" y2="{oy}" class="ax-y"/><text x="{ox + 54}" y="{oy + 5}">Y</text>'
                 f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy - 46}" class="ax-z"/><text x="{ox - 5}" y="{oy - 54}">Z</text></g>')
    parts.append("</svg>")
    return "\n".join(parts)


ICON_MIC = '<svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7"/></svg>'
ICON_KEY = '<svg viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="12" rx="2.5"/><path d="M7 10h.01M10.5 10h.01M14 10h.01M17 10h.01M7.5 14h9"/></svg>'
ICON_RESET = '<svg viewBox="0 0 24 24"><path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4.5 4.5v3.7h3.7"/><circle cx="12" cy="12" r="1.6"/></svg>'
ICON_PLAY = '<svg viewBox="0 0 24 24"><path d="M8 5.5v13l10.5-6.5z" fill="currentColor" stroke="none"/></svg>'
ICON_INFO = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.6v.2"/></svg>'
ICON_HELP = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .8-1 1.5v.4M12 16.6v.2"/></svg>'
APPROVAL = {
    "none": ('<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" stroke-dasharray="3 3"/><path d="M8.5 12h7"/></svg>', "未読込", "#6c7894"),
    "pending": ('<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>', "未承認", "#9aa6c2"),
}

CSS = """
*{box-sizing:border-box;margin:0}
body{width:1920px;height:1080px;overflow:hidden;font-family:"Yu Gothic UI","Segoe UI","Meiryo",sans-serif;color:#e8eefc;
 background:radial-gradient(1200px 800px at 72% 52%,#0f2147 0%,#0a1530 45%,#060c1c 100%);letter-spacing:.01em}
svg{fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
header{position:absolute;left:0;right:0;top:0;height:72px;display:flex;align-items:center;padding:0 40px;gap:14px}
.logo{display:flex;align-items:center;gap:12px;font-size:19px;font-weight:600;color:#dfe8ff}
.logo b{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;font-size:13px;letter-spacing:.04em;
 background:radial-gradient(circle at 35% 30%,#7fb6ff,#2f6fe0 60%,#1a3f8f);box-shadow:0 0 18px rgba(77,148,255,.65)}
.hdr-right{margin-left:auto;display:flex;align-items:center;gap:6px}
.sim{font-size:12px;font-weight:700;letter-spacing:.12em;color:#7fb2ff;border:1px solid rgba(127,178,255,.4);border-radius:999px;padding:4px 10px;margin-right:10px}
.ic{width:40px;height:40px;border-radius:12px;display:grid;place-items:center;color:#8d9abb}
.ic svg{width:22px;height:22px}
.appr{display:flex;align-items:center;gap:6px;font-size:13px;margin-right:6px}
.appr svg{width:22px;height:22px}
.left{position:absolute;left:0;top:72px;width:560px;bottom:0;display:flex;flex-direction:column;align-items:center}
.job{margin-top:34px;font-size:14px;color:#8a97b5;display:flex;gap:10px;align-items:center}
.job i{width:6px;height:6px;border-radius:50%;background:#4f8fff;box-shadow:0 0 8px #4f8fff;display:inline-block}
.target{margin-top:70px;text-align:center}
.target small{display:block;font-size:14px;color:#8a97b5;margin-bottom:6px;letter-spacing:.08em}
.target strong{font-size:44px;font-weight:600;letter-spacing:.06em;font-family:"Cascadia Mono","Consolas",monospace;color:#f2f6ff}
.mic{margin-top:64px;position:relative;width:210px;height:210px;border-radius:50%;display:grid;place-items:center;
 background:radial-gradient(circle at 38% 32%,#76b0ff 0%,#3577ec 45%,#1d4cb3 100%);
 box-shadow:0 0 0 14px rgba(61,139,255,.10),0 0 0 34px rgba(61,139,255,.05),0 0 90px rgba(61,139,255,.55)}
.mic svg{width:78px;height:78px;stroke:#fff;stroke-width:1.6}
.say{margin-top:46px;font-size:28px;font-weight:600;color:#eef3ff}
.ex{margin-top:14px;font-size:17px;color:#7f8db0}
.kbd{margin-top:40px;width:48px;height:48px;border-radius:50%;display:grid;place-items:center;color:#8d9abb;background:rgba(255,255,255,.04)}
.kbd svg{width:24px;height:24px}
.stage{position:absolute;left:540px;top:72px;right:0;bottom:0}
.scene{position:absolute;left:0;top:0;width:1380px;height:940px}
.grid{stroke:rgba(120,160,255,.10);stroke-width:1}
.drop{stroke:rgba(150,180,255,.16);stroke-width:1;stroke-dasharray:3 5}
.route{stroke:#cdd9f5;stroke-width:2.2;opacity:.85}
.route.ghost{stroke:#6f7c9a;stroke-dasharray:5 6;opacity:.55}
.route.after{stroke:#5aa2ff;stroke-width:2.6;opacity:1;filter:drop-shadow(0 0 6px rgba(90,162,255,.6))}
.pt{fill:#dfe7fb;stroke:none}.pt.sel{fill:#7fb6ff}
.ring{stroke:#7fb6ff;stroke-width:2}
.pt-before{fill:none;stroke:#8590ab;stroke-width:2;stroke-dasharray:3 3}
.pt-after{fill:#7fb6ff;stroke:#fff;stroke-width:2}
.arrow{stroke:#7fb6ff;stroke-width:2;marker-end:none}
.lab{fill:#9aa7c6;stroke:none;font-size:15px;font-family:"Cascadia Mono","Consolas",monospace}
.lab.sel{fill:#cfe2ff;font-size:17px;font-weight:600}
.lab.delta{fill:#7fb6ff;font-size:15px}
.axes text{fill:#7d8aab;stroke:none;font-size:13px}.ax-y{stroke:#45c48a}.ax-z{stroke:#5aa2ff}
.reset{position:absolute;right:44px;top:24px;width:46px;height:46px;border-radius:50%;display:grid;place-items:center;color:#a9b6d6;
 background:rgba(255,255,255,.05)}
.reset svg{width:22px;height:22px}
.play{position:absolute;left:50%;transform:translateX(-50%);bottom:56px;width:52px;height:52px;border-radius:50%;display:grid;place-items:center;
 color:#dce6ff;background:rgba(255,255,255,.07)}
.play svg{width:20px;height:20px}
.note{position:absolute;left:44px;bottom:22px;font-size:13px;color:#6f7da0}
/* 候補 */
.chat{margin-top:40px;width:440px;display:flex;flex-direction:column;gap:14px}
.u{align-self:flex-end;max-width:360px;padding:11px 16px;border-radius:18px 18px 4px 18px;background:rgba(255,255,255,.07);font-size:17px;color:#e7edfb}
.stop{padding:12px 16px;border-radius:14px;background:rgba(255,181,71,.08);color:#ffcf86;font-size:15px;line-height:1.55}
.stop b{color:#ffb547}
.mic.small{width:112px;height:112px;margin-top:auto;margin-bottom:22px;box-shadow:0 0 0 10px rgba(61,139,255,.08),0 0 50px rgba(61,139,255,.45)}
.mic.small svg{width:44px;height:44px}
.hint{font-size:14px;color:#7f8db0;margin-bottom:56px}
.card{position:absolute;left:1040px;top:560px;width:400px;padding:26px 28px;border-radius:22px;background:rgba(13,26,56,.82);
 box-shadow:0 20px 60px rgba(0,0,0,.45),inset 0 0 0 1px rgba(127,178,255,.18);backdrop-filter:blur(8px)}
.card .t{font-size:14px;color:#8a97b5;letter-spacing:.06em}
.card .pos{margin-top:6px;font-size:22px;font-weight:600}
.card .v{margin-top:16px;display:flex;align-items:baseline;gap:14px;font-family:"Cascadia Mono","Consolas",monospace}
.card .v .ax{font-size:16px;color:#5aa2ff;font-weight:700}
.card .v .a{font-size:26px;color:#9aa6c2}.card .v .to{color:#5aa2ff;font-size:22px}.card .v .b{font-size:30px;color:#fff;font-weight:600}
.card .d{margin-top:4px;font-size:15px;color:#7fb6ff;font-family:"Cascadia Mono","Consolas",monospace}
.card .w{margin-top:16px;font-size:14px;color:#a9b3cc;line-height:1.6}
.btn{margin-top:22px;height:56px;border-radius:16px;display:grid;place-items:center;font-size:18px;font-weight:600;color:#fff;
 background:linear-gradient(180deg,#4a8fff,#2d6ee6);box-shadow:0 8px 28px rgba(61,139,255,.45)}
.ghost-btn{margin-top:10px;height:44px;display:grid;place-items:center;font-size:15px;color:#8d9abb}
/* 承認確認 */
.veil{position:absolute;inset:0;background:rgba(4,9,22,.62);backdrop-filter:blur(6px)}
.modal{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:760px;padding:44px 52px 36px;border-radius:28px;
 background:linear-gradient(180deg,rgba(18,34,72,.96),rgba(11,22,48,.96));box-shadow:0 30px 90px rgba(0,0,0,.6),inset 0 0 0 1px rgba(127,178,255,.2)}
.modal .k{font-size:14px;color:#7fb2ff;letter-spacing:.16em;font-weight:700}
.modal h1{margin-top:12px;font-size:34px;font-weight:600;line-height:1.4;color:#f3f6ff}
.modal h1 em{font-style:normal;color:#7fb6ff}
.big{margin-top:26px;display:flex;align-items:baseline;gap:20px;font-family:"Cascadia Mono","Consolas",monospace}
.big .ax{font-size:20px;color:#5aa2ff;font-weight:700}.big .a{font-size:34px;color:#8f9bb8}.big .to{font-size:28px;color:#5aa2ff}.big .b{font-size:44px;color:#fff;font-weight:600}
.facts{margin-top:22px;display:grid;grid-template-columns:auto 1fr;gap:8px 22px;font-size:15px;color:#a9b3cc}
.facts span:nth-child(odd){color:#6f7da0}
.caution{margin-top:22px;padding:12px 16px;border-radius:12px;background:rgba(255,181,71,.07);color:#ffd398;font-size:14px;line-height:1.6}
.name{margin-top:26px;display:flex;gap:14px;align-items:center}
.name label{font-size:14px;color:#8a97b5;white-space:nowrap}
.name .in{flex:1;height:52px;border-radius:14px;background:rgba(255,255,255,.06);box-shadow:inset 0 0 0 1px rgba(127,178,255,.25);
 display:flex;align-items:center;padding:0 16px;font-size:18px;color:#e8eefc}
.row{margin-top:22px;display:flex;gap:14px;align-items:center}
.row .btn{margin:0;flex:1;height:60px;font-size:20px}
.row .back{width:140px;height:60px;display:grid;place-items:center;font-size:16px;color:#8d9abb;border-radius:16px;background:rgba(255,255,255,.04)}
.foot{margin-top:18px;font-size:13px;color:#6f7da0;text-align:center}
.tag{position:absolute;left:40px;bottom:16px;font-size:12px;color:#3d4a68}
"""


def header(state):
    svg, name, color = APPROVAL[state]
    return (f'<header><div class="logo"><b>VT</b>Voice Teaching</div><div class="hdr-right"><span class="sim" title="シミュレーションモード">SIM</span>'
            f'<span class="appr" style="color:{color}" title="承認の状態：{name}">{svg}</span>'
            f'<span class="ic">{ICON_INFO}</span><span class="ic">{ICON_HELP}</span></div></header>')


def stage(mode):
    note = "図は参考表示です。実際の動作・干渉は保証しません。離れて見えても当たらないとは限りません。"
    return (f'<div class="stage">{scene(mode)}<span class="reset" title="正面に戻す">{ICON_RESET}</span>'
            f'<span class="play" title="再生">{ICON_PLAY}</span><p class="note">{note}</p></div>')


def page(body, title):
    return f'<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>'


IDLE = header("pending") + f"""
<section class="left">
  <p class="job"><i></i>DEMO_C_PLACE　8 points</p>
  <div class="target"><small>選んでいる位置</small><strong>C00005</strong></div>
  <div class="mic">{ICON_MIC}</div>
  <p class="say">話しかけてください</p>
  <p class="ex">「Zプラス方向に 5 ミリ」</p>
  <span class="kbd" title="文字で入力">{ICON_KEY}</span>
</section>""" + stage("idle") + '<p class="tag">MOCK 1/3 待機中</p>'

CAND = header("pending") + f"""
<section class="left">
  <p class="job"><i></i>DEMO_C_PLACE　8 points</p>
  <div class="chat">
    <p class="u">Zプラス方向に30ミリ</p>
    <p class="stop"><b>変更しません。</b>30 mm は 1回の仮の上限 20 mm（確認待ち）を超えています。</p>
    <p class="u">Zプラス方向に5ミリ</p>
  </div>
  <div class="mic small">{ICON_MIC}</div>
  <p class="hint">続けて話せます</p>
</section>""" + stage("cand") + f"""
<div class="card">
  <p class="t">変更候補</p>
  <p class="pos">C00005</p>
  <div class="v"><span class="ax">Z</span><span class="a">200.000</span><span class="to">→</span><span class="b">205.000</span></div>
  <p class="d">+5.000 mm</p>
  <p class="w">この点に入る区間と出る区間も変わります。</p>
  <div class="btn">確認して承認へ</div>
  <div class="ghost-btn">やめる</div>
</div>""" + '<p class="tag">MOCK 2/3 変更候補</p>'

CONFIRM = CAND.replace('<p class="tag">MOCK 2/3 変更候補</p>', "") + """
<div class="veil"></div>
<div class="modal">
  <p class="k">承認の確認</p>
  <h1><em>C00005</em> を Zプラス方向に 5 mm 動かします。<br>これでいいですか？</h1>
  <div class="big"><span class="ax">Z</span><span class="a">200.000</span><span class="to">→</span><span class="b">205.000</span></div>
  <div class="facts"><span>変わる行</span><span>14行目　C00005（Z のみ）</span><span>出力</span><span>DEMO_C_PLACE_SIM.JBI（シミュレーション用・元のジョブは残ります）</span></div>
  <p class="caution">この点に出入りする区間も変わります。図は参考表示で、実機の動作・干渉は保証しません。</p>
  <div class="name"><label>承認する人</label><div class="in">唐川</div></div>
  <div class="row"><div class="back">戻る</div><div class="btn">承認する</div></div>
  <p class="foot">承認はこのボタンだけ。声では承認しません。実機への転送・ロボットの起動はしません。</p>
</div><p class="tag">MOCK 3/3 承認確認</p>"""

for name, body, title in (("1_idle", IDLE, "待機中"), ("2_candidate", CAND, "変更候補"), ("3_confirm", CONFIRM, "承認確認")):
    (OUT / f"{name}.html").write_text(page(body, title), encoding="utf-8")
print("ok")
