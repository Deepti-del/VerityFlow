from typing import Any, Literal

from pydantic import BaseModel, Field


Scope = Literal["customer_report_type", "customer", "report_type", "global"]
ReportTheme = Literal["corporate_blue", "minimal", "executive", "operations"]
SummaryPosition = Literal["top", "after_kpis"]
TextPosition = Literal["above", "beside", "below"]
ChartType = Literal[
    "line",
    "bar",
    "bar_line",
    "dual_axis_line",
    "stacked_bar",
    "waterfall",
    "heatmap",
    "table",
]
AggregationMethod = Literal["auto", "average", "sum"]
TimeGrain = Literal["raw", "15_minute", "hourly", "daily"]


class ValidateRequest(BaseModel):
    customer_id: str
    report_type: str = "daily_generation"
    report_date: str | None = Field(default=None, description="YYYY-MM-DD")
    file_id: str


class CalculateRequest(BaseModel):
    customer_id: str
    report_type: str = "daily_generation"
    report_date: str | None = Field(default=None, description="YYYY-MM-DD")
    file_id: str


class BigQuerySourceRequest(BaseModel):
    project_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    plant_id: str | None = None
    start_date: str | None = Field(default=None, description="YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="YYYY-MM-DD")
    use_demo_data: bool = False
    table_map: dict[str, str] = Field(default_factory=dict)


class BigQuerySourceResponse(BaseModel):
    file_id: str
    filename: str
    source_type: str = "bigquery"
    mode: str
    message: str
    views: dict[str, str] = Field(default_factory=dict)


class ApproveFormulaRequest(BaseModel):
    metric_name: str
    formula: str | None = None
    unit: str | None = None
    good_range: str | None = None
    poor_threshold: str | None = None
    scope: Scope = "customer_report_type"
    customer_id: str | None = None
    report_type: str | None = None
    output_column: str | None = None
    input_columns: list[str] = Field(default_factory=list)


class ApproveInsightRuleRequest(BaseModel):
    rule_id: int | None = None
    rule_name: str | None = None
    display_name: str | None = None
    condition: str | None = None
    input_columns: list[str] = Field(default_factory=list)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    severity: str = "medium"
    finding_template: str | None = None
    suggestion_template: str | None = None
    scope: Scope = "customer_report_type"
    customer_id: str | None = None
    report_type: str | None = None


class MappingUpdate(BaseModel):
    system_column: str = Field(min_length=1)
    customer_column: str = Field(min_length=1)
    data_type: str = "numeric"


class ApproveMappingsRequest(BaseModel):
    customer_id: str
    mappings: list[MappingUpdate] = Field(default_factory=list)


class ResetMappingsRequest(BaseModel):
    customer_id: str
    system_columns: list[str] = Field(default_factory=list)


class ValidateFormulaRequest(BaseModel):
    customer_id: str
    report_type: str = "daily_generation"
    metric_name: str
    formula: str
    input_columns: list[str] = Field(default_factory=list)
    available_columns: list[str] = Field(default_factory=list)


class ApproveQuestionRequest(BaseModel):
    question_text: str
    answer_purpose: str | None = None
    required_metrics: list[str] = Field(default_factory=list)
    preferred_components: list[str] = Field(default_factory=list)
    scope: Scope = "customer_report_type"
    customer_id: str
    report_type: str


class CreateCustomerRequest(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    parent_company: str | None = Field(default=None, max_length=120)
    customer_reference: str | None = Field(default=None, max_length=80)
    site_name: str = Field(min_length=2, max_length=120)
    location: str | None = Field(default=None, max_length=160)
    timezone: str = Field(default="Asia/Kolkata", min_length=1, max_length=80)
    dc_capacity_kwp: float | None = Field(default=None, gt=0)
    ac_capacity_kw: float | None = Field(default=None, gt=0)
    report_type: str = "daily_generation"
    reporting_period: str = "daily"
    configuration_name: str = Field(
        default="Daily Generation Report",
        min_length=2,
        max_length=120,
    )


class ReportComponentRequest(BaseModel):
    customer_id: str
    report_type: str = "daily_generation"
    report_date: str | None = Field(default=None, description="YYYY-MM-DD")
    file_id: str
    component_id: str | None = None
    title: str = Field(min_length=1, max_length=160)
    metrics: list[str] = Field(min_length=1)
    start_date: str | None = Field(default=None, description="YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="YYYY-MM-DD")
    breakdown: Literal["site_total", "inverter", "block", "loss_type"] = "site_total"
    chart_type: ChartType = "line"
    aggregation: AggregationMethod = "auto"
    aggregations: dict[str, AggregationMethod] = Field(default_factory=dict)
    time_grain: TimeGrain = "daily"


class SaveReportLayoutRequest(BaseModel):
    config_id: str
    customer_id: str
    report_type: str = "daily_generation"
    theme: ReportTheme = "corporate_blue"
    summary_position: SummaryPosition = "top"
    layout: dict[str, Any] = Field(default_factory=dict)
    create_revision: bool = False
    created_by: str = "analyst"


class ApproveReportLayoutRequest(BaseModel):
    layout_id: str
    approved_by: str = "analyst"


class ApproveReportSnapshotRequest(BaseModel):
    config_id: str
    customer_id: str
    report_type: str = "daily_generation"
    report_date: str = Field(description="YYYY-MM-DD")
    layout_id: str
    approved_by: str = "analyst"
    report: dict[str, Any]


class UploadResponse(BaseModel):
    file_id: str
    filename: str


class ValidationResponse(BaseModel):
    valid: bool
    errors: list[Any] = Field(default_factory=list)
    warnings: list[Any] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class CalculationResponse(BaseModel):
    customer_id: str
    report_date: str | None = None
    kpis: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    pending_approval: list[dict[str, Any]] = Field(default_factory=list)
    chart_specs: list[dict[str, Any]] = Field(default_factory=list)
    answer_plan: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    draft: dict[str, Any] = Field(default_factory=dict)


class ProfileResponse(BaseModel):
    customer_id: str
    report_type: str
    required_source: list[dict[str, Any]] = Field(default_factory=list)
    derivable: list[dict[str, Any]] = Field(default_factory=list)
    optional: list[dict[str, Any]] = Field(default_factory=list)
    insight_rules: list[dict[str, Any]] = Field(default_factory=list)
    customer_questions: list[dict[str, Any]] = Field(default_factory=list)
    pending_approval_count: int = 0
