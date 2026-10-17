import json
import struct


def test_inspect_safetensors(client, tmp_path):
    header = {"__metadata__": {"ss_base_model_version": "sdxl_base_v1-0", "ss_output_name": "demo"}}
    raw = json.dumps(header).encode()
    f = tmp_path / "demo.safetensors"
    f.write_bytes(struct.pack("<Q", len(raw)) + raw)
    r = client.post("/api/sd-models/inspect", json={"path": str(f), "compute_hash": True}).json()
    assert r["base_model"] == "SDXL" and r["metadata"]["ss_output_name"] == "demo"
    assert len(r["sha256"]) == 64


def test_inspect_rejects_non_model(client, tmp_path):
    f = tmp_path / "secret.txt"
    f.write_text("x")
    assert client.post("/api/sd-models/inspect", json={"path": str(f)}).status_code == 422
