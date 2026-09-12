# 危門十二月 v0.5

武俠人物推理 × 關係經營 × 證據鏈解謎 × 十二月危局。擔任青崖門代理掌門，與四名各有立場的弟子度過十二個月，追查前掌門與烈川堂留下的疑點。

本版優先完成「假名帖」的十二月推理流程；後山舊路、舊識來信保留原有事件排程，接入共用證據板與推理節點。所有內容與規則在本機執行，不使用 AI API。

## Windows 啟動

本工作區已有 Python 3.12 虛擬環境：

~~~powershell
Set-Location 'C:\Data\GitHub\危門十二月\WeiMen-Twelve-Months'
& '.\.venv\Scripts\python.exe' -m streamlit run app.py --server.address 127.0.0.1
~~~

開啟 <http://127.0.0.1:8501>。連接埠已使用時，可另指定 `--server.port 8502`。**種子 4 可體驗假名帖主線**；種子 0 是舊識來信、6 是後山舊路。本輪依設計文件要求，沒有啟動、重啟或部署 Streamlit。

其他電腦先安裝 Python 3.11 以上，再執行：

~~~powershell
py -3 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' -m streamlit run app.py --server.address 127.0.0.1
~~~

重現驗證環境可使用 requirements.lock.txt。搬移目錄後若虛擬環境失效，請在新位置重建。.tools/ 與 .venv/ 為本機輔助目錄，不應提交。

## 新版玩法

1. 看事件人物身份與目前疑點，再看四名弟子的觀點卡。姓名、專長、性格、傷疲與可否派遣直接顯示；背景與近況在各卡的詳細資料中。
2. 明確選擇本月調查方向，也可選「本月只處理門務」。再選門務方案與出勤弟子，確認總成本。NPC 不列入派遣名單。
3. 結果分別記錄門務代價與調查所得。證據板有已證實、待核實、人物說法、排除事項四類，原話與傳聞不能直接當作事實。
4. 夜間處理人物需求、同門關係、整理資料與共同分工；夜談不會自動補發核心證據。札記只有新狀況才新增，近況顯示實際更新月份。
5. 第四月夜談後提出初步假說；第八月選兩份已取得證據交叉核對；第十一月排列文件、物證與見證。可以明確保留判斷，誤判不會立即結束遊戲。
6. 第十、十一月可付出成本補查缺失的核心材料。第十二月依資源、人手與推理結果結局；完整揭破需要真的取得三項核心證據，並在十一月組成正確證據鏈。

一般查證若調查專長達 4，或本次門務順利交接，可完成核查；其他情況留下待核實方向。公開簿冊與補證有穩定取得管道，條件在選項提示中說明。普通失敗不會刪除既有證據。第五月假名帖的見證人，需要搭配「請證人核對原件」方案才穩定提供核對證詞；公開指控不能代替查證。

## 假名帖的月份安排

| 月 | 事件與推理功能 |
|---|---|
| 1 | 清點山門：缺頁、借車留底與用印 |
| 2 | 商隊追帳：借車說法與獨立紀錄 |
| 3 | 第二張名帖：日期、車號與墨樣 |
| 4 | 烈川堂挑釁；初步假說 |
| 5 | 渡口見證人：核對、指控或封存 |
| 6 | 門內質疑：區分外部聯絡、造假與動機 |
| 7 | 墨跡來源：出貨簿作佐證，實際墨樣比對另查 |
| 8 | 門內疑雲；兩份證據交叉核對 |
| 9 | 烈川堂施壓；正確交叉核對可開啟後續追問 |
| 10 | 最後補證：留底、封存墨樣、第二證人 |
| 11 | 封存與分工、共同夜談、最後證據鏈 |
| 12 | 完整或部分揭露，與守山結果分別判定 |

## 規則與資料邊界

每月扣 3 糧餉；出勤一至兩人，重傷、暫停派遣或已離門者不能派遣。沒有合法派遣時可留門休整。普通風險不會死亡；離門與倒戈須有兩個較早月份的相關預警，且至少一項可核實。對外通信本身不能證明背叛。

結局優先序維持：揭破陰謀 → 聯盟退敵 → 正面取勝 → 慘勝守山 → 門派覆滅。案件查明程度與守山勝負分開；證據鏈不足仍可能守住山門。

一般畫面只使用公開欄位，不顯示秘密原文、隱藏心理或精確成功率；人物心跡在結局後解鎖。問卷寫入 feedback/responses.jsonl，含版本號，重送不重複新增。

## 升級與重現

GameState 版本改為 0.5，新增 evidence、leads、claims、hypotheses、deduction_history、investigation_history。舊版尚未結束的 session 顯示「開始新版遊戲」，由玩家開新局；不把舊 intel 自動認定為已查證資料。沒有跨連線存檔，同版本、同 seed、相同行動可重現，跨版本不保證同一結果。舊問卷仍保留其原版本號。

JSON 在原檔擴充，沒有新增執行期依賴。保留 20 個基礎事件，假名帖使用主線中的月份覆寫；沒有另開一套遊戲。

## 驗證與報告

~~~powershell
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\python.exe' audit_narrative.py --seeds 200
& '.\.venv\Scripts\python.exe' simulate_balance.py --games-per-policy 250
& '.\.venv\Scripts\python.exe' review_playthroughs.py
~~~

- [實作與驗證報告](reports/verification.md)：155 項測試、架構、升級方式與待驗證事項。
- [200 局敘事摘要](reports/narrative_coverage.json)／[每局記錄](reports/narrative_runs.json)。
- [1,000 局平衡摘要](reports/balance_summary.md)／[完整統計](reports/balance_report.json)。
- [永久後果公平性案例](reports/fairness_audit.json)。
- 三局閱讀稿：[舊識來信](reports/reading_seed_0.md)、[假名帖](reports/reading_seed_4.md)、[後山舊路](reports/reading_seed_6.md)；[重現行動](reports/reading_actions.json)包括調查與推理選擇。

## 檔案責任

| 檔案 | 責任 |
|---|---|
| app.py | 分開呈現事件、四人觀點、調查、派遣、證據板、推理、夜談與結局 |
| models.py | 私有狀態、可讀傷疲、公開欄位白名單、經歷去重 |
| game_engine.py | 月份排程、門務、人物與關係、事實與回收、結局 |
| investigation.py | 調查焦點、證據分類、補證、推理驗證及完整證據鏈 |
| narrative.py | 完整句型與穩定變體，只接受公開 context，不消耗遊戲亂數 |
| data_loader.py | JSON、四角色對白、圖節點、推理組合與補證完整性驗證 |
| data/character_templates.json | 人物、性格、觀察、可靠領域與盲點 |
| data/mission_events.json | 20 個基礎場景、57 個方案、四角色完整對白 |
| data/personal_events.json | 六套個人弧線、關係與其他夜景 |
| data/story_threads.json | 三條證據圖、假說、補證、月份覆寫、NPC 與結局 |
| feedback.py | 固定問卷與版本化 JSONL |
| simulate_balance.py | 四種公開資訊策略及永久後果稽核 |
| audit_narrative.py | 敘事覆蓋、回收、重複率與推理節點覆蓋 |
| review_playthroughs.py | 可重現閱讀稿、調查／推理行動與公平性案例 |
| tests/ | 規則、證據、公私隔離、敘事、狀態與 Streamlit 操作回歸 |

下一步宜先讓真人試玩假名帖，確認調查提示、誤導與補證成本是否合適，再擴寫後山舊路及舊識來信的逐月專屬內容。自動化模擬與腳本閱讀稿不等於真人的理解、猶豫與重玩意願驗收。
