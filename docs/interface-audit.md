# Collector 流程與接口邊界

本 repo 的責任是取得已獲准的原文、擷取正文、保存私有 collector stage，並輸出文件證據。它不產生正式知識 Record，不整理或審核知識，不發布、呼叫 LLM 或直接供聊天搜尋。機器可讀清單是 [interfaces/collector.v1.json](../interfaces/collector.v1.json)，它只描述本 repo，沒有新增跨 repo payload schema。

## 實際流程與入口出口

| 階段 | 入口 | 實際輸出／副作用 | 下游 |
| --- | --- | --- | --- |
| 中央來源計畫 | `source_plan.source_from_plan`；相容 alias `cli.source_from_plan` | 驗證並原樣返回選定 source；不寫入、不連線、不授權 | intake／可選 HTTP |
| 本機檔案 | `python -m ssr_collector_peak intake-file` | JSON `saved`／`unchanged`、snapshot ID、hash；私有 SQLite 與觀測 | bundle |
| 資料包 | `python -m ssr_collector_peak bundle` | `ssr.collection.v1` JSON、bundle ID／路徑；不啟動接收端 | knowledge 文件接收 |
| 空資料／計數 | `python -m ssr_collector_peak stats` | JSON counts、knowledge_entries=0、can_review_or_publish=false | 本機操作者；此命令可能初始化 stage，不是唯讀命令 |
| 可選網路路徑 | `http-collect` | 預設 dry-run；另加 `--fetch` 才可能連線 | 本輪不重試已拒項目，未驗真站 |
| 獨立網頁 | `tools.acceptance_demo --collector-only`、固定 handler | 合成輸入實際呼叫 `intake_file`／`StageLedger.bundle`，以新唯讀連線讀回 | 同次結果、allowlist bundle、操作紀錄 |

CLI 成功為 stdout JSON／exit 0；驗證、IO、SQLite 失敗為 `{"status":"error","error":"..."}`／exit 1。argparse 語法錯誤保留 stderr usage／exit 2；可選 HTTP 的 `blocked_or_failed` 也使用 exit 2，但有 JSON 結果，不能與語法錯誤混同。空 stage 的 stats 成功回傳零計數；未知 snapshot、空正文及拒絕用途是錯誤，不假造成功文件。

CLI 的本機檔案路徑由明確操作員指定。網頁只接受 `request_id/session_id/format/text/synthetic`，不接受任意命令、Python 路徑、DB／檔案、來源政策、外部端點或 ACL。library 的 `intake_file`／`StageLedger` 是內部替換模組，輸入來源應先由計畫驗證器取得；它們不是任意未驗證 source 的通用 API。

## 格式、來源與權威

沿用 `ssr.source-plan.v1`、`ssr.collection.v1`、`ssr.browser-export.v1`。中央來源計畫的完整 `registry_sha256` 是整個 sources array 的 canonical hash；有提供時必須核對，不能先篩選來源再計算。原有只有 format／sources 的最小合成計畫仍相容，但缺 hash 不表示已通過 registry checksum 驗證。game 有提供時需為 `PEAK:3527290`。

選定來源符合既有中央 file／HTTP profile；unknown／prohibited 不變成 allowed。檔案來源維持 `approved-file:SOURCE_ID`、`approved_local_file`、allow_fetch=false；各用途及 policy reviewed_at 沿用現有驗證規則。合成測試可以建立當前時間的自製測試政策，不能自動刷新任何真實來源的授權。驗證用的正規化副本不會取代原 source，因此 `config_sha256` 綁定的仍是精確原設定。

source_id、URL、原設定 hash 是來源綁定，不是使用者身份、簽章或 ACL。權威仍是 knowledge 中央 registry；producer 不能在 metadata 夾帶 policy、uses、review 或發布指令。網頁的 Host／Origin／token 是本機操作邊界，並非通用使用者或 Record ACL 服務。

raw 保留原 bytes，UTF-8 BOM 只在正文解碼時移除，CRLF 不被換行正規化。HTML 只擷取中央 selector 的唯一正文，原文保留，script／hidden 內容不執行。每包一文件，沒有 typed tables 或自動多頁抓取。raw 為 40–2,000,000 bytes、body 為 40–2,000,000 字元；**整個 canonical JSON 還需 ≤6,000,000 bytes**，不能只檢查 raw／body 個別大小。

captured_at／observed_at 有時區，是取得觀測時間，不是網頁更新日期；未知 source_updated_at 保持 null。receipt 綁 exact original_url、raw hash 與 capture time，HTTP 未觀測時維持 null。snapshot ID 由 URL、raw hash、config hash 決定；相同原文去重但保留新觀測，更新內容產生新 snapshot。資料包重送／歷史 latest 的正式保存判定由接收端負責，collector 不自行批准知識修訂。

## 本輪已重現並修補的 producer 缺口

- 非 object source、缺 policy 等輸入曾出現 AttributeError／KeyError；現由獨立計畫驗證模組在 stage 寫入前拒絕。
- 有提供的 registry hash 曾被忽略；現核對整份 sources 的 hash，保留原設定且不放寬綁定。
- SQLite 損壞曾逸出非 JSON 例外；CLI 現以既有 error／exit 1 契約回報，保留原檔。
- receipt 的 method／export_format 以 array 傳入曾出現 TypeError；現回 ContractError，不擴充可接受 enum。
- 同原文的新 receipt 曾與第一次 snapshot capture time 混用；現輸出選定觀測的 receipt capture time，DB 原快照時間與舊資料包保留。capture／observation 順序或時區不合法時不輸出，不截短或夾定時間。
- 2 MB 的引號原文曾輸出 6,668,015-byte JSON，超出接收端既有 6 MB 限制；現於建立輸出目錄／檔案前拒絕，stage 原文保留，不截斷或改寫內容。

可執行契約案例見 [test_public_contract.py](../tests/test_public_contract.py)。當前結果必須以同一 HEAD＋dirty＋逐檔 fingerprint 的收據判定；案例定義、機器清單或舊版 pass 不代表本輪執行通過。產出的真實合成 source-plan／collection／CLI receipt 保留在 checkout 外的本輪 evidence，沒有真實來源文本。

## 對接與跨 repo 決策

實際消費者是 `ssr-knowledge.collection_handoff.validate_bundle/ingest_collection`；本輪只讀其程式與既有契約，沒有修改或啟動它。包根欄位維持 format／producer／source_ref／document／bundle_id；接收端以中央 config hash 重驗 URL、用途、raw、body 及時間，預設 `validated_only`，明確 apply 才存文件與 receipt。

**文件 Evidence 與完整知識 Record 不可混用。** collector 提供 raw／body／來源／觀測；它沒有 entry_id、revision_id、整理後 payload、知識欄位／關聯或審核發布狀態。knowledge 保存文件時 entries_created=0。若 reader 需要完整 Record，提供者應是 knowledge 的整理／待審修訂流程；reader 的正式 schema、必填欄位、版本、identity 與 scope 由總控確認。不要把 receipt／bundle 偽裝成完整 Record，也不要在 v1 包中偷加 entry／review 欄位。此處沒有已定義的 collector→reader 直接 Record API。

來源計畫完整 hash 與 6 MB 上限已按現有提供者／消費者語意對齊，沒有要求其他 repo 改 schema。接收端仍須獨立驗證不可信輸入；本輪不宣稱接收端錯誤封裝或 reader 全流程已驗收。

供總控協調的靜態風險：所讀 `ssr-knowledge/ssr_knowledge/capture_receipt.py` 的 method／export_format enum membership 尚未先檢查 string 型別，建議接收者也將錯誤 JSON 型別統一拒絕為自己的 ContractError；欄位與允許 enum 不需變更。這不是放寬格式，也不是要求 producer 輸出額外欄位。本輪未對該 repo 執行此惡意型別案例或修改它。引用版本為 HEAD `bd2f415d29eacd489d349e88c191148ba80712f1`，但其 checkout 有其他 dirty 工作；以本輪另外保存的精確 collection_handoff／capture_receipt 檔案 hash 綁定靜態證據，不只相信 HEAD。

## 已驗、未驗與限制

本機 native CLI／handler 收據與程式契約測試分開記錄；網頁已接本 repo 能力，不是以歷史成功輸出替代。共通最終門檻仍是使用者預設瀏覽器實際開啟並操作成功；目前 blocked，沒有瀏覽器證據或已驗證 URL。

WinError 10013、Registry/getproxies、舊 CLI 子程序誤擋、CIM、UserChoice、舊 checkout、socket 等限制保留；不重試或換路繞過。真站取得、LLM、正式資料修改、knowledge apply／修訂、reader 整合及總頁面都不計為本 repo 已通過項目。

`plans/*.json` 是規劃產物，不等於已取得文件或完成知識修訂；collector 命令沒有自動執行全遊戲計畫或維護完整內容進度帳。原有未追蹤計畫保留，正式內容分母與完整度未在本輪核對。
