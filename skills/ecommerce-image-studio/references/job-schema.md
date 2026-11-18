# 工作單結構

每個任務建立一份 `manifest.json`。範本位於 `assets/job-manifest.example.json`。

## 必要區塊

- `job_id`：不含個資的唯一識別碼。
- `status`：`planned`、`approved`、`generating`、`qa`、`complete` 或 `failed`。
- `product`：商品代號、類別、身份鎖、已確認事實與未確認項目。
- `platforms`：目標平台、站點、查核日期與官方規格來源。
- `brand`：品牌色、字體、語氣、禁止事項與 Logo 檔案。
- `deliverables`：每張圖的用途、尺寸、文案、參考圖、狀態與 QA 結果。
- `generation`：後端、模型、proof-first、最大重試、`dry_run` 與預算上限。
- `approval`：是否已核准付費生成，以及核准範圍。

## 身份鎖

身份鎖只描述參考資料看得到或使用者已確認的事實：

```json
{
  "shape": ["圓柱瓶身", "短頸", "平底"],
  "colors": [{"name": "霧黑", "source": "front.png"}],
  "materials": [{"value": "不確定", "status": "unconfirmed"}],
  "logos": [{"text": "AURA", "placement": "正面中央"}],
  "fixed_text": ["500 ml"],
  "components": ["瓶身", "旋蓋"],
  "must_not_change": ["Logo 拼字", "瓶身比例", "瓶蓋顏色"]
}
```

看不到的背面、內部結構、成分與規格不能從常識補齊。

## 狀態與續跑

- 所有 `generation.dry_run=false` 的實際生成都要先設定 `approval.paid_generation_approved=true` 並記錄 `approved_scope`；即使後端宣稱免費，也先讓使用者確認資料外送與生成範圍。
- 每個 deliverable 獨立記錄 `planned`、`generated`、`passed`、`warning` 或 `failed`。
- deliverable 的 `output` 必須是工作目錄內的安全相對路徑，不可使用絕對路徑或 `..` 跳脫。
- 失敗時保留錯誤碼與嘗試次數，但不得保存 Key、完整認證 Header 或含秘密的 URL。
- 續跑只處理未完成或明確要求重做的項目，不重做已通過項目。

## 角度政策

每個 deliverable 都必須設定 `viewpoint_policy`：

- `preserve`：保留參考圖的鏡頭角度、透視與商品朝向，只修改背景或指定局部。
- `correct_to_front`：允許把隨手拍的傾斜／俯視透視校正成正面電商視角，但不得改變 SKU 身份。
- `generate_new_angle`：建立新的觀察角度。若參考圖少於兩張，驗證器會警告看不到的結構可能是推定。

`correct_to_front` 與 `generate_new_angle` 必須填寫 `viewpoint_notes`，說明允許改變與必須保留的項目。

## 商品身份 QA gate

每張圖的 `qa.identity` 必須包含：

- `result`：`passed`、`warning`、`failed` 或尚未檢查時的 `null`。
- `score`：0 到 1 的身份信心分數；尚未檢查時為 `null`。
- `threshold`：0.8 到 1.0，建議使用 0.9。
- `reviewer`：`human`、`vision-model`、`human+vision-model` 或尚未檢查時的 `null`。
- `reviewed_against`：實際用於對照的安全相對路徑。
- `checks`：`shape`、`colors`、`materials`、`logos`、`fixed_text`、`components`、`constraints` 與 `viewpoint` 的逐項結果；`constraints` 對應身份鎖的 `must_not_change`。

只有身份鎖中有內容的項目是必查項目；`viewpoint` 永遠必查。必查項目只接受 `passed`，沒有對應資料的項目使用 `not_applicable`。完整判定方式見 [商品身份 QA](identity-qa.md)。

deliverable 標成 `passed` 時，技術 `qa.result` 與 `qa.identity.result` 都必須是 `passed`、身份分數必須達門檻，且所有必查項目都必須通過。工作單只有在所有 deliverable 都是 `passed` 時才能標成 `complete`。
