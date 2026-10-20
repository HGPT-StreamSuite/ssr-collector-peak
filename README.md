# ssr-collector-peak

PEAK（Steam app `3527290`）的獨立本機蒐集準備工具。只處理取得紀錄、原文、正文與私有暫存；沒有知識條目、審核、發布或正式搜尋功能。`ssr-knowledge` 保管中央來源政策、正式保存與查詢。兩者各自執行，以版本化 JSON 檔交接，沒有跨 repo import、共用套件或自動呼叫。

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
