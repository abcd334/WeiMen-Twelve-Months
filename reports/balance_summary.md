# 平衡模擬結果

每策略 250 局；共 1000 局。種子從 0 起連續取樣。

| 策略 | 揭破陰謀 | 聯盟退敵 | 正面取勝 | 慘勝守山 | 門派覆滅 | 平均留門人數 | 糧餉 | 防備 | 聲望 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random_policy | 3.6% | 0.8% | 4.0% | 16.8% | 74.8% | 3.64 | 6.92 | 44.09 | 32.04 |
| highest_skill_policy | 30.4% | 23.6% | 10.8% | 34.0% | 1.2% | 3.84 | 36.86 | 61.48 | 59.57 |
| conservative_policy | 0.0% | 34.0% | 8.0% | 56.4% | 1.6% | 3.42 | 28.66 | 63.16 | 61.55 |
| resource_guard_policy | 3.6% | 12.0% | 18.4% | 65.2% | 0.8% | 3.68 | 39.06 | 62.66 | 52.71 |

| 策略 | 永久離開 | 倒戈／背叛 | 重傷次數 | 死亡 |
|---|---:|---:|---:|---:|
| random_policy | 62 | 3 | 119 | 24 |
| highest_skill_policy | 38 | 0 | 26 | 1 |
| conservative_policy | 126 | 20 | 0 | 0 |
| resource_guard_policy | 74 | 6 | 78 | 1 |

各事件選項的選取／成功次數與跨種子公平性案例，完整保存於 balance_report.json。

所有重大人物後果皆經自動稽核：離開與倒戈有不同月份的前置警示且至少一條強線索；死亡有派遣前致命風險提示。

## 結局較常由哪些策略達成

- 揭破陰謀：highest_skill_policy（30.4%）、random_policy（3.6%）、resource_guard_policy（3.6%）、conservative_policy（0.0%）
- 聯盟退敵：conservative_policy（34.0%）、highest_skill_policy（23.6%）、resource_guard_policy（12.0%）、random_policy（0.8%）
- 正面取勝：resource_guard_policy（18.4%）、highest_skill_policy（10.8%）、conservative_policy（8.0%）、random_policy（4.0%）
- 慘勝守山：resource_guard_policy（65.2%）、conservative_policy（56.4%）、highest_skill_policy（34.0%）、random_policy（16.8%）
- 門派覆滅：random_policy（74.8%）、conservative_policy（1.6%）、highest_skill_policy（1.2%）、resource_guard_policy（0.8%）
