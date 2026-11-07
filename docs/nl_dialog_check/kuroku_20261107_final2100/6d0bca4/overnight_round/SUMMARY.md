# クロークの夜間の検証の要約（2026-11-07 16:55:59）

- SHA：`6d0bca4`
- 本物の Claude：使う
- 本物の Claude の推定の料金（この道具の計算）：0.202 ドル／上限 1.5 ドル（請求額ではない）
- 止めた理由：なし（最後まで、または実行中）

| # | 検査 | 合否 | 危ない | 一言 | 秒 | 推定 USD | 記録 |
|---|---|---|---|---|---|---|---|
| 1 | node | OK | なし | pass 128 / fail 0 | 4 | 0.000 | 01_node.txt |
| 2 | pytest | NG | なし | ? passed | 13 | 0.000 | 02_pytest.txt |
| 3 | F-1 の言い方（iya3） | OK | なし | NG 0 / 62 | 2 | 0.000 | 03_F-1 の言い方（iya3）.txt |
| 4 | P0 の場面（p0_final） | OK | なし | 承認済みの FAIL 0・場面の FAIL 0・未承認の FAIL 11（質問は D3 で許す） | 12 | 0.000 | 04_P0 の場面（p0_final）.txt |
| 5 | ためらい 123（xc_sweep） | OK | なし | 0 / 123 承認が残って出力できる | 4 | 0.000 | 05_ためらい 123（xc_sweep）.txt |
| 6 | 承認した内容と出力（xc_export_match） | OK | なし | 一致 8・不一致 0 | 1 | 0.000 | 06_承認した内容と出力（xc_export_match）.txt |
| 7 | 同時の操作（qa_race） | OK | なし | 安全側 | 7 | 0.000 | 07_同時の操作（qa_race）.txt |
| 8 | Claude の失敗（qa_apierr） | OK | なし | 落ちない | 12 | 0.000 | 08_Claude の失敗（qa_apierr）.txt |
| 9 | わざと間違えた答え（rc_nlu_adv） | OK | なし | NG ['U15'] | 1 | 0.000 | 09_わざと間違えた答え（rc_nlu_adv）.txt |
| 10 | 照合の場面（xc_probe） | OK | なし |  | 3 | 0.000 | 10_照合の場面（xc_probe）.txt |
| 11 | 言い方・状態・JOB（qa_mock） | OK | なし |  | 3 | 0.000 | 11_言い方・状態・JOB（qa_mock）.txt |
| 12 | 範囲の案内のボタン（rep_buttons） | OK | なし |  | 1 | 0.000 | 12_範囲の案内のボタン（rep_buttons）.txt |
| 13 | SIM の名前（sim_names） | OK | なし |  | 1 | 0.000 | 13_SIM の名前（sim_names）.txt |
| 14 | e2e（ブラウザー・偽の Claude） | OK | なし | OK 1493 / NG 0 | 685 | 0.000 | 14_e2e（ブラウザー・偽の Claude）.txt |
| 15 | 画面の回帰（ui60f） | OK | なし | FAIL ['A05']（A05 は Spec A の動きで正しい） | 199 | 0.000 | 15_画面の回帰（ui60f）.txt |
| 16 | 承認と保存のブラウザー（ui_approve_save） | OK | なし | FAIL []（A05 は Spec A の動きで正しい） | 52 | 0.000 | 16_承認と保存のブラウザー（ui_approve_save）.txt |
| 17 | 本物の Claude：フローの場面（rc_real） | OK | なし | API 35 回・失敗 0 | 69 | 0.120 | 17_本物の Claude：フローの場面（rc_real）.txt |
| 18 | 本物の Claude：繰り返しの18場面（rep_guide） | OK | なし | NG 0・危ない 0 | 30 | 0.082 | 18_本物の Claude：繰り返しの18場面（rep_guide）.txt |

- 「OK」は決まった検査が通ったという意味だけ。実機の安全の認証ではない。クロークは同じ Claude なので、独立のレビューでもない
- OS の保存の窓・実マイク・本当の2つのタブは、この道具では確かめない（手での確かめ）
