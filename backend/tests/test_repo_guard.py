"""仓库卫士：模型文件、用户数据、媒体文件永远不能进 git。"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_EXT = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx", ".db", ".sqlite", ".sqlite3", ".zip", ".7z", ".rar", ".psd", ".clip", ".kra", ".mp4", ".webm"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
# 只有这些目录允许出现图片（文档截图、前端图标）
IMAGE_ALLOWED = ("docs/screenshots/", "frontend/public/")


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line for line in out.splitlines() if line]


def test_no_model_or_data_files_tracked():
    bad = [f for f in tracked_files() if Path(f).suffix.lower() in FORBIDDEN_EXT]
    assert not bad, f"这些文件不应提交: {bad}"


def test_images_only_in_allowed_dirs():
    bad = [f for f in tracked_files() if Path(f).suffix.lower() in IMAGE_EXT and not f.startswith(IMAGE_ALLOWED)]
    assert not bad, f"图片只能放在 {IMAGE_ALLOWED}: {bad}"


def test_data_dirs_not_tracked():
    bad = [f for f in tracked_files() if f.startswith(("data/", "front-data/", "models/", "private/"))]
    assert not bad, bad
