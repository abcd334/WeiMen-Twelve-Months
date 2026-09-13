# 危門十二月 v0.6

武俠人物推理 × 關係經營 × 證據鏈解謎 × 十二月危局。擔任青崖門代理掌門，與四名弟子追查假名帖，安排出勤、共同核對與山門守備。

v0.6 完成「假名帖」十二月因果故事：每月一個核心問題、一次案件行動，白天結果決定夜談，夜間安排影響下月交接。後山舊路、舊識來信維持 v0.5 流程。所有規則與內容在本機執行，不使用 AI API。

## Windows 啟動

本工作區已有 Python 虛擬環境：

~~~powershell
Set-Location 'C:\Data\GitHub\危門十二月\WeiMen-Twelve-Months'
& '.\.venv\Scripts\python.exe' -m streamlit run app.py --server.address 127.0.0.1
~~~

開啟 <http://127.0.0.1:8501>。連接埠已使用時，可指定 `--server.port 8502`。**種子 4 可體驗假名帖**；種子 0 是舊識來信，6 是後山舊路。

其他電腦先安裝 Python 3.11 以上，再執行：

~~~powershell
py -3 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' -m streamlit run app.py --server.address 127.0.0.1
~~~

重現驗證環境可使用 `requirements.lock.txt`。搬移目錄後若虛擬環境失效，請在新位置重建。`.tools/` 與 `.venv/` 是本機輔助目錄，不應提交。

## 假名帖玩法

1. 閱讀本月問題、已知事實、待解部分與弟子的觀點。
2. 選一個案件行動和出勤弟子。選項直接說明查證目的、可能材料、成本與風險；NPC 不列入派遣名單。
3. 查看實際資源變化、傷疲，以及新增的證據、人物說法或待查線索。查證失敗不會刪除已有證據。
4. 夜間回應當日材料、失敗、傷勢與分工。公開已知部分、封存並補守備、共同複核，各有實際代價，也會改變下月交接。私人難處須有既有背景及本月情境支持。
5. 第四、八、十一月在白天由角色提出推理要求，分別選假說、交叉核對、排列證據鏈；當月不另派任務，完成後進入夜談。可以保留判斷，或在最後提交目前已有的部分材料。
6. 第十月可穩定補齊缺少的文件、物證及人證；低糧餉可請中立保管人代辦，下月支付 4 糧餉。也可只記錄說法、暫不認定。
7. 第十一月共同夜談後，第十二月分別判定「案件查明程度」與「門派狀態」。完整材料仍須在第十一月正確組成證據鏈。

穩定查證依明示的原簿、封存材料或獨立見證取得資料；其他查問會受到專長、傷疲與風險影響。人物說法不能直接作證，共同複核也不會憑空補發缺件。

另外兩條故事線仍採「調查方向＋門務方案」，第四、八、十一月的推理仍在夜談之後。

## 假名帖月份

| 月 | 核心工作 |
|---|---|
| 1 | 查明誰以青崖門名義借車、用印是否相符 |
| 2 | 核對商隊、車坊與交接記錄 |
| 3 | 比較第二張名帖的日期與墨樣 |
| 4 | 說明目前支持哪個假說，或保留判斷 |
| 5 | 在獨立見證、公開查問與匿名說法間選擇 |
| 6 | 核對紙張、印痕與材料供應 |
| 7 | 追查墨坊帳目、取貨與跑腿者 |
| 8 | 用已取得材料交叉核對，形成下一步追問 |
| 9 | 回應對方要求，或循核實線索追查交付鏈 |
| 10 | 核對送帖者、補查缺件，或記錄否認並保留判斷 |
| 11 | 組成證據鏈，與留門弟子確認明日的共同安排 |
| 12 | 同時呈現案件與守山結果 |

## 規則與資料邊界

每月扣 3 糧餉。一般出勤一至兩人，重傷、暫停派遣或已離門者不能派遣；沒有合法行動時可以留門休整。普通風險不會死亡。離門與倒戈須有兩個較早月份的相關預警，至少一項可核實；對外通信本身不構成背叛證據。

假名帖案件軸為 `complete / partial / unresolved`，門派軸為 `stable / weakened / collapsed`。結果包含揭破陰謀、洗清部分責任、真相未明但守住山門、查對案件但門派失和、門派覆滅；畫面會交代實際未恢復的人手、守備或合作問題。其他兩線保留既有五種結局判定。

一般畫面只使用公開欄位，不顯示秘密原文、隱藏心理或精確成功率。人物心跡在結局後解鎖。問卷寫入 `feedback/responses.jsonl`，保留版本號並防止重複送出。

## 升級與重現

GameState 版本為 0.6，新增案件問題、當日脈絡、承接原因、案件歷程及兩軸結局。舊版尚未結束的 session 顯示「開始新版遊戲」，點選後以原種子重開第一月；不自動轉換舊進度。介面會刷新過期引擎模組，避免開始新版遊戲時循環跳頁。

沒有跨連線存檔。同版本、同種子、相同行動可重現；跨版本不保證假名帖結果相同。本次另將 60 局舊路／來信與改版前快照比較，場景、資源、結局、推理及亂數狀態全部一致。沒有新增執行期依賴。

## 驗證與報告

~~~powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m pytest -q
& '.\.venv\Scripts\python.exe' -X utf8 audit_narrative.py --seeds 200
& '.\.venv\Scripts\python.exe' -X utf8 simulate_balance.py --games-per-policy 250
& '.\.venv\Scripts\python.exe' -X utf8 review_playthroughs.py
~~~

- [v0.6 驗證報告](reports/v0.6/verification.md)：193 項測試與驗收範圍。
- [重構設計與決策](reports/v0.6_migration_design.md)。
- [200 局敘事稽核](reports/v0.6/narrative_coverage.json)：69 局假名帖的夜談承接率 100%。
- [1,000 局平衡摘要](reports/v0.6/balance_summary.md)與[完整統計](reports/v0.6/balance_report.json)。
- 完整閱讀稿：[查明且穩定](reports/v0.6/reading_case_complete.md)、[保留判斷](reports/v0.6/reading_case_partial.md)、[真相未明](reports/v0.6/reading_case_unresolved.md)、[失敗後補證](reports/v0.6/reading_case_failure_recovery.md)、[案件查明但門派受損](reports/v0.6/reading_case_damaged.md)。
- [行動重播紀錄](reports/v0.6/reading_actions.json)、[永久後果公平性案例](reports/v0.6/fairness_audit.json)。

新版工具預設輸出 `reports/v0.6/`，保留原有 v0.5 報告。自動模擬與閱讀稿不等於真人試玩驗收；後續可針對提示理解、成本感受與重玩意願收集回饋。

## 程式分工

| 檔案 | 責任 |
|---|---|
| `app.py` | 依故事線呈現案件行動或舊式派遣、證據板、推理、夜談及結局 |
| `case_models.py` | CaseQuestion、CaseAction、DayContext 資料契約 |
| `case_engine.py` | 案件驗證、問題進度、行動、承接原因、情境夜談及兩軸結局 |
| `game_engine.py` | 月份流程及共用人物、派遣、資源、傷疲、關係與公平性規則 |
| `investigation.py` | 證據與說法、推理驗證、證據鏈及兩條舊線的調查 |
| `models.py`、`game_runtime.py` | 公私狀態邊界與舊模組刷新 |
| `data_loader.py`、`data/` | 資料完整性驗證、角色、事件、案件與私人弧線 |
| `narrative.py` | 只接受公開情境的敘事呈現 |
| `simulate_balance.py`、`audit_narrative.py`、`review_playthroughs.py` | 公開資訊策略、因果稽核、閱讀稿與行動重播 |
| `tests/`、`feedback.py` | 規則與 UI 回歸、版本化問卷 |
