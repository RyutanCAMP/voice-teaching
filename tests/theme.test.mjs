// 画面の明るさ（theme.js）と効果音（sfx.js）の決め方、テーマの色のコントラスト（feat/ui-refresh）。
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { normalizePref, resolveTheme, svgPalette, SVG_PALETTES, THEME_KEY } from '../voice_teaching/web/static/theme.js';
import { shouldPlay, readSoundOn, patternLength, PATTERNS, SOUND_KEY, SOUND_KINDS, GAIN } from '../voice_teaching/web/static/sfx.js';

const css = readFileSync(new URL('../voice_teaching/web/static/style.css', import.meta.url), 'utf8');

function lum(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [n >> 16, (n >> 8) & 255, n & 255]
    .map((c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; })
    .reduce((a, c, i) => a + c * [0.2126, 0.7152, 0.0722][i], 0);
}
function ratio(a, b) {
  const x = lum(a), y = lum(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}
// style.css の :root { ... }（ライト）と :root[data-theme="dark"] { ... }（ダーク）の変数（#rrggbb だけ）
function tokens(selector) {
  const out = {};
  const re = new RegExp(selector.replace(/[[\]"=]/g, (m) => '\\' + m) + '\\s*\\{([^}]*)\\}', 'g');
  for (const m of css.matchAll(re)) {
    for (const d of m[1].matchAll(/--([a-z0-9-]+):\s*(#[0-9a-f]{6})\b/gi)) out[d[1]] = d[2].toLowerCase();
  }
  return out;
}
const LIGHT = tokens(':root');
const DARK = tokens(':root[data-theme="dark"]');

test('theme preference: unknown values fall back to auto', () => {
  for (const v of [null, undefined, '', 'Dark', 'blue', 1]) assert.equal(normalizePref(v), 'auto');
  assert.equal(normalizePref('light'), 'light');
  assert.equal(normalizePref('dark'), 'dark');
  assert.equal(THEME_KEY, 'vt-theme');
});
test('auto follows the OS; an explicit choice wins over the OS', () => {
  assert.equal(resolveTheme('auto', true), 'dark');
  assert.equal(resolveTheme('auto', false), 'light');
  assert.equal(resolveTheme(null, true), 'dark');
  assert.equal(resolveTheme('light', true), 'light');
  assert.equal(resolveTheme('dark', false), 'dark');
});
test('both themes define the same SVG colours', () => {
  assert.deepEqual(Object.keys(SVG_PALETTES.dark).sort(), Object.keys(SVG_PALETTES.light).sort());
  assert.equal(svgPalette('unknown'), SVG_PALETTES.light);
});
test('light keeps the earlier after/stopped/MOVJ colours (tests and legends rely on them)', () => {
  const L = SVG_PALETTES.light;
  assert.equal(L.after, '#ff6a1a');
  assert.equal(L.afterText, '#c4470a');
  assert.equal(L.stopped, '#8e8e93');
  assert.equal(L.movj, '#8e8e96');
});
test('a stopped candidate is never drawn orange, in either theme', () => {
  for (const t of ['light', 'dark']) {
    const P = svgPalette(t);
    assert.notEqual(P.stopped, P.after, t);
    assert.notEqual(P.stopped, P.afterText, t);
    assert.notEqual(P.stopped, SVG_PALETTES.light.after, t);
    assert.notEqual(P.stopped, SVG_PALETTES.dark.after, t);
  }
});
test('SVG text is readable on the canvas (4.5:1), marks are visible (3:1 except the light orange line)', () => {
  for (const t of ['light', 'dark']) {
    const P = svgPalette(t);
    for (const k of ['label', 'afterText', 'selText']) assert.ok(ratio(P[k], P.canvas) >= 4.5, `${t} ${k} ${ratio(P[k], P.canvas)}`);
    for (const k of ['point', 'sel', 'stopped', 'cand', 'axisX', 'axisY', 'axisZ']) {
      assert.ok(ratio(P[k], P.canvas) >= 3, `${t} ${k} ${ratio(P[k], P.canvas)}`);
    }
    // ライトのオレンジの線（#ff6a1a）は 2.8:1。変更後は、名前・量の文字（afterText）と拡大の窓でも示す
    assert.ok(ratio(P.after, P.canvas) >= (t === 'light' ? 2.7 : 3), `${t} after`);
    assert.ok(ratio(P.line, P.canvas) >= 1.5 && ratio(P.before, P.canvas) >= 2, `${t} lines`);
  }
});
test('style.css canvas matches theme.js canvas', () => {
  assert.equal(LIGHT.canvas, SVG_PALETTES.light.canvas);
  assert.equal(DARK.canvas, SVG_PALETTES.dark.canvas);
});
test('the OS-dark block and the explicit dark block use the same values', () => {
  const m = css.match(/@media \(prefers-color-scheme: dark\) \{\s*:root:not\(\[data-theme="light"\]\) \{([^}]*)\}/);
  assert.ok(m);
  const auto = {};
  for (const d of m[1].matchAll(/--([a-z0-9-]+):\s*([^;]+);/g)) auto[d[1]] = d[2].trim();
  const expl = {};
  const e = css.match(/:root\[data-theme="dark"\] \{([^}]*)\}/);
  for (const d of e[1].matchAll(/--([a-z0-9-]+):\s*([^;]+);/g)) expl[d[1]] = d[2].trim();
  assert.deepEqual(auto, expl);
});
test('text colours keep contrast in both themes (warnings, red band, approve button)', () => {
  for (const [name, T] of [['light', LIGHT], ['dark', DARK]]) {
    const pairs = [
      ['text', 'bg', 4.5], ['text', 'card', 4.5], ['sub', 'card', 4.5], ['sub', 'bg', 4.5],
      ['red', 'danger-bg', 4.5], ['red', 'card', 4.5],    // 「承認できません」の帯・エラー
      ['text', 'warn-bg', 4.5],                           // 注意の文
      ['accent-dark', 'card', 4.5], ['ok', 'card', 4.5], ['link', 'card', 4.5],
      ['purple', 'purple-bg', 4.5], ['mode-fg', 'mode-bg', 4.5], ['ev-pos', 'ev-bg', 4.5],
      ['review-fg', 'review-bg', 4.5],                    // 確認だけの帯（fix/c026-r2 の .review-only の色の案）
      ['primary-fg', 'primary-bg', 3.0],                  // 承認ボタン（太字 18px）
    ];
    const all = { ...T, ...(name === 'light' ? tokens(':root') : tokens(':root[data-theme="dark"]')) };
    for (const [f, b, min] of pairs) {
      assert.ok(all[f] && all[b], `${name} ${f}/${b} missing`);
      assert.ok(ratio(all[f], all[b]) >= min, `${name} ${f} on ${b}: ${ratio(all[f], all[b]).toFixed(2)}`);
    }
    assert.ok(ratio('#ffffff', all['sel-bg']) >= 4.5, `${name} white on sel-bg`);  // 人の吹き出し・選んだ番号
  }
});
test('the red "cannot approve" band and the blue review-only band look different', () => {
  for (const T of [LIGHT, DARK]) {
    assert.notEqual(T['danger-bg'], T['review-bg']);
    assert.notEqual(T.red, T['review-fg']);
  }
});

// ---- 効果音 ----
test('sound is off unless storage says "on"', () => {
  const store = (v) => ({ getItem: (k) => (k === SOUND_KEY ? v : null) });
  assert.equal(readSoundOn(store(null)), false);
  assert.equal(readSoundOn(store('off')), false);
  assert.equal(readSoundOn(store('ON')), false);
  assert.equal(readSoundOn(store('on')), true);
  assert.equal(readSoundOn({ getItem() { throw new Error('blocked'); } }), false);
  assert.equal(SOUND_KEY, 'vt-sound');
});
test('no sound while the microphone is on, when off, or for unknown kinds', () => {
  for (const k of SOUND_KINDS) {
    assert.equal(shouldPlay(true, false, k), true, k);
    assert.equal(shouldPlay(true, true, k), false, k);
    assert.equal(shouldPlay(false, false, k), false, k);
    assert.equal(shouldPlay('on', false, k), false, k);
  }
  assert.equal(shouldPlay(true, false, 'alarm'), false);
  assert.equal(shouldPlay(true, false, 'toString'), false);
});
test('only three short, quiet sounds', () => {
  assert.deepEqual(Object.keys(PATTERNS).sort(), ['approve', 'candidate', 'load']);
  for (const k of SOUND_KINDS) assert.ok(patternLength(k) > 0 && patternLength(k) <= 0.35, k);
  assert.ok(GAIN <= 0.05);
  assert.equal(patternLength('nope'), 0);
});
