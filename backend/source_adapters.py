import os
from pathlib import Path
from typing import Any

import pandas as pd

from storage import register_existing_workbook, save_workbook_from_frames


REQUIRED_REPORTGEN_VIEWS = {
    "daily_kpis": "reportgen_daily_kpis",
    "daily_timeseries": "reportgen_daily_timeseries",
    "inverter_performance": "reportgen_inverter_performance",
    "loss_events": "reportgen_loss_events",
    "plant_metadata": "reportgen_plant_metadata",
    "historical_performance": "reportgen_historical_performance",
}


def _demo_workbook_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "data" / "Alpha_Solar_Dummy_Dataset.xlsx")


def _date_filter_sql(date_column: str, start_date: str | None, end_date: str | None) -> tuple[str, list[Any]]:
    filters = []
    parameters: list[Any] = []
    if start_date:
        filters.append(f"DATE({date_column}) >= @start_date")
        parameters.append(("start_date", "DATE", start_date))
    if end_date:
        filters.append(f"DATE({date_column}) <= @end_date")
        parameters.append(("end_date", "DATE", end_date))
    if not filters:
        return "", parameters
    return " WHERE " + " AND ".join(filters), parameters


def connect_bigquery_source(
    *,
    project_id: str,
    dataset_id: str,
    table_map: dict[str, str] | None = None,
    plant_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    use_demo_data: bool = False,
) -> dict:
    """
    Materializes clean BigQuery views into ReportGen's existing workbook package.

    BigQuery remains the input source. Joins/transforms should happen upstream in
    BigQuery views. ReportGen reads those clean views and then runs the existing
    validation, mapping, deterministic calculation, chart, and review pipeline.
    """
    table_map = table_map or {}
    resolved_views = {
        key: table_map.get(key) or default_name
        for key, default_name in REQUIRED_REPORTGEN_VIEWS.items()
    }

    if use_demo_data or project_id.lower() in {"demo", "local_demo"}:
        file_id = register_existing_workbook(
            _demo_workbook_path(),
            "BigQuery_Demo_Alpha_Solar_ReportGen.xlsx",
        )
        return {
            "file_id": file_id,
            "filename": "BigQuery_Demo_Alpha_Solar_ReportGen.xlsx",
            "source_type": "bigquery",
            "mode": "demo",
            "message": (
                "Demo BigQuery source connected. ReportGen is using the same "
                "report-ready tables it would read from approved BigQuery views."
            ),
            "views": resolved_views,
        }

    try:
        from google.cloud import bigquery
    except Exception as exc:
        raise RuntimeError(
            "BigQuery connector is configured, but google-cloud-bigquery is not "
            "installed or Google credentials are not available. For local testing, "
            "enable demo mode; for a pilot, install google-cloud-bigquery and set "
            "GOOGLE_APPLICATION_CREDENTIALS for a read-only service account."
        ) from exc

    client = bigquery.Client(project=project_id)
    frames: dict[str, pd.DataFrame] = {}

    for sheet_name, view_name in resolved_views.items():
        date_column = "timestamp" if sheet_name == "daily_timeseries" else "date"
        fully_qualified = f"`{project_id}.{dataset_id}.{view_name}`"
        where_sql, params = _date_filter_sql(date_column, start_date, end_date)
        query = f"SELECT * FROM {fully_qualified}{where_sql}"

        query_parameters = [
            bigquery.ScalarQueryParameter(name, parameter_type, value)
            for name, parameter_type, value in params
        ]
        if plant_id:
            joiner = " WHERE " if " WHERE " not in query else " AND "
            query += f"{joiner}plant_id = @plant_id"
            query_parameters.append(bigquery.ScalarQueryParameter("plant_id", "STRING", plant_id))

        job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
        frames[sheet_name] = client.query(query, job_config=job_config).to_dataframe()

    file_id = save_workbook_from_frames(
        frames,
        f"BigQuery_{dataset_id}_ReportGen.xlsx",
    )
    return {
        "file_id": file_id,
        "filename": f"BigQuery_{dataset_id}_ReportGen.xlsx",
        "source_type": "bigquery",
        "mode": "bigquery",
        "message": "BigQuery source connected and materialized into a ReportGen-ready package.",
        "views": resolved_views,
    }
