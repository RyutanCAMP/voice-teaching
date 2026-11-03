// 控えめな効果音（feat/ui-refresh）。Web Audio で短い電子音を作る（音のファイルは使わない）。
// - 既定は OFF。ON／OFF は、このブラウザーの localStorage にだけ覚える（"vt-sound" が "on" のときだけ鳴らす）。
// - 鳴らすのは3つだけ：JOB を読み込んだ・変更候補ができた・承認した。どれも 0.3 秒ほど・小さな音。
// - マイクが ON の間（聞いている・聞き直しを待っている）は鳴らさない（音を声として拾わないように）。
// - 音は合図だけ。音が鳴らなくても、画面の表示と承認ボタンの働きは変わらない。
"use strict";

export const SOUND_KEY = "vt-sound";
export const SOUND_KINDS = ["load", "candidate", "approve"];

// [周波数 Hz, 始まり 秒, 長さ 秒]。少しレトロな矩形波・三角波の短い音
export const PATTERNS = {
  load: { wave: "triangle", notes: [[660, 0, 0.06], [990, 0.07, 0.09]] },
  candidate: { wave: "square", notes: [[880, 0, 0.04], [880, 0.08, 0.04]] },
  approve: { wave: "triangle", notes: [[523.25, 0, 0.07], [659.25, 0.08, 0.07], [783.99, 0.16, 0.12]] },
};
export const GAIN = 0.035;  // 小さな音

export function patternLength(kind) {
  const p = PATTERNS[kind];
  if (!p) return 0;
  return Math.max(...p.notes.map(([, t, d]) => t + d));
}

// 鳴らしてよいか：ON で、マイクが ON でなく、知っている音のときだけ
export function shouldPlay(on, micActive, kind) {
  return on === true && !micActive && Object.prototype.hasOwnProperty.call(PATTERNS, kind);
}

export function readSoundOn(storage) {
  try { return storage.getItem(SOUND_KEY) === "on"; } catch (e) { return false; }
}

export class Sfx {
  // isMicActive()：マイクが ON か（app.js が渡す）
  constructor(isMicActive) {
    this.isMicActive = isMicActive || (() => false);
    this.ctx = null;
    this.on = typeof window !== "undefined" ? readSoundOn(window.localStorage) : false;
  }

  setOn(on) {
    this.on = on === true;
    try { window.localStorage.setItem(SOUND_KEY, this.on ? "on" : "off"); } catch (e) { /* 覚えられなくても今は切り替える */ }
  }

  // 鳴らしたら true。OFF・マイク ON・Web Audio が無いときは何もしない
  play(kind) {
    if (!shouldPlay(this.on, this.isMicActive(), kind)) return false;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return false;
    try {
      if (!this.ctx) this.ctx = new AC();  // ON のときだけ作る（OFF の間は何も作らない）
      const ctx = this.ctx;
      if (ctx.state === "suspended" && ctx.resume) ctx.resume();
      const p = PATTERNS[kind];
      const t0 = ctx.currentTime + 0.01;
      for (const [freq, at, dur] of p.notes) {
        const osc = ctx.createOscillator();
        const g = ctx.createGain();
        osc.type = p.wave;
        osc.frequency.setValueAtTime(freq, t0 + at);
        g.gain.setValueAtTime(0.0001, t0 + at);
        g.gain.linearRampToValueAtTime(GAIN, t0 + at + 0.008);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + at + dur);
        osc.connect(g); g.connect(ctx.destination);
        osc.start(t0 + at);
        osc.stop(t0 + at + dur + 0.02);
      }
      return true;
    } catch (e) {
      return false;  // 音が出せなくても、画面の操作は続ける
    }
  }
}
