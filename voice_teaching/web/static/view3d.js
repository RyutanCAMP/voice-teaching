// 3D の点と経路の表示（依存なし。SVG に投影して描く）。
// - 座標はジョブの位置の値（X・Y・Z、mm）をそのまま使う。作った座標・ロボット本体・関節は描かない。
// - ドラッグで回転、ホイールで拡大・縮小、点を押して選ぶ、視点を戻す。重なって見える点は、押すと選び分けの一覧を出す。
// - 経路は JOB の命令の順に点を直線で結んだ目安。再生は線の上を印が動くだけで、ロボットの動きではない。
// - 区間の種類（kind）で描き分ける（highlight.js の segmentLook）。MOVJ（関節移動）は細い灰色の点線で、
//   再生の印は MOVL の区間だけ線の上を動く。MOVJ・目安の区間では印を消し、終わったら終点に置く。
// - 画面の上下は Z、奥行きは X・Y を回して見せる（表示の向きだけ。指示の方向の解釈には使わない）。
// - 変更候補があるときは、動かす点に触れる区間（入る・出る）だけを変更後の色で描く。止まった候補は灰色の点線。
// - 色はテーマ（ライト・ダーク）の図の色（theme.js の palette）。描き分けの決まり（止まった候補をオレンジにしない等）はテーマで変えない。
// - JOB を読み込んだときだけ、点が順に現れ・直線の区間が引かれる短い演出（1秒以内）。prefers-reduced-motion のときはしない。
//   演出は透明度と線の引き方だけで、点の位置・線の形・色の属性は変えない。
"use strict";
import { displayMinus, segmentLook, segmentTitle } from "/static/highlight.js";
import { palette } from "/static/theme.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const DEFAULT_YAW = -0.75;    // 最初の向き（ラジアン）
const DEFAULT_PITCH = 0.42;
const OVERLAP_PX = 6;         // この距離より近く見える点は、まとめて選び分ける
const HOLD_MS = 700;          // MOVJ・目安の区間で、印を消しておく時間（画面の上だけ。実際の動きとは関係ない）
export const REVEAL_MS = 1000;  // 読み込んだときの演出の長さの上限（これより後の描き直しでは演出しない）
const REVEAL_SPREAD = 560;      // 点を順に出す時間（最初の点〜最後の点）。1つの点・線の演出は 300ms まで

export function reducedMotion() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function svgEl(tag, attrs) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, String(v));
  return e;
}

// 文字の幅の目安（px・12px の文字）。名前の重なりを避けるためだけに使う
function textWidth(s) {
  let w = 0;
  for (const ch of String(s)) w += ch.charCodeAt(0) < 0x2000 ? 7 : 12;
  return w;
}

function overlaps(a, b) {
  return a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0;
}

function niceStep(span) {
  const raw = span / 8;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const m of [1, 2, 5, 10]) if (raw <= m * p) return m * p;
  return 10 * p;
}

export class View3D {
  // host：描く場所（div）。opts.onPick(name)：点を選んだとき（無ければ選べない）
  constructor(host, opts = {}) {
    this.host = host;
    this.onPick = opts.onPick || null;
    this.onView = opts.onView || null;  // 回した・拡大した・戻したとき（「視点を戻す」を出すかどうか）
    this.hint = opts.hint !== false;    // 「ドラッグで回す・ホイールで拡大」を出す（確認表示の中では出さない）
    this.interacted = false;            // 一度でも回した・拡大したら、操作のヒントは出さない
    this.W = opts.width || 720;
    this.H = opts.height || 480;
    this.data = null;
    this.yaw = DEFAULT_YAW; this.pitch = DEFAULT_PITCH; this.zoom = 1;
    this.marker = null;      // 再生の印（世界座標）
    this.playToken = 0;
    this.chooser = null;
    this.revealAt = 0;       // 読み込んだときの演出を始めた時刻（0 なら演出しない）
    host.classList.add("view3d");
    this._bind();
  }

  // data: { points: [{name, xyz, line}], segments: [{from, to, line_no, text, kind, solid}],
  //         after: null | { points, segments, moved }, selected }
  setData(data) {
    this.data = data;
    const all = data.points.concat(data.after ? data.after.points : []).map((p) => p.xyz);
    const lo = [0, 1, 2].map((k) => Math.min(...all.map((v) => v[k])));
    const hi = [0, 1, 2].map((k) => Math.max(...all.map((v) => v[k])));
    this.center = [0, 1, 2].map((k) => (lo[k] + hi[k]) / 2);
    this.lo = lo; this.hi = hi;
    this.span = Math.max(Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]), 1);
    this.render();
  }

  // 読み込んだときの短い演出。prefers-reduced-motion のときはしない（host の data-reveal に結果を残す）
  reveal() {
    const reduce = reducedMotion();
    this.host.dataset.reveal = reduce ? "skipped" : "played";
    if (reduce || !this.data) { this.revealAt = 0; return false; }
    this.revealAt = performance.now();
    this.render();
    return true;
  }

  _applyReveal(svg, elapsed) {
    const order = Object.fromEntries(this.data.points.map((p, i) => [p.name, i]));
    const n = this.data.points.length;
    const step = Math.min(70, REVEAL_SPREAD / Math.max(1, n - 1));
    const delay = (i, extra = 0) => `${Math.round(i * step + extra - elapsed)}ms`;
    svg.classList.add("revealing");
    for (const g of svg.querySelectorAll("g.pt3")) {
      const i = Math.min(...g.dataset.names.split(" ").map((nm) => order[nm] ?? 0));
      g.style.animationDelay = delay(i);
    }
    for (const line of svg.querySelectorAll("line.seg")) {
      const i = order[line.dataset.from] ?? 0;
      if (!line.hasAttribute("stroke-dasharray")) {  // 実線（MOVL）だけ線を引く。点線・破線は形を変えずに出す
        line.classList.add("draw");
        line.setAttribute("pathLength", "1");
      }
      line.style.animationDelay = delay(i, 60);
    }
  }

  reset() {
    this.yaw = DEFAULT_YAW; this.pitch = DEFAULT_PITCH; this.zoom = 1;
    this.closeChooser();
    this.render();
    this.onView && this.onView();
  }

  // 最初の向き・大きさから変えたか
  changed() {
    return this.yaw !== DEFAULT_YAW || this.pitch !== DEFAULT_PITCH || this.zoom !== 1;
  }

  // 世界座標 → 画面（x, y, 奥行き）
  project(v) {
    const x = v[0] - this.center[0], y = v[1] - this.center[1], z = v[2] - this.center[2];
    const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw);
    const x1 = x * cy - y * sy, y1 = x * sy + y * cy;
    const cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
    const up = z * cp + y1 * sp, depth = y1 * cp - z * sp;
    const D = this.span * 2.6;
    const f = D / (D + depth);
    const k = (Math.min(this.W, this.H) * 0.82 / this.span) * this.zoom;
    return [this.W / 2 + x1 * k * f, this.H / 2 - up * k * f, depth];
  }

  render() {
    if (!this.data) return;
    const d = this.data;
    const svg = svgEl("svg", { viewBox: `0 0 ${this.W} ${this.H}`, width: this.W, height: this.H,
      role: "img", "aria-label": "3D の点と経路（ドラッグで回す・ホイールで拡大縮小）" });
    const P = palette();
    this._floor(svg, P);
    const c = d.after;
    const stopped = !!(c && d.stopped);
    const cAfter = stopped ? P.stopped : P.after, cAfterText = stopped ? P.stopped : P.afterText;
    // 経路（命令の順に結んだ直線）
    const lines = { before: [], after: [] };
    const seg = (s, pts, color, w, key) => {
      const at = Object.fromEntries(pts.map((p) => [p.name, p.xyz]));
      const a = at[s.from], b = at[s.to];
      if (!a || !b) return;
      const p = this.project(a), q = this.project(b);
      const look = segmentLook(s.kind);
      const playing = this.marker && this.marker.seg === s;  // 再生中の区間は少し太く
      const line = svgEl("line", { x1: p[0], y1: p[1], x2: q[0], y2: q[1],
        stroke: look.color && key === "before" ? P.movj : color, "stroke-width": w * look.width + (playing ? 1.5 : 0),
        "stroke-linecap": "round", class: `seg ${key} seg-${look.kind}`, "data-kind": look.kind, "data-from": s.from, "data-to": s.to });
      if (look.dash) line.setAttribute("stroke-dasharray", look.dash);
      // 止まった候補は、目安の区間（6 5 の破線）・MOVJ の点線と見分けられる細かい点線
      if (key === "after" && stopped) { line.setAttribute("stroke-dasharray", "0.5 7"); line.setAttribute("stroke-width", "4"); }
      const t = svgEl("title", {}); t.textContent = segmentTitle(s);
      line.append(t);
      svg.append(line);
      lines[key].push(line);
    };
    for (const s of d.segments) seg(s, d.points, c ? P.before : P.line, 2.5, "before");
    // 変更後は、動かす点に触れる区間だけ（ほかの区間は変更前と同じ線なので描き直さない）
    if (c) for (const s of c.segments) if (s.from === c.moved || s.to === c.moved) seg(s, c.points, cAfter, 3, "after");
    this.lines = lines;

    // 点（奥から手前の順に描く）。近く見える点は1つの印にまとめ、押すと選び分ける
    const items = d.points.map((p) => ({ p, s: this.project(p.xyz) }));
    items.sort((a, b) => b.s[2] - a.s[2]);
    const groups = [];
    for (const it of items) {
      const g = groups.find((q) => Math.hypot(q.s[0] - it.s[0], q.s[1] - it.s[1]) < OVERLAP_PX);
      if (g) g.names.push(it.p.name); else groups.push({ s: it.s, names: [it.p.name], p: it.p });
    }
    const moved = c ? c.moved : null;
    const labelBoxes = [];  // 置いた名前の四角（あとの名前・変更量の文字を重ならない所に置くため）
    // 名前を置いてはいけない所：すべての点・変更後の点の輪（r=14）・右上の拡大の窓。図の外にも置かない
    const qAfter = c ? c.points.find((p) => p.name === moved) : null;
    const afterS = qAfter ? this.project(qAfter.xyz) : null;
    const keepOut = groups.map((g) => ({ x0: g.s[0] - 9, x1: g.s[0] + 9, y0: g.s[1] - 9, y1: g.s[1] + 9 }));
    const insetBox = c ? { x0: this.W - 150, x1: this.W, y0: 0, y1: 150 } : null;
    const boxOf = (x, y, anchor, tw) => (anchor === "start"
      ? { x0: x - 2, x1: x + tw + 2, y0: y - 13, y1: y + 4 } : { x0: x - tw - 2, x1: x + 2, y0: y - 13, y1: y + 4 });
    const ring = (m) => (afterS ? [{ x0: afterS[0] - m, x1: afterS[0] + m, y0: afterS[1] - m, y1: afterS[1] + m }] : []);
    const free = (bx, ringM) => bx.x0 >= 2 && bx.x1 <= this.W - 2 && bx.y0 >= 2 && bx.y1 <= this.H - 2
      && !(insetBox && overlaps(bx, insetBox)) && !keepOut.concat(ring(ringM)).some((q) => overlaps(bx, q))
      && !labelBoxes.some((q) => overlaps(bx, q));
    // 近くの空いた所に置く。近くが空いていなければ、少し離して引き出し線でつなぐ（同じ所に点が重なるとき・変更量の文字が近いとき）
    const place = (px, py, tw, near, far, ringM = 17) => {
      for (const [dx, dy, anchor, lead] of near.concat(far.map((f) => [...f, true]))) {
        const bx = boxOf(px + dx, py + dy, anchor, tw);
        if (free(bx, ringM)) return { x: px + dx, y: py + dy, anchor, lead: !!lead, bx };
      }
      const [dx, dy, anchor] = near[0];
      return { x: px + dx, y: py + dy, anchor, lead: false, bx: boxOf(px + dx, py + dy, anchor, tw) };
    };
    const leader = (px, py, at, color) => {
      const ex = at.anchor === "start" ? at.x - 3 : at.x + 3, ey = at.y - 4;
      const len = Math.hypot(ex - px, ey - py) || 1;
      return svgEl("line", { x1: px + (ex - px) / len * 9, y1: py + (ey - py) / len * 9, x2: ex, y2: ey,
        stroke: color, "stroke-width": 1, "stroke-opacity": 0.7, class: "leader" });
    };
    const NAME_NEAR = [[12, -8, "start"], [-12, -8, "end"], [12, 18, "start"], [-12, 18, "end"]];
    const NAME_FAR = [[30, -30, "start"], [-30, -30, "end"], [30, 40, "start"], [-30, 40, "end"], [46, 4, "start"], [-46, 4, "end"]];
    for (const g of groups) {
      const [x, y] = g.s;
      const sel = g.names.includes(d.selected);
      const isMoved = g.names.includes(moved);
      const el = svgEl("g", { class: "pt3" + (sel ? " sel" : ""), "data-names": g.names.join(" ") });
      // 床への縦の補助線（奥行きを分かりやすくする）
      const floor = this.project([g.p.xyz[0], g.p.xyz[1], this.lo[2] - this.span * 0.08]);
      svg.insertBefore(svgEl("line", { x1: x, y1: y, x2: floor[0], y2: floor[1], stroke: P.drop,
        "stroke-width": 1, "stroke-dasharray": "2 3", class: "droplink" }), svg.firstChild.nextSibling);
      el.append(svgEl("circle", { cx: x, cy: y, r: 16, fill: "transparent" }));  // 押しやすい大きさ
      if (sel) el.append(svgEl("circle", { cx: x, cy: y, r: 12, fill: P.selFill, stroke: P.sel, "stroke-width": 2 }));
      // 会話で Claude（モック）が出した位置の候補：選んではいないので、選んだ点（青）と違う色の点線の輪で示す
      if (g.names.some((n) => (d.candidates || []).includes(n))) {
        el.classList.add("cand");
        el.append(svgEl("circle", { cx: x, cy: y, r: 19, fill: P.candFill, stroke: P.cand,
          "stroke-width": 2.5, "stroke-dasharray": "5 4", class: "cand-ring" }));
      }
      el.append(svgEl("circle", { cx: x, cy: y, r: 6, fill: isMoved ? P.movedBefore : (sel ? P.sel : P.point) }));
      // 動かす点の名前は、変更後の点の横に1つだけ出す（変更前の名前と重ならないように）
      const shownNames = isMoved && c ? g.names.filter((n) => n !== moved) : g.names;
      if (shownNames.length) {
        const name = shownNames.join(" / ");
        const at = place(x, y, textWidth(name), NAME_NEAR, NAME_FAR);
        const color = sel && !isMoved ? P.selText : P.label;
        if (at.lead) el.append(leader(x, y, at, color));
        const label = svgEl("text", { x: at.x, y: at.y, "text-anchor": at.anchor, fill: color,
          "font-weight": sel && !isMoved ? "600" : "400" });
        label.textContent = name;
        el.append(label);
        labelBoxes.push(at.bx);
      }
      const t = svgEl("title", {});
      t.textContent = g.names.map((n) => {
        const p = d.points.find((q) => q.name === n);
        return `${n}  ${p.line}`;
      }).join("\n");
      el.append(t);
      svg.append(el);
    }
    // 変更後の点と、変更前からの矢印（小さな変更でも見えるように）
    if (c) {
      const q = c.points.find((p) => p.name === moved);
      const p0 = d.points.find((p) => p.name === moved);
      if (q && p0) {
        const a = this.project(p0.xyz), b = this.project(q.xyz);
        svg.append(svgEl("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: cAfter, "stroke-width": 2 }));
        svg.append(svgEl("circle", { cx: b[0], cy: b[1], r: 7, fill: cAfter, class: "after-pt" }));
        svg.append(svgEl("circle", { cx: b[0], cy: b[1], r: 14, fill: "none", stroke: cAfter, "stroke-width": 1.5, "stroke-opacity": 0.5 }));
        const text = `${moved} ${displayMinus(d.delta_label || "")}`.trim();
        const tw = Math.ceil(textWidth(text) * 1.08);  // 太字
        // 同じ所にほかの位置（共用の座標など）の名前があっても重ならないように、右下・左・右上・下の順に空いている所を探す。
        // 近くが空いていなければ、離して引き出し線でつなぐ
        const at = place(b[0], b[1], tw,
          [[18, 24, "start"], [-18, 6, "end"], [18, -18, "start"], [-18, 24, "end"], [18, 40, "start"], [-18, -18, "end"]],
          [[34, 48, "start"], [-34, 48, "end"], [34, -42, "start"], [-34, -42, "end"], [54, 8, "start"], [-54, 8, "end"],
            [20, 66, "start"], [-20, 66, "end"]], 15);
        if (at.lead) svg.append(leader(b[0], b[1], at, cAfterText));
        const lab = svgEl("text", { x: at.x, y: at.y, "text-anchor": at.anchor, fill: cAfterText, "font-weight": "600", class: "moved-label" });
        lab.textContent = text;
        svg.append(lab);
        labelBoxes.push(at.bx);
        this._inset(svg, p0.xyz, q.xyz, displayMinus(d.delta_label || ""), cAfter, cAfterText, P);
      }
    }
    if (this.marker && this.marker.xyz) {  // MOVJ・目安の区間の間は xyz が無い（印を出さない）
      const m = this.project(this.marker.xyz);
      svg.append(svgEl("circle", { cx: m[0], cy: m[1], r: 9, fill: this.marker.color, stroke: P.markerRing, "stroke-width": 3, class: "marker" }));
    }
    const elapsed = this.revealAt ? performance.now() - this.revealAt : Infinity;
    if (elapsed < REVEAL_MS && !c) this._applyReveal(svg, elapsed);
    else this.revealAt = 0;
    this.host.querySelector("svg")?.remove();
    this.host.prepend(svg);
    this.svg = svg;
  }

  // 拡大の窓：変更前（灰）と変更後（オレンジ）を大きくして並べる。小さな変更も見えるように
  _inset(svg, a, b, label, color, textColor, P) {
    const S = 132, x0 = this.W - S - 12, y0 = 12;
    const pa = this.project(a), pb = this.project(b);
    const dx = pb[0] - pa[0], dy = pb[1] - pa[1];
    const len = Math.hypot(dx, dy);
    const g = svgEl("g", { class: "inset" });
    g.append(svgEl("rect", { x: x0, y: y0, width: S, height: S, rx: 14, fill: P.insetBg, stroke: P.insetStroke }));
    const cx = x0 + S / 2, cy = y0 + S / 2 + 12;
    let ux = 0, uy = -1;
    if (len > 0.01) { ux = dx / len; uy = dy / len; }
    const L = 24;  // 窓の中では、向きはそのまま・長さは決まった大きさで見せる
    const ax = cx - ux * L, ay = cy - uy * L, bx = cx + ux * L, by = cy + uy * L;
    g.append(svgEl("line", { x1: ax, y1: ay, x2: bx, y2: by, stroke: color, "stroke-width": 3, "stroke-linecap": "round" }));
    g.append(svgEl("circle", { cx: ax, cy: ay, r: 7, fill: P.movedBefore }));
    g.append(svgEl("circle", { cx: bx, cy: by, r: 8, fill: color }));
    const head = svgEl("text", { x: x0 + 12, y: y0 + 20, class: "inset-head" });
    head.textContent = "変更（拡大）";
    const sub = svgEl("text", { x: x0 + 12, y: y0 + 34, class: "inset-head" });
    sub.textContent = "長さは実寸ではありません";
    g.append(sub);
    const amt = svgEl("text", { x: x0 + S / 2, y: y0 + S - 12, "text-anchor": "middle", fill: textColor, "font-weight": "700", class: "inset-amt" });
    amt.textContent = label;
    g.append(head, amt);
    svg.append(g);
  }

  // 床の格子と、X・Y・Z の軸（向きを知るため）
  _floor(svg, P) {
    const z0 = this.lo[2] - this.span * 0.08;
    const pad = this.span * 0.15;
    const x0 = this.lo[0] - pad, x1 = this.hi[0] + pad, y0 = this.lo[1] - pad, y1 = this.hi[1] + pad;
    const step = niceStep(Math.max(x1 - x0, y1 - y0));
    const g = svgEl("g", { class: "floor" });
    const line = (a, b, attrs) => {
      const p = this.project(a), q = this.project(b);
      g.append(svgEl("line", Object.assign({ x1: p[0], y1: p[1], x2: q[0], y2: q[1] }, attrs)));
    };
    for (let x = Math.ceil(x0 / step) * step; x <= x1; x += step) line([x, y0, z0], [x, y1, z0], { stroke: P.grid, "stroke-width": 1 });
    for (let y = Math.ceil(y0 / step) * step; y <= y1; y += step) line([x0, y, z0], [x1, y, z0], { stroke: P.grid, "stroke-width": 1 });
    // 軸（床の角から、格子1目盛りの長さ）
    const pts = this.data.points.map((p) => this.project(p.xyz));
    const mx = pts.reduce((a, q) => a + q[0], 0) / pts.length, my = pts.reduce((a, q) => a + q[1], 0) / pts.length;
    const corners = [[x0, y0, z0], [x1, y0, z0], [x0, y1, z0], [x1, y1, z0]];
    const far = (c) => { const q = this.project(c); return Math.hypot(q[0] - mx, q[1] - my); };
    const o = corners.reduce((a, c) => (far(c) > far(a) ? c : a));
    const sx = o[0] === x0 ? 1 : -1, sy = o[1] === y0 ? 1 : -1;  // 角から床の内側へ向けて描く（＋の向きは矢印の先の文字で示す）
    const axes = [["X", [sx * step, 0, 0], P.axisX], ["Y", [0, sy * step, 0], P.axisY], ["Z", [0, 0, step], P.axisZ]];
    // 軸の文字は、点と点の名前に重ならない所に置く（軸の線の上を、先の方から根元の方へずらして探す）
    const taken = pts.flatMap((q) => [
      { x0: q[0] - 9, x1: q[0] + 9, y0: q[1] - 9, y1: q[1] + 9 },          // 点
      { x0: q[0] + 10, x1: q[0] + 110, y0: q[1] - 22, y1: q[1] - 2 }]);    // 点の名前（右上）
    const hit = (r) => taken.some((b) => r.x0 < b.x1 && r.x1 > b.x0 && r.y0 < b.y1 && r.y1 > b.y0);
    for (const [name, dv, color] of axes) {
      const end = [o[0] + dv[0], o[1] + dv[1], o[2] + dv[2]];
      line(o, end, { stroke: color, "stroke-width": 2 });
      let at = null;
      for (const f of [1, 0.8, 0.6, 0.4, 1.25]) {
        const p = this.project([o[0] + dv[0] * f, o[1] + dv[1] * f, o[2] + dv[2] * f]);
        for (const [ox, oy] of [[4, -4], [-26, -4], [4, 14], [-26, 14]]) {
          const r = { x0: p[0] + ox, x1: p[0] + ox + 22, y0: p[1] + oy - 12, y1: p[1] + oy + 2 };
          if (!hit(r)) { at = [p[0] + ox, p[1] + oy]; break; }
        }
        if (at) break;
      }
      if (!at) { const p = this.project(end); at = [p[0] + 4, p[1] - 4]; }
      const t = svgEl("text", { x: at[0], y: at[1], fill: color, class: "axis3", "font-weight": "600" });
      t.textContent = name + (name === "X" ? (sx > 0 ? "+" : "−") : name === "Y" ? (sy > 0 ? "+" : "−") : "+");
      taken.push({ x0: at[0], x1: at[0] + 22, y0: at[1] - 12, y1: at[1] + 2 });
      g.append(t);
    }
    const s = svgEl("text", { x: 12, y: this.H - 12, class: "axis" });
    s.textContent = `格子 ${step}mm`;
    g.append(s);
    if (this.hint && !this.interacted) {
      const hint = svgEl("text", { x: 12, y: this.H - 28, class: "hint3" });
      hint.textContent = "ドラッグで回す・ホイールで拡大";
      g.append(hint);
    }
    svg.append(g);
  }

  _pick(names, ev) {
    if (this.dragged || !this.onPick) return;
    ev.stopPropagation();
    if (names.length === 1) { this.closeChooser(); this.onPick(names[0]); return; }
    this.openChooser(names, ev);
  }

  // 重なって見える点の選び分け
  openChooser(names, ev) {
    this.closeChooser();
    const box = document.createElement("div");
    box.className = "chooser";
    const r = this.host.getBoundingClientRect();
    box.style.left = `${ev.clientX - r.left + 10}px`;
    box.style.top = `${ev.clientY - r.top + 10}px`;
    const head = document.createElement("p");
    head.textContent = "重なっている位置";
    const x = document.createElement("button");
    x.type = "button"; x.className = "close"; x.textContent = "×"; x.setAttribute("aria-label", "閉じる");
    x.addEventListener("click", (e) => { e.stopPropagation(); this.closeChooser(); });
    head.append(x);
    box.append(head);
    const blocked = (this.data && this.data.blocked) || {};
    for (const n of names) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = n + (blocked[n] ? "（変更できません）" : "");
      b.dataset.name = n;
      if (blocked[n]) { b.classList.add("blocked"); b.title = "この位置は変更できません：" + blocked[n]; }
      b.addEventListener("click", (e) => { e.stopPropagation(); this.closeChooser(); this.onPick(n); });
      box.append(b);
    }
    this.host.append(box);
    this.chooser = box;
  }

  closeChooser() {
    if (this.chooser) this.chooser.remove();
    this.chooser = null;
  }

  _bind() {
    const h = this.host;
    let start = null;
    h.addEventListener("pointerdown", (ev) => {
      if (ev.target.closest(".chooser")) return;
      start = { x: ev.clientX, y: ev.clientY, yaw: this.yaw, pitch: this.pitch };
      this.dragged = false;
      const pt = ev.target.closest && ev.target.closest(".pt3");
      this.downNames = pt ? pt.dataset.names.split(" ") : null;  // 再生中に作り直されても選べるように
    });
    h.addEventListener("pointermove", (ev) => {
      if (!start || !(ev.buttons & 1)) return;
      const dx = ev.clientX - start.x, dy = ev.clientY - start.y;
      if (!this.dragged && Math.hypot(dx, dy) < 4) return;
      if (!this.dragged) { this.dragged = true; this.interacted = true; this.closeChooser(); h.setPointerCapture?.(ev.pointerId); }
      this.yaw = start.yaw + dx * 0.006;
      this.pitch = Math.max(0.05, Math.min(1.3, start.pitch + dy * 0.006));  // 床が裏返らない範囲
      this.render();
      this.onView && this.onView();
    });
    const end = () => { start = null; this.downNames = null; setTimeout(() => { this.dragged = false; }, 0); };
    h.addEventListener("pointerup", (ev) => {
      if (start && !this.dragged && this.downNames) {
        this.justPicked = true;
        this._pick(this.downNames, ev);
      }
      end();
    });
    h.addEventListener("pointercancel", end);
    h.addEventListener("wheel", (ev) => {
      if (!this.data) return;
      ev.preventDefault();
      this.interacted = true;
      this.closeChooser();
      this.zoom = Math.max(0.6, Math.min(5, this.zoom * Math.exp(-ev.deltaY * 0.0012)));
      this.render();
      this.onView && this.onView();
    }, { passive: false });
    h.addEventListener("click", (ev) => {
      if (this.justPicked) { this.justPicked = false; return; }  // 点を押した直後の click では閉じない
      if (!ev.target.closest(".chooser")) this.closeChooser();
    });
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") this.closeChooser(); });
  }

  // ---- 経路の再生：runs = [{name, color, segments, points}]。onStep(run, seg) で今の命令の行を知らせる ----
  stop() {
    this.playToken++;
    this.marker = null;
    this.render();
  }

  play(runs, onStep, onEnd) {
    this.stop();
    const token = this.playToken;
    const SPEED = this.span * 0.9;  // 世界座標の速さ（mm/秒の目安。実際のロボットの速度とは関係ない）
    const list = [];
    for (const run of runs) {
      const at = Object.fromEntries(run.points.map((p) => [p.name, p.xyz]));
      for (const s of run.segments) if (at[s.from] && at[s.to]) list.push({ run, s, a: at[s.from], b: at[s.to] });
    }
    let i = 0, t0 = null;
    const step = (now) => {
      if (token !== this.playToken) return;
      if (i >= list.length) { this.marker = null; this.render(); onEnd && onEnd(); return; }
      const it = list[i];
      if (t0 === null) { t0 = now; onStep && onStep(it.run, it.s); }
      const animate = segmentLook(it.s.kind).animate;
      const len = Math.hypot(it.b[0] - it.a[0], it.b[1] - it.a[1], it.b[2] - it.a[2]);
      const dur = animate ? Math.max(350, (len / SPEED) * 1000) : HOLD_MS;
      const f = Math.min(1, (now - t0) / dur);
      // MOVL の区間だけ線の上を動かす。MOVJ・目安の区間は、直線の上に印を置かない（区間の間は消す）
      this.marker = { color: it.run.color, seg: it.s,
        xyz: animate ? [0, 1, 2].map((k) => it.a[k] + (it.b[k] - it.a[k]) * f) : null };
      this.render();
      if (f >= 1) { i++; t0 = null; }
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
}
