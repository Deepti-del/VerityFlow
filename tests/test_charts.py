import os
import sys

import pandas as pd


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

sys.path.insert(0, BACKEND_DIR)

from charts import build_chart_specs, build_report_component


def _daily_df():
    return pd.DataFrame([
        {
            "date": "2025-06-13",
            "generation_kwh": 494600,
            "gti_kwh_m2": 5.83,
            "pr_percent": 76.17,
            "total_loss_kwh": 154000,
            "outage_loss_kwh": 10000,
            "environmental_loss_kwh": 20000,
            "clipping_loss_kwh": 5000,
            "data_availability_percent": 99.2,
        },
        {
            "date": "2025-06-14",
            "generation_kwh": 513698,
            "gti_kwh_m2": 7.49,
            "pr_percent": 50.88,
            "total_loss_kwh": 377000,
            "outage_loss_kwh": 86000,
            "environmental_loss_kwh": 30000,
            "clipping_loss_kwh": 10000,
            "data_availability_percent": 98.7,
        },
    ])


def test_build_chart_specs_from_answer_plan_components():
    answer_plan = {
        "requested_components": [
            "kpi_cards",
            "generation_vs_gti_chart",
            "pr_trend_chart",
        ]
    }

    result = build_chart_specs(_daily_df(), answer_plan=answer_plan)

    assert result["status"] == "ready"
    assert [chart["component_id"] for chart in result["chart_specs"]] == [
        "kpi_cards",
        "generation_vs_gti_chart",
        "pr_trend_chart",
    ]
    assert result["chart_specs"][1]["series"][0]["metric"] == "generation_kwh"
    assert result["chart_specs"][1]["series"][1]["metric"] == "gti_kwh_m2"


def test_build_chart_specs_skips_missing_chart_columns():
    result = build_chart_specs(
        pd.DataFrame([{"date": "2025-06-14", "pr_percent": 50.88}]),
        requested_components=["generation_vs_gti_chart", "pr_trend_chart"],
    )

    assert result["status"] == "ready"
    assert [chart["component_id"] for chart in result["chart_specs"]] == [
        "pr_trend_chart",
    ]
    assert result["skipped_charts"][0]["component_id"] == "generation_vs_gti_chart"
    assert result["skipped_charts"][0]["missing_columns"] == [
        "generation_kwh",
        "gti_kwh_m2",
    ]


def test_loss_breakdown_uses_available_loss_columns():
    result = build_chart_specs(
        _daily_df().drop(columns=["outage_loss_kwh"]),
        requested_components=["loss_breakdown_chart"],
    )

    chart = result["chart_specs"][0]

    assert chart["component_id"] == "loss_breakdown_chart"
    assert [series["metric"] for series in chart["series"]] == [
        "environmental_loss_kwh",
        "clipping_loss_kwh",
        "total_loss_kwh",
    ]


def test_report_component_applies_metric_specific_daily_aggregation():
    source = pd.DataFrame([
        {
            "timestamp": "2025-06-14 10:00:00",
            "generation_kwh": 100,
            "gti_wm2": 600,
            "pr_percent": 70,
            "cuf_percent": 18,
        },
        {
            "timestamp": "2025-06-14 10:05:00",
            "generation_kwh": 120,
            "gti_wm2": 800,
            "pr_percent": 80,
            "cuf_percent": 22,
        },
    ])

    component = build_report_component(
        source,
        component_id="daily_aggregation",
        title="Daily aggregation",
        metrics=[
            "generation_kwh",
            "gti_wm2",
            "pr_percent",
            "cuf_percent",
        ],
        chart_type="table",
        time_grain="daily",
    )

    row = component["rows"][0]
    assert row["generation_kwh"] == 220
    assert row["gti_wm2"] == 700
    assert row["pr_percent"] == 75
    assert row["cuf_percent"] == 20
    assert component["aggregations"] == {
        "generation_kwh": "sum",
        "gti_wm2": "average",
        "pr_percent": "average",
        "cuf_percent": "average",
    }


def test_heatmap_requires_equipment_breakdown():
    try:
        build_report_component(
            _daily_df(),
            component_id="invalid_heatmap",
            title="Invalid heatmap",
            metrics=["pr_percent"],
            chart_type="heatmap",
            breakdown="site_total",
        )
    except ValueError as exc:
        assert "inverter" in str(exc)
    else:
        raise AssertionError("Site-total heatmap should have been rejected.")


def test_intraday_request_reports_actual_available_date_range():
    source = pd.DataFrame([
        {
            "timestamp": "2025-06-14 10:00:00",
            "inv_power_kw": 100,
            "gti_wm2": 600,
        },
        {
            "timestamp": "2025-06-14 11:00:00",
            "inv_power_kw": 120,
            "gti_wm2": 800,
        },
    ])

    try:
        build_report_component(
            pd.DataFrame(),
            component_id="invalid_intraday_date",
            title="Inverter Power vs GTI",
            metrics=["inv_power_kw", "gti_wm2"],
            chart_type="dual_axis_line",
            start_date="2025-06-01",
            end_date="2025-06-01",
            time_grain="hourly",
            supplementary_data={"daily_timeseries": source},
        )
    except ValueError as exc:
        assert "2025-06-14 to 2025-06-14" in str(exc)
    else:
        raise AssertionError("Out-of-range intraday data should be rejected.")


def test_daily_values_cannot_be_presented_as_hourly_data():
    try:
        build_report_component(
            _daily_df(),
            component_id="invalid_hourly_pr",
            title="Hourly PR",
            metrics=["pr_percent"],
            chart_type="line",
            time_grain="hourly",
        )
    except ValueError as exc:
        assert "Daily KPI data" in str(exc)
        assert "cannot be converted into hourly or 15-minute values" in str(exc)
    else:
        raise AssertionError("Daily KPI data should not become an hourly chart.")


def test_single_day_daily_dual_axis_requires_more_than_one_observation():
    source = pd.DataFrame([
        {
            "timestamp": "2025-06-14 10:00:00",
            "inv_power_kw": 100,
            "gti_wm2": 600,
        },
        {
            "timestamp": "2025-06-14 11:00:00",
            "inv_power_kw": 120,
            "gti_wm2": 800,
        },
    ])

    try:
        build_report_component(
            pd.DataFrame(),
            component_id="single_day_daily_dual_axis",
            title="Inverter Power vs GTI",
            metrics=["inv_power_kw", "gti_wm2"],
            chart_type="dual_axis_line",
            start_date="2025-06-14",
            end_date="2025-06-14",
            time_grain="daily",
            supplementary_data={"daily_timeseries": source},
        )
    except ValueError as exc:
        assert "produce only one observation" in str(exc)
        assert "Choose Source interval" in str(exc)
    else:
        raise AssertionError("A one-point dual-axis line should be rejected.")


def test_heatmap_requires_one_metric():
    inverter = pd.DataFrame([
        {
            "date": "2025-06-14",
            "inverter_id": "INV-01",
            "pr_percent": 75,
            "generation_kwh": 100,
        },
    ])
    try:
        build_report_component(
            _daily_df(),
            component_id="invalid_multi_metric_heatmap",
            title="Invalid Heatmap",
            metrics=["pr_percent", "generation_kwh"],
            chart_type="heatmap",
            breakdown="inverter",
            supplementary_data={"inverter_performance": inverter},
        )
    except ValueError as exc:
        assert "one KPI at a time" in str(exc)
        assert "Select a single metric" in str(exc)
    else:
        raise AssertionError("A multi-metric heatmap should be rejected.")


def test_loss_type_breakdown_uses_loss_event_source():
    loss_events = pd.DataFrame([
        {
            "date": "2025-06-14",
            "loss_type": "Outage",
            "estimated_loss_kwh": 120,
        },
        {
            "date": "2025-06-14",
            "loss_type": "Clipping",
            "estimated_loss_kwh": 30,
        },
    ])
    component = build_report_component(
        _daily_df(),
        component_id="loss_event_table",
        title="Loss Events",
        metrics=["estimated_loss_kwh"],
        chart_type="table",
        breakdown="loss_type",
        start_date="2025-06-14",
        end_date="2025-06-14",
        supplementary_data={"loss_events": loss_events},
    )

    assert component["breakdown"] == "loss_type"
    assert component["columns"] == ["_period", "loss_type", "estimated_loss_kwh"]
    assert {row["loss_type"] for row in component["rows"]} == {
        "Clipping",
        "Outage",
    }


def test_component_evidence_compares_pr_with_previous_day():
    component = build_report_component(
        _daily_df(),
        component_id="daily_pr",
        title="Daily PR",
        metrics=["pr_percent"],
        chart_type="line",
        start_date="2025-06-14",
        end_date="2025-06-14",
        time_grain="daily",
    )

    evidence = component["evidence_summary"]
    assert evidence["metrics"]["pr_percent"]["previous_value"] == 76.17
    assert evidence["metrics"]["pr_percent"]["change_vs_previous_percent"] < 0
    assert "versus the prior available observation" in evidence["summary"]


def test_inverter_heatmap_evidence_identifies_lowest_inverter():
    inverter = pd.DataFrame([
        {"date": "2025-06-14", "inverter_id": "INV-01", "pr_percent": 70},
        {"date": "2025-06-14", "inverter_id": "INV-02", "pr_percent": 55},
    ])
    component = build_report_component(
        _daily_df(),
        component_id="inverter_pr",
        title="Inverter PR",
        metrics=["pr_percent"],
        chart_type="heatmap",
        breakdown="inverter",
        start_date="2025-06-14",
        end_date="2025-06-14",
        supplementary_data={"inverter_performance": inverter},
    )

    metric_evidence = component["evidence_summary"]["metrics"]["pr_percent"]
    assert metric_evidence["lowest_equipment"] == "INV-02"
    assert metric_evidence["fleet_average"] == 62.5
