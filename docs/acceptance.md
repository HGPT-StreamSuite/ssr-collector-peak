# 親自驗收：合成檔案交接

此入口使用本機既有 uv／Python，開一個僅綁 127.0.0.1 的唯讀展示。沒有雲端、模型、新安裝、排程或開機自動啟動。它不是網站蒐集器，不取得任何真站。

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

## 看什麼，如何判讀

1. **來源計畫與合成輸入**：展開中央來源設定，核對 allowed／unknown、allow_fetch=false。輸入「Lunar Rope（月亮繩，別名月繩）」明確為虛構，SOURCE_COMMAND 只作文字保存。
2. **collector 資料包**：查看第一版、更新版與拒收測試包。原文 base64、正文、雜湊、時間及 acquisition_method=synthetic_fixture 可對照；http_requests=0，不宣稱 Chrome 匯出。
3. **保存端測試 DB**：每次刷新均直接 SELECT SQLite。應有 2 個 snapshot、2 個 receipt；collector 有 2 份文件、3 次觀測。第一版保留歷史，latest 指向第二版。展開正文應看到原始／更新的合成文本。
4. **拒收與去重**：完整 CLI trace 記錄預設 validated_only、--apply saved、重匯 unchanged、更新新 ID、舊包重放，以及夾帶 policy 被拒的 exit 1。拒收前後 DB bytes 相同；偽造 bundle_id 不在 receipt。
5. **正式查詢隔離**：月、月亮繩、Lunar Rope、月繩、SOURCE_COMMAND 的獨立 CLI 正式查詢全部 no_data。原因是本次只保存來源文件，entries／entry_revisions 為 0，沒有自動整理、批准或發布。
6. **既有正式 DB**：金色區域僅為待審預覽，顯示 DB 實際筆數、狀態、SHA 與最多 10 筆現存摘要。可輸入名稱／別名查找；不套用成正式發布查詢，也沒有寫入按鈕。未指定正式 DB 時明確顯示未載入。
7. **同版證據**：查看兩邊獨立測試 log、結束碼與測試時 commit；同時比對目前 commit 與工作樹。只有兩邊版本相同且工作樹乾淨才顯示版本一致。程式改動後，停止並重新啟動驗收以取得新證據。

展示頁不提供 DB 寫入、來源核准、人工審核或發布 API；Host 限制在 localhost／127.0.0.1，檔案讀取只接受本次 artifact allowlist。來源文字以文字節點顯示，不能變成命令或 HTML 腳本。

## 測試、證據與限制

啟動器分別在兩個 repo 執行 `python -m unittest discover -s tests -v`；knowledge 使用既有 extraction 群組。每次交接命令都在獨立 CLI 程序執行。測試 DB、資料包、完整 log／trace／JSON 留在第二個路徑；不要 push。公開 repo 只有程式、文件及合成 fixtures。

這個 opt-in 操作員工具會執行另一個 repo 的 CLI 作檔案交接驗收，**不是兩個生產核心的自動整合**，沒有跨 repo import、共用套件或聊天流程依賴。

真站取得至入庫尚未驗收。本輪真實原文入庫 0；既有真實內容並非本輪重新蒐集。網站操作只使用本機 Chrome computer use；頁面能讀、內容授權與自動／批次取得條件分開核對，明確限制不換路繞過。HTTP transport 的合成測試不能算真站取得成功。
