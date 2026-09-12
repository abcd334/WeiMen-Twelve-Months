# 危門十二月 v0.4

武俠人物推理 × 關係經營 × 十二月危局。擔任青崖門代理掌門，與四名各有立場的弟子度過十二個月，追查前掌門失蹤與烈川堂逼山的目的。

本版依更新後的 v0.4 敘事重構文件修改原專案，保留規則引擎、固定選項、五種結局與單局狀態。所有文字由本地 JSON 與確定性規則組合，不使用 AI API。

## Windows 啟動

本工作區已備妥 Python 3.12 虛擬環境：

~~~powershell
Set-Location 'C:\Data\GitHub\危門十二月\WeiMen-Twelve-Months'
& '.\.venv\Scripts\python.exe' -m streamlit run app.py --server.address 127.0.0.1
~~~

開啟 <http://127.0.0.1:8501>。若連接埠已使用，可加上 --server.port 8502。切換到新版後請開始新局；同一版本、同一 seed、相同行動可以重現，v0.3 與 v0.4 的相同 seed 不保證同一結果。

其他電腦先安裝 Python 3.11 以上，再於專案目錄執行：

~~~powershell
py -3 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' -m streamlit run app.py --server.address 127.0.0.1
~~~

重現驗證環境可改用 requirements.lock.txt。搬移目錄後若虛擬環境失效，請在新位置重建。.tools/ 與 .venv/ 是本機輔助目錄，不應提交。

入口維持 app.py，資料相對於程式路徑載入，依賴列在 requirements.txt；共用設定不再鎖定 loopback 位址，以保留 Streamlit Community Cloud 的部署條件。本輪未部署或驗證雲端服務。問卷存在執行伺服器的磁碟，沒有雲端持久儲存。

## 本版變更

- 三條主線：後山舊路、假名帖、舊識來信。依 seed 選擇，四幕推進，後續事件回想真正發生的物件、NPC 與人物選擇。
- 20 個既有題材重寫開場；57 個方案各有兩組成功、兩組失敗敘述。派遣前有公開背景／立場反應，回山後能看見同門互助與衝突。
- 六套人物弧線有不同選項、代價與後續安排。夜間包含個人、關係、主線、日常及第十一月群像。
- 第八月引用實際可疑來往、核實情報與最初矛盾，普通人物反應不列為證據。外部聯繫本身不能直接證明背叛。
- 揭破陰謀需要當局三項核心證據，無關情報不替代。情報不足時，結局保留未解之處。
- 事件先呈現，人物卡收在「門內眾人」。小傳、近況、經歷使用一致正文，近況標示真正更新月份，重複經歷不再顯示。
- 掌門札記只記新的言行或事實。同一狀況不會逐月重記；重大人物後果仍需跨月、不同內容的預警。

## 玩法與公平性

1. 第 1～11 月先處理白天事件，再回應夜間場景；第 12 月根據累積結果直接結局。
2. 每月扣除 3 點糧餉。比較成本、能力、風險與人物反應，選一至兩人出勤。重傷及暫停派遣者不能出勤，留守者可休養。
3. 夜談的協助、規矩、授權不等於固定的好／壞／中立答案。有些選擇只界定信任與查證範圍。
4. 普通風險不會死亡。離開或倒戈需兩個較早月份的相關預警，至少一項可核實，當月預警不能立即放行永久後果。
5. 無合法派遣時可留門休整，承擔防備／聲望代價。第十一月的共同提醒只改敘述，不覆蓋累積結果。

結局優先序：揭破陰謀 → 聯盟退敵 → 正面取勝 → 慘勝守山 → 門派覆滅。

狀態保存於 st.session_state，沒有跨連線存檔。一般畫面不顯示隱藏心理、秘密原文或精確成功率；心跡在結局後才解鎖。固定問卷寫入 feedback/responses.jsonl，包含版本號，不影響亂數／結局，相同問卷重送不重複新增。

## 驗證

~~~powershell
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\python.exe' audit_narrative.py --seeds 200
& '.\.venv\Scripts\python.exe' simulate_balance.py --games-per-policy 250
& '.\.venv\Scripts\python.exe' review_playthroughs.py
~~~

- [完整驗證報告](reports/verification.md)：架構、104 項測試、覆蓋、三條具體事件鏈與真人驗收限制。
- [敘事覆蓋摘要](reports/narrative_coverage.json)／[每局資料](reports/narrative_runs.json)：200 個 seed 的實際結果。
- [1,000 局平衡摘要](reports/balance_summary.md)／[完整統計](reports/balance_report.json)。
- [公平性案例](reports/fairness_audit.json)：本版自然觸發的離門、倒戈與死亡各三例。
- 三局閱讀稿：[seed 0](reports/reading_seed_0.md)、[seed 4](reports/reading_seed_4.md)、[seed 6](reports/reading_seed_6.md)；[重現行動](reports/reading_actions.json)。

## 檔案責任

| 檔案 | 責任 |
|---|---|
| app.py | 事件、派遣、夜談、人物資料、札記與結局介面 |
| models.py | 狀態與人物、公開欄位白名單、經歷去重 |
| game_engine.py | 規則、事實、場景排程、線索公平性、結局與因果 ID |
| narrative.py | 只接受公開 context 的純文字 renderer，不消耗遊戲亂數 |
| data_loader.py | 資料載入、占位句／長度／變體／選項驗證 |
| data/character_templates.json | 人物模板、聲音、立場、習慣與觀察文字 |
| data/mission_events.json | 20 個場景與 57 個方案的數值、結果及人物連結 |
| data/personal_events.json | 六套三階段弧線、其他夜景與獨立後續安排 |
| data/story_threads.json | 三條主線、證據、推進文本、五名 NPC 與結局場景 |
| feedback.py | 固定問卷與帶版本號的 JSONL 保存 |
| simulate_balance.py | 四種公開資訊策略及永久後果稽核 |
| audit_narrative.py | 回收、人物曝光、場景覆蓋與文字重複率 |
| review_playthroughs.py | 可重現閱讀稿與本版公平性案例 |
| tests/ | 規則、敘事、公私隔離、去重及 Streamlit 操作回歸 |

十一晚不能保證每人都走完三階段私事；排程保證的是長期留門人物的曝光。未完成的安排不會被說成已完成。三局閱讀稿來自腳本完整流程與代理抽查，沒有代替真人的角色記憶、猶豫、遊玩時長與重玩意願驗收。
