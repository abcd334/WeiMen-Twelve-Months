# Streamlit Cloud 升級載入修正

2026-09-13

## 問題

線上 `weimen-twelve-months.streamlit.app` 更新至 v0.7 後，只顯示「遊戲程式尚未完成更新」。GitHub 已包含新版檔案，但長駐程序仍可保留 v0.6 的 `game_runtime` 模組。

新版 `app.py` 直接從該舊模組取得 `load_current_engine`。舊函式只認識 v0.6 `game_engine` 依賴，即使逐一 reload，也無法選到 v0.7 `sect_engine`，因而永遠版本不符。重新整理瀏覽器不會重啟伺服器的 Python 程序。

## 修正

在主入口檢查載入器是否具備 `load_sect_engine`；缺少時，先重新載入 `game_runtime` 本身，再從模組呼叫目前的引擎選擇函式。已支援 v0.7 的載入器不會在一般 rerun 反覆 reload。

不更動遊戲規則、角色、種子或存檔格式。舊局仍需使用原本的「開始新版遊戲」流程；同版本進度不會因這個檢查被重開。

## 測試

- 新增 `tests/runtime_v06_fixture.txt`，取自 v0.6 commit `a3b6553` 的實際載入器。
- `tests/test_cloud_upgrade.py` 把此舊模組置入程序快取，再啟動目前的 `app.py`。修正前，無既有進度／有 v0.6 進度兩案均重現同一紅色錯誤。
- 修正後兩案都可啟動六人新局、完成第一次門務；保留舊局的原種子，普通 rerun 不重複結算、不改變 RNG，亦不反覆載入模組。
- 完整測試：`python -B -X utf8 -m pytest -q`，248 passed。

這項修正針對長駐程序的部署升級；先前只測過引擎模組過期，漏測了載入器本身過期。
