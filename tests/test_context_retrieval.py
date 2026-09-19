import asyncio
import os
import sys
import types


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

import database
from context_retrieval import ApprovedContextRetriever, ground_report_draft


def _setup_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "reportgen.db"))
    database.create_tables()
    database.seed_default_data()


def test_approved_context_is_scoped_and_unapproved_context_is_excluded(
    monkeypatch,
    tmp_path,
):
    _setup_database(monkeypatch, tmp_path)
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO customers (customer_id, customer_name) VALUES (?, ?)",
        ("other_customer", "Other Customer"),
    )
    database.save_approved_context(cursor, {
        "context_id": "other-pr-context",
        "customer_id": "other_customer",
        "report_type": "daily_generation",
        "kpi": "pr_percent",
        "context_type": "reporting_guideline",
        "content": "This context must never leak into Alpha Solar retrieval.",
        "approved_by_analyst": 1,
    })
    database.save_approved_context(cursor, {
        "context_id": "alpha-unapproved-context",
        "customer_id": "alpha_solar",
        "report_type": "daily_generation",
        "kpi": "pr_percent",
        "context_type": "reporting_guideline",
        "content": "This draft context is not yet approved.",
        "approved_by_analyst": 0,
    })
    conn.commit()
    conn.close()

    results = database.get_approved_context(
        "alpha_solar",
        "daily_generation",
        ["pr_percent"],
    )
    ids = {item["context_id"] for item in results}
    assert "alpha-pr-definition-v1" in ids
    assert "alpha-reporting-guidance-v1" in ids
    assert "other-pr-context" not in ids
    assert "alpha-unapproved-context" not in ids


def test_grounded_draft_keeps_evidence_and_context_provenance(monkeypatch, tmp_path):
    _setup_database(monkeypatch, tmp_path)
    retriever = ApprovedContextRetriever()
    retriever.enabled = False
    draft = {
        "customer_id": "alpha_solar",
        "report_type": "daily_generation",
        "report_date": "2025-06-14",
        "latest_kpis": {"pr_percent": 50.88, "generation_kwh": 513700},
        "triggered_findings": [{
            "rule_name": "PR below minimum",
            "severity": "high",
            "message": "PR is below the approved minimum target.",
            "evidence": {
                "date": "2025-06-14",
                "pr_percent": 50.88,
                "thresholds": {"min_pr_percent": 65},
            },
        }],
    }

    result = asyncio.run(ground_report_draft(draft, retriever=retriever))

    assert result["provider"] == "local_fallback"
    assert result["filters"]["customer_id"] == "alpha_solar"
    assert result["filters"]["report_type"] == "daily_generation"
    assert "pr_percent" in result["filters"]["kpis"]
    assert result["evidence_packet"]["findings"][0]["evidence"]["pr_percent"] == 50.88
    assert result["retrieved_context"]
    assert all(
        item["metadata"]["customer_id"] == "alpha_solar"
        for item in result["retrieved_context"]
    )
    assert result["reviewable_narrative"]["context_ids"]
    assert result["retrieval_latency_ms"] >= 0


def test_moss_adapter_passes_governance_filters_to_runtime(monkeypatch, tmp_path):
    _setup_database(monkeypatch, tmp_path)

    class FakeQueryOptions:
        def __init__(self, top_k=None, filter=None):
            self.top_k = top_k
            self.filter = filter

    class FakeMutationOptions:
        def __init__(self, upsert=None):
            self.upsert = upsert

    monkeypatch.setitem(sys.modules, "moss", types.SimpleNamespace(
        QueryOptions=FakeQueryOptions,
        MutationOptions=FakeMutationOptions,
    ))

    class Doc:
        id = "alpha-pr-definition-v1"
        text = "Approved PR definition"
        score = 0.91
        metadata = {
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "kpi": "pr_percent",
            "approval_status": "approved",
        }

    class Result:
        docs = [Doc()]
        time_taken_ms = 2.4

    class FakeMossClient:
        def __init__(self):
            self.options = None
            self.added = []

        async def get_index(self, _name):
            return {"name": "verityflow-approved-context"}

        async def add_docs(self, _name, docs, _options):
            self.added = docs

        async def load_index(self, _name):
            return "loaded"

        async def query(self, _name, _query, options):
            self.options = options
            return Result()

    retriever = ApprovedContextRetriever()
    retriever.enabled = True
    retriever.project_id = "test-project"
    retriever.project_key = "test-key"
    retriever._client = FakeMossClient()

    result = asyncio.run(retriever.query(
        query="PR below target",
        customer_id="alpha_solar",
        report_type="daily_generation",
        kpis=["pr_percent"],
    ))

    assert result.provider == "moss"
    assert result.retrieval_latency_ms == 2.4
    assert result.documents[0]["metadata"]["approval_status"] == "approved"
    options = retriever._client.options
    assert options.filter["$and"][0]["condition"]["$eq"] == "alpha_solar"
    assert "pr_percent" in options.filter["$and"][3]["condition"]["$in"]
