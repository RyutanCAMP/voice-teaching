// 画面の明るさ（ライト・ダーク）と、図（SVG）の色（feat/ui-refresh）。
// - 既定は OS の設定に合わせる（自動）。切り替えのボタンで選んだものは、このブラウザーの localStorage にだけ覚える。
// - 画面の色は style.css の変数（:root と [data-theme="dark"]）。図の線・点・格子の色は、ここの SVG_PALETTES で決める。
// - 色は見やすさのためだけ。止まった候補（承認できない）の変更後をオレンジにしない、などの決まりはテーマで変えない。
// - DOM が無くても試せるように、決め方の関数（normalizePref・resolveTheme・svgPalette）は外から値を受け取る。
"use strict";

export const THEME_KEY = "vt-theme";  // "auto" | "light" | "dark"
export const THEME_PREFS = ["auto", "light", "dark"];

export function normalizePref(v) {
  return v === "light" || v === "dark" ? v : "auto";
}

// 選んだもの（自動・ライト・ダーク）と OS の設定から、実際に使うテーマを決める
export function resolveTheme(pref, osDark) {
  const p = normalizePref(pref);
  if (p === "auto") return osDark ? "dark" : "light";
  return p;
}

// 図の色。ライトの変更後（after）・止まった候補（stopped）・MOVJ の点線（movj）は、これまでの値のまま
export const SVG_PALETTES = {
  light: {
    canvas: "#fbfbfd",       // 図の地（style.css の --canvas と同じ値）
    line: "#b6bbc3",         // 変更候補が無いときの区間
    before: "#9aa0a8",       // 変更前の区間（候補があるとき）
    movedBefore: "#a1a6ad",  // 動かす点の、変更前の位置
    after: "#ff6a1a",        // 変更後の区間・点
    afterText: "#c4470a",    // 変更後の名前・量（文字）
    stopped: "#8e8e93",      // 止まった候補の変更後（オレンジにしない）
    movj: "#8e8e96",         // MOVJ の細い点線（highlight.js の segmentLook と同じ値）
    point: "#1d1d1f",
    sel: "#0a84ff",          // 選んだ点
    selText: "#0066cc",      // 選んだ点の名前（文字）
    selFill: "rgba(10,132,255,0.15)",
    cand: "#5e5ce6",         // 会話で出した位置の候補（選んではいない）
    candFill: "rgba(94,92,230,0.10)",
    label: "#6e6e73",
    grid: "#dcdce2",
    drop: "#d8d8de",         // 点から床への補助線
    axisX: "#e5484d", axisY: "#30a46c", axisZ: "#0a84ff",
    insetBg: "#ffffff", insetStroke: "#e5e5ea",
    markerRing: "#ffffff",
    runBefore: "#6e6e73",    // 再生の印（変更前）
  },
  dark: {
    canvas: "#0e131a",
    line: "#5c6672",
    before: "#7d8794",
    movedBefore: "#7d8794",
    after: "#ff8a3d",
    afterText: "#ffa565",
    stopped: "#b8bec6",
    movj: "#8b949e",
    point: "#e6edf3",
    sel: "#3ea6ff",
    selText: "#6cbcff",
    selFill: "rgba(62,166,255,0.18)",
    cand: "#8f8cff",
    candFill: "rgba(143,140,255,0.14)",
    label: "#9aa4b0",
    grid: "#232a33",
    drop: "#2f3742",
    axisX: "#ff6b6b", axisY: "#3fd68c", axisZ: "#4cb2ff",
    insetBg: "#161b22", insetStroke: "#30363d",
    markerRing: "#0e131a",
    runBefore: "#9aa4b0",
  },
};

export function svgPalette(theme) {
  return SVG_PALETTES[theme === "dark" ? "dark" : "light"];
}

// ---- ブラウザーの中だけ ----
function readPref() {
  try { return normalizePref(window.localStorage.getItem(THEME_KEY)); } catch (e) { return "auto"; }
}

const media = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
let pref = typeof window !== "undefined" ? readPref() : "auto";
const listeners = [];

export function themePref() { return pref; }

export function currentTheme() {
  return resolveTheme(pref, !!(media && media.matches));
}

// 今のテーマの図の色
export function palette() { return svgPalette(currentTheme()); }

function apply() {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  // 自動のときは属性を付けない（style.css の prefers-color-scheme に任せる。JS より先に正しい色で出る）
  if (pref === "auto") delete root.dataset.theme; else root.dataset.theme = pref;
  root.dataset.resolvedTheme = currentTheme();
  for (const fn of listeners) fn(currentTheme());
}

export function setThemePref(p) {
  pref = normalizePref(p);
  try { window.localStorage.setItem(THEME_KEY, pref); } catch (e) { /* 覚えられなくても、今の画面は切り替える */ }
  apply();
}

export function onThemeChange(fn) { listeners.push(fn); }

if (media && media.addEventListener) media.addEventListener("change", () => { if (pref === "auto") apply(); });
apply();
