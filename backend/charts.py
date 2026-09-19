import math
from typing import Any

import pandas as pd


REPORT_TYPE = "daily_generation"

DEFAULT_COMPONENTS = [
    "kpi_cards",
    "generation_vs_gti_chart",
    "inv_pow_gti_chart",
    "pr_trend_chart",
    "loss_breakdown_chart",
    "loss_waterfall",
    "inverter_pr_table",
    "specific_yield_trend_chart",
    "data_availability_trend_chart",
]

KPI_CARD_COLUMNS = [
    ("generation_kwh", "Generation", "kWh"),
    ("gti_kwh_m2", "GTI", "kWh/m²"),
    ("pr_percent", "PR", "%"),
    ("cuf_percent", "CUF", "%"),
    ("specific_yield_kwh_per_kwp", "Specific Yield", "kWh/kWp"),
    ("total_loss_kwh", "Total Loss", "kWh"),
]

METRIC_UNITS = {
    "generation_kwh": "kWh",
    "expected_generation_kwh": "kWh",
    "gti_kwh_m2": "kWh/m²",
    "gti_wm2": "W/m²",
    "inv_power_kw": "kW",
    "pr_percent": "%",
    "cuf_percent": "%",
    "specific_yield_kwh_per_kwp": "kWh/kWp",
    "total_loss_kwh": "kWh",
    "outage_loss_kwh": "kWh",
    "environmental_loss_kwh": "kWh",
    "clipping_loss_kwh": "kWh",
    "data_availability_percent": "%",
    "availability_percent": "%",
}

METRIC_LABELS = {
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

METRIC_AGGREGATION_DEFAULTS = {
    "generation_kwh": "sum",
    "expected_generation_kwh": "sum",
    "gti_kwh_m2": "sum",
    "gti_wm2": "average",
    "pr_percent": "average",
    "cuf_percent": "average",
    "specific_yield_kwh_per_kwp": "average",
    "total_loss_kwh": "sum",
    "outage_loss_kwh": "sum",
    "environmental_loss_kwh": "sum",
    "clipping_loss_kwh": "sum",
    "data_availability_percent": "average",
    "availability_percent": "average",
    "inv_power_kw": "average",
    "temperature_c": "average",
}

WATERFALL_METRICS = [
    "expected_generation_kwh",
    "outage_loss_kwh",
    "environmental_loss_kwh",
    "clipping_loss_kwh",
    "generation_kwh",
]


class ChartCompatibilityError(ValueError):
    """Analyst-facing chart compatibility failure with developer detail preserved."""

    def __init__(
        self,
        *,
        analyst_reason: str,
        developer_reason: str,
        recommended_options: list[str] | None = None,
        available_metrics: list[str] | None = None,
    ) -> None:
        super().__init__(analyst_reason)
        self.analyst_reason = analyst_reason
        self.developer_reason = developer_reason
        self.recommended_options = recommended_options or []
        self.available_metrics = available_metrics or []

    def to_detail(self) -> dict[str, Any]:
        return {
            "message": self.analyst_reason,
            "analyst_reason": self.analyst_reason,
            "developer_reason": self.developer_reason,
            "recommended_options": self.recommended_options,
            "available_metrics": self.available_metrics,
        }


def _chart_recommendations(chart_type: str) -> list[str]:
    if chart_type == "waterfall":
        return ["stacked_bar", "bar", "table"]
    if chart_type == "heatmap":
        return ["bar", "table"]
    if chart_type in {"bar_line", "dual_axis_line"}:
        return ["line", "bar", "table"]
    if chart_type == "stacked_bar":
        return ["bar", "table"]
    return ["table"]


def _chart_purpose(chart_type: str) -> str:
    purposes = {
        "line": (
            "A line chart is used to show how one or more KPIs change over time. "
            "It needs approved date or timestamp values and numeric KPI values."
        ),
        "bar": (
            "A bar chart is used to compare KPI values across dates, equipment, or "
            "categories. It needs at least one numeric KPI and a date, equipment, "
            "or category field to compare against."
        ),
        "bar_line": (
            "A bar + line chart is used when one KPI is best shown as bars and "
            "another related KPI is best shown as a trend line, such as Generation "
            "as bars with GTI or PR as a line. It needs at least two numeric KPIs."
        ),
        "dual_axis_line": (
            "A dual-axis line chart is used to compare two time-series KPIs with "
            "different units or scales, such as Inverter Power and GTI. It needs at "
            "least two numeric KPIs measured over the same approved time period."
        ),
        "stacked_bar": (
            "A stacked bar chart is used to show how multiple components contribute "
            "to a total across dates or categories, such as different loss types "
            "contributing to total loss. It needs at least two numeric components "
            "or a category-based loss structure."
        ),
        "waterfall": (
            "A waterfall chart explains how a starting value changes through a "
            "series of positive or negative additions/subtractions to reach a final "
            "ending total."
        ),
        "heatmap": (
            "A heatmap is used to compare one KPI across equipment or categories "
            "using colour intensity. For solar performance, this is usually used "
            "to compare PR, availability, or power across inverters or blocks."
        ),
        "table": (
            "A table is used when the selected data should be reviewed directly "
            "instead of transformed into a visual shape. It is the safest fallback "
            "when a chart is not meaningful for the selected KPIs."
        ),
    }
    return purposes.get(chart_type, "This chart needs approved numeric data in a compatible shape.")


def _raise_chart_error(
    chart_type: str,
    *,
    analyst_reason: str,
    developer_reason: str,
    available_metrics: list[str] | None = None,
    recommended_options: list[str] | None = None,
) -> None:
    raise ChartCompatibilityError(
        analyst_reason=analyst_reason,
        developer_reason=developer_reason,
        recommended_options=recommended_options or _chart_recommendations(chart_type),
        available_metrics=available_metrics,
    )


def _rows_to_dataframe(calculation_result_or_df: dict | pd.DataFrame) -> pd.DataFrame:
    if isinstance(calculation_result_or_df, pd.DataFrame):
        return calculation_result_or_df.copy()

    clean_rows = []
    for row in calculation_result_or_df.get("rows", []):
        clean_rows.append({
            key: value
            for key, value in row.items()
            if key not in ("metric_sources", "changes")
        })
    return pd.DataFrame(clean_rows)


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        if value.hour or value.minute or value.second:
            return value.isoformat(sep=" ")
        return str(value.date())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 6)
    return value


def _values(df: pd.DataFrame, column: str) -> list[Any]:
    return [_json_value(value) for value in df[column].tolist()]


def _format_evidence_value(metric: str, value: Any) -> str:
    if value is None or pd.isna(value):
        return "not available"
    numeric = float(value)
    formatted = f"{numeric:,.2f}".rstrip("0").rstrip(".")
    unit = METRIC_UNITS.get(metric, "")
    return f"{formatted}{unit if unit == '%' else f' {unit}' if unit else ''}"


def _aggregation_verb(method: str) -> str:
    return "totaled" if method == "sum" else "averaged"


def _dimension_label(dimension: str, count: int) -> str:
    labels = {
        "inverter_id": ("inverter", "inverters"),
        "block_id": ("block", "blocks"),
        "loss_type": ("loss category", "loss categories"),
    }
    singular, plural = labels.get(dimension, (humanize_metric(dimension), humanize_metric(dimension)))
    return singular if count == 1 else plural


def _percent_change(current: Any, previous: Any) -> float | None:
    try:
        current_value = float(current)
        previous_value = float(previous)
    except (TypeError, ValueError):
        return None
    if previous_value == 0 or not math.isfinite(previous_value):
        return None
    return round((current_value - previous_value) / abs(previous_value) * 100, 2)


def _component_evidence(
    *,
    component: dict,
    plotted_df: pd.DataFrame,
    source_df: pd.DataFrame,
    metrics: list[str],
    dimension: str,
    aggregations: dict[str, str],
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "metrics": {},
        "start_date": start_date,
        "end_date": end_date,
        "breakdown": component.get("breakdown") or (
            "site_total" if dimension == "site_total" else dimension
        ),
    }
    if plotted_df.empty or not metrics:
        evidence["summary"] = "No approved evidence is available for this component."
        return evidence

    if dimension != "site_total" and dimension in plotted_df.columns:
        metric = metrics[0]
        equipment = (
            plotted_df.groupby(dimension, dropna=False)[metric]
            .mean()
            .dropna()
            .sort_values()
        )
        if not equipment.empty:
            lowest_id = str(equipment.index[0])
            lowest_value = float(equipment.iloc[0])
            fleet_average = float(equipment.mean())
            count = int(len(equipment))
            evidence["metrics"][metric] = {
                "fleet_average": round(fleet_average, 4),
                "lowest_equipment": lowest_id,
                "lowest_value": round(lowest_value, 4),
                "equipment_count": count,
            }
            evidence["summary"] = (
                f"{humanize_metric(metric)} averaged "
                f"{_format_evidence_value(metric, fleet_average)} across "
                f"{count} {_dimension_label(dimension, count)}. "
                f"{lowest_id} was lowest at "
                f"{_format_evidence_value(metric, lowest_value)}."
            )
            return evidence

    for metric in metrics:
        values = pd.to_numeric(plotted_df[metric], errors="coerce").dropna()
        if values.empty:
            continue
        method = aggregations.get(metric, "average")
        period_value = values.sum() if method == "sum" else values.mean()
        min_index = values.idxmin()
        max_index = values.idxmax()
        metric_evidence = {
            "aggregation": method,
            "period_value": round(float(period_value), 6),
            "first_value": round(float(values.iloc[0]), 6),
            "last_value": round(float(values.iloc[-1]), 6),
            "minimum_value": round(float(values.loc[min_index]), 6),
            "maximum_value": round(float(values.loc[max_index]), 6),
            "change_percent": _percent_change(values.iloc[-1], values.iloc[0]),
        }

        source_date_column = next(
            (column for column in ("timestamp", "date") if column in source_df.columns),
            None,
        )
        plotted_date_column = next(
            (column for column in ("timestamp", "date", "_period") if column in plotted_df.columns),
            None,
        )
        if plotted_date_column:
            min_date = pd.to_datetime(
                plotted_df.loc[min_index, plotted_date_column],
                errors="coerce",
            )
            max_date = pd.to_datetime(
                plotted_df.loc[max_index, plotted_date_column],
                errors="coerce",
            )
            if pd.notna(min_date):
                metric_evidence["minimum_date"] = min_date.strftime("%Y-%m-%d")
            if pd.notna(max_date):
                metric_evidence["maximum_date"] = max_date.strftime("%Y-%m-%d")
        if source_date_column and start_date:
            source_dates = pd.to_datetime(source_df[source_date_column], errors="coerce")
            previous_rows = source_df.loc[source_dates < pd.Timestamp(start_date)]
            if not previous_rows.empty and metric in previous_rows.columns:
                previous_value = pd.to_numeric(
                    previous_rows.iloc[-1][metric],
                    errors="coerce",
                )
                if pd.notna(previous_value):
                    metric_evidence["previous_value"] = round(float(previous_value), 6)
                    metric_evidence["change_vs_previous_percent"] = _percent_change(
                        values.iloc[-1],
                        previous_value,
                    )
        evidence["metrics"][metric] = metric_evidence

    if {"inv_power_kw", "gti_wm2"}.issubset(metrics):
        paired = plotted_df[["inv_power_kw", "gti_wm2"]].apply(
            pd.to_numeric,
            errors="coerce",
        ).dropna()
        correlation = (
            paired["inv_power_kw"].corr(paired["gti_wm2"])
            if len(paired) > 1 else None
        )
        power_peak = paired["inv_power_kw"].max() if not paired.empty else 0
        gti_peak = paired["gti_wm2"].max() if not paired.empty else 0
        mismatch_count = 0
        if power_peak > 0 and gti_peak > 0:
            power_ratio = paired["inv_power_kw"] / power_peak
            gti_ratio = paired["gti_wm2"] / gti_peak
            mismatch_count = int(
                ((gti_ratio >= 0.5) & (power_ratio <= gti_ratio - 0.3)).sum()
            )
        evidence["relationship"] = {
            "correlation": (
                round(float(correlation), 3)
                if correlation is not None and pd.notna(correlation) else None
            ),
            "high_irradiance_low_power_intervals": mismatch_count,
            "observations": int(len(paired)),
        }
        correlation_text = (
            f"Correlation was {correlation:.2f}. "
            if correlation is not None and pd.notna(correlation) else ""
        )
        evidence["summary"] = (
            f"Inverter power and GTI were compared across {len(paired)} "
            f"approved observations. {correlation_text}"
            f"{mismatch_count} interval(s) showed relatively high irradiance "
            "with disproportionately low power, which is evidence for analyst "
            "review of a possible plant-side constraint."
        )
        return evidence

    if "pr_percent" in evidence["metrics"]:
        values = evidence["metrics"]["pr_percent"]
        summary = (
            f"PR averaged {_format_evidence_value('pr_percent', values['period_value'])} "
            f"and ended at {_format_evidence_value('pr_percent', values['last_value'])}."
        )
        if values.get("change_vs_previous_percent") is not None:
            summary += (
                f" The ending PR changed by "
                f"{values['change_vs_previous_percent']:+.2f}% versus the prior "
                "available observation."
            )
        evidence["summary"] = summary
        return evidence

    if "data_availability_percent" in evidence["metrics"]:
        values = evidence["metrics"]["data_availability_percent"]
        summary = (
            "Data Availability "
            f"{_aggregation_verb(values.get('aggregation', 'average'))} "
            f"{_format_evidence_value('data_availability_percent', values['period_value'])} "
            "for the selected period."
        )
        if values.get("minimum_value") is not None:
            summary += (
                " The lowest observed value was "
                f"{_format_evidence_value('data_availability_percent', values['minimum_value'])}"
                + (f" on {values['minimum_date']}" if values.get("minimum_date") else "")
                + "."
            )
        if values.get("first_value") != values.get("last_value"):
            summary += (
                " It moved from "
                f"{_format_evidence_value('data_availability_percent', values['first_value'])} "
                "to "
                f"{_format_evidence_value('data_availability_percent', values['last_value'])}."
            )
        evidence["summary"] = summary
        return evidence

    if {"generation_kwh", "gti_kwh_m2"}.issubset(evidence["metrics"]):
        generation = evidence["metrics"]["generation_kwh"]
        gti = evidence["metrics"]["gti_kwh_m2"]
        evidence["summary"] = (
            f"Generation {_aggregation_verb(generation.get('aggregation', 'sum'))} "
            f"{_format_evidence_value('generation_kwh', generation['period_value'])} "
            f"and GTI {_aggregation_verb(gti.get('aggregation', 'average'))} "
            f"{_format_evidence_value('gti_kwh_m2', gti['period_value'])} "
            "for the selected period."
        )
        return evidence

    loss_metrics = [
        metric for metric in metrics
        if metric.endswith("_loss_kwh") and metric != "total_loss_kwh"
        and metric in evidence["metrics"]
    ]
    if loss_metrics:
        dominant = max(
            loss_metrics,
            key=lambda metric: evidence["metrics"][metric]["period_value"],
        )
        total_loss = evidence["metrics"].get("total_loss_kwh", {}).get("period_value")
        if not total_loss and {
            "expected_generation_kwh",
            "generation_kwh",
        }.issubset(evidence["metrics"]):
            total_loss = (
                evidence["metrics"]["expected_generation_kwh"]["period_value"]
                - evidence["metrics"]["generation_kwh"]["period_value"]
            )
        share_text = ""
        if total_loss:
            share = evidence["metrics"][dominant]["period_value"] / total_loss * 100
            share_text = f", about {share:.0f}% of selected total losses"
        bridge_text = ""
        if {"expected_generation_kwh", "generation_kwh"}.issubset(evidence["metrics"]):
            bridge_text = (
                f"Expected Generation was "
                f"{_format_evidence_value('expected_generation_kwh', evidence['metrics']['expected_generation_kwh']['period_value'])} "
                f"and actual Generation was "
                f"{_format_evidence_value('generation_kwh', evidence['metrics']['generation_kwh']['period_value'])}. "
            )
        evidence["summary"] = (
            f"{bridge_text}"
            f"{humanize_metric(dominant)} was the largest selected loss category "
            f"at {_format_evidence_value(dominant, evidence['metrics'][dominant]['period_value'])}"
            f"{share_text}."
        )
        return evidence

    phrases = [
        f"{humanize_metric(metric)} {_aggregation_verb(values.get('aggregation', 'average'))} "
        f"{_format_evidence_value(metric, values['period_value'])}"
        for metric, values in evidence["metrics"].items()
    ]
    evidence["summary"] = (
        "For the selected period, " + ", ".join(phrases) + "."
        if phrases else "No numeric evidence is available."
    )
    return evidence


def _missing(df: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if column not in df.columns]


def _skip(component_id: str, missing_columns: list[str]) -> dict:
    return {
        "component_id": component_id,
        "reason": "missing_columns",
        "missing_columns": missing_columns,
        "message": (
            f"Cannot generate {component_id} because "
            f"{', '.join(missing_columns)} is missing."
        ),
    }


def _kpi_cards(
    df: pd.DataFrame,
    supplementary_data: dict[str, pd.DataFrame] | None = None,
) -> tuple[dict | None, dict | None]:
    available_cards = []
    latest = df.iloc[-1] if len(df) else None

    if latest is None:
        return None, _skip("kpi_cards", ["rows"])

    for column, label, unit in KPI_CARD_COLUMNS:
        if column not in df.columns:
            continue
        available_cards.append({
            "metric": column,
            "label": label,
            "value": _json_value(latest[column]),
            "unit": unit,
        })

    if not available_cards:
        return None, _skip("kpi_cards", [column for column, _, _ in KPI_CARD_COLUMNS])

    return {
        "component_id": "kpi_cards",
        "type": "kpi_cards",
        "title": "Daily KPI Summary",
        "cards": available_cards,
    }, None


def _generation_vs_gti(
    df: pd.DataFrame,
    supplementary_data: dict[str, pd.DataFrame] | None = None,
) -> tuple[dict | None, dict | None]:
    required = ["date", "generation_kwh", "gti_kwh_m2"]
    missing = _missing(df, required)
    if missing:
        return None, _skip("generation_vs_gti_chart", missing)

    return {
        "component_id": "generation_vs_gti_chart",
        "type": "bar_line",
        "title": "Generation vs GTI",
        "x": _values(df, "date"),
        "series": [
            {
                "name": "Generation",
                "metric": "generation_kwh",
                "type": "bar",
                "unit": "kWh",
                "y": _values(df, "generation_kwh"),
            },
            {
                "name": "GTI",
                "metric": "gti_kwh_m2",
                "type": "line",
                "unit": "kWh/m²",
                "y": _values(df, "gti_kwh_m2"),
                "axis": "right",
            },
        ],
    }, None


def _line_chart(
    df: pd.DataFrame,
    component_id: str,
    title: str,
    metric: str,
    label: str,
    unit: str,
    supplementary_data: dict[str, pd.DataFrame] | None = None,
) -> tuple[dict | None, dict | None]:
    required = ["date", metric]
    missing = _missing(df, required)
    if missing:
        return None, _skip(component_id, missing)

    return {
        "component_id": component_id,
        "type": "line",
        "title": title,
        "x": _values(df, "date"),
        "series": [{
            "name": label,
            "metric": metric,
            "type": "line",
            "unit": unit,
            "y": _values(df, metric),
        }],
    }, None


def _loss_breakdown(
    df: pd.DataFrame,
    supplementary_data: dict[str, pd.DataFrame] | None = None,
) -> tuple[dict | None, dict | None]:
    loss_columns = [
        ("outage_loss_kwh", "Outage Loss"),
        ("environmental_loss_kwh", "Environmental Loss"),
        ("clipping_loss_kwh", "Clipping Loss"),
        ("total_loss_kwh", "Total Loss"),
    ]
    available = [
        (column, label)
        for column, label in loss_columns
        if column in df.columns
    ]

    if "date" not in df.columns:
        return None, _skip("loss_breakdown_chart", ["date"])

    if not available:
        return None, _skip(
            "loss_breakdown_chart",
            [column for column, _ in loss_columns],
        )

    return {
        "component_id": "loss_breakdown_chart",
        "type": "stacked_bar",
        "title": "Loss Breakdown",
        "x": _values(df, "date"),
        "series": [
            {
                "name": label,
                "metric": column,
                "type": "bar",
                "unit": "kWh",
                "y": _values(df, column),
            }
            for column, label in available
        ],
    }, None


def _inv_pow_gti(
    df: pd.DataFrame,
    supplementary_data: dict[str, pd.DataFrame] | None = None,
) -> tuple[dict | None, dict | None]:
    timeseries = (supplementary_data or {}).get("daily_timeseries")
    if timeseries is None:
        return None, _skip("inv_pow_gti_chart", ["daily_timeseries"])

    required = ["timestamp", "inv_power_kw", "gti_wm2"]
    missing = _missing(timeseries, required)
    if missing:
        return None, _skip("inv_pow_gti_chart", missing)

    return {
        "component_id": "inv_pow_gti_chart",
        "type": "dual_axis_line",
        "title": "Inverter Power vs GTI",
        "metrics": ["inv_power_kw", "gti_wm2"],
        "breakdown": "site_total",
        # Preserve the interval observations used to build the initial chart.
        # Without this field the review UI falls back to "daily" and a
        # single-day regeneration collapses the two lines into one point.
        "time_grain": "raw",
        "data_coverage": _date_coverage(timeseries),
        "x": _values(timeseries, "timestamp"),
        "series": [
            {
                "name": "Inverter Power",
                "metric": "inv_power_kw",
                "type": "line",
                "unit": "kW",
                "y": _values(timeseries, "inv_power_kw"),
            },
            {
                "name": "GTI",
                "metric": "gti_wm2",
                "type": "line",
                "unit": "W/m²",
                "axis": "right",
                "y": _values(timeseries, "gti_wm2"),
            },
        ],
    }, None


def _inverter_pr_table(
    df: pd.DataFrame,
    supplementary_data: dict[str, pd.DataFrame] | None = None,
) -> tuple[dict | None, dict | None]:
    inverter_df = (supplementary_data or {}).get("inverter_performance")
    if inverter_df is None:
        return None, _skip("inverter_pr_table", ["inverter_performance"])

    required = ["inverter_id", "pr_percent"]
    missing = _missing(inverter_df, required)
    if missing:
        return None, _skip("inverter_pr_table", missing)

    columns = [
        column for column in [
            "inverter_id",
            "pr_percent",
            "status",
            "generation_kwh",
            "availability_percent",
            "deviation_from_fleet_avg_pct",
        ]
        if column in inverter_df.columns
    ]

    return {
        "component_id": "inverter_pr_table",
        "type": "table",
        "title": "Inverter PR Table",
        "columns": columns,
        "rows": [
            {
                column: _json_value(row[column])
                for column in columns
            }
            for _, row in inverter_df.iterrows()
        ],
    }, None


def _loss_waterfall(
    df: pd.DataFrame,
    supplementary_data: dict[str, pd.DataFrame] | None = None,
) -> tuple[dict | None, dict | None]:
    required = ["expected_generation_kwh", "generation_kwh"]
    missing = _missing(df, required)
    if missing:
        return None, _skip("loss_waterfall", missing)

    totals = {
        column: pd.to_numeric(df[column], errors="coerce").sum()
        for column in WATERFALL_METRICS
        if column in df.columns
    }
    steps = [{
        "label": "Expected Generation",
        "metric": "expected_generation_kwh",
        "value": _json_value(totals["expected_generation_kwh"]),
        "type": "absolute",
        "unit": "kWh",
    }]

    for column, label in [
        ("outage_loss_kwh", "Outage Loss"),
        ("environmental_loss_kwh", "Environmental Loss"),
        ("clipping_loss_kwh", "Clipping Loss"),
    ]:
        if column in totals:
            steps.append({
                "label": label,
                "metric": column,
                "value": -abs(_json_value(totals[column]) or 0),
                "type": "relative",
                "unit": "kWh",
            })

    steps.append({
        "label": "Actual Generation",
        "metric": "generation_kwh",
        "value": _json_value(totals["generation_kwh"]),
        "type": "total",
        "unit": "kWh",
    })

    return {
        "component_id": "loss_waterfall",
        "type": "waterfall",
        "title": "Generation vs Losses Waterfall",
        "steps": steps,
        "metrics": [
            metric for metric in WATERFALL_METRICS
            if metric in df.columns
        ],
    }, None


CHART_BUILDERS = {
    "kpi_cards": _kpi_cards,
    "generation_vs_gti_chart": _generation_vs_gti,
    "inv_pow_gti_chart": _inv_pow_gti,
    "inverter_pr_table": _inverter_pr_table,
    "loss_waterfall": _loss_waterfall,
    "pr_trend_chart": lambda df, supplementary_data=None: _line_chart(
        df,
        "pr_trend_chart",
        "PR Trend",
        "pr_percent",
        "PR",
        "%",
        supplementary_data,
    ),
    "specific_yield_trend_chart": lambda df, supplementary_data=None: _line_chart(
        df,
        "specific_yield_trend_chart",
        "Specific Yield Trend",
        "specific_yield_kwh_per_kwp",
        "Specific Yield",
        "kWh/kWp",
        supplementary_data,
    ),
    "data_availability_trend_chart": lambda df, supplementary_data=None: _line_chart(
        df,
        "data_availability_trend_chart",
        "Data Availability Trend",
        "data_availability_percent",
        "Data Availability",
        "%",
        supplementary_data,
    ),
    "loss_breakdown_chart": _loss_breakdown,
}


def _enrich_default_component(
    component: dict,
    daily_df: pd.DataFrame,
    supplementary_data: dict[str, pd.DataFrame] | None,
) -> dict:
    component_id = component.get("component_id")
    if component_id == "inv_pow_gti_chart":
        source_df = (supplementary_data or {}).get("daily_timeseries")
        dimension = "site_total"
    elif component_id == "inverter_pr_table":
        source_df = (supplementary_data or {}).get("inverter_performance")
        dimension = "inverter_id"
    else:
        source_df = daily_df
        dimension = "site_total"
    if source_df is None or source_df.empty:
        return component

    metrics = list(dict.fromkeys([
        *(component.get("metrics") or []),
        *[
            series.get("metric")
            for series in component.get("series", [])
            if series.get("metric")
        ],
        *[
            column for column in component.get("columns", [])
            if column in source_df.columns
            and pd.api.types.is_numeric_dtype(source_df[column])
        ],
        *[
            step.get("metric")
            for step in component.get("steps", [])
            if step.get("metric")
        ],
    ]))
    metrics = [
        metric for metric in metrics
        if metric in source_df.columns
        and pd.api.types.is_numeric_dtype(source_df[metric])
    ]
    if not metrics:
        return component

    coverage = _date_coverage(source_df)
    aggregations = {
        metric: METRIC_AGGREGATION_DEFAULTS.get(metric, "average")
        for metric in metrics
    }
    enriched = {
        **component,
        "breakdown": "site_total" if dimension == "site_total" else "inverter",
        "data_coverage": coverage,
    }
    enriched["evidence_summary"] = _component_evidence(
        component=enriched,
        plotted_df=source_df,
        source_df=source_df,
        metrics=metrics,
        dimension=dimension,
        aggregations=aggregations,
        start_date=coverage.get("start_date") if coverage else None,
        end_date=coverage.get("end_date") if coverage else None,
    )
    return enriched


def build_chart_specs(
    calculation_result_or_df: dict | pd.DataFrame,
    answer_plan: dict | None = None,
    requested_components: list[str] | None = None,
    supplementary_data: dict[str, pd.DataFrame] | None = None,
) -> dict:
    """
    Builds frontend/report-renderer chart specs from calculated KPI data.

    This function does not design pages or export images. It prepares structured
    components that answer_planner.py has requested.
    """
    df = _rows_to_dataframe(calculation_result_or_df)

    if requested_components is None:
        requested_components = (
            (answer_plan or {}).get("requested_components")
            or DEFAULT_COMPONENTS
        )

    chart_specs = []
    skipped_charts = []

    if df.empty:
        return {
            "valid": False,
            "status": "blocked",
            "chart_specs": [],
            "skipped_charts": [],
            "warnings": ["No calculated rows were provided for chart generation."],
            "action_required": [{
                "type": "calculate_kpis_first",
                "message": "Calculate KPIs before building chart specs.",
            }],
        }

    for component_id in dict.fromkeys(requested_components):
        builder = CHART_BUILDERS.get(component_id)
        if not builder:
            skipped_charts.append({
                "component_id": component_id,
                "reason": "unknown_component",
                "message": f"No chart builder exists for {component_id}.",
            })
            continue

        spec, skipped = builder(df, supplementary_data)
        if spec:
            chart_specs.append(
                _enrich_default_component(spec, df, supplementary_data)
            )
        if skipped:
            skipped_charts.append(skipped)

    return {
        "valid": True,
        "status": "ready",
        "chart_specs": chart_specs,
        "skipped_charts": skipped_charts,
        "warnings": [],
        "action_required": [],
    }


def _filter_dates(
    df: pd.DataFrame,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    date_column = next(
        (column for column in ("date", "timestamp") if column in df.columns),
        None,
    )
    if not date_column or (not start_date and not end_date):
        return df.copy()
    dates = pd.to_datetime(df[date_column], errors="coerce")
    mask = dates.notna()
    if start_date:
        mask &= dates >= pd.Timestamp(start_date)
    if end_date:
        mask &= dates < pd.Timestamp(end_date) + pd.Timedelta(days=1)
    return df.loc[mask].copy()


def _date_coverage(df: pd.DataFrame) -> dict[str, Any] | None:
    date_column = next(
        (column for column in ("timestamp", "date") if column in df.columns),
        None,
    )
    if not date_column:
        return None
    timestamps = pd.to_datetime(df[date_column], errors="coerce").dropna()
    if timestamps.empty:
        return None
    has_intraday = date_column == "timestamp" and (
        timestamps.dt.normalize() != timestamps
    ).any()
    return {
        "date_column": date_column,
        "start_date": timestamps.min().strftime("%Y-%m-%d"),
        "end_date": timestamps.max().strftime("%Y-%m-%d"),
        "native_grain": "intraday" if has_intraday else "daily",
        "time_grains": (
            ["raw", "15_minute", "hourly", "daily"]
            if has_intraday
            else ["raw", "daily"]
        ),
    }


def build_chart_capabilities(
    calculation_result_or_df: dict | pd.DataFrame,
    supplementary_data: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    """Describe what the uploaded workbook can truthfully chart."""
    source_frames = [
        ("daily_kpis", "site_total", _rows_to_dataframe(calculation_result_or_df)),
        *[
            (source_name, breakdown, (supplementary_data or {}).get(source_name))
            for source_name, breakdown in (
                ("daily_timeseries", "site_total"),
                ("inverter_performance", "inverter"),
                ("block_performance", "block"),
                ("loss_events", "loss_type"),
            )
        ],
    ]
    sources = []
    for source_name, breakdown, frame in source_frames:
        if frame is None or frame.empty:
            continue
        coverage = _date_coverage(frame)
        numeric_metrics = [
            column for column in frame.columns
            if pd.api.types.is_numeric_dtype(frame[column])
        ]
        if not coverage or not numeric_metrics:
            continue
        sources.append({
            "source": source_name,
            "breakdown": breakdown,
            "metrics": numeric_metrics,
            **coverage,
        })
    return {
        "sources": sources,
        "breakdowns": list(dict.fromkeys(
            ["site_total", *[source["breakdown"] for source in sources]]
        )),
    }


def _component_dataframe(
    calculation_result_or_df: dict | pd.DataFrame,
    supplementary_data: dict[str, pd.DataFrame] | None,
    breakdown: str,
) -> tuple[pd.DataFrame, str]:
    if breakdown == "inverter":
        inverter_df = (supplementary_data or {}).get("inverter_performance")
        if inverter_df is None:
            raise ValueError(
                "Inverter-level data is not available for this workbook and date."
            )
        return inverter_df.copy(), "inverter_id"
    if breakdown == "block":
        block_df = (supplementary_data or {}).get("block_performance")
        if block_df is None:
            raise ValueError("Block-level data is not available in this workbook.")
        return block_df.copy(), "block_id"
    if breakdown == "loss_type":
        loss_df = (supplementary_data or {}).get("loss_events")
        if loss_df is None:
            raise ValueError("Loss-event data is not available in this workbook.")
        return loss_df.copy(), "loss_type"
    return _rows_to_dataframe(calculation_result_or_df), "site_total"


def _resolved_aggregation(
    metric: str,
    aggregation: str,
    aggregations: dict[str, str] | None,
) -> str:
    requested = (aggregations or {}).get(metric, aggregation)
    if requested and requested != "auto":
        return requested
    return METRIC_AGGREGATION_DEFAULTS.get(metric, "average")


def _bucket_period(
    values: pd.Series,
    time_grain: str,
) -> pd.Series:
    timestamps = pd.to_datetime(values, errors="coerce")
    if time_grain == "15_minute":
        return timestamps.dt.floor("15min")
    if time_grain == "hourly":
        return timestamps.dt.floor("h")
    return timestamps.dt.floor("D")


def _aggregate_for_chart(
    df: pd.DataFrame,
    *,
    metrics: list[str],
    dimension: str,
    aggregation: str,
    aggregations: dict[str, str] | None,
    time_grain: str,
) -> tuple[pd.DataFrame, str | None, dict[str, str]]:
    date_column = next(
        (column for column in ("timestamp", "date") if column in df.columns),
        None,
    )
    resolved = {
        metric: _resolved_aggregation(metric, aggregation, aggregations)
        for metric in metrics
    }
    if time_grain == "raw" or not date_column:
        return df.copy(), date_column, resolved

    working = df.copy()
    working["_period"] = _bucket_period(working[date_column], time_grain)
    working = working[working["_period"].notna()]
    group_columns = ["_period"]
    if dimension != "site_total" and dimension in working.columns:
        group_columns.insert(0, dimension)
    agg_map = {
        metric: "sum" if method == "sum" else "mean"
        for metric, method in resolved.items()
    }
    aggregated = (
        working.groupby(group_columns, as_index=False, dropna=False)
        .agg(agg_map)
        .sort_values(group_columns)
    )
    return aggregated, "_period", resolved


def build_report_component(
    calculation_result_or_df: dict | pd.DataFrame,
    *,
    component_id: str,
    title: str,
    metrics: list[str],
    chart_type: str,
    start_date: str | None = None,
    end_date: str | None = None,
    breakdown: str = "site_total",
    aggregation: str = "auto",
    aggregations: dict[str, str] | None = None,
    time_grain: str = "daily",
    supplementary_data: dict[str, pd.DataFrame] | None = None,
) -> dict:
    """Regenerate one analyst-configured component from approved backend data."""
    df, dimension = _component_dataframe(
        calculation_result_or_df,
        supplementary_data,
        breakdown,
    )
    requested_metrics = [
        metric.strip() for metric in metrics if metric and metric.strip()
    ]
    if chart_type == "waterfall":
        requested_metrics = WATERFALL_METRICS.copy()
    if (
        breakdown == "site_total"
        and any(metric not in df.columns for metric in requested_metrics)
    ):
        timeseries = (supplementary_data or {}).get("daily_timeseries")
        if timeseries is not None and all(
            metric in timeseries.columns for metric in requested_metrics
        ):
            df = timeseries.copy()
    source_df = df.copy()
    source_coverage = _date_coverage(source_df)
    df = _filter_dates(df, start_date, end_date)
    if df.empty:
        available = (
            f" Available dates are {source_coverage['start_date']} to "
            f"{source_coverage['end_date']}."
            if source_coverage else ""
        )
        _raise_chart_error(
            chart_type,
            analyst_reason=(
                f"{_chart_purpose(chart_type)} This request cannot be generated "
                "for the selected period because VerityFlow did not find approved "
                "data in that date range."
                + available
            ),
            developer_reason="filtered dataframe is empty for selected date range",
            available_metrics=list(source_df.columns),
        )

    metrics = list(dict.fromkeys(requested_metrics))
    missing = [metric for metric in metrics if metric not in df.columns]
    if missing:
        if chart_type == "waterfall":
            _raise_chart_error(
                chart_type,
                analyst_reason=(
                    "This waterfall chart cannot be generated from the selected KPIs. "
                    "A waterfall chart explains how a starting value changes through "
                    "a series of positive or negative additions/subtractions to reach "
                    "a final ending total. For a generation-loss waterfall, VerityFlow "
                    "needs the starting expected generation, the loss components, and "
                    "the ending actual generation. The selected approved data does not "
                    f"include: {', '.join(humanize_metric(metric) for metric in missing)}. "
                    "Use stacked bar, bar chart, or table if you only want to compare "
                    "loss categories."
                ),
                developer_reason="missing metric columns: " + ", ".join(missing),
                recommended_options=["stacked_bar", "bar", "table"],
                available_metrics=list(df.columns),
            )
        _raise_chart_error(
            chart_type,
            analyst_reason=(
                f"{_chart_purpose(chart_type)} This request cannot be generated because the selected approved "
                "data source does not contain every KPI needed for the request. "
                f"Missing KPI(s): {', '.join(humanize_metric(metric) for metric in missing)}."
            ),
            developer_reason="missing metric columns: " + ", ".join(missing),
            available_metrics=list(df.columns),
        )
    numeric_metrics = [
        metric for metric in metrics
        if pd.api.types.is_numeric_dtype(df[metric])
    ]
    if len(numeric_metrics) != len(metrics):
        invalid = [metric for metric in metrics if metric not in numeric_metrics]
        _raise_chart_error(
            chart_type,
            analyst_reason=(
                f"{_chart_purpose(chart_type)} This request needs numeric KPI values so the backend can calculate "
                "the visual from approved data. The selected field(s) are not numeric: "
                f"{', '.join(humanize_metric(metric) for metric in invalid)}."
            ),
            developer_reason="non-numeric metric columns: " + ", ".join(invalid),
            available_metrics=list(df.columns),
        )

    if chart_type == "heatmap" and breakdown == "site_total":
        _raise_chart_error(
            chart_type,
            analyst_reason=(
                f"{_chart_purpose(chart_type)} Choose 'By inverter' or 'By block' "
                "instead of site total so VerityFlow knows what rows to compare."
            ),
            developer_reason="heatmap requested with site_total breakdown",
            available_metrics=list(df.columns),
        )
    if chart_type == "heatmap" and len(metrics) != 1:
        _raise_chart_error(
            chart_type,
            analyst_reason=(
                f"{_chart_purpose(chart_type)} A heatmap shows intensity for one KPI at a time. Select a single "
                "metric such as PR, availability, or inverter power, then choose "
                "an equipment breakdown."
            ),
            developer_reason=f"heatmap requested with {len(metrics)} metrics",
            available_metrics=list(df.columns),
        )
    if chart_type in {"bar_line", "dual_axis_line", "stacked_bar"} and len(metrics) < 2:
        _raise_chart_error(
            chart_type,
            analyst_reason=(
                f"{_chart_purpose(chart_type)} Select at least two numeric KPIs, "
                "or use a line, bar, or table when you only want to show one KPI."
            ),
            developer_reason=f"{chart_type} requested with fewer than two metrics",
            available_metrics=list(df.columns),
        )
    if chart_type == "waterfall" and breakdown != "site_total":
        _raise_chart_error(
            chart_type,
            analyst_reason=(
                f"{_chart_purpose(chart_type)} "
                "For the current VerityFlow waterfall, use the site-total breakdown so "
                "the generation bridge can be calculated consistently."
            ),
            developer_reason="waterfall requested with non-site-total breakdown",
            available_metrics=list(df.columns),
        )
    if (
        source_coverage
        and source_coverage["native_grain"] == "daily"
        and time_grain in {"15_minute", "hourly"}
    ):
        _raise_chart_error(
            chart_type,
            analyst_reason=(
                f"{_chart_purpose(chart_type)} This request asks for a more detailed time grain than the approved "
                "data contains. Daily KPI data can be shown as daily trends, bars, "
                "tables, or daily heatmaps, but it cannot be converted into hourly "
                "or 15-minute values unless that interval data is present in the source."
            ),
            developer_reason=(
                f"{time_grain} requested from daily native grain"
            ),
            available_metrics=list(df.columns),
        )

    df, date_column, resolved_aggregations = _aggregate_for_chart(
        df,
        metrics=metrics,
        dimension=dimension,
        aggregation=aggregation,
        aggregations=aggregations,
        time_grain=time_grain,
    )
    if df.empty:
        _raise_chart_error(
            chart_type,
            analyst_reason=(
                f"{_chart_purpose(chart_type)} This request could not be generated after applying the selected "
                "aggregation policy. Try a wider date range, a different time grain, "
                "or table view to inspect the approved data."
            ),
            developer_reason="aggregated dataframe is empty",
            available_metrics=list(source_df.columns),
        )

    if chart_type == "dual_axis_line" and len(df) < 2:
        _raise_chart_error(
            chart_type,
            analyst_reason=(
                f"{_chart_purpose(chart_type)} The selected date range and time "
                "grain produce only one observation, so there are not enough "
                "points to draw or compare two lines. Choose Source interval, "
                "15 minute, or Hourly for a single-day report, or select a wider "
                "date range for a Daily comparison."
            ),
            developer_reason=(
                "dual_axis_line aggregation produced fewer than two observations"
            ),
            available_metrics=list(source_df.columns),
        )

    if chart_type == "waterfall":
        spec, skipped = _loss_waterfall(
            df,
            supplementary_data,
        )
        if skipped:
            missing_columns = skipped.get("missing_columns", [])
            _raise_chart_error(
                chart_type,
                analyst_reason=(
                    "This waterfall chart cannot be generated from the selected KPIs. "
                    f"{_chart_purpose(chart_type)} For a generation-loss waterfall, VerityFlow "
                    "needs the starting expected generation, the loss components, and "
                    "the ending actual generation. The selected approved data does not "
                    f"include: {', '.join(humanize_metric(metric) for metric in missing_columns)}. "
                    "Use stacked bar, bar chart, or table if you only want to compare "
                    "loss categories."
                ),
                developer_reason=skipped["message"],
                recommended_options=["stacked_bar", "bar", "table"],
                available_metrics=list(df.columns),
            )
        component = {
            **spec,
            "component_id": component_id,
            "title": title,
            "start_date": start_date,
            "end_date": end_date,
            "breakdown": breakdown,
            "aggregations": resolved_aggregations,
            "aggregation_overrides": aggregations or {},
            "time_grain": time_grain,
            "data_coverage": source_coverage,
        }
        component["evidence_summary"] = _component_evidence(
            component=component,
            plotted_df=df,
            source_df=source_df,
            metrics=[metric for metric in WATERFALL_METRICS if metric in df.columns],
            dimension=dimension,
            aggregations=resolved_aggregations,
            start_date=start_date,
            end_date=end_date,
        )
        return component

    if chart_type == "table":
        columns = [
            column for column in (date_column, dimension, *metrics)
            if column and column != "site_total" and column in df.columns
        ]
        component = {
            "component_id": component_id,
            "type": "table",
            "title": title,
            "columns": list(dict.fromkeys(columns)),
            "rows": [
                {column: _json_value(row[column]) for column in dict.fromkeys(columns)}
                for _, row in df.iterrows()
            ],
            "metrics": metrics,
            "start_date": start_date,
            "end_date": end_date,
            "breakdown": breakdown,
            "aggregations": resolved_aggregations,
            "aggregation_overrides": aggregations or {},
            "time_grain": time_grain,
            "data_coverage": source_coverage,
        }
        component["evidence_summary"] = _component_evidence(
            component=component,
            plotted_df=df,
            source_df=source_df,
            metrics=metrics,
            dimension=dimension,
            aggregations=resolved_aggregations,
            start_date=start_date,
            end_date=end_date,
        )
        return component

    if chart_type == "heatmap":
        metric = metrics[0]
        column_source = (
            pd.to_datetime(df[date_column], errors="coerce").dt.strftime(
                "%Y-%m-%d %H:%M" if time_grain in {"raw", "15_minute", "hourly"} else "%Y-%m-%d"
            )
            if date_column
            else pd.Series(["Value"] * len(df), index=df.index)
        )
        heatmap_df = df.assign(_column=column_source).pivot_table(
            index=dimension,
            columns="_column",
            values=metric,
            aggfunc="mean",
        )
        component = {
            "component_id": component_id,
            "type": "heatmap",
            "title": title,
            "metric": metric,
            "unit": METRIC_UNITS.get(metric, ""),
            "row_dimension": dimension,
            "row_labels": [str(value) for value in heatmap_df.index],
            "column_labels": [str(value) for value in heatmap_df.columns],
            "values": [
                [_json_value(value) for value in row]
                for row in heatmap_df.to_numpy().tolist()
            ],
            "start_date": start_date,
            "end_date": end_date,
            "breakdown": breakdown,
            "aggregations": resolved_aggregations,
            "aggregation_overrides": aggregations or {},
            "time_grain": time_grain,
            "data_coverage": source_coverage,
        }
        component["evidence_summary"] = _component_evidence(
            component=component,
            plotted_df=df,
            source_df=source_df,
            metrics=metrics,
            dimension=dimension,
            aggregations=resolved_aggregations,
            start_date=start_date,
            end_date=end_date,
        )
        return component

    if date_column is None:
        if dimension == "site_total":
            raise ValueError("The selected data has no date or timestamp column.")
        x_values = [str(value) for value in df[dimension]]
    else:
        x_values = _values(df, date_column)

    series = []
    for index, metric in enumerate(metrics):
        series_type = "line"
        axis = None
        if chart_type in {"bar", "stacked_bar"}:
            series_type = "bar"
        elif chart_type == "bar_line":
            series_type = "bar" if index == 0 else "line"
            axis = "right" if index > 0 else None
        elif chart_type == "dual_axis_line":
            axis = "right" if index > 0 else None
        item = {
            "name": humanize_metric(metric),
            "metric": metric,
            "type": series_type,
            "unit": METRIC_UNITS.get(metric, ""),
            "y": _values(df, metric),
        }
        if axis:
            item["axis"] = axis
        if chart_type == "stacked_bar":
            item["stack"] = "total"
        series.append(item)

    component = {
        "component_id": component_id,
        "type": chart_type,
        "title": title,
        "x": x_values,
        "series": series,
        "metrics": metrics,
        "start_date": start_date,
        "end_date": end_date,
        "breakdown": breakdown,
        "aggregations": resolved_aggregations,
        "aggregation_overrides": aggregations or {},
        "time_grain": time_grain,
        "data_coverage": source_coverage,
    }
    component["evidence_summary"] = _component_evidence(
        component=component,
        plotted_df=df,
        source_df=source_df,
        metrics=metrics,
        dimension=dimension,
        aggregations=resolved_aggregations,
        start_date=start_date,
        end_date=end_date,
    )
    return component


def humanize_metric(metric: str) -> str:
    if metric in METRIC_LABELS:
        return METRIC_LABELS[metric]
    return " ".join(word.capitalize() for word in metric.split("_"))
