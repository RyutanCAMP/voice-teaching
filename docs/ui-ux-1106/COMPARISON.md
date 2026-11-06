# 同解像度のスクリーンショット比較

[比較ビューを開く](index.html)。すべて合成JOB・モック・Chrome156で撮影。

共通76項目：変更前 73 PASS / 3 FAIL → 変更後 76 PASS / 0 FAIL。

変更前だけの3項目は、不具合発生時に追加した証拠画像の横スクロール検査。共通ケースの比較には含めない。

| 解像度 | 場面 | 変更前 | 変更後 |
|---|---|---|---|
| 1920×1080 | 読み込み後 | [画像](before/1920x1080_loaded.png) | [画像](after/1920x1080_loaded.png) |
| 1920×1080 | 候補・座標差分 | [画像](before/1920x1080_candidate.png) | [画像](after/1920x1080_candidate.png) |
| 1920×1080 | 長い返答 | [画像](before/1920x1080_long_conversation.png) | [画像](after/1920x1080_long_conversation.png) |
| 1440×900 | 読み込み後 | [画像](before/1440x900_loaded.png) | [画像](after/1440x900_loaded.png) |
| 1440×900 | 候補・座標差分 | [画像](before/1440x900_candidate.png) | [画像](after/1440x900_candidate.png) |
| 1440×900 | 長い返答 | [画像](before/1440x900_long_conversation.png) | [画像](after/1440x900_long_conversation.png) |
| 1280×720 | 読み込み後 | [画像](before/1280x720_loaded.png) | [画像](after/1280x720_loaded.png) |
| 1280×720 | 候補・座標差分 | [画像](before/1280x720_candidate.png) | [画像](after/1280x720_candidate.png) |
| 1280×720 | 長い返答 | [画像](before/1280x720_long_conversation.png) | [画像](after/1280x720_long_conversation.png) |

## 3Dの表示領域

| 解像度・場面 | 前 | 後 |
|---|---:|---:|
| 1920×1080 loaded | 1350.8×842 | 1370.8×842 |
| 1920×1080 repeat_candidate | 1350.8×782 | 1370.8×782 |
| 1440×900 loaded | 876.4×676 | 896.4×676 |
| 1440×900 repeat_candidate | 876.4×616 | 896.4×616 |
| 1280×720 loaded | 786.8×496 | 790.8×496 |
| 1280×720 repeat_candidate | 786.8×436 | 790.8×436 |

安全の最終合格判定、実Claudeの意味理解、実マイクの認識精度をこの数値から主張しない。
比較の元データはbefore/audit.json・after/audit.json、画像とCSSのハッシュはcomparison.json。
