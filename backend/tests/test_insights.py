import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agents import narrator
from agents.analysis import build_eda
from agents.insights import _quality, build_insights
from agents.kpis import build_kpis
from agents.profiling import profile_dataframe
from agents.quality import build_quality_report
from config import settings
from main import app
from services import llm_service

client = TestClient(app)

SAMPLE_CSV = b'''Order ID,Order Date,City,Product,Price,Quantity
1001,05/01/2024,Hyderabad,Laptop,"55,000",2
1002,18/01/2024,hyderabad,Mouse,700,5
1003,22/01/2024,Vizag,Keyboard,"1,500",3
1004,03/02/2024,VIZAG ,Laptop,"55,000",1
1005,14/02/2024,Chennai,Monitor,"12,000",
1006,27/02/2024,Chennai,Mouse,700,10
1007,09/03/2024,Hyderabad,Laptop,"55,000",2
1008,21/03/2024,-,Keyboard,"1,500",4
1009,30/03/2024,Vizag,Monitor,"12,000",2
1010,11/04/2024,Hyderabad,Mouse,N/A,6
1011,19/04/2024,Chennai,Laptop,"5,50,000",1
1012,25/04/2024,hyderabad,Keyboard,"1,500",3
1012,25/04/2024,hyderabad,Keyboard,"1,500",3
'''

FACTS = {"insights": [{"id": "I1", "importance": "high",
                       "text": "'C' contributes 50.0% of total revenue"}]}
INSIGHTS = [{"id": "I1", "type": "composition", "importance": "high",
             "message": "'C' contributes 50.0% of total revenue", "evidence": {}, "columns": []}]


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


@pytest.fixture
def sales_df():
    i = np.arange(90)
    return pd.DataFrame(
        {
            "order_date": pd.date_range("2024-01-01", periods=90, freq="D"),
            "product": ["A", "B", "C"] * 30,
            "region": ["North", "South"] * 45,
            "units": [1, 2, 3] * 30,
            "revenue": 100 * ((i % 3) + 1),
        }
    )


@pytest.fixture
def hr_df():
    i = np.arange(40)
    department = np.array(["Engineering"] * 15 + ["Sales"] * 15 + ["HR"] * 10)
    base = np.where(department == "Engineering", 90000, np.where(department == "Sales", 60000, 50000))
    return pd.DataFrame(
        {
            "employee_id": i + 1,
            "department": department,
            "salary": base + (i % 5) * 1000,
            "age": 25 + (i % 20),
        }
    )


def run(df):
    eda = build_eda(df)
    kpis = build_kpis(df, eda)
    profile = profile_dataframe(df)
    quality = build_quality_report(profile, profile, {})
    return build_insights(df, eda, kpis, quality)


def find(insights, kind, **evidence):
    return next(
        (i for i in insights
         if i["type"] == kind and all(i["evidence"].get(k) == v for k, v in evidence.items())),
        None,
    )


# ---------- calculated insights ----------

def test_top_group_share(sales_df):
    insight = find(run(sales_df), "composition", group="C")
    assert insight is not None
    assert insight["evidence"]["share_pct"] == 50.0
    assert insight["importance"] == "high"


def test_hr_payroll_share(hr_df):
    insight = find(run(hr_df), "composition", group="Engineering")
    assert insight["evidence"]["share_pct"] == 48.8
    assert insight["importance"] == "medium"


def test_average_gap_between_groups():
    df = pd.DataFrame({"score": [10] * 5 + [30] * 5, "grp": ["a"] * 5 + ["b"] * 5})
    insight = find(run(df), "composition", best_group="b")
    assert insight["evidence"]["gap_pct"] == 200.0
    assert "above" in insight["message"]


def test_trend_insight():
    i = np.arange(120)
    df = pd.DataFrame(
        {
            "order_date": pd.date_range("2024-01-01", periods=120, freq="D"),
            "region": np.where(i % 2 == 0, "North", "South"),
            "revenue": 1000 + 10 * i,
        }
    )
    insight = find(run(df), "trend", direction="increasing")
    assert insight is not None
    assert insight["importance"] == "high"
    assert insight["evidence"]["change_pct"] > 25


def test_correlation_insight():
    x = np.linspace(0, 10, 30)
    insight = find(run(pd.DataFrame({"x": x, "y": 3 * x + 1})), "correlation")
    assert insight["importance"] == "high"
    assert "same information" in insight["message"]


def test_outlier_insight():
    df = pd.DataFrame({"v": [10, 11, 12, 11, 10, 12, 11, 1000]})
    insight = find(run(df), "outliers")
    assert insight["evidence"]["count"] == 1
    assert insight["evidence"]["max"] == 1000
    assert insight["importance"] == "high"


def test_small_dataset_caution():
    df = pd.DataFrame({"score": [10] * 5 + [30] * 5, "grp": ["a"] * 5 + ["b"] * 5})
    assert find(run(df), "caution", rows=10) is not None


def test_quality_insights_include_score_and_duplicates():
    raw = pd.DataFrame({"a": [1, 2, 2, 3], "b": ["x", "y", "y", "z"]})
    clean = raw.drop_duplicates().reset_index(drop=True)
    quality = build_quality_report(
        profile_dataframe(raw), profile_dataframe(clean), {"duplicates_removed": 1}
    )
    messages = [i["message"] for i in _quality(quality)]
    assert any("Data quality score" in m and "up from" in m for m in messages)
    assert any("removed 1 duplicate" in m for m in messages)


def test_ids_order_cap_and_json_safe(sales_df):
    insights = run(sales_df)
    json.dumps(insights)
    assert [i["id"] for i in insights] == [f"I{n}" for n in range(1, len(insights) + 1)]
    assert len(insights) <= 12
    order = {"high": 0, "medium": 1, "low": 2}
    ranks = [order[i["importance"]] for i in insights]
    assert ranks == sorted(ranks)


# ---------- narration and the hallucination guard ----------

def test_guard_accepts_verified_numbers():
    ok, bad = narrator.is_grounded("Product C brings 50.0% of revenue [I1].", json.dumps(FACTS))
    assert ok and bad == []


def test_guard_rejects_invented_numbers():
    ok, bad = narrator.is_grounded("Revenue grew 87% last month.", json.dumps(FACTS))
    assert not ok
    assert 87.0 in bad


def test_narrate_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    result = narrator.narrate(FACTS, INSIGHTS)
    assert result["source"] == "rules"
    assert "50.0%" in result["summary"]


def test_narrate_accepts_grounded_ai_answer(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        llm_service, "complete_json",
        lambda system, user, **kw: {
            "summary": "Product C contributes 50.0% of revenue [I1].",
            "recommendations": ["Check how dependent revenue is on Product C."],
            "questions": ["How do the other products compare?"],
        },
    )
    result = narrator.narrate(FACTS, INSIGHTS)
    assert result["source"] == "ai"
    assert result["model"] == settings.openai_model


def test_narrate_rejects_hallucinated_answer(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        llm_service, "complete_json",
        lambda system, user, **kw: {"summary": "Revenue grew 87% last month [I1].",
                                    "recommendations": [], "questions": []},
    )
    result = narrator.narrate(FACTS, INSIGHTS)
    assert result["source"] == "rules"
    assert "verified" in result["note"]


def test_narrate_survives_llm_failure(monkeypatch):
    def down(system, user, **kw):
        raise llm_service.LLMUnavailable("down")

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(llm_service, "complete_json", down)
    result = narrator.narrate(FACTS, INSIGHTS)
    assert result["source"] == "rules"
    assert result["note"] == "down"


def test_clean_text_flattens_and_truncates():
    cleaned = narrator.clean_text("a\n\nb" + "x" * 500)
    assert "\n" not in cleaned
    assert len(cleaned) <= 200


# ---------- endpoint ----------

def upload():
    return client.post("/upload", files={"file": ("s.csv", SAMPLE_CSV)}).json()["dataset_id"]


def test_insights_endpoint_without_key(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    body = client.get(f"/datasets/{upload()}/insights").json()
    assert body["cached"] is False
    assert body["narration"]["source"] == "rules"
    assert body["insights"][0]["id"] == "I1"
    assert any("Data quality score" in i["message"] for i in body["insights"])


def test_ai_narration_is_cached(monkeypatch):
    calls = []

    def fake(system, user, **kw):
        calls.append(1)
        return {"summary": "The data shows a few notable patterns [I1].",
                "recommendations": ["Review the quality issues."],
                "questions": ["Which product drives most revenue?"]}

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(llm_service, "complete_json", fake)
    dataset_id = upload()

    first = client.get(f"/datasets/{dataset_id}/insights").json()
    assert first["narration"]["source"] == "ai" and first["cached"] is False

    second = client.get(f"/datasets/{dataset_id}/insights").json()
    assert second["cached"] is True and len(calls) == 1

    refreshed = client.get(f"/datasets/{dataset_id}/insights?refresh=true").json()
    assert refreshed["cached"] is False and len(calls) == 2


def test_insights_unknown_dataset():
    assert client.get(f"/datasets/{'0' * 32}/insights").status_code == 404