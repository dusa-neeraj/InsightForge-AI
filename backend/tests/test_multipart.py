import pytest
from fastapi.testclient import TestClient

from agents.question_splitter import split_question
from config import settings
from main import app

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

NO_PROFIT_CSV = b"order_date,product,sales\n2025-01-05,Laptop,100\n2025-02-05,Mouse,50\n2025-03-05,Laptop,120\n"

PROMPT = """Give me:
1. Total sales
2. Total profit
3. Average order value
4. Best-performing category
5. Best-performing region
6. Top 3 products
7. Monthly sales trend
8. Customer-type performance
9. Sales-channel performance
10. 5 actionable recommendations
11. Appropriate visualizations"""


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


@pytest.fixture
def dataset_id(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    return client.post("/upload", files={"file": ("sales.csv", CSV)}).json()["dataset_id"]


def ask(dataset_id, question, session_id=None):
    body = {"question": question}
    if session_id:
        body["session_id"] = session_id
    response = client.post(f"/datasets/{dataset_id}/chat", json=body)
    assert response.status_code == 200, response.text
    return response.json()


# ---------- splitting ----------

def test_numbered_lists_are_split():
    text = "Give me: 1. Total sales 2. Average order value 10. Top 5 products"
    assert split_question(text) == ["Total sales", "Average order value", "Top 5 products"]


def test_bulleted_lists_are_split():
    text = "Analyze this:\n- Total sales\n- Total profit\n- Top 5 products"
    assert split_question(text) == ["Total sales", "Total profit", "Top 5 products"]


def test_several_questions_are_split():
    text = "Which product sells most? What is the average price?"
    assert split_question(text) == ["Which product sells most?", "What is the average price?"]


def test_single_requests_stay_whole():
    single = "Give me 5 important business insights from this dataset."
    assert split_question(single) == [single]
    prose = "x" * 150 + "\n" + "y" * 150
    assert split_question(prose) == [prose]


# ---------- the long prompt ----------

def test_a_long_prompt_is_answered_part_by_part(dataset_id):
    body = ask(dataset_id, PROMPT)
    parts = body["parts"]
    assert len(parts) == 11
    assert body["status"] == "ok" and body["source"] == "multi"
    assert body["answer"].startswith("Answered 11 of 11")

    def part(n):
        return parts[n - 1]

    assert part(1)["result"]["scalar"] == 176100
    assert part(2)["result"]["scalar"] == 31450
    assert part(3)["result"]["scalar"] == 22012.5
    assert part(4)["result"]["rows"][0][0] == "Tech"
    assert part(5)["result"]["rows"][0][0] == "North"
    assert [r[0] for r in part(6)["result"]["rows"]] == ["Laptop", "Chair", "Desk"]

    trend = part(7)
    assert trend["result"]["kind"] == "trend"
    assert trend["plan"]["aggregation"] == "sum"  # the "average" in part 3 must not leak here
    assert trend["result"]["rows"][0] == ["2025-01", 50700]

    assert {r[0] for r in part(8)["result"]["rows"]} == {"Retail", "Wholesale"}
    channel = part(9)["result"]
    assert channel["columns"][0] == "sales_channel"
    assert {r[0] for r in channel["rows"]} == {"Online", "Store"}
    assert part(10)["source"] == "insights" and part(10)["status"] == "ok"
    assert part(11)["source"] == "dashboard"


def test_the_part_limit_is_enforced(dataset_id):
    prompt = "\n".join(f"{i}. Total sales" for i in range(1, 21))
    body = ask(dataset_id, prompt)
    assert len(body["parts"]) == 15
    assert "first 15" in body["note"]


def test_a_multi_part_message_is_one_history_turn(dataset_id):
    first = ask(dataset_id, PROMPT)
    turns = client.get(f"/datasets/{dataset_id}/chat/{first['session_id']}").json()["turns"]
    assert len(turns) == 1
    assert turns[0]["answer"].startswith("Answered")


# ---------- column matching ----------

def test_sales_is_not_mistaken_for_the_sales_channel_column(dataset_id):
    body = ask(dataset_id, "Total sales")
    assert body["plan"]["group_by"] == []
    assert body["result"]["scalar"] == 176100
    assert body["parts"] is None


def test_synonyms_find_the_right_column(dataset_id):
    assert ask(dataset_id, "What is the total revenue?")["result"]["scalar"] == 176100


def test_a_missing_measure_is_not_silently_replaced(dataset_id):
    body = ask(dataset_id, "What is the total cost?")
    assert body["status"] == "unsupported"
    assert "cost" in body["answer"]

    other = client.post("/upload", files={"file": ("n.csv", NO_PROFIT_CSV)}).json()["dataset_id"]
    profit = ask(other, "Total profit")
    assert profit["status"] == "unsupported"
    assert "profit" in profit["answer"]


# ---------- special requests ----------

def test_recommendations_alone(dataset_id):
    body = ask(dataset_id, "Give me 3 recommendations")
    assert body["source"] == "insights" and body["status"] == "ok"
    assert "1." in body["answer"]


def test_visualization_requests_point_to_the_dashboard(dataset_id):
    body = ask(dataset_id, "Show me appropriate visualizations")
    assert body["source"] == "dashboard"
    assert "Dashboard" in body["answer"]