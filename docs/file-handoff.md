# 檔案交接契約 v1

瀏覽器觀測可用 `local_chrome_computer_use` 或明確標示的 `local_chrome_playwright`；選定文章完整 DOM 使用 `rendered_dom_html`，指定 paragraphIndices 的純文字段落匯出使用 `rendered_text_html`。後者排除圖片及未選段落，scope 保留零起算段落索引，並依同一 exact URL、raw hash、中央許可規則驗證。這不改變原 `ssr.collection.v1` 根欄位或保存端責任。

蒐集前先完成[遊戲知識規劃](game-knowledge-planning.md)。自有與客製擷取程式共同使用本契約；來源權限仍由接收端中央登記判定。

最小必要格式、可選 DOM receipt、編碼／表格／時間／版本／多頁限制與唯一合成範例，統一以[接收端契約](https://github.com/HGPT-StreamSuite/ssr-knowledge/blob/codex/peak-local-collection/docs/collection-contract-v1.md)及實際 `validate_bundle` 為準。自有與客製 collector 使用同一 format，producer 保留各自識別。

`tools/capture_browser_export.mjs` 是既有 local computer-use runtime 的獨立 DOM 檔案 adapter：接受選定 tab、明確許可的 source plan、文章 selector 與 checkout 外輸出目錄。它不導覽、不發 HTTP、不開 DB、不呼叫 knowledge；不允許 unknown／prohibited 來源。另以 `intake-file --origin operator_file --format html --capture-receipt FILE` 驗證檔案後產生既有 v1 資料包。許可／實際 tab 與來源核對由操作者負責，metadata 不是權限或抓取成功的簽章。

目前 Wiki 採集受已讀條款限制，不能用合成檢查或這個 adapter 宣稱 Shroomberry／徽章真站至 DB 已通過。已取得私有檔案保留，不自動登記成允許來源。

這是第一步分離：新 repo 擁有自己的蒐集核心、私有 spool 和檔案輸出；`ssr-knowledge` 新增接收端。原 repo 的既有離線流程、HTTP、研究工作與文件仍保留，並未宣稱全面遷移完成。不串接 ssr-chat，不共用程式套件，不部署服務。

## 唯一政策來源

`ssr-knowledge` 的 `sources.config_json` 是中央政策。每份政策區分 `local_cache`、`search_index`、`ai_input`、`ai_train`，附核對時間與依據。知識條目只引用固定來源 snapshot／段落，不重複維護完整授權。snapshot 保留當時的政策作為歷史證據，正式查詢仍檢查中央現行政策。

`catalog --data-dir PATH export-source-plan` 以 read-only SQLite 匯出 `ssr.source-plan.v1`：game、created_at、selected_acquisition_route、http_is_optional、registry_sha256、sources、note。`--source-id` 可重複指定以縮小範圍。這是政策快照，不是新的授權。collector 只保留它的副本；修改副本不能修改中央政策。

本機檔案要先在中央以 `register-file-source --file CONFIG` 登記獨立來源：`url=approved-file:SOURCE_ID`、`original_url` 是出處 HTTPS URL、`acquisition.kind=approved_local_file`、`allow_fetch=false`、明確 `allow_import`，其餘欄位見合成 fixture。這表示另一條已獲准的取得路徑，不能把網站本身的禁止政策改成允許 HTTP。真實來源仍需要可核對的取得和使用依據。本次只登記合成測試資料，沒有批准任何真實來源。

## 資料流與操作

1. 在 **ssr-knowledge** 執行 `catalog --data-dir C:\private\fixture-archive register-file-source --file C:\path\to\collector\fixtures\permitted-source.synthetic.json`。此測試 archive 必須與真實資料分開。
2. 在 **ssr-knowledge** 執行 `catalog --data-dir C:\private\fixture-archive export-source-plan`，將 UTF-8 JSON stdout 存成私有 `source-plan.json`。匯出不寫 DB，不含知識條目。
3. 在 **collector** 執行 README 的 `intake-file`，得到 snapshot ID，再執行 `bundle`。plain_text 原樣保存 UTF-8 文字；html 只取中央 selector 指定的正文，略過 script/style/hidden。均不執行來源文字、不呼叫 LLM。
4. 在 **ssr-knowledge** 執行 `catalog --data-dir C:\private\fixture-archive ingest-collection --file C:\private\handoff\ID.collection.json`。預設只檢查、read-only、`state=validated_only`。
5. 同一命令加 `--apply` 才保存原文、正文、metadata、receipt 和來源最新 snapshot。這是文件接收的保存點；此命令不建立知識條目或生成摘要。**B 的完整責任還包括整理與知識保存**：已有可使用的補充內容時，須從已存原文建立逐項有來源的草稿，再以 knowledge 的 `catalog import-drafts --file FILE` 實際存成待審修訂；不能只保存 snapshot 或新增待辦就結束。人工審核與發布是另行操作。
6. `catalog --data-dir PATH snapshot --snapshot-id ID --body` 可在另一程序讀回；`catalog search --text TEXT` 的正式結果仍只來自經審核發布且用途允許的知識條目。

以上是在各自 repo 使用 `uv --offline run --no-sync python -m ssr_knowledge ...` 或 `python -m ssr_collector_peak ...`，不由任何一端啟動另一端。操作員或獨立驗收腳本傳遞檔案。

保存修訂後以新程序 `catalog entry --entry-id ID` 及 `catalog relations --entry-id ID` 讀回，再由同一 DB 的查詢頁核對。待審內容可使用 `search --preview` 或唯讀審查頁；預設正式搜尋查不到待審資料不代表保存失敗，也不能為了展示而自動批准。完整責任與 DoD 見 [保存與查詢驗收](https://github.com/HGPT-StreamSuite/ssr-knowledge/blob/codex/peak-local-collection/docs/persistence-and-query-acceptance.md)。

可選的 `Start-Acceptance.cmd`／`tools.acceptance_demo` 是操作員明確啟動的驗收腳本，使用兩個獨立 CLI 程序傳檔，並提供唯讀展示；不在生產 collector 核心內呼叫保存端。具體操作見 [親自驗收](acceptance.md)。

## `ssr.collection.v1`

根欄位恰為 `format`、`producer`、`source_ref`、`document`、`bundle_id`。本 collector 的 producer 為 `ssr-collector-peak/0.1.0`；相容客製 collector 使用自身名稱與 semantic version。

`source_ref` 只有中央 source_id 和 config_sha256，不含政策。`document` 恰含 url、captured_at、observed_at、raw_base64、raw_sha256、body、body_sha256、metadata。bundle_id 是其餘根欄位 canonical JSON 的 SHA-256；canonical 使用排序鍵、UTF-8、不跳脫 Unicode、緊湊分隔符且拒絕 NaN。正文雜湊同樣以 UTF-8 計算。

原文限 40 bytes 至 2,000,000 bytes，正文限 40 至 2,000,000 字元，JSON 檔至多 6,000,000 bytes。時間需含時區，不能倒置或顯著來自未來。接收端核對中央來源 ID、精確設定雜湊、URL、雜湊、用途，並重新解析原文確認正文相同。設定變更後需重新匯出計畫，舊包不能授予權限。包內權限、審核、發布欄位被拒絕。

檔案 metadata 明確記錄 acquisition_method=operator_file 或 synthetic_fixture、http_requests=0、collector_called_llm=false；不接受假稱 browser_fetch_succeeded。captured_at 是暫存時間，observed_at 是本次取得觀測時間，均不是網頁更新時間。來源更新未知時保持 null。

雜湊保護完整性，**不提供身分驗證、簽章或網站取得的證明**。metadata 是生產端宣告的觀測紀錄；操作員仍須核對真實取得與許可。目前有明確許可來源的選定 tab DOM 匯出 adapter 與可選 receipt 驗證；沒有無人爬站、權限判定自動化或真實來源端到端通過證據。

## 去重、失敗與可選 HTTP

snapshot 以 URL、原文雜湊、中央政策雜湊決定，同內容不重存原文；每次觀測獨立保存。重匯相同 bundle 回傳 unchanged；新的正文產生新 snapshot。較舊觀測可保存為歷史，但不倒退 latest。正式接收的 snapshot、來源 head、event、receipt 同一交易，失敗不留下半份文件。預設驗證完全不寫入。

`http-collect` 不加 `--fetch` 時零請求、不建立 spool。可選 HTTP 核心保留精確 HTTPS allowlist、DNS/IP/TLS/proxy 防護、robots、固定 `SSRKnowledge` User-Agent、限流及有限重試。相同 DB 的 origin 共用冷卻；沒有跨 DB／跨電腦全域排程。403、redirect、政策未知或機器人挑戰停止；429/5xx 有界重試，過長 Retry-After 延後，不登入、不換身分、不繞過限制。ETag/Last-Modified 有記錄，但尚無 conditional GET/304，刷新仍需完整下載後去重。HTTP 測試使用假的 transport，不能解讀成真站抓取成功。

核心移植自 `ssr-knowledge` commit `928ddf3db50c7b2f03eb9a3398a3c497cf492dea` 的 acquisition.py；只將內部儲存與 primitives 接面改為本 repo，沒有在執行時引用原 repo。原碼仍保留在原 repo，後續修改需各自驗證；沒有共用套件。
