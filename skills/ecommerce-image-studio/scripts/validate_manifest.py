#!/usr/bin/env python3
"""驗證電商圖片工作單的必要結構與安全欄位。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = {"planned", "approved", "generating", "qa", "complete", "failed"}
ALLOWED_DELIVERABLE_STATUSES = {"planned", "generated", "passed", "warning", "failed"}
ALLOWED_VIEWPOINT_POLICIES = {"preserve", "correct_to_front", "generate_new_angle"}
ALLOWED_QA_RESULTS = {"passed", "warning", "failed"}
ALLOWED_IDENTITY_CHECK_RESULTS = {"passed", "warning", "failed", "not_applicable"}
ALLOWED_IDENTITY_REVIEWERS = {"human", "vision-model", "human+vision-model"}
IDENTITY_CHECK_KEYS = {
    "shape",
    "colors",
    "materials",
    "logos",
    "fixed_text",
    "components",
    "constraints",
    "viewpoint",
}
SECRET_KEY_PATTERN = re.compile(r"(api[_-]?key|token|secret|authorization|password)", re.IGNORECASE)
SECRET_VALUE_PATTERNS = (
    re.compile(r"^Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"^sk-[A-Za-z0-9_-]{8,}$"),
    re.compile(r"^AIza[A-Za-z0-9_-]{20,}$"),
)
WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[/\\]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="驗證 ecommerce-image-studio 的 manifest.json")
    parser.add_argument("manifest", type=Path, help="manifest.json 路徑")
    return parser.parse_args()


def find_secret_locations(value: Any, path: str = "$") -> list[str]:
    """遞迴找出秘密欄位或疑似秘密值，只回報位置而不洩漏內容。"""
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if SECRET_KEY_PATTERN.search(str(key)):
                findings.append(child_path)
            findings.extend(find_secret_locations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_secret_locations(child, f"{path}[{index}]"))
    elif isinstance(value, str) and any(pattern.search(value.strip()) for pattern in SECRET_VALUE_PATTERNS):
        findings.append(path)
    return findings


def is_safe_relative_path(value: Any) -> bool:
    """只接受不含上層跳脫的相對路徑，兼顧 POSIX 與 Windows 表示法。"""
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or WINDOWS_ABSOLUTE_PATH.match(value):
        return False
    return ".." not in normalized.split("/")


def validate(data: Any) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return ["根節點必須是 JSON object"], warnings

    required = {"job_id", "status", "product", "platforms", "brand", "deliverables", "generation", "approval"}
    for key in sorted(required - data.keys()):
        errors.append(f"缺少必要欄位：{key}")

    if data.get("status") not in ALLOWED_STATUSES:
        errors.append(f"status 必須是：{', '.join(sorted(ALLOWED_STATUSES))}")

    identity_lock: Any = {}
    product = data.get("product")
    if isinstance(product, dict):
        if not product.get("sku"):
            errors.append("product.sku 不可為空")
        identity_lock = product.get("identity_lock")
        if not isinstance(identity_lock, dict):
            errors.append("product.identity_lock 必須是 object")
        elif not identity_lock.get("must_not_change"):
            warnings.append("identity_lock.must_not_change 為空，商品一致性可能不足")
    elif "product" in data:
        errors.append("product 必須是 object")

    platforms = data.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        errors.append("platforms 必須是至少包含一個項目的 array")
    else:
        for index, platform in enumerate(platforms):
            if not isinstance(platform, dict):
                errors.append(f"platforms[{index}] 必須是 object")
            elif not platform.get("name"):
                errors.append(f"platforms[{index}].name 不可為空")

    if not isinstance(data.get("brand"), dict):
        errors.append("brand 必須是 object")

    deliverables = data.get("deliverables")
    if not isinstance(deliverables, list) or not deliverables:
        errors.append("deliverables 必須是至少包含一個項目的 array")
    else:
        seen_ids: set[str] = set()
        seen_outputs: set[str] = set()
        for index, item in enumerate(deliverables):
            if not isinstance(item, dict):
                errors.append(f"deliverables[{index}] 必須是 object")
                continue
            item_id = item.get("id")
            if not item_id:
                errors.append(f"deliverables[{index}].id 不可為空")
            elif item_id in seen_ids:
                errors.append(f"deliverable id 重複：{item_id}")
            else:
                seen_ids.add(item_id)
            for key in ("type", "size", "status", "output"):
                if not item.get(key):
                    errors.append(f"deliverables[{index}].{key} 不可為空")

            item_status = item.get("status")
            if item_status and item_status not in ALLOWED_DELIVERABLE_STATUSES:
                errors.append(
                    f"deliverables[{index}].status 必須是："
                    f"{', '.join(sorted(ALLOWED_DELIVERABLE_STATUSES))}"
                )

            output = item.get("output")
            if output:
                if not is_safe_relative_path(output):
                    errors.append(f"deliverables[{index}].output 必須是工作目錄內的安全相對路徑")
                elif output in seen_outputs:
                    errors.append(f"deliverable output 重複：{output}")
                else:
                    seen_outputs.add(output)

            viewpoint_policy = item.get("viewpoint_policy")
            if viewpoint_policy not in ALLOWED_VIEWPOINT_POLICIES:
                errors.append(
                    f"deliverables[{index}].viewpoint_policy 必須是："
                    f"{', '.join(sorted(ALLOWED_VIEWPOINT_POLICIES))}"
                )
            elif viewpoint_policy in {"correct_to_front", "generate_new_angle"} and not item.get("viewpoint_notes"):
                errors.append(f"deliverables[{index}].viewpoint_notes 不可為空")

            references = item.get("references")
            if not isinstance(references, list) or not references:
                errors.append(f"deliverables[{index}].references 必須是至少包含一個項目的 array")
            else:
                for reference_index, reference in enumerate(references):
                    if not is_safe_relative_path(reference):
                        errors.append(
                            f"deliverables[{index}].references[{reference_index}] 必須是安全相對路徑"
                        )
                if viewpoint_policy == "generate_new_angle" and len(references) < 2:
                    warnings.append(
                        f"deliverables[{index}] 只用一張參考圖生成新角度；看不到的結構可能是推定"
                    )

            qa = item.get("qa")
            if not isinstance(qa, dict):
                errors.append(f"deliverables[{index}].qa 必須是 object")
                continue

            technical_result = qa.get("result")
            if technical_result is not None and technical_result not in ALLOWED_QA_RESULTS:
                errors.append(
                    f"deliverables[{index}].qa.result 必須是 null 或："
                    f"{', '.join(sorted(ALLOWED_QA_RESULTS))}"
                )

            identity = qa.get("identity")
            if not isinstance(identity, dict):
                errors.append(f"deliverables[{index}].qa.identity 必須是 object")
                continue

            identity_result = identity.get("result")
            if identity_result is not None and identity_result not in ALLOWED_QA_RESULTS:
                errors.append(
                    f"deliverables[{index}].qa.identity.result 必須是 null 或："
                    f"{', '.join(sorted(ALLOWED_QA_RESULTS))}"
                )

            score = identity.get("score")
            if score is not None and (
                not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 1
            ):
                errors.append(f"deliverables[{index}].qa.identity.score 必須是 0 到 1 的數字或 null")

            threshold = identity.get("threshold")
            if (
                not isinstance(threshold, (int, float))
                or isinstance(threshold, bool)
                or not 0.8 <= threshold <= 1
            ):
                errors.append(f"deliverables[{index}].qa.identity.threshold 必須是 0.8 到 1 的數字")

            reviewer = identity.get("reviewer")
            if reviewer is not None and reviewer not in ALLOWED_IDENTITY_REVIEWERS:
                errors.append(
                    f"deliverables[{index}].qa.identity.reviewer 必須是 null 或："
                    f"{', '.join(sorted(ALLOWED_IDENTITY_REVIEWERS))}"
                )

            reviewed_against = identity.get("reviewed_against")
            if not isinstance(reviewed_against, list):
                errors.append(f"deliverables[{index}].qa.identity.reviewed_against 必須是 array")
                reviewed_against = []
            else:
                for reference_index, reference in enumerate(reviewed_against):
                    if not is_safe_relative_path(reference):
                        errors.append(
                            f"deliverables[{index}].qa.identity.reviewed_against[{reference_index}] "
                            "必須是安全相對路徑"
                        )

            checks = identity.get("checks")
            if not isinstance(checks, dict):
                errors.append(f"deliverables[{index}].qa.identity.checks 必須是 object")
                checks = {}
            else:
                for check_key in sorted(IDENTITY_CHECK_KEYS):
                    if check_key not in checks:
                        errors.append(f"deliverables[{index}].qa.identity.checks 缺少：{check_key}")
                        continue
                    check_result = checks.get(check_key)
                    if check_result is not None and check_result not in ALLOWED_IDENTITY_CHECK_RESULTS:
                        errors.append(
                            f"deliverables[{index}].qa.identity.checks.{check_key} 必須是 null 或："
                            f"{', '.join(sorted(ALLOWED_IDENTITY_CHECK_RESULTS))}"
                        )

            if identity_result == "passed" or item_status == "passed":
                if technical_result != "passed":
                    errors.append(f"deliverables[{index}] 通過前，qa.result 必須是 passed")
                if identity_result != "passed":
                    errors.append(f"deliverables[{index}] 通過前，qa.identity.result 必須是 passed")
                if not isinstance(score, (int, float)) or isinstance(score, bool):
                    errors.append(f"deliverables[{index}] 通過前，qa.identity.score 必須有數值")
                elif isinstance(threshold, (int, float)) and not isinstance(threshold, bool) and score < threshold:
                    errors.append(
                        f"deliverables[{index}] 身份分數 {score:.2f} 低於門檻 {threshold:.2f}，不可通過"
                    )
                if reviewer not in ALLOWED_IDENTITY_REVIEWERS:
                    errors.append(f"deliverables[{index}] 通過前，qa.identity.reviewer 必須記錄審查來源")
                if not reviewed_against:
                    errors.append(f"deliverables[{index}] 通過前，qa.identity.reviewed_against 不可為空")

                required_checks = {"viewpoint"}
                if isinstance(identity_lock, dict):
                    for check_key in IDENTITY_CHECK_KEYS - {"viewpoint"}:
                        identity_key = "must_not_change" if check_key == "constraints" else check_key
                        if identity_lock.get(identity_key):
                            required_checks.add(check_key)
                for check_key in sorted(required_checks):
                    if checks.get(check_key) != "passed":
                        errors.append(
                            f"deliverables[{index}] 通過前，身份必查項目 {check_key} 必須是 passed"
                        )

                blocking_checks = [
                    check_key
                    for check_key, check_result in checks.items()
                    if check_key in IDENTITY_CHECK_KEYS and check_result in {"warning", "failed"}
                ]
                if blocking_checks:
                    errors.append(
                        f"deliverables[{index}] 身份檢查仍有阻擋項目：{', '.join(sorted(blocking_checks))}"
                    )

    if data.get("status") == "complete" and isinstance(deliverables, list):
        incomplete = [
            str(item.get("id") or index)
            for index, item in enumerate(deliverables)
            if not isinstance(item, dict) or item.get("status") != "passed"
        ]
        if incomplete:
            errors.append(f"工作單標成 complete 前，所有 deliverable 都必須 passed：{', '.join(incomplete)}")

    generation = data.get("generation")
    if not isinstance(generation, dict):
        errors.append("generation 必須是 object")
    else:
        if not isinstance(generation.get("dry_run"), bool):
            errors.append("generation.dry_run 必須是 boolean")
        for key in ("max_attempts", "max_calls"):
            value = generation.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                errors.append(f"generation.{key} 必須是大於等於 1 的整數")
        max_cost = generation.get("max_cost")
        if max_cost is not None and (
            not isinstance(max_cost, (int, float)) or isinstance(max_cost, bool) or max_cost < 0
        ):
            errors.append("generation.max_cost 必須是大於等於 0 的數字或 null")

    approval = data.get("approval")
    if not isinstance(approval, dict):
        errors.append("approval 必須是 object")
    else:
        approved = approval.get("paid_generation_approved")
        if not isinstance(approved, bool):
            errors.append("approval.paid_generation_approved 必須是 boolean")
        elif approved and not approval.get("approved_scope"):
            errors.append("已核准付費生成時，approval.approved_scope 不可為空")
        if isinstance(generation, dict) and generation.get("dry_run") is False and approved is not True:
            errors.append("generation.dry_run=false 前必須先核准付費生成")

    secret_locations = sorted(set(find_secret_locations(data)))
    for location in secret_locations:
        errors.append(f"工作單不得包含秘密欄位或秘密值：{location}")

    return errors, warnings


def main() -> int:
    args = parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(json.dumps({"ok": False, "errors": ["找不到工作單檔案"]}, ensure_ascii=False, indent=2))
        return 2
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": [f"JSON 格式錯誤：{exc}"]}, ensure_ascii=False, indent=2))
        return 2

    errors, warnings = validate(data)
    result = {"ok": not errors, "errors": errors, "warnings": warnings}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
