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
    assert calculation["draft"]["available_breakdowns"] == [
        "site_total",
        "inverter",
        "loss_type",
    ]
    timeseries_source = next(
        source
        for source in calculation["draft"]["chart_capabilities"]["sources"]
        if source["source"] == "daily_timeseries"
    )
    assert timeseries_source["start_date"] == "2025-06-14"
    assert timeseries_source["end_date"] == "2025-06-14"
    assert timeseries_source["native_grain"] == "intraday"
    grounding = calculation["draft"]["grounding"]
    assert grounding["provider"] == "local_fallback"
    assert grounding["filters"]["customer_id"] == "alpha_solar"
    assert grounding["retrieved_context"]
    assert grounding["reviewable_narrative"]["status"] == "awaiting_analyst_approval"
    power_chart = next(
        component
        for component in calculation["draft"]["chart_specs"]
        if component["component_id"] == "inv_pow_gti_chart"
    )
    assert "relationship" in power_chart["evidence_summary"]
    assert "approved observations" in power_chart["evidence_summary"]["summary"]
    assert any(
        item["type"] == "needs_formula_approval"
        for item in calculation["pending_approval"]
    )


def test_bigquery_demo_source_uses_existing_validation_pipeline(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    response = client.post(
        "/sources/bigquery/connect",
        json={
            "project_id": "demo",
            "dataset_id": "reportgen_demo",
            "plant_id": "alpha_plant",
            "start_date": "2025-06-14",
            "end_date": "2025-06-14",
            "use_demo_data": True,
        },
    )

    assert response.status_code == 200
    source = response.json()
    assert source["source_type"] == "bigquery"
    assert source["mode"] == "demo"
    assert source["file_id"]
    assert source["views"]["daily_kpis"] == "reportgen_daily_kpis"

    validate_response = client.post(
        "/validate",
        json={
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "report_date": "2025-06-14",
            "file_id": source["file_id"],
        },
    )
    assert validate_response.status_code == 200
    assert validate_response.json()["valid"] is True

    calculate_response = client.post(
        "/calculate",
        json={
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "report_date": "2025-06-14",
            "file_id": source["file_id"],
        },
    )
    assert calculate_response.status_code == 200
    calculation = calculate_response.json()
    assert calculation["kpis"]["generation_kwh"] == 513700.0
    assert calculation["draft"]["chart_specs"]


def test_customers_endpoint(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    response = client.get("/customers")

    assert response.status_code == 200
    customers = response.json()["customers"]
    assert customers[0]["customer_id"] == "alpha_solar"
    assert customers[0]["status"] == "pending_first_approval"
    assert customers[0]["site_count"] == 1
    assert customers[0]["configuration_count"] == 1


def test_create_customer_and_load_context(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    response = client.post(
        "/customers",
        json={
            "customer_name": "Beta Renewable Energy",
            "parent_company": "Beta Holdings",
            "customer_reference": "BETA-01",
            "site_name": "Beta Solar Park",
            "location": "Rajasthan, India",
            "timezone": "Asia/Kolkata",
            "dc_capacity_kwp": 50000,
            "ac_capacity_kw": 40000,
            "report_type": "daily_generation",
            "reporting_period": "daily",
            "configuration_name": "Daily Generation Report",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["customer_id"] == "beta_01"

    context_response = client.get(
        f"/customers/{created['customer_id']}/context"
    )
    assert context_response.status_code == 200
    context = context_response.json()
    assert context["customer"]["parent_company"] == "Beta Holdings"
    assert context["sites"][0]["site_name"] == "Beta Solar Park"
    assert context["report_configurations"][0]["reporting_period"] == "daily"

    mappings_response = client.get(f"/mappings/{created['customer_id']}")
    assert mappings_response.status_code == 200
    mappings = mappings_response.json()
    assert mappings["mapping_count"] > 0
    assert mappings["confirmed_count"] == 0
    assert any(
        item["system_column"] == "generation_kwh"
        for item in mappings["mappings"]
    )


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


def test_mapping_suggestions_remain_after_saving_one_new_customer_mapping(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    created = client.post(
        "/customers",
        json={
            "customer_name": "SuryaVista Solar",
            "site_name": "SuryaVista Plant",
            "timezone": "Asia/Kolkata",
            "report_type": "daily_generation",
            "reporting_period": "daily",
            "configuration_name": "Daily Generation Report",
        },
    ).json()
    customer_id = created["customer_id"]

    reset_response = client.post(
        "/mappings/reset",
        json={
            "customer_id": customer_id,
            "system_columns": [
                "generation_kwh",
                "gti_kwh_m2",
                "pr_percent",
                "dc_capacity_kwp",
            ],
        },
    )
    assert reset_response.status_code == 200

    save_response = client.post(
        "/approve/mappings",
        json={
            "customer_id": customer_id,
            "mappings": [{
                "system_column": "generation_kwh",
                "customer_column": "generation_kwh",
                "data_type": "numeric",
            }],
        },
    )
    assert save_response.status_code == 200

    response = client.get(f"/mappings/{customer_id}")
    assert response.status_code == 200
    body = response.json()
    by_system_column = {
        item["system_column"]: item
        for item in body["mappings"]
    }
    assert by_system_column["generation_kwh"]["confirmed_by_analyst"] is True
    assert by_system_column["gti_kwh_m2"]["confirmed_by_analyst"] is False
    assert by_system_column["pr_percent"]["confirmed_by_analyst"] is False
    assert body["mapping_count"] >= 4
    assert body["confirmed_count"] == 1


def test_profile_pending_count_ignores_required_source_columns(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)

    created = client.post(
        "/customers",
        json={
            "customer_name": "Gamma Solar",
            "site_name": "Gamma Plant",
            "timezone": "Asia/Kolkata",
            "report_type": "daily_generation",
            "reporting_period": "daily",
            "configuration_name": "Daily Generation Report",
        },
    ).json()
    customer_id = created["customer_id"]

    mappings = client.get(f"/mappings/{customer_id}").json()["mappings"]
    approve_mappings = client.post(
        "/approve/mappings",
        json={
            "customer_id": customer_id,
            "mappings": [
                {
                    "system_column": item["system_column"],
                    "customer_column": item["customer_column"],
                    "data_type": item["data_type"],
                }
                for item in mappings
            ],
        },
    )
    assert approve_mappings.status_code == 200

    for output_column, metric_name in [
        ("cuf_percent", "CUF"),
        ("expected_generation_kwh", "Expected Generation"),
        ("pr_percent", "PR"),
        ("specific_yield_kwh_per_kwp", "Specific Yield"),
        ("total_loss_kwh", "Total Losses"),
    ]:
        response = client.post(
            "/approve/formula",
            json={
                "customer_id": customer_id,
                "report_type": "daily_generation",
                "metric_name": metric_name,
                "output_column": output_column,
                "scope": "customer_report_type",
            },
        )
        assert response.status_code == 200

    profile_before_final_approval = client.get(
        f"/profile/{customer_id}/daily_generation"
    ).json()
    for question in profile_before_final_approval["customer_questions"]:
        response = client.post(
            "/approve/question",
            json={
                "question_text": question["question_text"],
                "answer_purpose": question.get("answer_purpose"),
                "required_metrics": question.get("required_metrics", []),
                "preferred_components": question.get("preferred_components", []),
                "scope": "customer_report_type",
                "customer_id": customer_id,
                "report_type": "daily_generation",
            },
        )
        assert response.status_code == 200

    for rule in profile_before_final_approval["insight_rules"]:
        response = client.post(
            "/approve/insight-rule",
            json={
                "rule_name": rule["rule_name"],
                "condition": rule["condition"],
                "input_columns": rule.get("input_columns", []),
                "thresholds": rule.get("thresholds", {}),
                "severity": rule.get("severity", "medium"),
                "finding_template": rule.get("finding_template"),
                "suggestion_template": rule.get("suggestion_template"),
                "scope": "customer_report_type",
                "customer_id": customer_id,
                "report_type": "daily_generation",
            },
        )
        assert response.status_code == 200

    profile = client.get(f"/profile/{customer_id}/daily_generation").json()
    assert profile["pending_approval_count"] == 0
    assert any(
        metric["output_column"] == "generation_kwh"
        and metric["approved_by_analyst"] is False
        for metric in profile["required_source"]
    )


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


def test_generate_report_component_from_approved_backend_data(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)
    file_id = _upload_dummy_workbook(client)

    response = client.post(
        "/report-components/generate",
        json={
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "report_date": "2025-06-14",
            "file_id": file_id,
            "component_id": "analyst_generation_gti",
            "title": "Weekly Generation and GTI",
            "metrics": ["generation_kwh", "gti_kwh_m2"],
            "start_date": "2025-06-01",
            "end_date": "2025-06-07",
            "breakdown": "site_total",
            "chart_type": "bar_line",
        },
    )

    assert response.status_code == 200
    component = response.json()["component"]
    assert component["component_id"] == "analyst_generation_gti"
    assert component["type"] == "bar_line"
    assert [series["metric"] for series in component["series"]] == [
        "generation_kwh",
        "gti_kwh_m2",
    ]
    assert len(component["x"]) == 7
    assert component["aggregations"] == {
        "generation_kwh": "sum",
        "gti_kwh_m2": "sum",
    }
    assert component["time_grain"] == "daily"


def test_generate_real_inverter_heatmap(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)
    file_id = _upload_dummy_workbook(client)

    response = client.post(
        "/report-components/generate",
        json={
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "report_date": "2025-06-14",
            "file_id": file_id,
            "component_id": "inverter_pr_heatmap",
            "title": "Inverter PR Heatmap",
            "metrics": ["pr_percent"],
            "start_date": "2025-06-14",
            "end_date": "2025-06-14",
            "breakdown": "inverter",
            "chart_type": "heatmap",
        },
    )

    assert response.status_code == 200
    component = response.json()["component"]
    assert component["type"] == "heatmap"
    assert component["metric"] == "pr_percent"
    assert component["row_labels"]
    assert component["column_labels"] == ["2025-06-14"]
    assert len(component["values"]) == len(component["row_labels"])


def test_each_basic_chart_type_uses_requested_shape(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)
    file_id = _upload_dummy_workbook(client)

    for chart_type in ("line", "bar", "table"):
        response = client.post(
            "/report-components/generate",
            json={
                "customer_id": "alpha_solar",
                "report_type": "daily_generation",
                "report_date": "2025-06-14",
                "file_id": file_id,
                "component_id": f"pr_{chart_type}",
                "title": f"PR {chart_type}",
                "metrics": ["pr_percent"],
                "start_date": "2025-06-01",
                "end_date": "2025-06-14",
                "breakdown": "site_total",
                "chart_type": chart_type,
                "time_grain": "daily",
            },
        )
        assert response.status_code == 200
        assert response.json()["component"]["type"] == chart_type


def test_intraday_chart_respects_date_and_hourly_grain(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)
    file_id = _upload_dummy_workbook(client)
    payload = {
        "customer_id": "alpha_solar",
        "report_type": "daily_generation",
        "report_date": "2025-06-14",
        "file_id": file_id,
        "component_id": "power_gti_hourly",
        "title": "Inverter Power vs GTI",
        "metrics": ["inv_power_kw", "gti_wm2"],
        "start_date": "2025-06-14",
        "end_date": "2025-06-14",
        "breakdown": "site_total",
        "chart_type": "dual_axis_line",
        "time_grain": "hourly",
    }

    response = client.post("/report-components/generate", json=payload)
    assert response.status_code == 200
    component = response.json()["component"]
    assert component["type"] == "dual_axis_line"
    assert component["data_coverage"]["start_date"] == "2025-06-14"
    assert component["data_coverage"]["end_date"] == "2025-06-14"
    assert all(value.startswith("2025-06-14") for value in component["x"])

    invalid = client.post(
        "/report-components/generate",
        json={**payload, "start_date": "2025-06-01", "end_date": "2025-06-01"},
    )
    assert invalid.status_code == 400
    assert "Available dates are 2025-06-14 to 2025-06-14" in invalid.json()["detail"]


def test_waterfall_uses_selected_period_totals(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)
    file_id = _upload_dummy_workbook(client)
    response = client.post(
        "/report-components/generate",
        json={
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "report_date": "2025-06-14",
            "file_id": file_id,
            "component_id": "weekly_waterfall",
            "title": "Weekly Generation vs Losses",
            "metrics": [
                "expected_generation_kwh",
                "outage_loss_kwh",
                "environmental_loss_kwh",
                "clipping_loss_kwh",
                "generation_kwh",
            ],
            "start_date": "2025-06-01",
            "end_date": "2025-06-07",
            "breakdown": "site_total",
            "chart_type": "waterfall",
            "time_grain": "daily",
        },
    )
    assert response.status_code == 200
    component = response.json()["component"]
    expected = next(
        step for step in component["steps"]
        if step["metric"] == "expected_generation_kwh"
    )
    assert expected["value"] > 1_000_000


def test_waterfall_auto_includes_required_metrics(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)
    file_id = _upload_dummy_workbook(client)
    response = client.post(
        "/report-components/generate",
        json={
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "report_date": "2025-06-14",
            "file_id": file_id,
            "component_id": "loss_waterfall",
            "title": "Loss Breakdown",
            "metrics": [
                "outage_loss_kwh",
                "environmental_loss_kwh",
                "clipping_loss_kwh",
                "total_loss_kwh",
            ],
            "start_date": "2025-06-14",
            "end_date": "2025-06-14",
            "breakdown": "site_total",
            "chart_type": "waterfall",
            "time_grain": "daily",
        },
    )
    assert response.status_code == 200
    component = response.json()["component"]
    assert component["type"] == "waterfall"
    assert "expected_generation_kwh" in component["metrics"]
    assert "generation_kwh" in component["metrics"]


def test_stacked_bar_returns_stack_metadata(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)
    file_id = _upload_dummy_workbook(client)
    response = client.post(
        "/report-components/generate",
        json={
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "report_date": "2025-06-14",
            "file_id": file_id,
            "component_id": "stacked_losses",
            "title": "Loss Categories",
            "metrics": [
                "outage_loss_kwh",
                "environmental_loss_kwh",
                "clipping_loss_kwh",
            ],
            "start_date": "2025-06-01",
            "end_date": "2025-06-14",
            "breakdown": "site_total",
            "chart_type": "stacked_bar",
            "time_grain": "daily",
        },
    )
    assert response.status_code == 200
    component = response.json()["component"]
    assert component["type"] == "stacked_bar"
    assert all(series["stack"] == "total" for series in component["series"])


def test_layout_versioning_and_immutable_report_snapshot(monkeypatch, tmp_path):
    client = _setup_api(monkeypatch, tmp_path)
    config_id = "alpha_solar_alpha_plant_daily_generation"
    payload = {
        "config_id": config_id,
        "customer_id": "alpha_solar",
        "report_type": "daily_generation",
        "theme": "executive",
        "summary_position": "top",
        "layout": {
            "components": [{
                "componentId": "pr_trend_chart",
                "included": True,
                "metrics": ["pr_percent"],
                "textPosition": "beside",
            }]
        },
        "created_by": "API test analyst",
    }

    saved_response = client.put(f"/report-layouts/{config_id}", json=payload)
    assert saved_response.status_code == 200
    saved = saved_response.json()["layout"]
    assert saved["version"] == 1
    assert saved["status"] == "draft"
    assert saved["layout_json"]["components"][0]["textPosition"] == "beside"

    approved_response = client.post(
        f"/report-layouts/{saved['layout_id']}/approve",
        json={
            "layout_id": saved["layout_id"],
            "approved_by": "API test analyst",
        },
    )
    assert approved_response.status_code == 200
    approved = approved_response.json()["layout"]
    assert approved["status"] == "approved"

    locked_response = client.put(f"/report-layouts/{config_id}", json=payload)
    assert locked_response.status_code == 409

    revision_response = client.put(
        f"/report-layouts/{config_id}",
        json={**payload, "theme": "operations", "create_revision": True},
    )
    assert revision_response.status_code == 200
    revision = revision_response.json()["layout"]
    assert revision["version"] == 2
    assert revision["status"] == "draft"

    approved_revision = client.post(
        f"/report-layouts/{revision['layout_id']}/approve",
        json={
            "layout_id": revision["layout_id"],
            "approved_by": "API test analyst",
        },
    ).json()["layout"]
    assert approved_revision["status"] == "approved"

    snapshot_response = client.post(
        "/report-snapshots/approve",
        json={
            "config_id": config_id,
            "customer_id": "alpha_solar",
            "report_type": "daily_generation",
            "report_date": "2025-06-14",
            "layout_id": approved_revision["layout_id"],
            "approved_by": "API test analyst",
            "report": {
                "status": "approved",
                "pending_approvals": [],
                "executive_summary": "Approved evidence-backed summary.",
                "components": [],
            },
        },
    )
    assert snapshot_response.status_code == 201
    snapshot = snapshot_response.json()["snapshot"]
    assert snapshot["layout_version"] == 2
    assert snapshot["revision"] == 1
    assert snapshot["snapshot_json"]["executive_summary"] == (
        "Approved evidence-backed summary."
    )
