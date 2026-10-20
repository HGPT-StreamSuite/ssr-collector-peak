# ssr-collector-peak

PEAK（Steam app `3527290`）的獨立本機蒐集準備工具。只處理取得紀錄、原文、正文與私有暫存；沒有知識條目、審核、發布或正式搜尋功能。`ssr-knowledge` 保管中央來源政策、正式保存與查詢。兩者各自執行，以版本化 JSON 檔交接，沒有跨 repo import、共用套件或自動呼叫。

## 一鍵本機驗收

在 Windows 使用既有 ssr-knowledge checkout 的 `.venv` 和 uv；不安裝或建立環境。在本 repo 執行：

```cmd
Start-Acceptance.cmd "C:\path\ssr-knowledge" "C:\private\peak-acceptance" "C:\private\existing-data\knowledge.sqlite3"
```

第三個參數可省略。約需數十秒跑兩邊獨立測試與合成 CLI 交接，成功後開啟 `http://127.0.0.1:8766/`。頁面每次直接讀 SQLite，展示來源計畫、輸入、兩版資料包、測試 DB、拒收／去重／更新、測試 log 與 commit。**測試資料**與**正式 DB 唯讀待審預覽**顯著分區；正式 DB 不會交給寫入 CLI。Ctrl+C 停止，所有舊驗收資料保留。

首頁優先呈現**既有真實內容**：名稱／別名、效果數值、出現區域、逐項徽章條件、精確來源及缺欄。搜尋「成就」依類別列出已保存的遊戲徽章並分頁；來源逐筆區分 PEAK Wiki、其他 Wiki 與官方本機資源。Hash、revision 與合成工程 trace 收在次要展開區，工程通過不當成內容完整性通過。

`tools/acceptance_demo.py` 是操作者明確啟動的驗收工具，以子程序跑兩邊 CLI；生產核心沒有這項依賴。第一次啟動若缺既有 `.venv`、uv、權限或 port 被占用會報錯，不自動安裝、不用示範資料掩蓋失敗。重播、停止和實際觀測方式見 [親自驗收](docs/acceptance.md)。本版真站至入庫仍未通過，本輪真實網站原文新增 0。

使用者目前選定的網站取得方式是 **computer use／本機 Chrome**。本版的 `intake-file` 接收已獲准的本機檔案，**不會開啟 Chrome，也不宣稱檔案由 Chrome 抓取**。瀏覽器可讀、robots 允許或顯示授權文字，均不能單獨推定另有外部批次蒐集權限；明確禁止的網站不得換用瀏覽器繞過。

`http-collect` 保留為可選架構，預設只列計畫、零網路請求，不是本次選定的取得流程。必須另有中央核可的精確來源設定及 `--fetch` 才會請求 HTTP。未知用途維持 unknown，禁止用途維持 prohibited，不自動改判。

## 本機執行

Python 3.11+，只有標準函式庫。沿用電腦既有的 uv 和 Python 環境；本工作沒有建立新虛擬環境、安裝套件、服務或模型。若既有環境位於另一個資料夾，可指定 `UV_PROJECT_ENVIRONMENT`，再以 `uv --offline run --no-sync` 使用它。這只是選定本機直譯器，不是 repo 的執行依賴。

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:UV_PROJECT_ENVIRONMENT = 'C:\existing-python-project\.venv'
# 以下命令均在本 repo 執行。計畫由 ssr-knowledge 唯讀匯出。
uv --offline run --no-sync python -m ssr_collector_peak intake-file --plan C:\private\source-plan.json --source-id synthetic-export --file fixtures\permitted-input.synthetic.txt --stage-dir C:\private\collector-stage --format plain_text --origin synthetic_fixture
uv --offline run --no-sync python -m ssr_collector_peak bundle --stage-dir C:\private\collector-stage --snapshot-id SNAPSHOT_ID --output-dir C:\private\handoff
uv --offline run --no-sync python -m ssr_collector_peak stats --stage-dir C:\private\collector-stage
uv --offline run --no-sync python -m unittest discover -s tests -v
```

暫存為 `collector-stage.sqlite3`，至少需要 50 MiB 可用空間。暫存和輸出必須在所有 Git checkout 外，且不得位於含 `knowledge.sqlite3` 的目錄或其子目錄。原文、DB、來源計畫、資料包和真實驗收輸出都保持私有。`fixtures/` 只有清楚標記的合成文本與測試權限；沒有真實 PEAK 網頁或使用許可。

來源計畫、接收端命令、限制和權限邊界見 [檔案交接契約](docs/file-handoff.md)。
