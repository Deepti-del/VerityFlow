import json
import os
from typing import Any

import pandas as pd

from database import get_calculation_profile
from mapper import apply_mapping


REPORT_TYPE = "daily_generation"
DAILY_KPIS_SHEET = "daily_kpis"

METRIC_LABELS = {
    "date": "Date",
    "timestamp": "Timestamp",
    "plant_id": "Plant ID",
    "generation_kwh": "Generation",
    "expected_generation_kwh": "Expected Generation",
    "gti_kwh_m2": "GTI",
    "gti_wm2": "GTI",
    "inv_power_kw": "Inverter Power",
    "pr_percent": "PR",
    "cuf_percent": "CUF",
    "specific_yield_kwh_per_kwp": "Specific Yield",
    "total_loss_kwh": "Total Loss",
    "outage_loss_kwh": "Outage Loss",
    "environmental_loss_kwh": "Environmental Loss",
    "clipping_loss_kwh": "Clipping Loss",
    "data_availability_percent": "Data Availability",
    "availability_percent": "Availability",
}

IMPACT_MAP = {
    "date": ["date filtering", "daily trends", "scheduled report selection"],
    "timestamp": ["time-series charts", "hourly/15-minute aggregation"],
    "plant_id": ["customer/site filtering", "duplicate checks"],
    "generation_kwh": ["Generation", "PR", "CUF", "Specific Yield", "Total Loss", "waterfall"],
    "expected_generation_kwh": ["Total Loss", "waterfall", "loss explanations"],
    "gti_kwh_m2": ["PR", "Generation vs GTI", "expected generation checks"],
    "gti_wm2": ["Inverter Power vs GTI", "irradiance/power mismatch checks"],
    "inv_power_kw": ["Inverter Power vs GTI", "plant-side constraint checks"],
    "pr_percent": ["PR trend", "PR rules", "performance explanations"],
    "cuf_percent": ["CUF scorecard", "CUF trend"],
    "specific_yield_kwh_per_kwp": ["Specific Yield trend", "specific-yield rules"],
    "total_loss_kwh": ["loss rules", "loss breakdown"],
    "outage_loss_kwh": ["loss breakdown", "waterfall"],
    "environmental_loss_kwh": ["loss breakdown", "waterfall"],
    "clipping_loss_kwh": ["loss breakdown", "waterfall"],
    "data_availability_percent": ["data trust", "data availability rule", "final approval confidence"],
    "availability_percent": ["inverter availability", "equipment-level performance"],
}


def _metric_label(column: str) -> str:
    return METRIC_LABELS.get(column, column.replace("_", " ").title())


def _impacts(columns: list[str]) -> list[str]:
    impacts: list[str] = []
    for column in columns:
        impacts.extend(IMPACT_MAP.get(column, [_metric_label(column)]))
    return list(dict.fromkeys(impacts))


def _issue(
    *,
    severity: str,
    title: str,
    message: str,
    location: str,
    affected_columns: list[str] | None = None,
    affects: list[str] | None = None,
    suggested_action: str,
    examples: list[Any] | None = None,
) -> dict[str, Any]:
    columns = affected_columns or []
    return {
        "severity": severity,
        "title": title,
        "message": message,
        "location": location,
        "affected_columns": columns,
        "affects": affects or _impacts(columns),
        "suggested_action": suggested_action,
        "examples": examples or [],
    }


def _issue_text(issue: dict[str, Any]) -> str:
    text = f"{issue['title']}: {issue['message']}"
    if issue.get("affects"):
        text += " Affects: " + ", ".join(issue["affects"]) + "."
    if issue.get("suggested_action"):
        text += " Suggested action: " + issue["suggested_action"]
    return text


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return str(value.date())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _metric_columns(profile: dict, category: str) -> list[str]:
    return [
        metric["output_column"]
        for metric in profile.get(category, [])
        if metric.get("output_column")
    ]


def _sample_rows(df: pd.DataFrame, mask: pd.Series, columns: list[str], limit: int = 3) -> list[dict]:
    present = [column for column in columns if column in df.columns]
    if not present:
        present = list(df.columns[:4])
    samples = df.loc[mask, present].head(limit)
    return [
        {column: _json_value(row[column]) for column in present}
        for _, row in samples.iterrows()
    ]


def _validate_date_column(
    df: pd.DataFrame,
    column: str = "date",
    sheet_name: str = DAILY_KPIS_SHEET,
) -> dict:
    if column not in df.columns:
        issue = _issue(
            severity="critical",
            title="Date column is missing",
            message=(
                f"VerityFlow could not find the {_metric_label(column)} column needed "
                "to select the reporting period."
            ),
            location=f"{sheet_name}.{column}",
            affected_columns=[column],
            suggested_action=(
                "Correct the source file/view so every report row has a valid date."
            ),
        )
        return {
            "valid": False,
            "errors": [_issue_text(issue)],
            "warnings": [],
            "issues": [issue],
            "date_range": None,
        }

    parsed = pd.to_datetime(df[column], errors="coerce")
    invalid_count = int(parsed.isna().sum())

    errors = []
    warnings = []
    issues = []
    if invalid_count:
        issue = _issue(
            severity="critical",
            title="Invalid report dates",
            message=(
                f"{invalid_count} row(s) contain a date value VerityFlow cannot read. "
                "Those rows cannot be safely assigned to a reporting period."
            ),
            location=f"{sheet_name}.{column}",
            affected_columns=[column],
            suggested_action=(
                "Fix the date format upstream and rerun validation before calculation."
            ),
            examples=_sample_rows(df, parsed.isna(), [column, "plant_id"]),
        )
        errors.append(_issue_text(issue))
        issues.append(issue)

    date_range = None
    if not parsed.dropna().empty:
        date_range = [
            str(parsed.min().date()),
            str(parsed.max().date()),
        ]

    if parsed.dropna().is_monotonic_increasing is False:
        issue = _issue(
            severity="warning",
            title="Dates are not sorted",
            message=(
                "The date column is valid, but rows are not ordered from oldest to newest. "
                "Trend charts and previous-period comparisons are easier to audit when "
                "the source is sorted."
            ),
            location=f"{sheet_name}.{column}",
            affected_columns=[column],
            suggested_action="Sort the source data by date before sending it to VerityFlow.",
        )
        warnings.append(_issue_text(issue))
        issues.append(issue)

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "issues": issues,
        "date_range": date_range,
    }


def _validate_numeric_columns(
    df: pd.DataFrame,
    columns: list[str],
    sheet_name: str = DAILY_KPIS_SHEET,
) -> dict:
    errors = []
    warnings = []
    details = {}
    issues = []

    for column in columns:
        if column not in df.columns:
            continue
        converted = pd.to_numeric(df[column], errors="coerce")
        invalid_count = int(converted.isna().sum() - df[column].isna().sum())
        missing_count = int(df[column].isna().sum())

        details[column] = {
            "missing_count": missing_count,
            "invalid_numeric_count": invalid_count,
        }

        if invalid_count:
            issue = _issue(
                severity="critical",
                title=f"{_metric_label(column)} has non-numeric values",
                message=(
                    f"{invalid_count} value(s) in {_metric_label(column)} are not numeric, "
                    "so VerityFlow cannot use them safely in approved formulas or charts."
                ),
                location=f"{sheet_name}.{column}",
                affected_columns=[column],
                suggested_action=(
                    "Correct the source field to contain only numeric values, or map it "
                    "to the correct numeric column."
                ),
                examples=_sample_rows(df, converted.isna() & df[column].notna(), [column, "date", "timestamp", "plant_id"]),
            )
            errors.append(_issue_text(issue))
            issues.append(issue)
        elif missing_count:
            issue = _issue(
                severity="warning",
                title=f"{_metric_label(column)} has blank values",
                message=(
                    f"{missing_count} row(s) have no value for {_metric_label(column)}. "
                    "VerityFlow will not fill these values automatically."
                ),
                location=f"{sheet_name}.{column}",
                affected_columns=[column],
                suggested_action=(
                    "Correct the missing values in the source system/file, or confirm "
                    "that the affected period should be excluded upstream."
                ),
                examples=_sample_rows(df, df[column].isna(), [column, "date", "timestamp", "plant_id"]),
            )
            warnings.append(_issue_text(issue))
            issues.append(issue)

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "details": details,
        "issues": issues,
    }


def _validate_duplicates(
    df: pd.DataFrame,
    keys: list[str],
    sheet_name: str = DAILY_KPIS_SHEET,
) -> dict:
    keys_present = [key for key in keys if key in df.columns]
    if not keys_present:
        return {
            "valid": True,
            "errors": [],
            "warnings": [],
            "issues": [],
            "duplicate_count": 0,
            "keys": [],
        }

    duplicate_count = int(df.duplicated(subset=keys_present).sum())
    warnings = []
    issues = []
    if duplicate_count:
        duplicate_mask = df.duplicated(subset=keys_present, keep=False)
        issue = _issue(
            severity="warning",
            title="Duplicate reporting rows",
            message=(
                f"{duplicate_count} duplicate row(s) were found using "
                f"{', '.join(_metric_label(key) for key in keys_present)}. "
                "Duplicates can overstate sums and distort averages."
            ),
            location=f"{sheet_name} rows",
            affected_columns=keys_present,
            suggested_action=(
                "Deduplicate the source rows upstream or confirm the intended grain "
                "before generating the report."
            ),
            examples=_sample_rows(df, duplicate_mask, keys_present),
        )
        warnings.append(_issue_text(issue))
        issues.append(issue)

    return {
        "valid": True,
        "errors": [],
        "warnings": warnings,
        "issues": issues,
        "duplicate_count": duplicate_count,
        "keys": keys_present,
    }


def _relevant_mapping_summary(mapping_result: dict, relevant_columns: list[str]) -> dict:
    relevant = set(relevant_columns)
    mapped = [
        mapping for mapping in mapping_result["mapped"]
        if mapping["system_col"] in relevant
    ]
    missing = [
        column for column in relevant_columns
        if column not in {mapping["system_col"] for mapping in mapped}
    ]

    return {
        "confirmed": mapping_result["confirmed"],
        "mapped": mapped,
        "missing": missing,
    }


def _infer_expected_interval_minutes(timestamps: pd.Series) -> float | None:
    ordered = pd.to_datetime(timestamps, errors="coerce").dropna().sort_values()
    if len(ordered) < 3:
        return None
    gaps = ordered.diff().dropna().dt.total_seconds() / 60
    positive_gaps = gaps[gaps > 0]
    if positive_gaps.empty:
        return None
    return float(positive_gaps.median())


def _validate_daily_timeseries(df: pd.DataFrame, sheet_name: str = "daily_timeseries") -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    issues: list[dict[str, Any]] = []

    if df.empty:
        issue = _issue(
            severity="warning",
            title="Time-series sheet is empty",
            message=(
                "The workbook contains a daily_timeseries sheet, but it has no rows. "
                "Interval charts cannot be generated from it."
            ),
            location=sheet_name,
            affected_columns=["timestamp"],
            suggested_action="Check the upstream export/query for interval telemetry.",
        )
        warnings.append(_issue_text(issue))
        issues.append(issue)
        return {"errors": errors, "warnings": warnings, "issues": issues}

    if "timestamp" not in df.columns:
        issue = _issue(
            severity="warning",
            title="Interval timestamp is missing",
            message=(
                "The daily_timeseries sheet has no timestamp column, so VerityFlow "
                "cannot create hourly, 15-minute, or source-interval charts."
            ),
            location=f"{sheet_name}.timestamp",
            affected_columns=["timestamp"],
            suggested_action="Add a timestamp column to the clean source view/file.",
        )
        warnings.append(_issue_text(issue))
        issues.append(issue)
        return {"errors": errors, "warnings": warnings, "issues": issues}

    parsed = pd.to_datetime(df["timestamp"], errors="coerce")
    invalid_mask = parsed.isna()
    if invalid_mask.any():
        issue = _issue(
            severity="warning",
            title="Invalid interval timestamps",
            message=(
                f"{int(invalid_mask.sum())} interval row(s) have timestamps that "
                "VerityFlow cannot read."
            ),
            location=f"{sheet_name}.timestamp",
            affected_columns=["timestamp"],
            suggested_action="Fix timestamp formatting upstream before using interval charts.",
            examples=_sample_rows(df, invalid_mask, ["timestamp", "plant_id"]),
        )
        warnings.append(_issue_text(issue))
        issues.append(issue)

    duplicate_mask = df.duplicated(subset=["timestamp"], keep=False)
    if duplicate_mask.any():
        issue = _issue(
            severity="warning",
            title="Duplicate interval timestamps",
            message=(
                f"{int(df.duplicated(subset=['timestamp']).sum())} duplicate timestamp row(s) "
                "were found. Duplicate intervals can distort hourly averages and line charts."
            ),
            location=f"{sheet_name}.timestamp",
            affected_columns=["timestamp"],
            suggested_action="Deduplicate the interval source in BigQuery/Excel before reporting.",
            examples=_sample_rows(df, duplicate_mask, ["timestamp", "plant_id"]),
        )
        warnings.append(_issue_text(issue))
        issues.append(issue)

    clean_times = parsed.dropna().sort_values()
    expected_minutes = _infer_expected_interval_minutes(clean_times)
    if expected_minutes:
        gaps = clean_times.diff().dropna()
        gap_mask = gaps > pd.Timedelta(minutes=expected_minutes * 1.5)
        if gap_mask.any():
            first_gap_end = clean_times.iloc[1:][gap_mask].iloc[0]
            first_gap_start = first_gap_end - gaps[gap_mask].iloc[0]
            issue = _issue(
                severity="warning",
                title="Missing interval gap detected",
                message=(
                    f"VerityFlow detected {int(gap_mask.sum())} timestamp gap(s) larger "
                    f"than the expected ~{expected_minutes:.0f}-minute interval. "
                    "This can affect interval charts and any KPI derived from telemetry."
                ),
                location=f"{sheet_name}.timestamp",
                affected_columns=["timestamp", "gti_wm2", "inv_power_kw"],
                suggested_action=(
                    "Correct the upstream telemetry export/query or mark the affected "
                    "period as unavailable before final report approval."
                ),
                examples=[{
                    "gap_start": first_gap_start.isoformat(),
                    "gap_end": first_gap_end.isoformat(),
                }],
            )
            warnings.append(_issue_text(issue))
            issues.append(issue)

    numeric_result = _validate_numeric_columns(
        df,
        [column for column in ("gti_wm2", "inv_power_kw") if column in df.columns],
        sheet_name=sheet_name,
    )
    warnings.extend(numeric_result["warnings"])
    errors.extend(numeric_result["errors"])
    issues.extend(numeric_result["issues"])

    if {"gti_wm2", "inv_power_kw"}.issubset(df.columns):
        gti = pd.to_numeric(df["gti_wm2"], errors="coerce")
        power = pd.to_numeric(df["inv_power_kw"], errors="coerce")
        daylight_zero_mask = (gti > 50) & (power <= 0)
        if daylight_zero_mask.any():
            issue = _issue(
                severity="warning",
                title="Zero inverter power during irradiance",
                message=(
                    f"{int(daylight_zero_mask.sum())} interval row(s) show GTI above "
                    "50 W/m² while inverter power is zero or negative. This may be a "
                    "communication drop, curtailment event, or plant-side outage."
                ),
                location=sheet_name,
                affected_columns=["gti_wm2", "inv_power_kw"],
                suggested_action=(
                    "Confirm the event in the monitoring portal/source data before "
                    "using this interval evidence in the customer report."
                ),
                examples=_sample_rows(df, daylight_zero_mask, ["timestamp", "gti_wm2", "inv_power_kw"]),
            )
            warnings.append(_issue_text(issue))
            issues.append(issue)

    return {"errors": errors, "warnings": warnings, "issues": issues}


def _validate_inverter_performance(df: pd.DataFrame, sheet_name: str = "inverter_performance") -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    issues: list[dict[str, Any]] = []

    if df.empty:
        return {"errors": errors, "warnings": warnings, "issues": issues}

    required = ["date", "inverter_id", "pr_percent"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        issue = _issue(
            severity="warning",
            title="Equipment performance detail is incomplete",
            message=(
                "The inverter_performance sheet is present, but it is missing "
                f"{', '.join(_metric_label(column) for column in missing)}."
            ),
            location=sheet_name,
            affected_columns=missing,
            suggested_action=(
                "Correct the clean source view/file if you want inverter heatmaps, "
                "weakest-inverter evidence, or equipment-level explanations."
            ),
        )
        warnings.append(_issue_text(issue))
        issues.append(issue)
        return {"errors": errors, "warnings": warnings, "issues": issues}

    duplicate_result = _validate_duplicates(
        df,
        ["date", "inverter_id"],
        sheet_name=sheet_name,
    )
    warnings.extend(duplicate_result["warnings"])
    issues.extend(duplicate_result["issues"])

    numeric_result = _validate_numeric_columns(
        df,
        [column for column in ("pr_percent", "generation_kwh", "availability_percent") if column in df.columns],
        sheet_name=sheet_name,
    )
    warnings.extend(numeric_result["warnings"])
    errors.extend(numeric_result["errors"])
    issues.extend(numeric_result["issues"])

    if "pr_percent" in df.columns:
        pr = pd.to_numeric(df["pr_percent"], errors="coerce")
        impossible_mask = (pr < 0) | (pr > 100)
        if impossible_mask.any():
            issue = _issue(
                severity="warning",
                title="Inverter PR is outside expected bounds",
                message=(
                    f"{int(impossible_mask.sum())} inverter row(s) show PR below 0% "
                    "or above 100%. This can make heatmaps and weakest-inverter "
                    "comparisons misleading."
                ),
                location=f"{sheet_name}.pr_percent",
                affected_columns=["pr_percent"],
                suggested_action="Check the inverter PR calculation or source mapping upstream.",
                examples=_sample_rows(df, impossible_mask, ["date", "inverter_id", "pr_percent"]),
            )
            warnings.append(_issue_text(issue))
            issues.append(issue)

    return {"errors": errors, "warnings": warnings, "issues": issues}


def validate_daily_kpis_sheet(
    df: pd.DataFrame,
    customer_id: str,
    report_type: str = REPORT_TYPE,
) -> dict:
    profile = get_calculation_profile(customer_id, report_type)
    mapping_result = apply_mapping(df, customer_id)
    mapped_df = mapping_result["df"]

    errors = []
    warnings = []
    issues = []

    if df.empty:
        issue = _issue(
            severity="critical",
            title="Daily KPI sheet is empty",
            message=(
                "The daily_kpis sheet has no rows, so VerityFlow has no report-ready "
                "daily data to validate or calculate."
            ),
            location=DAILY_KPIS_SHEET,
            suggested_action="Correct the upstream export/query and upload a file with daily KPI rows.",
        )
        errors.append(_issue_text(issue))
        issues.append(issue)

    if not mapping_result["confirmed"]:
        issue = _issue(
            severity="critical",
            title="Column mappings need analyst approval",
            message=(
                "VerityFlow found source data, but the customer column mappings have "
                "not been confirmed yet. KPI formulas should not run until the analyst "
                "confirms which source columns map to approved standard metrics."
            ),
            location="customer mapping memory",
            suggested_action="Go to Mapping & Formulas, confirm the customer mappings, then rerun validation.",
        )
        errors.append(_issue_text(issue))
        issues.append(issue)

    required_columns = _metric_columns(profile, "required_source")
    missing_required = [
        column for column in required_columns
        if column not in mapped_df.columns
    ]
    if missing_required:
        issue = _issue(
            severity="critical",
            title="Required KPI inputs are missing",
            message=(
                "VerityFlow could not find these required mapped inputs: "
                + ", ".join(_metric_label(column) for column in missing_required)
                + ". Approved KPI formulas may be incomplete without them."
            ),
            location=f"{DAILY_KPIS_SHEET} after mapping",
            affected_columns=missing_required,
            suggested_action=(
                "Correct the source view/file or update the customer mapping so these "
                "standard inputs are available before calculation."
            ),
        )
        errors.append(_issue_text(issue))
        issues.append(issue)

    optional_columns = _metric_columns(profile, "optional")
    missing_optional = [
        column for column in optional_columns
        if column not in mapped_df.columns
    ]
    if missing_optional:
        issue = _issue(
            severity="warning",
            title="Optional evidence is missing",
            message=(
                "The report can continue, but these optional evidence fields were not "
                "found after mapping: "
                + ", ".join(_metric_label(column) for column in missing_optional)
                + ". Some charts or explanations may be less detailed."
            ),
            location=f"{DAILY_KPIS_SHEET} after mapping",
            affected_columns=missing_optional,
            suggested_action=(
                "If these fields should appear in the report, add them to the clean "
                "source data or map them to the correct customer columns."
            ),
        )
        warnings.append(_issue_text(issue))
        issues.append(issue)

    date_result = _validate_date_column(mapped_df, "date", DAILY_KPIS_SHEET)
    errors.extend(date_result["errors"])
    warnings.extend(date_result["warnings"])
    issues.extend(date_result.get("issues", []))

    numeric_columns = [
        column for column in (
            _metric_columns(profile, "required_source")
            + _metric_columns(profile, "derivable")
            + _metric_columns(profile, "optional")
        )
        if column not in {"date", "plant_id"} and column in mapped_df.columns
    ]
    numeric_result = _validate_numeric_columns(mapped_df, numeric_columns, DAILY_KPIS_SHEET)
    errors.extend(numeric_result["errors"])
    warnings.extend(numeric_result["warnings"])
    issues.extend(numeric_result.get("issues", []))

    duplicate_result = _validate_duplicates(mapped_df, ["plant_id", "date"], DAILY_KPIS_SHEET)
    warnings.extend(duplicate_result["warnings"])
    issues.extend(duplicate_result.get("issues", []))

    relevant_columns = list(dict.fromkeys(required_columns + optional_columns))
    mapping_summary = _relevant_mapping_summary(mapping_result, relevant_columns)

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "data_quality_issues": issues,
        "sheet_name": DAILY_KPIS_SHEET,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": list(df.columns),
        "mapped_columns": list(mapped_df.columns),
        "date_range": date_result["date_range"],
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "numeric_checks": numeric_result["details"],
        "duplicates": {
            "count": duplicate_result["duplicate_count"],
            "keys": duplicate_result["keys"],
        },
        "mapping": {
            "confirmed": mapping_result["confirmed"],
            "mapped": mapping_summary["mapped"],
            "missing": mapping_summary["missing"],
        },
    }


def validate_workbook(
    excel_path: str,
    customer_id: str,
    report_type: str = REPORT_TYPE,
    required_sheets: list[str] | None = None,
) -> dict:
    required_sheets = required_sheets or [DAILY_KPIS_SHEET]
    errors = []
    warnings = []
    data_quality_issues = []
    sheet_results = {}

    if not os.path.exists(excel_path):
        issue = _issue(
            severity="critical",
            title="Connected data source was not found",
            message=(
                "VerityFlow could not find the uploaded workbook or generated source file "
                "for this validation run."
            ),
            location=excel_path,
            suggested_action="Reconnect the source data and run validation again.",
        )
        return {
            "valid": False,
            "errors": [_issue_text(issue)],
            "warnings": [],
            "data_quality_issues": [issue],
            "sheets": {},
        }

    try:
        workbook = pd.ExcelFile(excel_path)
    except Exception as exc:
        issue = _issue(
            severity="critical",
            title="Data source could not be opened",
            message=(
                "VerityFlow could not open this workbook/source extract. It may be "
                "corrupt, password-protected, or not in a readable Excel format."
            ),
            location=excel_path,
            suggested_action=(
                "Export the clean report-ready data again as a readable workbook, or "
                "reconnect the source query."
            ),
        )
        return {
            "valid": False,
            "errors": [_issue_text(issue), f"Technical detail: {exc}"],
            "warnings": [],
            "data_quality_issues": [issue],
            "sheets": {},
        }

    available_sheets = workbook.sheet_names
    missing_sheets = [
        sheet for sheet in required_sheets
        if sheet not in available_sheets
    ]
    if missing_sheets:
        issue = _issue(
            severity="critical",
            title="Required report data sheet is missing",
            message=(
                "VerityFlow cannot validate or calculate the report because these "
                "required clean data sheets/views are missing: "
                + ", ".join(missing_sheets)
                + "."
            ),
            location="workbook/source schema",
            affects=["validation", "KPI calculations", "draft generation"],
            suggested_action=(
                "Update the Excel workbook or BigQuery source configuration so the "
                "required report-ready sheet/view is available."
            ),
        )
        errors.append(_issue_text(issue))
        data_quality_issues.append(issue)

    for sheet in required_sheets:
        if sheet not in available_sheets:
            continue

        df = pd.read_excel(workbook, sheet_name=sheet)
        if sheet == DAILY_KPIS_SHEET:
            result = validate_daily_kpis_sheet(
                df,
                customer_id=customer_id,
                report_type=report_type,
            )
        else:
            result = {
                "valid": True,
                "errors": [],
                "warnings": [
                    f"No sheet-specific validator implemented for '{sheet}' yet."
                ],
                "sheet_name": sheet,
                "row_count": int(len(df)),
                "column_count": int(len(df.columns)),
                "columns": list(df.columns),
            }

        sheet_results[sheet] = result
        errors.extend(result["errors"])
        warnings.extend(result["warnings"])
        data_quality_issues.extend(result.get("data_quality_issues", result.get("issues", [])))

    optional_sheet_validators = {
        "daily_timeseries": _validate_daily_timeseries,
        "inverter_performance": _validate_inverter_performance,
    }
    optional_sheet_results = {}
    for sheet, sheet_validator in optional_sheet_validators.items():
        if sheet not in available_sheets or sheet in sheet_results:
            continue
        df = pd.read_excel(workbook, sheet_name=sheet)
        result = sheet_validator(df, sheet)
        optional_sheet_results[sheet] = {
            **result,
            "sheet_name": sheet,
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "columns": list(df.columns),
        }
        errors.extend(result.get("errors", []))
        warnings.extend(result.get("warnings", []))
        data_quality_issues.extend(result.get("issues", []))

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "data_quality_issues": data_quality_issues,
        "workbook": {
            "path": excel_path,
            "available_sheets": available_sheets,
            "required_sheets": required_sheets,
        },
        "sheets": sheet_results,
        "optional_sheet_checks": optional_sheet_results,
    }


if __name__ == "__main__":
    data_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "data",
        "Alpha_Solar_Dummy_Dataset.xlsx",
    )

    result = validate_workbook(
        data_path,
        customer_id="alpha_solar",
    )
    print(json.dumps(result, indent=2))
