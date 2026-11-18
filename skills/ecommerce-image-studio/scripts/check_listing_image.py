#!/usr/bin/env python3
"""以客觀像素條件檢查電商圖片，不宣稱取代平台審核。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError
except ImportError:  # pragma: no cover - 實際環境缺套件時提供明確訊息
    Image = None
    ImageChops = None
    ImageOps = None
    UnidentifiedImageError = OSError


PROFILES: dict[str, dict[str, Any]] = {
    "general": {"min_width": 800, "min_height": 800},
    "amazon-main": {
        "min_width": 1000,
        "min_height": 1000,
        "expected_ratio": 1.0,
        "ratio_tolerance": 0.02,
        "require_opaque": True,
        "min_white_border_ratio": 0.98,
        "min_subject_span": 0.85,
    },
    "social-portrait": {
        "min_width": 1080,
        "min_height": 1350,
        "expected_ratio": 0.8,
        "ratio_tolerance": 0.02,
    },
    "story": {
        "min_width": 1080,
        "min_height": 1920,
        "expected_ratio": 0.5625,
        "ratio_tolerance": 0.02,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="檢查電商圖片尺寸、比例、透明度與白底主圖條件")
    parser.add_argument("image", type=Path, help="要檢查的圖片")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="general")
    parser.add_argument("--min-width", type=int)
    parser.add_argument("--min-height", type=int)
    parser.add_argument("--expected-ratio", type=float, help="寬除以高，例如 1:1 輸入 1")
    parser.add_argument("--ratio-tolerance", type=float)
    parser.add_argument("--max-bytes", type=int)
    parser.add_argument("--json-output", type=Path, help="另外寫出 JSON 報告；不覆寫輸入圖片")
    return parser.parse_args()


def has_transparency(image: Any) -> bool:
    if image.mode in {"RGBA", "LA"}:
        alpha = image.getchannel("A")
        return alpha.getextrema()[0] < 255
    if image.mode == "P" and "transparency" in image.info:
        alpha = image.convert("RGBA").getchannel("A")
        return alpha.getextrema()[0] < 255
    return False


def analyze_white_background(image: Any) -> tuple[float, float | None]:
    """估算邊界白色比例與前景最長邊占比；白色商品需人工覆核。"""
    rgb = image.convert("RGB")
    rgb.thumbnail((512, 512))
    width, height = rgb.size
    pixels = rgb.load()

    border: list[tuple[int, int, int]] = []
    for x in range(width):
        border.append(pixels[x, 0])
        if height > 1:
            border.append(pixels[x, height - 1])
    for y in range(1, max(1, height - 1)):
        border.append(pixels[0, y])
        if width > 1:
            border.append(pixels[width - 1, y])

    white_count = sum(1 for red, green, blue in border if red >= 250 and green >= 250 and blue >= 250)
    white_ratio = white_count / len(border) if border else 0.0

    # 與純白比較後建立前景遮罩；柔和陰影可能會被算進前景。
    difference = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white"))
    mask = difference.convert("L").point(lambda value: 255 if value > 10 else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return white_ratio, None
    left, top, right, bottom = bbox
    span = max((right - left) / width, (bottom - top) / height)
    return white_ratio, span


def main() -> int:
    args = parse_args()
    if Image is None:
        print(json.dumps({"ok": False, "errors": ["缺少 Pillow；請先安裝 Pillow 才能執行圖片檢查"]}, ensure_ascii=False, indent=2))
        return 3

    if not args.image.is_file():
        print(json.dumps({"ok": False, "errors": ["找不到圖片檔案"]}, ensure_ascii=False, indent=2))
        return 2

    if args.json_output and args.image.resolve() == args.json_output.resolve():
        print(
            json.dumps(
                {"ok": False, "errors": ["JSON 報告路徑不可與輸入圖片相同"]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    config = dict(PROFILES[args.profile])
    for name in ("min_width", "min_height", "expected_ratio", "ratio_tolerance", "max_bytes"):
        value = getattr(args, name)
        if value is not None:
            config[name] = value

    errors: list[str] = []
    warnings: list[str] = []
    try:
        with Image.open(args.image) as source_image:
            source_format = source_image.format
            image = ImageOps.exif_transpose(source_image)
            image.load()
            width, height = image.size
            ratio = width / height
            transparent = has_transparency(image)
            metrics: dict[str, Any] = {
                "path": str(args.image),
                "format": source_format,
                "mode": image.mode,
                "width": width,
                "height": height,
                "aspect_ratio": round(ratio, 6),
                "bytes": args.image.stat().st_size,
                "has_transparency": transparent,
            }

            if width < config.get("min_width", 0):
                errors.append(f"寬度 {width}px 低於要求 {config['min_width']}px")
            if height < config.get("min_height", 0):
                errors.append(f"高度 {height}px 低於要求 {config['min_height']}px")

            expected_ratio = config.get("expected_ratio")
            tolerance = config.get("ratio_tolerance", 0.02)
            if expected_ratio is not None and abs(ratio - expected_ratio) > tolerance:
                errors.append(f"比例 {ratio:.4f} 超出目標 {expected_ratio:.4f} ± {tolerance:.4f}")

            if config.get("max_bytes") and metrics["bytes"] > config["max_bytes"]:
                errors.append(f"檔案大小 {metrics['bytes']} bytes 超過上限 {config['max_bytes']} bytes")
            if config.get("require_opaque") and transparent:
                errors.append("此 profile 不接受透明像素")

            if args.profile == "amazon-main":
                white_ratio, subject_span = analyze_white_background(image)
                metrics["white_border_ratio"] = round(white_ratio, 6)
                metrics["estimated_subject_span"] = None if subject_span is None else round(subject_span, 6)
                if white_ratio < config["min_white_border_ratio"]:
                    errors.append(f"邊界白色比例 {white_ratio:.1%} 低於 {config['min_white_border_ratio']:.1%}")
                if subject_span is None:
                    warnings.append("無法估算主體占比；圖片可能接近全白，需人工檢查")
                elif subject_span < config["min_subject_span"]:
                    warnings.append(
                        f"估算主體最長邊占比 {subject_span:.1%} 低於目標 "
                        f"{config['min_subject_span']:.1%}"
                    )
                warnings.append("白底與主體占比為像素估算；白色、透明、反光商品需人工覆核")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        print(
            json.dumps(
                {"ok": False, "errors": ["圖片無法辨識、已損壞或無法安全讀取"]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    report = {
        "ok": not errors,
        "profile": args.profile,
        "metrics": metrics,
        "errors": errors,
        "warnings": warnings,
        "disclaimer": "此報告是客觀像素檢查，不代表平台保證通過。",
    }
    if args.json_output:
        try:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            errors.append("無法寫入 JSON 報告")
            report["ok"] = False
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
