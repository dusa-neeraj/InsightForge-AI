import os
import time

import pytest
from fastapi.testclient import TestClient

from config import settings
from main import app
from services import cleanup, file_service, rate_limit
from utils.errors import DatasetError

client = TestClient(app)

CSV = b"a,b\n1,x\n2,y\n3,z\n"


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


def upload():
    return client.post("/upload", files={"file": ("d.csv", CSV)})


# ---------- one error format ----------

def test_validation_errors_use_the_standard_format_and_do_not_echo_input():
    url = f"/datasets/{'0' * 32}/chat"
    r = client.post(url, json={"question": ""})
    body = r.json()
    assert r.status_code == 422
    assert "error" in body and body["details"][0]["field"] == "question"

    big = client.post(url, json={"question": "x" * 3000})
    assert big.status_code == 422
    assert "xxxxxxxxxx" not in big.text


def test_unknown_routes_and_wrong_methods_return_json():
    missing = client.get("/no-such-page")
    assert missing.status_code == 404 and missing.json() == {"error": "Not found."}
    wrong = client.post("/health")
    assert wrong.status_code == 405 and "error" in wrong.json()


def test_internal_errors_hide_details(monkeypatch):
    dataset = upload().json()["dataset_id"]

    def boom(_dataset_id):
        raise RuntimeError("secret path C:\\private\\data")

    monkeypatch.setattr(file_service, "load_clean_dataset", boom)
    quiet = TestClient(app, raise_server_exceptions=False)
    r = quiet.get(f"/datasets/{dataset}/preview")
    assert r.status_code == 500
    assert r.json() == {"error": "Something went wrong on the server."}
    assert "private" not in r.text


# ---------- headers and CORS ----------

def test_security_headers_are_set():
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_cors_allows_only_the_expected_methods():
    origin = settings.origins_list[0]
    allowed = client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "DELETE"})
    assert allowed.status_code == 200
    assert "DELETE" in allowed.headers["access-control-allow-methods"]
    refused = client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "PUT"})
    assert refused.status_code == 400


# ---------- rate limiting ----------

def test_the_limiter_counts_per_key_and_resets_after_the_window():
    now = [0.0]
    limiter = rate_limit.RateLimiter(clock=lambda: now[0])
    assert limiter.check("a", 2, 60) == 0
    assert limiter.check("a", 2, 60) == 0
    wait = limiter.check("a", 2, 60)
    assert 0 < wait <= 60
    assert limiter.check("b", 2, 60) == 0  # another client is not affected
    now[0] = 61
    assert limiter.check("a", 2, 60) == 0


def test_uploads_are_rate_limited(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_upload_per_min", 2)
    rate_limit.limiter.reset()
    assert upload().status_code == 200
    assert upload().status_code == 200
    blocked = upload()
    assert blocked.status_code == 429
    assert "Too many requests" in blocked.json()["error"]
    assert int(blocked.headers["retry-after"]) >= 1
    assert client.get("/health").status_code == 200  # other endpoints are untouched


def test_rate_limiting_can_be_turned_off():
    assert all(upload().status_code == 200 for _ in range(12))


# ---------- upload size ----------

def test_oversized_uploads_are_refused_before_anything_is_stored(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    big = b"a,b\n" + b"1,2\n" * 400_000  # about 1.6 MB
    r = client.post("/upload", files={"file": ("big.csv", big)})
    assert r.status_code == 413
    assert "1 MB" in r.json()["error"]
    assert list(settings.upload_dir.iterdir()) == []


# ---------- retention and deletion ----------

def test_expired_datasets_are_removed_and_others_are_kept():
    old_id = upload().json()["dataset_id"]
    new_id = upload().json()["dataset_id"]
    (settings.upload_dir / "notes").mkdir()  # not a dataset folder, must be left alone
    long_ago = time.time() - 200 * 3600
    os.utime(settings.upload_dir / old_id / "clean.csv", (long_ago, long_ago))

    assert cleanup.remove_expired(retention_hours=168) == 1
    assert not (settings.upload_dir / old_id).exists()
    assert (settings.upload_dir / new_id).exists()
    assert (settings.upload_dir / "notes").exists()
    assert cleanup.remove_expired(retention_hours=0) == 0  # 0 means keep forever


def test_a_dataset_can_be_deleted():
    dataset = upload().json()["dataset_id"]
    r = client.delete(f"/datasets/{dataset}")
    assert r.status_code == 200 and r.json() == {"deleted": True}
    assert client.get(f"/datasets/{dataset}/preview").status_code == 404
    assert client.delete(f"/datasets/{dataset}").status_code == 404
    assert client.delete("/datasets/not-an-id").status_code == 400


def test_deleting_cannot_reach_outside_the_data_folder():
    for bad in ("../x", "..", "C:\\Windows", "a" * 31, "A" * 32):
        with pytest.raises(DatasetError) as info:
            cleanup.delete_dataset(bad)
        assert info.value.status_code == 400


# ---------- secrets ----------

def test_the_api_key_never_appears_in_responses(monkeypatch):
    secret = "sk-test-secret-123456"
    monkeypatch.setattr(settings, "openai_api_key", secret)
    dataset = upload().json()["dataset_id"]
    responses = [
        client.get("/health"),
        client.get(f"/datasets/{dataset}/preview"),
        client.get(f"/datasets/{dataset}/kpis"),
        client.get(f"/datasets/{dataset}/sql/schema"),
        client.post(f"/datasets/{dataset}/chat", json={"question": "Give me 3 insights"}),
    ]
    for r in responses:
        assert r.status_code == 200
        assert secret not in r.text
        assert secret not in str(dict(r.headers))