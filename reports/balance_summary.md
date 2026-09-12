# 平衡模擬結果

每策略 250 局；共 1000 局。種子從 0 起連續取樣。

| 策略 | 揭破陰謀 | 聯盟退敵 | 正面取勝 | 慘勝守山 | 門派覆滅 | 平均留門人數 | 糧餉 | 防備 | 聲望 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random_policy | 17.2% | 0.8% | 6.0% | 16.0% | 60.0% | 3.76 | 11.14 | 48.88 | 33.68 |
| highest_skill_policy | 76.0% | 6.0% | 7.2% | 7.6% | 3.2% | 3.97 | 41.9 | 66.31 | 56.74 |
| conservative_policy | 8.0% | 26.8% | 12.4% | 46.4% | 6.4% | 3.75 | 22.58 | 65.0 | 58.04 |
| resource_guard_policy | 40.4% | 4.8% | 16.4% | 38.0% | 0.4% | 3.88 | 46.14 | 64.46 | 54.45 |

| 策略 | 永久離開 | 倒戈／背叛 | 重傷次數 | 死亡 |
|---|---:|---:|---:|---:|
| random_policy | 33 | 1 | 134 | 27 |
| highest_skill_policy | 5 | 0 | 27 | 2 |
| conservative_policy | 60 | 3 | 0 | 0 |
| resource_guard_policy | 30 | 0 | 110 | 0 |

各事件選項的選取／成功次數與跨種子公平性案例，完整保存於 balance_report.json。

所有重大人物後果皆經自動稽核：離開與倒戈有不同月份的前置警示且至少一條強線索；死亡有派遣前致命風險提示。

## 結局較常由哪些策略達成

- 揭破陰謀：highest_skill_policy（76.0%）、resource_guard_policy（40.4%）、random_policy（17.2%）、conservative_policy（8.0%）
- 聯盟退敵：conservative_policy（26.8%）、highest_skill_policy（6.0%）、resource_guard_policy（4.8%）、random_policy（0.8%）
- 正面取勝：resource_guard_policy（16.4%）、conservative_policy（12.4%）、highest_skill_policy（7.2%）、random_policy（6.0%）
- 慘勝守山：conservative_policy（46.4%）、resource_guard_policy（38.0%）、random_policy（16.0%）、highest_skill_policy（7.6%）
- 門派覆滅：random_policy（60.0%）、conservative_policy（6.4%）、highest_skill_policy（3.2%）、resource_guard_policy（0.4%）
