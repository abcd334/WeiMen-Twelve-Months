# 平衡模擬結果

每策略 250 局；共 1000 局。種子從 0 起連續取樣。

| 策略 | 揭破陰謀 | 聯盟退敵 | 正面取勝 | 慘勝守山 | 門派覆滅 | 平均留門人數 | 糧餉 | 防備 | 聲望 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random_policy | 0.8% | 0.4% | 7.6% | 20.4% | 70.8% | 3.88 | 6.23 | 47.76 | 30.96 |
| highest_skill_policy | 96.8% | 0.0% | 0.0% | 1.2% | 2.0% | 3.99 | 31.83 | 69.47 | 53.57 |
| conservative_policy | 0.0% | 23.6% | 24.0% | 48.4% | 4.0% | 3.84 | 27.28 | 67.68 | 55.05 |
| resource_guard_policy | 94.4% | 0.0% | 0.8% | 4.8% | 0.0% | 3.94 | 41.15 | 75.14 | 52.87 |

| 策略 | 永久離開 | 倒戈／背叛 | 重傷次數 | 死亡 |
|---|---:|---:|---:|---:|
| random_policy | 16 | 1 | 102 | 12 |
| highest_skill_policy | 2 | 0 | 13 | 0 |
| conservative_policy | 38 | 3 | 0 | 0 |
| resource_guard_policy | 15 | 0 | 72 | 0 |

各事件選項的選取／成功次數與跨種子公平性案例，完整保存於 balance_report.json。

所有重大人物後果皆經自動稽核：離開與倒戈有不同月份的前置警示且至少一條強線索；死亡有派遣前致命風險提示。

## 結局較常由哪些策略達成

- 揭破陰謀：highest_skill_policy（96.8%）、resource_guard_policy（94.4%）、random_policy（0.8%）、conservative_policy（0.0%）
- 聯盟退敵：conservative_policy（23.6%）、random_policy（0.4%）、highest_skill_policy（0.0%）、resource_guard_policy（0.0%）
- 正面取勝：conservative_policy（24.0%）、random_policy（7.6%）、resource_guard_policy（0.8%）、highest_skill_policy（0.0%）
- 慘勝守山：conservative_policy（48.4%）、random_policy（20.4%）、resource_guard_policy（4.8%）、highest_skill_policy（1.2%）
- 門派覆滅：random_policy（70.8%）、conservative_policy（4.0%）、highest_skill_policy（2.0%）、resource_guard_policy（0.0%）
