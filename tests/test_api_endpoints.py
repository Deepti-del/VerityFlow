import os
import sys

from fastapi.testclient import TestClient


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
DATA_PATH = os.path.join(
    ROOT_DIR,
    "data",
    "Alpha_Solar_Dummy_Dataset.xlsx",
)

sys.path.insert(0, BACKEND_DIR)

import database
import storage
from main import app
from mapper import confirm_alpha_solar_daily_kpi_mappings


def _setup_api(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "reportgen.db"))
    monkeypatch.setattr(storage, "UPLOAD_DIR", str(tmp_path / "uploads"))
    database.create_tables()
    database.seed_default_data()
    confirm_alpha_solar_daily_kpi_mappings()
    return TestClient(app)


def _upload_dummy_workbook(client: TestClient) -> str:
    with open(DATA_PATH, "rb") as handle:
        response = client.post(
            "/upload",
            files={
                "file": (
                    "Alpha_Solar_Dummy_Dataset.xlsx",
                    handle,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "Alpha_Solar_Dummy_Dataset.xlsx"
    assert body["file_id"]
    return body["file_id"]


def test_upload_validate_calculate_and_profile_endpoints(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)
    file_id = _upload_dummy_workbook(client)

    validate_response = client.post(
        "/validate",
        json={
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "report_date": "2025-06-14",
            "file_id": file_id,
        },
    )
    assert validate_response.status_code == 200
    validate_body = validate_response.json()
    assert validate_body["valid"] is True
    assert (
        validate_body["summary"]["sheets"]["daily_kpis"]["mapping"]["confirmed"]
        is True
    )

    profile_response = client.get("/profile/alpha_solar/daily_generation")
    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["customer_id"] == "alpha_solar"
    assert any(
        metric["output_column"] == "specific_yield_kwh_per_kwp"
        for metric in profile["derivable"]
    )
    assert profile["pending_approval_count"] > 0

    calculate_response = client.post(
        "/calculate",
        json={
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "report_date": "2025-06-14",
            "file_id": file_id,
        },
    )
    assert calculate_response.status_code == 200
    calculation = calculate_response.json()
    assert calculation["customer_id"] == "alpha_solar"
    assert calculation["report_date"] == "2025-06-14"
    assert calculation["kpis"]["pr_percent"] == 50.88
    assert calculation["draft"]["status"] == "needs_analyst_input"
    assert any(
        item["type"] == "needs_formula_approval"
        for item in calculation["pending_approval"]
    )


def test_customers_endpoint(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    response = client.get("/customers")

    assert response.status_code == 200
    customers = response.json()["customers"]
    assert customers[0]["customer_id"] == "alpha_solar"
    assert customers[0]["status"] == "pending_first_approval"


def test_approve_formula_endpoint(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    response = client.post(
        "/approve/formula",
        json={
            "metric_name": "Specific Yield",
            "scope": "customer_report_type",
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "output_column": "specific_yield_kwh_per_kwp",
            "input_columns": ["generation_kwh", "dc_capacity_kwp"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["action"] == "approved_suggested_formula"
    assert body["output_column"] == "specific_yield_kwh_per_kwp"


def test_approve_insight_rule_endpoint(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    response = client.post(
        "/approve/insight-rule",
        json={
            "rule_name": "PR below minimum API test",
            "condition": "pr_percent < min_pr_percent",
            "input_columns": ["pr_percent"],
            "thresholds": {"min_pr_percent": 65},
            "severity": "high",
            "finding_template": "PR is below target.",
            "suggestion_template": "Review PR trend and generation vs GTI.",
            "scope": "customer_report_type",
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
        },
    )

    assert response.status_code == 200
    rules = response.json()["rules"]
    saved_rule = [
        rule for rule in rules
        if rule["rule_name"] == "PR below minimum API test"
    ][0]
    assert saved_rule["approved_by_analyst"] is True
    assert saved_rule["thresholds"] == {"min_pr_percent": 65}


def test_approve_mappings_endpoint(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    response = client.post(
        "/approve/mappings",
        json={
            "customer_id": "alpha_solar",
            "mappings": [
                {
                    "system_column": "generation_kwh",
                    "customer_column": "generation_kwh",
                    "data_type": "numeric",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["confirmed_count"] == 1


def test_get_and_reset_saved_mappings(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    response = client.get("/mappings/alpha_solar")
    assert response.status_code == 200
    body = response.json()
    generation = [
        item for item in body["mappings"]
        if item["system_column"] == "generation_kwh"
    ][0]
    assert generation["customer_column"] == "generation_kwh"
    assert generation["confirmed_by_analyst"] is True
    assert body["confirmed_count"] == 18

    reset_response = client.post(
        "/mappings/reset",
        json={
            "customer_id": "alpha_solar",
            "system_columns": ["generation_kwh"],
        },
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["reset_count"] == 1

    refreshed = client.get("/mappings/alpha_solar").json()
    generation = [
        item for item in refreshed["mappings"]
        if item["system_column"] == "generation_kwh"
    ][0]
    assert generation["confirmed_by_analyst"] is False


def test_reset_mappings_requires_selection(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)
    response = client.post(
        "/mappings/reset",
        json={"customer_id": "alpha_solar", "system_columns": []},
    )
    assert response.status_code == 400
    assert "Select at least one mapping" in response.json()["detail"]


def test_mapping_update_rejects_blank_columns(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)
    response = client.post(
        "/approve/mappings",
        json={
            "customer_id": "alpha_solar",
            "mappings": [{
                "system_column": "generation_kwh",
                "customer_column": "",
                "data_type": "numeric",
            }],
        },
    )
    assert response.status_code == 422


def test_formula_retrieval_validation_and_edit(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    response = client.get("/formulas/alpha_solar/daily_generation")
    assert response.status_code == 200
    body = response.json()
    specific_yield = [
        item for item in body["formulas"]
        if item["output_column"] == "specific_yield_kwh_per_kwp"
    ][0]
    assert specific_yield["formula"] == "generation_kwh / dc_capacity_kwp"
    assert specific_yield["approved_by_analyst"] is False
    assert "generation_kwh" in body["available_columns"]

    validation = client.post(
        "/formulas/validate",
        json={
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "metric_name": "Specific Yield",
            "formula": "generation_kwh / dc_capacity_kwp",
            "input_columns": ["generation_kwh", "dc_capacity_kwp"],
        },
    )
    assert validation.status_code == 200
    assert validation.json()["valid"] is True

    edit = client.post(
        "/approve/formula",
        json={
            "metric_name": "Specific Yield",
            "formula": "generation_kwh / dc_capacity_kwp * 1.0",
            "unit": "kWh/kWp",
            "good_range": "3.5-5.0",
            "poor_threshold": "<3.0",
            "scope": "customer_report_type",
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "output_column": "specific_yield_kwh_per_kwp",
            "input_columns": ["generation_kwh", "dc_capacity_kwp"],
        },
    )
    assert edit.status_code == 200
    assert edit.json()["action"] == "saved_custom_formula"

    refreshed = client.get("/formulas/alpha_solar/daily_generation").json()
    specific_yield = [
        item for item in refreshed["formulas"]
        if item["output_column"] == "specific_yield_kwh_per_kwp"
    ][0]
    assert specific_yield["approved_by_analyst"] is True
    assert specific_yield["scope"] == "customer_report_type"
    assert specific_yield["formula"] == "generation_kwh / dc_capacity_kwp * 1.0"


def test_formula_validation_rejects_undeclared_column(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)
    response = client.post(
        "/formulas/validate",
        json={
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "metric_name": "Specific Yield",
            "formula": "generation_kwh / missing_capacity",
            "input_columns": ["generation_kwh", "dc_capacity_kwp"],
        },
    )
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["reason"] == "formula_references_undeclared_columns"


def test_approve_question_endpoint(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    response = client.post(
        "/approve/question",
        json={
            "question_text": "What caused the PR change?",
            "required_metrics": ["pr_percent"],
            "preferred_components": ["pr_trend_chart"],
            "scope": "customer_report_type",
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
        },
    )

    assert response.status_code == 200
    saved = [
        item for item in response.json()["questions"]
        if item["question_text"] == "What caused the PR change?"
    ][0]
    assert saved["approved_by_analyst"] is True
    assert saved["preferred_components"] == ["pr_trend_chart"]


def test_upload_rejects_unsupported_file_type(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    response = client.post(
        "/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_validate_returns_404_for_unknown_file_id(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    response = client.post(
        "/validate",
        json={
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "report_date": "2025-06-14",
            "file_id": "missing-file-id",
        },
    )

    assert response.status_code == 404
