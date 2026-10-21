# 親自驗收：真實內容瀏覽與合成工程診斷

此入口使用本機既有 uv／Python，開一個僅綁 127.0.0.1 的唯讀展示。沒有雲端、模型、新安裝、排程或開機自動啟動。它不是網站蒐集器，不取得任何真站。

首頁以既有正式 DB 的內容為主，直接顯示數值、區域、徽章條件、引用來源和缺失。輸入「飛機餐」核對已保存欄位；輸入「成就」按遊戲徽章分類列逐項條件，每頁 12 項，可前後翻頁。名稱／別名／內容文字也可搜尋。制度概述不充當逐項清單，來源依實際紀錄區分 Wiki 網站與本機官方遊戲文字。

核心要求：**輸入查詢條件 → 直接查指定資料庫 → 顯示實際查詢結果**。測試／報告／驗收頁本身執行查詢；真實與合成模式須各自明確選定持久 DB，不以靜態資料替代。歷史 `/audit` 檔案只作過去來源盤點，不作當前 DB 查詢驗收結果。遊戲分析、目標與來源對應先依[規劃流程](game-knowledge-planning.md)建立；真實新知識另須有 pending 修訂寫入→獨立讀回→API→實際頁面之同筆證據。

Hash、revision、測試 exit code、虛構輸入、資料包和預期 no_data 查詢收在「合成測試與工程診斷」展開區。工程檢查通過只代表檔案傳遞／隔離符合預期，**不代表真實內容完整**。詳細頁未保存就顯示未保存；不以原站連結冒充已取得正文。

## 啟動與停止

在 collector checkout 執行：

```cmd
Start-Acceptance.cmd "C:\path\ssr-knowledge" "C:\private\peak-acceptance" "C:\private\existing-data\knowledge.sqlite3"
```

- 第一個路徑是包含既有 `.venv\Scripts\python.exe` 的 ssr-knowledge checkout；啟動器使用該環境和 `.uv-cache`，以 `uv --offline run --no-sync` 執行，不建立新環境或下載依賴。
- 第二個路徑是私有驗收資料夾，必須在所有 Git checkout 和正式 DB 目錄外。至少需 100 MiB 可用空間。每次建立新的 run 子目錄，保留前次資料。
- 第三個路徑可省略；指定時只開既有正式 `knowledge.sqlite3` 的 mode=ro／query_only 連線，記錄並對照 SHA。不存在就報錯，不建立或填入替代資料。
- 測試約數十秒後開啟 `http://127.0.0.1:8766/`；不要關閉啟動器視窗。Ctrl+C 停止，DB 和檔案保留。
- 再按一次時，若相同版本、乾淨工作樹與同一份 DB 的驗收仍在執行，只開啟現有頁面，不重播或終止服務。程式或資料選擇不同會明確報錯，請先停止舊服務或換 port。

若 port 被占用，先停止原驗收視窗或用進階命令換 port。程式失敗會在視窗報錯及保留 failure／trace；不得把舊頁面當本次成功。

```powershell
# 先依實際位置設定既有 UV_PROJECT_ENVIRONMENT，再執行；不使用 uv sync。
uv --offline run --no-sync python -m tools.acceptance_demo --knowledge-repo C:\path\ssr-knowledge --data-dir C:\private\peak-acceptance --formal-db C:\private\existing-data\knowledge.sqlite3 --port 8767
# 只重跑測試與交接，不開展示頁：
uv --offline run --no-sync python -m tools.acceptance_demo --knowledge-repo C:\path\ssr-knowledge --data-dir C:\private\peak-acceptance --check-only
```

## 真實內容先看什麼

1. 搜尋名稱，直接看已保存的具體值；n/a、0、未記載保持不同，不推定缺失效果。
2. 查看出現區域、官方英繁條件、現有用途／攻略及逐項缺欄。來源的適用版本未知時不外推。
3. 看來源行，再展開「精確來源與引用」，核對頁面網址、取得方式、表格行號或官方文字 key。Steam 商店僅能是遊戲歸屬連結，不能替代本機資源的證據定位。
4. 用「成就」或成就／徽章分類查看逐項條件並翻頁；制度概述仍按其實際來源保留，不混作一個徽章。

## 次要合成工程診斷的判讀

1. **來源計畫與合成輸入**：展開中央來源設定，核對 allowed／unknown、allow_fetch=false。輸入「Lunar Rope（月亮繩，別名月繩）」明確為虛構，SOURCE_COMMAND 只作文字保存。
2. **collector 資料包**：查看第一版、更新版與拒收測試包。原文 base64、正文、雜湊、時間及 acquisition_method=synthetic_fixture 可對照；http_requests=0，不宣稱 Chrome 匯出。
3. **保存端測試 DB**：每次刷新均直接 SELECT SQLite。應有 2 個 snapshot、2 個 receipt；collector 有 2 份文件、3 次觀測。第一版保留歷史，latest 指向第二版。展開正文應看到原始／更新的合成文本。
4. **拒收與去重**：完整 CLI trace 記錄預設 validated_only、--apply saved、重匯 unchanged、更新新 ID、舊包重放，以及夾帶 policy 被拒的 exit 1。拒收前後 DB bytes 相同；偽造 bundle_id 不在 receipt。
5. **正式查詢隔離**：月、月亮繩、Lunar Rope、月繩、SOURCE_COMMAND 的獨立 CLI 正式查詢全部 no_data。原因是本次只保存來源文件，entries／entry_revisions 為 0，沒有自動整理、批准或發布。
6. **既有正式 DB**：首頁每次重新唯讀查詢內容，分類分頁，顯示實際欄位與來源；不套用成正式發布查詢，也沒有寫入按鈕。未指定正式 DB 時明確顯示未載入。
7. **同版證據**：查看兩邊獨立測試 log、結束碼與測試時 commit；同時比對目前 commit 與工作樹。只有兩邊版本相同且工作樹乾淨才顯示版本一致。程式改動後，停止並重新啟動驗收以取得新證據。

展示頁不提供 DB 寫入、來源核准、人工審核或發布 API；Host 限制在 localhost／127.0.0.1，檔案讀取只接受本次 artifact allowlist。來源文字以文字節點顯示，不能變成命令或 HTML 腳本。

## 測試、證據與限制

啟動器分別在兩個 repo 執行 `python -m unittest discover -s tests -v`；knowledge 使用既有 extraction 群組。每次交接命令都在獨立 CLI 程序執行。測試 DB、資料包、完整 log／trace／JSON 留在第二個路徑；不要 push。公開 repo 只有程式、文件及合成 fixtures。

這個 opt-in 操作員工具會執行另一個 repo 的 CLI 作檔案交接驗收，**不是兩個生產核心的自動整合**，沒有跨 repo import、共用套件或聊天流程依賴。

真站取得至入庫尚未驗收。本輪真實原文入庫 0；既有真實內容並非本輪重新蒐集。網站操作只使用本機 Chrome computer use；頁面能讀、內容授權與自動／批次取得條件分開核對，明確限制不換路繞過。HTTP transport 的合成測試不能算真站取得成功。
