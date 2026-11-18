# Ecommerce Image Studio Skill

一套可安裝到 Codex、Claude Code、Cursor 等 Agent 的電商圖片工作流程。

它不只提供提示詞，也把商品身份鎖、生成核准、成本上限、可續跑工作單與圖片 QA 納入同一套流程。

## 功能

- 白底／英雄主圖
- 情境與生活方式圖片
- 賣點資訊圖與尺寸圖
- 多角度與模特上身規劃
- A+／詳情頁模組
- 社群與廣告素材
- 多後端能力路由
- 工作單與批次續跑
- 尺寸、比例、透明度、白底與主體占比檢查
- 每張圖明確選擇保留角度、校正為正面或生成新角度
- 商品身份分數、逐項核對與阻擋門檻；只有技術 QA 與身份 QA 都通過才能交付

## Demo

以下圖片是使用本 Skill 將隨手拍透視校正成正式電商視角，再經技術 QA 與商品身份 QA 通過的公開 Demo。Repository 不包含生成時使用的原始商品照：

![SØNDAG 北歐晨光情境圖](docs/demo/sondag-nordic-lifestyle-demo.png)

## 隱私設計

這個 repository 只包含 Skill、文件、範本、檢查腳本、測試，以及經人工確認可公開的 Demo 生成圖；不包含生成時使用的真實商品原圖或工作單。

- `.gitignore` 排除 `inputs/`、`output/`、`private/` 及非 Demo 目錄的點陣圖片。
- 只有經人工確認可公開的圖片可以放在 `docs/demo/`。
- `scripts/privacy_check.py` 會拒絕 Demo 目錄以外的圖片、測試產物與本機絕對路徑。
- GitHub Actions 會在 push 與 pull request 自動執行隱私檢查和測試。
- API Key 只能從環境變數或本機秘密設定讀取，不可寫進工作單。

## 安裝

Repository 上傳後，可使用 Agent Skills CLI：

```bash
npx skills add Xuanwinnie/ecommerce-image-studio-skill --skill ecommerce-image-studio
```

也可以手動複製：

```bash
cp -R skills/ecommerce-image-studio ~/.codex/skills/
```

## 使用

```text
使用 $ecommerce-image-studio，根據我的商品照片規劃一套電商圖片。
先建立商品身份鎖和生成計畫，未經我確認不要呼叫付費 API。
```

## 本機驗證

```bash
python3 scripts/privacy_check.py
python3 -m unittest discover -s skills/ecommerce-image-studio/tests -v
python3 skills/ecommerce-image-studio/scripts/validate_manifest.py \
  skills/ecommerce-image-studio/assets/job-manifest.example.json
```

圖片 QA 需要 Pillow：

```bash
python3 skills/ecommerce-image-studio/scripts/check_listing_image.py \
  /path/to/local-product-image.png --profile general
```

真實商品圖片應放在此 repository 之外，或放在被 `.gitignore` 排除的本機目錄。只有已確認可公開的展示圖才能放進 `docs/demo/`。
