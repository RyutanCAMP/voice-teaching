// ［承認して保存］の画面の確かめ（モック・読むだけ）：名前なし／二度押し／出力の数／範囲の案内のボタン
const { chromium } = require('playwright'); const fs = require('fs'), path = require('path');
const [, , BASE, REPO, OUT] = process.argv;
const T = async (p, s) => ((await p.textContent(s).catch(() => '')) || '').replace(/\s+/g, ' ').trim();
const simDir = path.join(REPO, 'output/sim');
const count = () => (fs.existsSync(simDir) ? fs.readdirSync(simDir).length : 0);
const clear = () => { if (fs.existsSync(simDir)) for (const f of fs.readdirSync(simDir)) fs.unlinkSync(path.join(simDir, f)); };
async function send(p, t) { if (!(await p.isVisible('#text-input'))) { await p.click('#kbd-button'); await p.waitForTimeout(300); } await p.fill('#text-input', t); await p.click('#text-send'); await p.waitForTimeout(1600); }
const res = []; const ok = (id, pass, d) => { res.push({ id, pass, d }); console.log(`${pass ? 'PASS' : 'FAIL'} ${id} :: ${d}`); };
(async () => {
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' }); clear();
  for (const [w, h] of [[1920, 1080], [1280, 720]]) {
    const p = await b.newPage({ viewport: { width: w, height: h } });
    await p.goto(BASE); await p.waitForTimeout(700);
    await p.setInputFiles('#file-input', path.join(REPO, 'samples/dummy/DEMO_BUTTON_REPEAT.JBI')); await p.waitForTimeout(1300);
    await send(p, 'C1C4を2回繰り返したい');
    const guideTxt = await T(p, '#reply-message');
    const btns = await p.$$eval('#reply-message button, #ask-turns button', (bs) => bs.map((x) => x.innerText.trim()).filter(Boolean));
    await p.screenshot({ path: path.join(OUT, `ui_${w}_1_guide.png`) });
    ok(`${w} 案内カード`, /C00001〜C00003/.test(guideTxt) && btns.some((t) => /3回にする/.test(t)), `ボタン=${JSON.stringify(btns.slice(-3))}`);
    const pick = p.locator('#reply-message button, #ask-turns button', { hasText: '3回にする' }).last();
    if (await pick.count()) { await pick.click(); await p.waitForTimeout(1200); }
    ok(`${w} 案内のボタンでは候補にならない`, !(await p.isVisible('#quick-approve')) && (await p.isVisible('#range-yes')), `範囲の確認のボタン=${await p.isVisible('#range-yes')}`);
    if (await p.isVisible('#range-yes')) { await p.click('#range-yes'); await p.waitForTimeout(1400); }
    const qaVisible = await p.isVisible('#quick-approve-button');
    ok(`${w} ［承認して保存］が見える`, qaVisible, await T(p, '#quick-approve'));
    // 名前なし
    if (qaVisible) {
      await p.fill('#quick-approver', ''); await p.click('#quick-approve-button'); await p.waitForTimeout(600);
      const err = await T(p, '#quick-approve-error');
      ok(`${w} 名前なしは承認しない・出力しない`, /名前/.test(err) && count() === 0, `注意「${err}」・ファイル ${count()}`);
      await p.screenshot({ path: path.join(OUT, `ui_${w}_2_noname.png`) });
      // 二度押し
      await p.fill('#quick-approver', '確認');
      await p.dblclick('#quick-approve-button'); await p.waitForTimeout(2500);
      const n1 = count();
      const st = await T(p, '#status-line'); const er = await T(p, '#export-result');
      ok(`${w} 二度押しでも出力は1つ`, n1 === 1, `ファイル ${n1}・結果「${er.slice(0, 90)}」`);
      if (await p.isVisible('#export-button') && await p.isEnabled('#export-button')) { await p.click('#export-button'); await p.waitForTimeout(1200); }
      ok(`${w} 出力のあと押し直してもファイルは増えない`, count() === 1, `ファイル ${count()}・［出力］見える=${await p.isVisible('#export-button')}`);
      await p.screenshot({ path: path.join(OUT, `ui_${w}_3_saved.png`) });
      // 承認のあとの否定 → 出力できない
      await send(p, '違う');
      const enabled = (await p.isVisible('#export-button')) && (await p.isEnabled('#export-button'));
      ok(`${w} 承認のあと「違う」→ ［出力］を押せない`, !enabled && count() === 1, `押せる=${enabled}・返事「${(await T(p, '#reply-message')).slice(0, 80)}」`);
    }
    await p.close(); clear();
  }
  fs.writeFileSync(path.join(OUT, 'ui_result.json'), JSON.stringify(res, null, 1));
  console.log(`合計 PASS ${res.filter((r) => r.pass).length} / ${res.length}`);
  await b.close();
})();
