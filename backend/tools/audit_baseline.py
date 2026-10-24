"""Reproducible v0.7 audit using disposable generated data, never a personal library.

Run from the repository root:
  .venv/Scripts/python backend/tools/audit_baseline.py --run baseline-01
Outputs stay in .cache/audit/<run>; an existing run is never overwritten.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import platform
import sqlite3
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    if not args.run or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in args.run):
        parser.error("run must be an alphanumeric name")
    out = ROOT / ".cache" / "audit" / args.run
    out.mkdir(parents=True, exist_ok=False)
    os.environ["FRONT_DATA_DIR"] = str(out / "data")
    os.environ["FRONT_CIVITAI"] = "off"
    # seed() substitutes local ASGI clients for the three metadata providers.
    os.environ.pop("FRONT_GALGAME", None)
    for name in ("FRONT_AI_BASE_URL", "FRONT_AI_API_KEY", "FRONT_AI_MODEL", "FRONT_SD_WEBUI_URL", "FRONT_COMFYUI_URL"):
        os.environ.pop(name, None)
    sys.path.insert(0, str(ROOT / "backend"))
    sys.path.insert(0, str(ROOT / "backend" / "tests"))
    from fastapi.testclient import TestClient
    from front_api.main import create_app
    from front_api.seed import seed
    from front_api import models as m
    from front_api.db import new_session
    import samples as s
    from PIL import Image

    result = {"environment": {"platform": platform.system(), "python": platform.python_version(), "sqlite": sqlite3.sqlite_version},
              "method": "Generated fixtures; in-process ASGI timings, 15 sequential samples; no TCP/browser latency. Large upload memory uses tracemalloc (Python allocations, not RSS). Not real production assets or GPU validation."}
    started = time.perf_counter()
    app = create_app()
    result["empty_app_creation_ms"] = round((time.perf_counter() - started) * 1000, 2)
    with TestClient(app, raise_server_exceptions=False) as client:
        refs = seed(client)
        os.environ["FRONT_GALGAME"] = "off"
        result["seed_refs"] = refs
        generated = {
            "lighthouse.glb": s.glb(*s.gltf_lighthouse()), "keeper.vrm": s.glb(*s.gltf_lighthouse("1.0")),
            "lighthouse.obj": s.obj_lighthouse(), "lantern.zip": s.pmx_zip(), "live2d.zip": s.live2d_zip(),
            "note.docx": s.docx("Audit", [("p", "Generated document")]),
            "reading.pdf": s.pdf("Audit", ["Generated PDF"]), "music.wav": s.wav(),
            "novel.txt": "第一章 雾港\n生成的审计文本".encode(), "note.md": b"# Generated Markdown\n\nAudit text",
            "drawing.svg": b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="purple"/></svg>',
            "broken.glb": b"malformed-model-fixture",
        }
        for ext, fmt in (("png", "PNG"), ("jpg", "JPEG"), ("webp", "WEBP"), ("gif", "GIF")):
            buf = io.BytesIO()
            Image.new("RGB", (80, 64), (50, 80, 120)).save(buf, format=fmt)
            generated[f"image.{ext}"] = buf.getvalue()
        fixture_results = []
        for name, data in generated.items():
            response = client.post("/api/assets/upload", files={"file": (name, data, "application/octet-stream")})
            body = response.json()
            fixture_results.append({"name": name, "status": response.status_code, "id": body.get("id"),
                                    "kind": body.get("kind"), "width": body.get("width"), "meta": body.get("meta", {}).get("file", {})})
        result["generated_files"] = fixture_results
        # This is a record-count baseline, not 2,000 full-resolution images.
        with new_session() as session:
            session.add_all([m.Asset(title=f"审计记录 {i:04}", kind="novel" if i >= 1500 else "reference",
                                     content=("审计长文本 " * 512) if i >= 1500 else None) for i in range(2000)])
            session.commit()
        endpoints = ["/api/stats", "/api/assets?limit=200", "/api/assets?limit=200&offset=200",
                     "/api/search?q=审计", "/api/notes/tree", "/api/graph", "/api/diagrams", "/api/galgames",
                     f"/api/prompts/{refs['prompt_id']}/compare"]
        metrics = {}
        for endpoint in endpoints:
            samples = []
            for _ in range(15):
                tick = time.perf_counter()
                response = client.get(endpoint)
                samples.append((time.perf_counter() - tick) * 1000)
            metrics[endpoint] = {"status": response.status_code, "bytes": len(response.content),
                                 "median_ms": round(statistics.median(samples), 2), "p95_ms": round(sorted(samples)[14], 2)}
        result["api_timings"] = metrics
        large = out / "large.dat"
        with large.open("wb") as handle:
            for _ in range(32):
                handle.write(b"front-audit-data!" * 65536)
        tracemalloc.start()
        tick = time.perf_counter()
        with large.open("rb") as handle:
            response = client.post("/api/assets/upload", files={"file": (large.name, handle, "application/octet-stream")})
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result["large_upload"] = {"bytes": large.stat().st_size, "status": response.status_code,
                                  "elapsed_ms": round((time.perf_counter() - tick) * 1000, 2), "python_peak_bytes": peak}
        result["stats"] = client.get("/api/stats").json()
        # Reproduce rollback safety only on a new, disposable fixture; repair it
        # before removing it so the audit dataset is not left with a missing file.
        probe_data = b"disposable-rollback-audit-fixture"
        probe = client.post("/api/assets/upload", files={"file": ("rollback.txt", probe_data)}).json()
        with new_session() as session:
            asset = session.get(m.Asset, probe["id"])
            probe_path = out / "data" / asset.file_path
            session.delete(asset)
            session.flush()
            session.rollback()
            result["delete_rollback_probe"] = {"row_restored": session.get(m.Asset, probe["id"]) is not None,
                                               "file_preserved": probe_path.exists()}
        if not probe_path.exists():
            probe_path.write_bytes(probe_data)
        client.delete(f"/api/assets/{probe['id']}").raise_for_status()
        schema = app.openapi()
        inventory = [{"method": method.upper(), "path": path, "tags": operation.get("tags", []),
                      "required_parameters": [p["name"] for p in operation.get("parameters", []) if p.get("required")]}
                     for path, methods in schema["paths"].items() for method, operation in methods.items()
                     if method in {"get", "post", "put", "patch", "delete"}]
        result["operation_count"] = len(inventory)
        (out / "api-inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    with sqlite3.connect(out / "data" / "front.db") as conn:
        result["database"] = {"integrity_check": conn.execute("PRAGMA integrity_check").fetchone()[0],
                              "foreign_key_check": conn.execute("PRAGMA foreign_key_check").fetchall(),
                              "tables": conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall(),
                              "indexes": conn.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' ORDER BY name").fetchall()}
    assets = ROOT / "frontend" / "dist" / "static"
    result["bundle"] = [{"name": path.name, "bytes": path.stat().st_size, "gzip_bytes": len(gzip.compress(path.read_bytes()))}
                        for path in sorted(assets.glob("*.js"), key=lambda p: p.stat().st_size, reverse=True)]
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out.relative_to(ROOT) / "results.json"))


if __name__ == "__main__":
    main()
