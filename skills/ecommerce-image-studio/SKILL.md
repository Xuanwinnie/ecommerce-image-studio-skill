---
name: ecommerce-image-studio
description: Plan, generate, batch-process, and verify ecommerce product image sets from product photos for marketplaces and social channels. Use for hero images, lifestyle scenes, infographics, A+ or detail-page modules, model try-on, sale ads, localization, and listing-image QA; do not use for unrelated illustration requests.
---

# 電商圖片工作室

把真實商品照片轉成一致、可驗收、適合指定平台的圖片套組。先保護商品真實性，再追求視覺效果；可重複的客觀檢查交給腳本處理。

## 不可省略的原則

- 建立「商品身份鎖」：形狀、顏色、材質、Logo、標籤文字、配件與包裝內容皆以參考圖和使用者資料為準。
- 不臆測尺寸、材質、認證、功效、相容性、保固、折扣或包裝內容。不確定的資訊標成 `unconfirmed`，需要呈現在圖片上時才詢問。
- 原始圖片只讀；所有結果寫入新的工作目錄，不覆寫輸入檔。
- 付費 API、第三方上傳或大量生成前，先列出生成清單、後端、預估呼叫數與成本上限，取得使用者同意。支援時先做 `dry-run`。
- 優先使用目前環境內建的圖片生成／編輯工具。除非使用者明確指定，否則不推薦未知 API 中轉站，也不要求把 Key 貼進對話；Key 僅從環境變數或本機秘密設定讀取。
- 平台規則可能變動。準備正式上架時，要查核該平台當下的官方規格；[平台規格](references/platforms.md) 只提供安全的規劃預設值。
- 未經明確要求，不發布、不上架、不傳送素材到社群或電商平台。

## 工作流程

1. **確認任務**：至少取得商品參考圖、目標平台與想要的交付物。其餘資訊能從圖片安全判斷就先判斷，只有會影響真實性或成本時才提問。
2. **建立工作單**：依 [工作單結構](references/job-schema.md) 建立 `manifest.json`，記錄身份鎖、已確認事實、未確認項目、品牌限制、交付尺寸、預算與核准狀態。每張圖必須選擇 `preserve`、`correct_to_front` 或 `generate_new_angle` 其中一種角度政策；不得寫入任何 API Key。
3. **提出生成計畫**：列出每張圖的角色、比例／像素、文案、參考圖、生成或編輯方式與 QA 條件。先產生 1 張 proof，身份與風格通過後才批次擴展。
4. **選擇後端**：依 [後端與模型路由](references/provider-routing.md) 以能力選模型，不把單一供應商或版本名稱寫死。需要保留文字／Logo、局部編輯或多參考圖時，優先選支援高保真影像編輯的模型。
5. **生成與修正**：每次提示都帶入身份鎖。視覺問題優先重生成；只有裁切、縮放、純白背景、格式轉換等確定性工作才用腳本修正。各類圖片的特殊要求見 [圖片類型](references/image-types.md)。
6. **雙層驗收**：依 [商品身份 QA](references/identity-qa.md) 對照參考圖檢查商品形狀、顏色、材質、Logo、固定文字、零件與角度政策，再用 `scripts/check_listing_image.py` 檢查尺寸、比例、透明度、背景與主體占比。技術 QA 通過不代表商品身份通過；兩者都通過且身份分數達門檻，交付圖才能標記為 `passed`。
7. **交付**：輸出原圖、上架版、`manifest.json` 與 `qa-report.json`；清楚列出通過、警告、失敗及仍需人工確認的項目。

## 任務路由

- 白底主圖、情境圖、賣點圖、尺寸圖、模特上身、多角度、A+／詳情頁、社群或廣告圖：讀 [圖片類型](references/image-types.md)。
- Amazon、Shopify、淘寶／天貓、蝦皮、TikTok Shop、小紅書等平台：讀 [平台規格](references/platforms.md)，正式上架前再核對官方文件。
- 要接外部模型、批次處理或估算成本：讀 [後端與模型路由](references/provider-routing.md)。
- 要建立可續跑任務、批次清單或交付 manifest：讀 [工作單結構](references/job-schema.md)。
- 要生成或修改真實商品、決定是否可交付：讀 [商品身份 QA](references/identity-qa.md)。

## 建議輸出結構

```text
output/<商品代號>/<日期時間>/
├── manifest.json
├── proofs/
├── final/
├── qa-report.json
└── prompts/
```

提示詞可以保存，但要移除秘密資訊。每個輸出檔名包含序號、圖片用途、比例或平台，例如 `01-hero-amazon-1x1.png`。

## 確定性檢查

```bash
python3 scripts/validate_manifest.py manifest.json
python3 scripts/check_listing_image.py final/01-hero-amazon-1x1.png \
  --profile amazon-main --json-output qa-report.json
```

若缺少 Pillow，說明客觀圖片檢查尚未執行，不要假裝已通過。

## 機器強制規則

| 規則 | 強制機制 |
|---|---|
| 工作單不得包含秘密欄位或秘密值 | `validate_manifest.py` 的遞迴秘密掃描與反向測試 |
| `dry_run=false` 前必須完成生成核准 | `validate_manifest.py` 的核准狀態檢查 |
| 交付檔只能使用工作目錄內的安全相對路徑 | `validate_manifest.py` 的路徑邊界檢查 |
| QA 報告不得覆寫輸入圖片 | `check_listing_image.py` 的同路徑拒絕與檔案保留測試 |
| 損壞或不安全圖片必須回傳結構化錯誤 | `check_listing_image.py` 的輸入例外處理與 JSON 介面測試 |
| 每張圖必須明確指定角度政策 | `validate_manifest.py` 的 `viewpoint_policy` 枚舉驗證 |
| 技術尺寸通過不可取代商品身份檢查 | `validate_manifest.py` 的雙重 QA gate |
| 身份分數未達門檻或必查項目有警告／失敗時不可通過 | `validate_manifest.py` 的身份門檻與逐項狀態驗證 |
| 尚有未通過圖片時工作單不可標成完成 | `validate_manifest.py` 的完成狀態 gate |
