import json
import math
import re
import uuid
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from answer_planner import build_answer_plan
from calculator import calculate_daily_kpis_from_excel
from charts import (
    build_chart_capabilities,
    build_chart_specs,
    build_report_component,
)
from database import (
    approve_customer_question,
    approve_insight_rule,
    approve_report_layout,
    create_report_snapshot,
    get_calculation_profile,
    get_connection,
    get_customer_questions,
    get_insight_rules,
    get_report_layout,
    save_report_layout_draft,
)
from formula_service import add_custom_formula, approve_suggested_formula
from formula_utils import validate_formula
from insights import generate_insights
from mapper import (
    confirm_mappings,
    get_saved_mappings,
    initialize_standard_solar_mappings,
    reset_mappings,
)
from models import (
    ApproveFormulaRequest,
    ApproveInsightRuleRequest,
    ApproveMappingsRequest,
    ApproveQuestionRequest,
    CalculateRequest,
    CalculationResponse,
    BigQuerySourceRequest,
    BigQuerySourceResponse,
    CreateCustomerRequest,
    ApproveReportLayoutRequest,
    ApproveReportSnapshotRequest,
    ProfileResponse,
    ReportComponentRequest,
    ResetMappingsRequest,
    SaveReportLayoutRequest,
    UploadResponse,
    ValidateRequest,
    ValidationResponse,
    ValidateFormulaRequest,
)
from report_draft import assemble_report_draft
from source_adapters import connect_bigquery_source
from storage import get_upload_path, save_upload
from validator import validate_workbook


app = FastAPI(title="ReportGen API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _http_error(status_code: int, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


def _sheet_if_exists(workbook: dict[str, pd.DataFrame], sheet_name: str) -> pd.DataFrame | None:
    return workbook.get(sheet_name)


def _filter_by_report_date(
    df: pd.DataFrame | None,
    report_date: str | None,
    date_column: str = "date",
) -> pd.DataFrame | None:
    if df is None or not report_date or date_column not in df.columns:
        return df
    dates = pd.to_datetime(df[date_column], errors="coerce").dt.strftime("%Y-%m-%d")
    return df[dates == report_date].copy()


def _supplementary_data(path: str, report_date: str | None) -> dict[str, pd.DataFrame]:
    try:
        workbook = pd.read_excel(path, sheet_name=None)
    except Exception:
        return {}

    data = {}
    daily_timeseries = _sheet_if_exists(workbook, "daily_timeseries")
    if daily_timeseries is not None:
        if report_date and "timestamp" in daily_timeseries.columns:
            timestamps = pd.to_datetime(
                daily_timeseries["timestamp"],
                errors="coerce",
            ).dt.strftime("%Y-%m-%d")
            daily_timeseries = daily_timeseries[timestamps == report_date].copy()
        data["daily_timeseries"] = daily_timeseries

    inverter_performance = _filter_by_report_date(
        _sheet_if_exists(workbook, "inverter_performance"),
        report_date,
    )
    if inverter_performance is not None:
        data["inverter_performance"] = inverter_performance

    block_performance = _filter_by_report_date(
        _sheet_if_exists(workbook, "block_performance"),
        report_date,
    )
    if block_performance is not None:
        data["block_performance"] = block_performance

    loss_events = _filter_by_report_date(
        _sheet_if_exists(workbook, "loss_events"),
        report_date,
    )
    if loss_events is not None:
        data["loss_events"] = loss_events

    return data


def _available_breakdowns(
    supplementary_data: dict[str, pd.DataFrame],
) -> list[str]:
    available = ["site_total"]
    frames = list(supplementary_data.values())
    if any("inverter_id" in frame.columns for frame in frames):
        available.append("inverter")
    if any("block_id" in frame.columns for frame in frames):
        available.append("block")
    if any("loss_type" in frame.columns for frame in frames):
        available.append("loss_type")
    return available


def _pending_profile_count(profile: dict, rules: list[dict], questions: list[dict]) -> int:
    pending = 0
    pending += sum(
        1 for metric in profile.get("derivable", [])
        if not metric.get("approved_by_analyst")
    )
    pending += sum(1 for rule in rules if not rule.get("approved_by_analyst"))
    pending += sum(1 for question in questions if not question.get("approved_by_analyst"))
    return pending


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if pd.isna(value) if not isinstance(value, (dict, list, tuple)) else False:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return _jsonable(value.item())
        except (ValueError, TypeError):
            pass
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or f"customer_{uuid.uuid4().hex[:8]}"


def _configuration(config_id: str) -> dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM report_configurations WHERE config_id = ?",
        (config_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if row is None:
        raise _http_error(404, "Report configuration not found.")
    return dict(row)


@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    try:
        file_id = save_upload(await file.read(), file.filename or "upload.xlsx")
    except ValueError as exc:
        raise _http_error(400, str(exc)) from exc

    return {
        "file_id": file_id,
        "filename": file.filename or "",
    }


@app.post("/sources/bigquery/connect", response_model=BigQuerySourceResponse)
def connect_bigquery(request: BigQuerySourceRequest):
    try:
        return connect_bigquery_source(
            project_id=request.project_id,
            dataset_id=request.dataset_id,
            table_map=request.table_map,
            plant_id=request.plant_id,
            start_date=request.start_date,
            end_date=request.end_date,
            use_demo_data=request.use_demo_data,
        )
    except RuntimeError as exc:
        raise _http_error(501, str(exc)) from exc
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc)) from exc
    except ValueError as exc:
        raise _http_error(400, str(exc)) from exc


@app.post("/validate", response_model=ValidationResponse)
def validate(request: ValidateRequest):
    try:
        path = get_upload_path(request.file_id)
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc)) from exc

    result = validate_workbook(
        path,
        customer_id=request.customer_id,
        report_type=request.report_type,
    )

    return {
        "valid": result["valid"],
        "errors": result.get("errors", []),
        "warnings": result.get("warnings", []),
        "summary": result,
    }


@app.post("/calculate", response_model=CalculationResponse)
def calculate(request: CalculateRequest):
    try:
        path = get_upload_path(request.file_id)
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc)) from exc

    validation = validate_workbook(
        path,
        customer_id=request.customer_id,
        report_type=request.report_type,
    )
    calculation = calculate_daily_kpis_from_excel(
        path,
        customer_id=request.customer_id,
        report_type=request.report_type,
    )
    insights = generate_insights(
        calculation,
        customer_id=request.customer_id,
        report_type=request.report_type,
    )
    answer_plan = build_answer_plan(
        calculation,
        customer_id=request.customer_id,
        report_type=request.report_type,
        insights_result=insights,
    )
    supplementary_data = _supplementary_data(path, request.report_date)
    full_supplementary_data = _supplementary_data(path, None)
    charts = build_chart_specs(
        calculation,
        answer_plan=answer_plan,
        supplementary_data=supplementary_data,
    )
    draft = assemble_report_draft(
        customer_id=request.customer_id,
        report_type=request.report_type,
        report_date=request.report_date,
        validation_result=validation,
        mapping_result=calculation.get("mapping"),
        calculation_result=calculation,
        insights_result=insights,
        answer_plan=answer_plan,
        chart_result=charts,
    )
    chart_capabilities = build_chart_capabilities(
        calculation,
        full_supplementary_data,
    )
    draft["chart_capabilities"] = chart_capabilities
    draft["available_breakdowns"] = chart_capabilities["breakdowns"]

    return _jsonable({
        "customer_id": request.customer_id,
        "report_date": draft.get("report_date"),
        "kpis": draft.get("latest_kpis", {}),
        "findings": draft.get("triggered_findings", []),
        "pending_approval": draft.get("pending_approvals", []),
        "chart_specs": draft.get("chart_specs", []),
        "answer_plan": answer_plan,
        "warnings": draft.get("warnings", []),
        "draft": draft,
    })


@app.post("/report-components/generate")
def generate_report_component(request: ReportComponentRequest):
    try:
        path = get_upload_path(request.file_id)
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc)) from exc

    calculation = calculate_daily_kpis_from_excel(
        path,
        customer_id=request.customer_id,
        report_type=request.report_type,
    )
    try:
        component = build_report_component(
            calculation,
            component_id=request.component_id or f"custom_{uuid.uuid4().hex[:10]}",
            title=request.title,
            metrics=request.metrics,
            chart_type=request.chart_type,
            start_date=request.start_date,
            end_date=request.end_date,
            breakdown=request.breakdown,
            aggregation=request.aggregation,
            aggregations=request.aggregations,
            time_grain=request.time_grain,
            supplementary_data=_supplementary_data(path, None),
        )
    except ValueError as exc:
        raise _http_error(400, str(exc)) from exc

    return {
        "ok": True,
        "component": _jsonable(component),
        "calculation_status": calculation.get("status"),
        "warnings": calculation.get("warnings", []),
    }


@app.get("/report-layouts/{config_id}")
def report_layout(config_id: str):
    configuration = _configuration(config_id)
    layout = get_report_layout(config_id)
    return {
        "config_id": config_id,
        "customer_id": configuration["customer_id"],
        "report_type": configuration["report_type"],
        "layout": layout,
    }


@app.put("/report-layouts/{config_id}")
def save_report_layout(config_id: str, request: SaveReportLayoutRequest):
    configuration = _configuration(config_id)
    if request.config_id != config_id:
        raise _http_error(400, "config_id must match the URL.")
    if (
        configuration["customer_id"] != request.customer_id
        or configuration["report_type"] != request.report_type
    ):
        raise _http_error(
            400,
            "The layout scope does not match the report configuration.",
        )
    try:
        layout = save_report_layout_draft(
            layout_id=f"layout_{uuid.uuid4().hex}",
            config_id=config_id,
            customer_id=request.customer_id,
            report_type=request.report_type,
            theme=request.theme,
            summary_position=request.summary_position,
            layout=request.layout,
            create_revision=request.create_revision,
            created_by=request.created_by,
        )
    except ValueError as exc:
        raise _http_error(409, str(exc)) from exc
    return {"ok": True, "layout": layout}


@app.post("/report-layouts/{layout_id}/approve")
def approve_layout(layout_id: str, request: ApproveReportLayoutRequest):
    if request.layout_id != layout_id:
        raise _http_error(400, "layout_id must match the URL.")
    try:
        layout = approve_report_layout(layout_id, request.approved_by)
    except ValueError as exc:
        raise _http_error(404, str(exc)) from exc
    return {"ok": True, "layout": layout}


@app.post("/report-snapshots/approve", status_code=201)
def approve_report_snapshot(request: ApproveReportSnapshotRequest):
    layout = get_report_layout(request.config_id, include_draft=False)
    if not layout or layout["layout_id"] != request.layout_id:
        raise _http_error(
            409,
            "Approve the selected layout version before approving the report.",
        )
    pending = (
        request.report.get("pending_approvals")
        or (request.report.get("draft") or {}).get("pending_approvals")
        or []
    )
    if pending:
        raise _http_error(
            409,
            "Resolve all pending approvals before approving the report.",
        )
    try:
        snapshot = create_report_snapshot(
            snapshot_id=f"snapshot_{uuid.uuid4().hex}",
            config_id=request.config_id,
            customer_id=request.customer_id,
            report_type=request.report_type,
            report_date=request.report_date,
            layout=layout,
            snapshot=request.report,
            approved_by=request.approved_by,
        )
    except ValueError as exc:
        raise _http_error(409, str(exc)) from exc
    return {"ok": True, "snapshot": snapshot}


@app.get("/profile/{customer_id}/{report_type}", response_model=ProfileResponse)
def profile(customer_id: str, report_type: str):
    calc_profile = get_calculation_profile(customer_id, report_type)
    insight_profile = get_insight_rules(
        customer_id,
        report_type,
        include_unapproved=True,
    )
    question_profile = get_customer_questions(
        customer_id,
        report_type,
        include_unapproved=True,
    )

    rules = insight_profile["rules"]
    questions = question_profile["questions"]

    return {
        "customer_id": customer_id,
        "report_type": report_type,
        "required_source": calc_profile["required_source"],
        "derivable": calc_profile["derivable"],
        "optional": calc_profile["optional"],
        "insight_rules": rules,
        "customer_questions": questions,
        "pending_approval_count": _pending_profile_count(
            calc_profile,
            rules,
            questions,
        ),
    }


@app.get("/customers")
def customers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            c.customer_id,
            c.customer_name,
            c.parent_company,
            c.customer_reference,
            c.status,
            COUNT(r.report_id) AS report_count,
            MAX(r.report_date) AS last_report_date,
            (SELECT COUNT(*) FROM customer_sites s
             WHERE s.customer_id = c.customer_id) AS site_count,
            (SELECT COUNT(*) FROM report_configurations rc
             WHERE rc.customer_id = c.customer_id AND rc.active = 1) AS configuration_count
        FROM customers c
        LEFT JOIN report_history r ON r.customer_id = c.customer_id
        GROUP BY c.customer_id, c.customer_name, c.parent_company,
                 c.customer_reference, c.status
        ORDER BY c.customer_name
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"customers": rows}


@app.get("/customers/{customer_id}/context")
def customer_context(customer_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
    customer = cursor.fetchone()
    if customer is None:
        conn.close()
        raise _http_error(404, "Customer not found.")

    cursor.execute("""
        SELECT * FROM customer_sites
        WHERE customer_id = ?
        ORDER BY site_name
    """, (customer_id,))
    sites = [dict(row) for row in cursor.fetchall()]
    cursor.execute("""
        SELECT
            rc.*,
            s.site_name
        FROM report_configurations rc
        JOIN customer_sites s ON s.site_id = rc.site_id
        WHERE rc.customer_id = ? AND rc.active = 1
        ORDER BY s.site_name, rc.configuration_name
    """, (customer_id,))
    configurations = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {
        "customer": dict(customer),
        "sites": sites,
        "report_configurations": configurations,
    }


@app.post("/customers", status_code=201)
def create_customer(request: CreateCustomerRequest):
    if request.report_type != "daily_generation" or request.reporting_period != "daily":
        raise _http_error(
            400,
            "The current MVP supports the Daily Generation Report only.",
        )

    conn = get_connection()
    cursor = conn.cursor()
    base_customer_id = _slug(request.customer_reference or request.customer_name)
    customer_id = base_customer_id
    cursor.execute("SELECT 1 FROM customers WHERE customer_id = ?", (customer_id,))
    if cursor.fetchone():
        customer_id = f"{base_customer_id}_{uuid.uuid4().hex[:6]}"
    site_id = f"{customer_id}_{_slug(request.site_name)}"
    config_id = f"{site_id}_{request.report_type}"

    try:
        cursor.execute("""
            INSERT INTO customers
            (customer_id, customer_name, parent_company, customer_reference, status)
            VALUES (?, ?, ?, ?, ?)
        """, (
            customer_id,
            request.customer_name.strip(),
            request.parent_company.strip() if request.parent_company else None,
            request.customer_reference.strip() if request.customer_reference else None,
            "pending_first_approval",
        ))
        cursor.execute("""
            INSERT INTO customer_sites
            (site_id, customer_id, site_name, location, timezone, dc_capacity_kwp,
             ac_capacity_kw)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            site_id,
            customer_id,
            request.site_name.strip(),
            request.location.strip() if request.location else None,
            request.timezone,
            request.dc_capacity_kwp,
            request.ac_capacity_kw,
        ))
        cursor.execute("""
            INSERT INTO report_configurations
            (config_id, customer_id, site_id, report_type, configuration_name,
             reporting_period)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            config_id,
            customer_id,
            site_id,
            request.report_type,
            request.configuration_name.strip(),
            request.reporting_period,
        ))
        conn.commit()
        initialize_standard_solar_mappings(customer_id, request.report_type)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "customer_id": customer_id,
        "site_id": site_id,
        "config_id": config_id,
        "report_type": request.report_type,
        "reporting_period": request.reporting_period,
    }


def _profile_columns(profile: dict) -> list[str]:
    columns = []
    for category in ("required_source", "derivable", "optional", "reference"):
        columns.extend(
            metric["output_column"]
            for metric in profile.get(category, [])
            if metric.get("output_column")
        )
    return list(dict.fromkeys(columns))


@app.get("/formulas/{customer_id}/{report_type}")
def formulas(customer_id: str, report_type: str):
    profile = get_calculation_profile(customer_id, report_type)
    formulas = profile.get("derivable", [])
    return {
        "customer_id": customer_id,
        "report_type": report_type,
        "formulas": formulas,
        "formula_count": len(formulas),
        "approved_count": sum(
            bool(metric.get("approved_by_analyst")) for metric in formulas
        ),
        "available_columns": _profile_columns(profile),
    }


@app.post("/formulas/validate")
def validate_formula_endpoint(request: ValidateFormulaRequest):
    profile = get_calculation_profile(request.customer_id, request.report_type)
    available_columns = request.available_columns or _profile_columns(profile)
    return validate_formula(
        request.formula,
        available_columns=available_columns,
        input_columns=request.input_columns,
        metric_name=request.metric_name,
    )


@app.post("/approve/formula")
def approve_formula_endpoint(request: ApproveFormulaRequest):
    customer_id = request.customer_id
    report_type = request.report_type
    if not customer_id or not report_type:
        raise _http_error(400, "customer_id and report_type are required.")

    if request.formula:
        if not request.output_column:
            raise _http_error(400, "output_column is required for a custom formula.")
        profile = get_calculation_profile(customer_id, report_type)
        available_columns = list(dict.fromkeys(
            _profile_columns(profile) + request.input_columns
        ))
        result = add_custom_formula(
            customer_id=customer_id,
            report_type=report_type,
            metric_name=request.metric_name,
            output_column=request.output_column,
            formula=request.formula,
            input_columns=request.input_columns,
            available_columns=available_columns,
            unit=request.unit,
            good_range=request.good_range,
            poor_threshold=request.poor_threshold,
            scope=request.scope,
        )
    else:
        result = approve_suggested_formula(
            customer_id=customer_id,
            report_type=report_type,
            output_column=request.output_column,
            metric_name=request.metric_name,
            scope=request.scope,
            available_columns=request.input_columns or None,
        )

    if not result.get("ok"):
        raise _http_error(400, result.get("message", "Formula approval failed."))

    return result


@app.post("/approve/mappings")
def approve_mappings_endpoint(request: ApproveMappingsRequest):
    if not request.mappings:
        raise _http_error(400, "At least one mapping is required.")
    confirm_mappings(
        request.customer_id,
        [mapping.model_dump() for mapping in request.mappings],
    )
    return {
        "ok": True,
        "customer_id": request.customer_id,
        "confirmed_count": len(request.mappings),
    }


@app.get("/mappings/{customer_id}")
def mappings(customer_id: str):
    return get_saved_mappings(customer_id)


@app.post("/mappings/reset")
def reset_mappings_endpoint(request: ResetMappingsRequest):
    result = reset_mappings(request.customer_id, request.system_columns)
    if not result.get("ok"):
        raise _http_error(400, result["message"])
    return result


@app.post("/approve/question")
def approve_question_endpoint(request: ApproveQuestionRequest):
    return approve_customer_question(
        question_text=request.question_text,
        answer_purpose=request.answer_purpose,
        required_metrics=request.required_metrics,
        preferred_components=request.preferred_components,
        scope=request.scope,
        customer_id=request.customer_id,
        report_type=request.report_type,
    )


def _load_rule_by_id(rule_id: int) -> dict[str, Any] | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM insight_rules WHERE rule_id = ?", (rule_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def _json_or_value(value: Any, fallback: Any):
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


@app.post("/approve/insight-rule")
def approve_insight_rule_endpoint(request: ApproveInsightRuleRequest):
    rule_data = _load_rule_by_id(request.rule_id) if request.rule_id else None

    rule_name = request.rule_name or request.display_name or (
        rule_data.get("rule_name") if rule_data else None
    )
    condition = request.condition or (rule_data.get("condition") if rule_data else None)
    customer_id = request.customer_id
    report_type = request.report_type

    if not rule_name or not condition:
        raise _http_error(400, "rule_name and condition are required.")
    if not customer_id or not report_type:
        raise _http_error(400, "customer_id and report_type are required.")

    result = approve_insight_rule(
        rule_name=rule_name,
        condition=condition,
        input_columns=(
            request.input_columns
            or _json_or_value(rule_data.get("input_columns") if rule_data else None, [])
        ),
        thresholds=(
            request.thresholds
            or _json_or_value(rule_data.get("thresholds") if rule_data else None, {})
        ),
        severity=request.severity or (rule_data.get("severity") if rule_data else "medium"),
        message_template=request.finding_template
        or (rule_data.get("message_template") if rule_data else None),
        suggestion_template=request.suggestion_template
        or (rule_data.get("suggestion_template") if rule_data else None),
        scope=request.scope,
        customer_id=customer_id,
        report_type=report_type,
    )
    return result
