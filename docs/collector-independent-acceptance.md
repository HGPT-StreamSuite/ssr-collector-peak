# Collector 獨立驗收與本機輸入輸出頁

本頁的範圍是 `ssr-collector-peak`，驗收標準的唯一機器可讀來源為 [collector-independent-criteria.json](collector-independent-criteria.json)。既有跨 repo 合成交接及正式內容唯讀 Viewer 保留；新增 `--collector-only` 模式延用相同 HTML、設計及 Host 邊界，無須 knowledge checkout、服務或 `.venv`。

## 所有 repo 共通門檻：預設瀏覽器可開啟運作

**目前狀態：BLOCKED，網頁驗收未通過。** 所有 repo 都須在使用者的預設瀏覽器實際開啟頁面、操作適用的輸入、輸出與錯誤流程，並留下實際頁面及操作證據。不能以程式存在、HTTP 成功、後端測試、記憶體路由、模擬 DOM 或未連線預覽替代。具體功能依 repo 職責而異，共通門檻不降低。

本輪沒有啟動預設瀏覽器，沒有開啟、點擊、輸入、輸出或錯誤畫面證據，也沒有已驗證可用的 URL。前置限制是先前 3 項 Viewer 對 `127.0.0.1` 臨時測試伺服器的連線遭 `PermissionError [WinError 10013]` 拒絕；限制仍有效，不重試、換埠、工具、路徑、shell 或執行器。預設瀏覽器名稱／版本亦未實測記錄。這是受阻，不是不適用或通過。

## 本 repo 功能測例與預期輸入輸出

操作者只能輸入合成 UTF-8 文字或含唯一 `main` 的 HTML。來源固定為 repo 合成 fixture，`origin=synthetic_fixture`；沒有 URL、檔案路徑、來源政策、正式 DB 或 HTTP fetch 的輸入欄位。40–20,000 bytes，正文至少 40 字元。後端實際呼叫 `intake_file`、`StageLedger.bundle`，重新以唯讀 SQLite 連線讀回。快照、正文、SHA-256、觀測數和 bundle 都是本次實際產物；不是預填成功資料。

相同內容以新請求送出：一份 snapshot、多次 observation、`state=unchanged`。同一 request_id 重送：回傳原結果，不新增 observation；同 ID 改內容拒絕。變更內容產生新 snapshot，舊包保留。無效輸入回錯誤且不增加 snapshot／observation。新工作階段使用新目錄，保留舊資料；清除／取消輸入與返回編輯只在頁面操作。提交期間停用修改，沒有宣稱能取消或回滾已進入後端的操作。連線中斷不自動重送，先重新讀取狀態確認。

每一工作階段記錄合成輸入、結果及事件。頁面只呈現安全摘要與該次合成結果，沒有完整本機環境或原有私人紀錄；可選的測試結果檔亦只抽取計數、狀態、HEAD 和 manifest hash，不提供原檔下載。測試證據與操作證據分開，不能將文件包成功視為 knowledge 保存或發布成功。

## 啟動、停止與目前限制

在本 checkout 用**既有** Python 3.11+：

```powershell
# 只檢查獨立模式設定與輸出狀態，不開 socket：
& 'C:\Projects\StreamSuite\runtime\envs\pathmove-b893a045-20261105-r1\knowledge-review\Scripts\python.exe' -B -m tools.acceptance_demo --collector-only --data-dir 'C:\Projects\StreamSuite\evidence\collector-lab-synthetic' --check-only
# 服務命令供權限限制解除後由操作者啟動；本輪未執行：
& 'C:\Projects\StreamSuite\runtime\envs\pathmove-b893a045-20261105-r1\knowledge-review\Scripts\python.exe' -B -m tools.acceptance_demo --collector-only --data-dir 'C:\Projects\StreamSuite\evidence\collector-lab-synthetic' --no-browser
```

程式預設僅綁定 `127.0.0.1:8766`。啟動成功時才輸出本次 URL；Ctrl+C 停止，工作階段與證據保留。占用或政策拒絕即停止，不自動換埠、不終止既有服務。可加 `--evidence-summary FILE` 選取本輪合成程式測試的 `result.json`，頁面只讀安全摘要。

**本輪沒有已驗證可連線的 URL 或預設瀏覽器開啟方法。** `tools/acceptance.html` 是原始網頁檔案入口，未用預設瀏覽器開啟驗證；檔案存在或未連線預覽不算共通門檻通過，也不是繞過連線限制的替代驗收。

## 已實際驗證結果與證據層級

新增測試以合成隔離目錄驗證 intake／bundle／新連線讀回、重送、錯誤、重開 session、下載 allowlist 與 POST 邊界。路由測試直接用記憶體 HTTP request/response 執行現有 handler，**不建立 socket，也不繞過被拒的本機連線**；前端狀態測試使用 Node 的記憶體狀態機，另核對 HTML 標籤與控制項，不宣稱是真實瀏覽器。

既有 52 項測試的結果仍按原版證據保存（48 pass、3 項 OS 連線拒絕、1 項 runner 子程序參數處理錯誤）。新增程式測試只證明新工作版本的明列案例；不重試被拒項目，不把舊證據標為新 UI 全部通過。

上一工作版本的新增程式測試為 16 Python＋9 前端狀態案例通過；原生 `--collector-only --check-only` 成功但未開服務；保留的實際合成操作為 1 snapshot／2 observation、重送去重及短輸入錯誤。證據 ID：`ssr-collector-peak-viewer-final-20261105T183535Z-0d6c438f`；對應 HEAD `7819055e1f244e869570cee50a985ccb9998e8d1`，工作檔 manifest `9f7ab5ee21365b7f19cd8c106cd676b4107a809d2c341f9fcd8f26f129d6e564`。這些是具體程式／合成操作證據，不是瀏覽器證據；本次文件與頁面分類調整另留新 manifest，不把舊計數改稱新版全量通過。

## 不適用及理由

- knowledge 接收、知識整理、審核及發布屬其他 repo，本 repo 不把它們列為通過。
- 總頁面與跨 repo 導覽由使用者留待後續，本輪不適用，不計通過。
- 正式使用者資料、私人紀錄或憑證不作為此合成頁的操作資料；不得用它們補足驗收。

## 未測／阻塞

- **BLOCKED**：預設瀏覽器實際開啟、輸入、輸出、錯誤、重送與返回；原因為上述尚有效的 loopback 拒絕，未重試。
- **未驗證**：實際 HTTP、鍵盤流程、窄視窗視覺 QA、新版全量回歸；不能由程式測試推定通過。
- **未測**：核心可選 HTTP 真站取得、目前正式內容完整度；假 transport、既存快取或合成輸入不能替代。
- 舊驗收 runner 的 CLI／Git 參數字串處理錯誤是驗收工具問題，與 repo 缺陷及 OS loopback 拒絕分開保存；不以改工具重試補成通過。
