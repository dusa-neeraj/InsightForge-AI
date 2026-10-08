import re

import pytest
from fastapi.testclient import TestClient

from config import settings
from main import app
from services import llm_service

client = TestClient(app)

CSV = b"""order_id,order_date,product,region,revenue,units
1,2024-01-05,Laptop,North,50000,1
2,2024-01-12,Mouse,North,700,5
3,2024-02-03,Laptop,South,50000,1
4,2024-02-14,Keyboard,South,1500,3
5,2024-03-09,Laptop,North,50000,1
6,2024-03-21,Mouse,South,900,4
7,2024-04-11,Keyboard,North,1500,2
8,2024-04-25,Laptop,South,50000,1
"""


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


@pytest.fixture
def dataset_id(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    return client.post("/upload", files={"file": ("sales.csv", CSV)}).json()["dataset_id"]


def ask(dataset_id, question):
    response = client.post(f"/datasets/{dataset_id}/chat", json={"question": question})
    assert response.status_code == 200, response.text
    return response.json()


def numbered(answer):
    return [line for line in answer.splitlines() if re.match(r"^\d+\. ", line)]


def test_insight_questions_are_answered_by_the_insight_engine(dataset_id):
    body = ask(dataset_id, "Give me 5 important business insights from this dataset.")
    assert body["status"] == "ok" and body["source"] == "insights"
    assert 1 <= len(numbered(body["answer"])) <= 5
    assert "AI Insights page" in body["answer"]
    assert body["method"] and body["result"] is None


def test_the_requested_number_is_respected(dataset_id):
    assert len(numbered(ask(dataset_id, "Show me 2 key insights")["answer"])) == 2


def test_other_phrasings_work(dataset_id):
    for question in ("What are the key findings?", "What stands out in this data?", "Any highlights?"):
        assert ask(dataset_id, question)["source"] == "insights"


def test_normal_questions_still_use_the_planner(dataset_id):
    body = ask(dataset_id, "Which product has the highest revenue?")
    assert body["source"] == "rules"
    assert body["result"]["rows"] == [["Laptop", 200000]]


def test_no_ai_call_is_made_for_insight_questions(dataset_id, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the AI must not be called for insight questions")

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(llm_service, "complete_json", boom)
    assert ask(dataset_id, "Give me 3 insights")["status"] == "ok"