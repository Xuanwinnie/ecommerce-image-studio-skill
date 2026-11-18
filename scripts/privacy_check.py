#!/usr/bin/env python3
"""在發佈前阻擋商品圖片、產物目錄與本機路徑。"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BLOCKED_DIRECTORIES = {"inputs", "output", "private", "customer-data"}
BLOCKED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".heic",
    ".heif",
    ".gif",
    ".tif",
    ".tiff",
    ".bmp",
    ".avif",
}
PUBLIC_DEMO_DIRECTORY = ("docs", "demo")
TEXT_EXTENSIONS = {"", ".md", ".py", ".json", ".yaml", ".yml", ".gitignore"}
MACOS_USER_ROOT = "/" + "Users" + "/"
WINDOWS_USER_ROOT = "Users" + "\\"
LOCAL_PATH_PATTERNS = (
    re.compile(re.escape(MACOS_USER_ROOT) + r"[^/\s]+/"),
    re.compile(r"[A-Za-z]:\\" + re.escape(WINDOWS_USER_ROOT) + r"[^\\\s]+\\"),
)


def iter_repository_files() -> list[Path]:
    files: list[Path] = []
    for root, directories, filenames in os.walk(REPO_ROOT):
        directories[:] = [name for name in directories if name not in {".git", "__pycache__", ".pytest_cache"}]
        root_path = Path(root)
        for filename in filenames:
            files.append(root_path / filename)
    return files


def check_file(path: Path) -> list[str]:
    relative = path.relative_to(REPO_ROOT)
    errors: list[str] = []

    if BLOCKED_DIRECTORIES.intersection(relative.parts):
        errors.append(f"禁止的本機資料目錄：{relative}")
    is_public_demo = relative.parts[: len(PUBLIC_DEMO_DIRECTORY)] == PUBLIC_DEMO_DIRECTORY
    if path.suffix.lower() in BLOCKED_EXTENSIONS and not is_public_demo:
        errors.append(f"點陣圖片只能放在 docs/demo/：{relative}")

    if path.suffix.lower() in TEXT_EXTENSIONS:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"無法確認內容的二進位檔案：{relative}")
        else:
            if any(pattern.search(content) for pattern in LOCAL_PATH_PATTERNS):
                errors.append(f"包含本機使用者絕對路徑：{relative}")

    return errors


def main() -> int:
    errors: list[str] = []
    for path in iter_repository_files():
        errors.extend(check_file(path))

    if errors:
        print("隱私檢查失敗：")
        for error in errors:
            print(f"- {error}")
        return 2

    print("隱私檢查通過：圖片只存在於允許的 Demo 目錄，且未發現產物目錄或本機使用者路徑。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
