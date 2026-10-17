import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from front_api.config import get_settings
from front_api.main import create_app


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONT_DATA_DIR", str(tmp_path / "data"))
    for key in ("FRONT_AI_BASE_URL", "FRONT_AI_API_KEY", "FRONT_AI_MODEL"):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield tmp_path / "data"
    get_settings.cache_clear()


@pytest.fixture()
def app(data_dir):
    return create_app()


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


def png_bytes(color=(200, 80, 120), size=(64, 48), text=None):
    from PIL import PngImagePlugin

    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    info = PngImagePlugin.PngInfo()
    for k, v in (text or {}).items():
        info.add_text(k, v)
    img.save(buf, format="PNG", pnginfo=info)
    return buf.getvalue()
