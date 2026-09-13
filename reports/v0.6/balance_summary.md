# 平衡模擬結果

每策略 250 局；共 1000 局。種子從 0 起連續取樣。

| 策略 | 揭破陰謀 | 聯盟退敵 | 正面取勝 | 慘勝守山 | 門派覆滅 | 洗清部分責任 | 真相未明但守住山門 | 查對案件但門派失和 | 平均留門人數 | 糧餉 | 防備 | 聲望 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random_policy | 0.4% | 0.4% | 5.2% | 11.6% | 46.4% | 34.4% | 1.6% | 0.0% | 3.91 | 18.56 | 53.47 | 40.0 |
| highest_skill_policy | 62.4% | 0.0% | 0.0% | 0.8% | 2.0% | 0.0% | 0.0% | 34.8% | 4.0 | 39.33 | 65.93 | 64.97 |
| conservative_policy | 0.0% | 23.6% | 8.0% | 28.4% | 4.0% | 22.0% | 8.4% | 5.6% | 3.88 | 34.48 | 75.34 | 55.04 |
| resource_guard_policy | 60.0% | 0.0% | 0.4% | 3.6% | 0.0% | 24.0% | 4.0% | 8.0% | 3.94 | 49.18 | 64.96 | 63.01 |

| 策略 | 永久離開 | 倒戈／背叛 | 重傷次數 | 死亡 |
|---|---:|---:|---:|---:|
| random_policy | 9 | 1 | 91 | 12 |
| highest_skill_policy | 1 | 0 | 12 | 0 |
| conservative_policy | 30 | 1 | 0 | 0 |
| resource_guard_policy | 14 | 0 | 56 | 0 |

各事件選項的選取／成功次數與跨種子公平性案例，完整保存於 balance_report.json。

所有重大人物後果皆經自動稽核：離開與倒戈有不同月份的前置警示且至少一條強線索；死亡有派遣前致命風險提示。

## 結局較常由哪些策略達成

- 揭破陰謀：highest_skill_policy（62.4%）、resource_guard_policy（60.0%）、random_policy（0.4%）、conservative_policy（0.0%）
- 聯盟退敵：conservative_policy（23.6%）、random_policy（0.4%）、highest_skill_policy（0.0%）、resource_guard_policy（0.0%）
- 正面取勝：conservative_policy（8.0%）、random_policy（5.2%）、resource_guard_policy（0.4%）、highest_skill_policy（0.0%）
- 慘勝守山：conservative_policy（28.4%）、random_policy（11.6%）、resource_guard_policy（3.6%）、highest_skill_policy（0.8%）
- 門派覆滅：random_policy（46.4%）、conservative_policy（4.0%）、highest_skill_policy（2.0%）、resource_guard_policy（0.0%）
- 洗清部分責任：random_policy（34.4%）、resource_guard_policy（24.0%）、conservative_policy（22.0%）、highest_skill_policy（0.0%）
- 真相未明但守住山門：conservative_policy（8.4%）、resource_guard_policy（4.0%）、random_policy（1.6%）、highest_skill_policy（0.0%）
- 查對案件但門派失和：highest_skill_policy（34.8%）、resource_guard_policy（8.0%）、conservative_policy（5.6%）、random_policy（0.0%）
