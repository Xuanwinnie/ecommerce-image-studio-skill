#!/usr/bin/env python3
"""測試工作單驗證與圖片 QA 的可觀察行為。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = SKILL_ROOT / "scripts" / "validate_manifest.py"
IMAGE_SCRIPT = SKILL_ROOT / "scripts" / "check_listing_image.py"
EXAMPLE_MANIFEST = SKILL_ROOT / "assets" / "job-manifest.example.json"


def run_script(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


class ManifestValidationTests(unittest.TestCase):
    def validate_data(self, data: dict[str, object]) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "manifest.json"
            manifest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            result = run_script(str(VALIDATE_SCRIPT), str(manifest))
        return result, json.loads(result.stdout)

    def test_example_manifest_is_valid(self) -> None:
        result = run_script(str(VALIDATE_SCRIPT), str(EXAMPLE_MANIFEST))
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["errors"], [])

    def test_secret_field_is_rejected(self) -> None:
        data = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))
        data["generation"]["api_key"] = "不可保存的示例值"
        result, payload = self.validate_data(data)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(payload["ok"])
        self.assertTrue(any("秘密欄位" in message for message in payload["errors"]))

    def test_secret_value_is_rejected_without_echoing_it(self) -> None:
        data = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))
        secret = "Bearer sk-live-example-value"
        data["generation"]["provider_config"] = secret
        result, payload = self.validate_data(data)

        self.assertEqual(result.returncode, 2)
        self.assertTrue(any("秘密欄位或秘密值" in message for message in payload["errors"]))
        self.assertNotIn(secret, result.stdout)

    def test_invalid_deliverable_status_is_rejected(self) -> None:
        data = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))
        data["deliverables"][0]["status"] = "nonsense"
        result, payload = self.validate_data(data)

        self.assertEqual(result.returncode, 2)
        self.assertTrue(any("deliverables[0].status" in message for message in payload["errors"]))

    def test_output_path_cannot_escape_work_directory(self) -> None:
        data = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))
        data["deliverables"][0]["output"] = "../../outside.png"
        result, payload = self.validate_data(data)

        self.assertEqual(result.returncode, 2)
        self.assertTrue(any("安全相對路徑" in message for message in payload["errors"]))

    def test_live_generation_requires_approval(self) -> None:
        data = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))
        data["generation"]["dry_run"] = False
        result, payload = self.validate_data(data)

        self.assertEqual(result.returncode, 2)
        self.assertTrue(any("必須先核准" in message for message in payload["errors"]))

    def test_viewpoint_policy_is_required(self) -> None:
        data = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))
        del data["deliverables"][0]["viewpoint_policy"]
        result, payload = self.validate_data(data)

        self.assertEqual(result.returncode, 2)
        self.assertTrue(any("viewpoint_policy" in message for message in payload["errors"]))

    def test_correct_to_front_requires_notes(self) -> None:
        data = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))
        data["deliverables"][0]["viewpoint_notes"] = ""
        result, payload = self.validate_data(data)

        self.assertEqual(result.returncode, 2)
        self.assertTrue(any("viewpoint_notes" in message for message in payload["errors"]))

    def test_passed_deliverable_requires_identity_gate(self) -> None:
        data = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))
        data["deliverables"][0]["status"] = "passed"
        data["deliverables"][0]["qa"]["result"] = "passed"
        result, payload = self.validate_data(data)

        self.assertEqual(result.returncode, 2)
        self.assertTrue(any("qa.identity.result" in message for message in payload["errors"]))
        self.assertTrue(any("身份必查項目" in message for message in payload["errors"]))

    def test_identity_score_below_threshold_is_rejected(self) -> None:
        data = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))
        deliverable = data["deliverables"][0]
        deliverable["status"] = "passed"
        deliverable["qa"]["result"] = "passed"
        identity = deliverable["qa"]["identity"]
        identity["result"] = "passed"
        identity["score"] = 0.89
        identity["reviewer"] = "vision-model"
        identity["reviewed_against"] = ["inputs/front.png"]
        identity["checks"]["constraints"] = "passed"
        identity["checks"]["viewpoint"] = "passed"
        result, payload = self.validate_data(data)

        self.assertEqual(result.returncode, 2)
        self.assertTrue(any("低於門檻" in message for message in payload["errors"]))

    def test_complete_job_requires_every_deliverable_to_pass(self) -> None:
        data = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))
        data["status"] = "complete"
        result, payload = self.validate_data(data)

        self.assertEqual(result.returncode, 2)
        self.assertTrue(any("所有 deliverable 都必須 passed" in message for message in payload["errors"]))

    def test_complete_job_with_both_qa_gates_is_valid(self) -> None:
        data = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))
        data["status"] = "complete"
        deliverable = data["deliverables"][0]
        deliverable["status"] = "passed"
        deliverable["qa"]["result"] = "passed"
        identity = deliverable["qa"]["identity"]
        identity["result"] = "passed"
        identity["score"] = 0.96
        identity["reviewer"] = "human+vision-model"
        identity["reviewed_against"] = ["inputs/front.png"]
        identity["checks"]["constraints"] = "passed"
        identity["checks"]["viewpoint"] = "passed"
        result, payload = self.validate_data(data)

        self.assertEqual(result.returncode, 0)
        self.assertTrue(payload["ok"])


class ImageValidationTests(unittest.TestCase):
    def test_amazon_profile_accepts_square_white_image_with_large_subject(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "hero.png"
            image = Image.new("RGB", (1000, 1000), "white")
            drawer = ImageDraw.Draw(image)
            drawer.rectangle((75, 200, 925, 800), fill=(20, 20, 20))
            image.save(image_path)

            result = run_script(str(IMAGE_SCRIPT), str(image_path), "--profile", "amazon-main")

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["metrics"]["white_border_ratio"], 0.98)
        self.assertGreaterEqual(payload["metrics"]["estimated_subject_span"], 0.85)

    def test_amazon_profile_rejects_non_square_non_white_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "bad-hero.png"
            Image.new("RGB", (1200, 1000), (30, 30, 30)).save(image_path)
            result = run_script(str(IMAGE_SCRIPT), str(image_path), "--profile", "amazon-main")

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(payload["ok"])
        self.assertGreaterEqual(len(payload["errors"]), 2)

    def test_json_report_cannot_overwrite_input_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "hero.png"
            Image.new("RGB", (1000, 1000), "white").save(image_path)
            original_bytes = image_path.read_bytes()
            result = run_script(
                str(IMAGE_SCRIPT),
                str(image_path),
                "--json-output",
                str(image_path),
            )
            preserved_bytes = image_path.read_bytes()

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(preserved_bytes, original_bytes)

    def test_corrupt_image_returns_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "broken.png"
            image_path.write_bytes(b"not an image")
            result = run_script(str(IMAGE_SCRIPT), str(image_path))

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(result.stderr, "")
        self.assertTrue(any("無法辨識" in message for message in payload["errors"]))


if __name__ == "__main__":
    unittest.main()
