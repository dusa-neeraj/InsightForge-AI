import io
import threading

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agents.report_charts import render_chart
from config import settings
from main import app
from services import report_service

client = TestClient(app)

CSV = b"""order_id,order_date,product,category,region,customer_type,sales_channel,sales,profit
1,2025-01-05,Laptop,Tech,North,Retail,Online,50000,9000
2,2025-01-12,Mouse,Tech,North,Wholesale,Store,700,100
3,2025-02-03,Chair,Furniture,South,Retail,Online,6000,800
4,2025-02-14,Desk,Furniture,South,Retail,Store,12000,2500
5,2025-03-09,Laptop,Tech,North,Wholesale,Online,50000,8500
6,2025-03-21,Mouse,Tech,South,Retail,Online,900,150
7,2025-04-11,Chair,Furniture,North,Wholesale,Store,6500,900
8,2025-04-25,Laptop,Tech,South,Retail,Online,50000,9500
"""

BAR = {
    "id": "bar-x", "type": "bar", "title": "Test bar", "reason": "test",
    "figure": {"data": [{"type": "bar", "x": ["a", "b"], "y": [1, 2]}], "layout": {}},
}


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


@pytest.fixture
def dataset_id(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    return client.post("/upload", files={"file": ("sales.csv", CSV)}).json()["dataset_id"]


def upload(csv: bytes) -> str:
    return client.post("/upload", files={"file": ("d.csv", csv)}).json()["dataset_id"]


# ---------- cleaned CSV ----------

def test_clean_csv_download(dataset_id):
    r = client.get(f"/datasets/{dataset_id}/download/clean.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf")  # BOM so Excel reads UTF-8
    frame = pd.read_csv(io.BytesIO(r.content))
    assert len(frame) == 8 and "sales" in frame.columns


def test_formula_cells_are_neutralized_in_the_csv():
    dataset = upload(b"name,amount\n=SUM(A1),5\nok,6\n+x,7\n")
    r = client.get(f"/datasets/{dataset}/download/clean.csv")
    names = pd.read_csv(io.BytesIO(r.content), dtype=str, encoding="utf-8-sig")["name"].tolist()
    assert "'=SUM(A1)" in names and "'+x" in names and "ok" in names


# ---------- HTML report ----------

def test_html_report_has_every_section(dataset_id):
    r = client.get(f"/datasets/{dataset_id}/reports/html")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "inline" in r.headers["content-disposition"]
    assert "default-src 'none'" in r.headers["content-security-policy"]
    page = r.text
    for heading in ("Data Analysis Report", "Key findings", "Key numbers", "Data quality",
                    "Cleaning steps", "Statistics", "Charts", "All insights"):
        assert heading in page
    assert "data:image/svg+xml;base64," in page
    assert "<script" not in page.lower()


def test_html_report_can_be_downloaded(dataset_id):
    r = client.get(f"/datasets/{dataset_id}/reports/html?download=true")
    assert "attachment" in r.headers["content-disposition"]


def test_report_text_from_the_file_is_escaped():
    dataset = upload(b"product,sales\n<b>bold</b>,10\n<b>bold</b>,20\nplain,5\nplain,7\nother,9\nother,3\n")
    r = client.get(f"/datasets/{dataset}/reports/html", params={"name": "<script>alert(1)</script>"})
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text
    assert "<b>bold</b>" not in r.text


def test_currency_symbol_is_applied_and_validated(dataset_id):
    page = client.get(f"/datasets/{dataset_id}/reports/html", params={"currency": "₹"}).text
    assert "₹176,100" in page
    other = client.get(f"/datasets/{dataset_id}/reports/html", params={"currency": "X"}).text
    assert "X176,100" not in other and "176,100" in other
    assert client.get(f"/datasets/{dataset_id}/reports/html", params={"currency": "XY"}).status_code == 422


# ---------- PDF report ----------

def test_pdf_report(dataset_id):
    r = client.get(f"/datasets/{dataset_id}/reports/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF") and len(r.content) > 5000


def test_pdf_survives_text_the_builtin_font_cannot_draw():
    dataset = upload("product,sales\nతెలుగు,10\nతెలుగు,20\nहिन्दी,5\nहिन्दी,7\nplain,9\nplain,3\n".encode("utf-8"))
    r = client.get(f"/datasets/{dataset}/reports/pdf", params={"name": "डेटा", "currency": "₹"})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_reports_work_for_a_tiny_text_only_dataset():
    dataset = upload(b"city\nHyd\nVizag\nHyd\n")
    assert client.get(f"/datasets/{dataset}/reports/html").status_code == 200
    assert client.get(f"/datasets/{dataset}/reports/pdf").status_code == 200


# ---------- charts, limits and errors ----------

def test_charts_render_as_svg_and_png_and_failures_return_none():
    assert b"<svg" in render_chart(BAR, "svg")
    assert render_chart(BAR, "png").startswith(b"\x89PNG")
    assert render_chart({**BAR, "type": "pie"}, "svg") is None
    broken = {**BAR, "figure": {"data": [{"type": "bar", "x": ["a", "b"], "y": [1, 2, 3]}], "layout": {}}}
    assert render_chart(broken, "svg") is None


def test_a_busy_server_answers_429(dataset_id, monkeypatch):
    full = threading.BoundedSemaphore(1)
    full.acquire()
    monkeypatch.setattr(report_service, "_slots", full)
    r = client.get(f"/datasets/{dataset_id}/reports/pdf")
    assert r.status_code == 429
    assert "busy" in r.json()["error"]


def test_report_endpoints_return_404_for_unknown_datasets():
    missing = "0" * 32
    for path in ("download/clean.csv", "reports/html", "reports/pdf"):
        assert client.get(f"/datasets/{missing}/{path}").status_code == 404