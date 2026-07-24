import os
import pandas as pd

from database import get_calculation_profile, get_connection


def _mapping_data_type(system_column: str) -> str:
    if system_column == "date":
        return "date"
    if system_column == "timestamp":
        return "datetime"
    if system_column.endswith("_id") or system_column in {"plant_id"}:
        return "text"
    return "numeric"


def standard_solar_mapping_suggestions(
    customer_id: str,
    report_type: str = "daily_generation",
) -> list[dict]:
    """
    Returns ReportGen's standard solar metric mapping candidates.

    These are not analyst-approved mappings. They are the product's known
    daily-generation schema shown so a new customer never starts from a blank
    mapping page. The analyst can keep the suggested customer column name,
    edit it, and then explicitly save approval for that customer.
    """
    profile = get_calculation_profile(customer_id, report_type)
    suggestions = []
    seen = set()

    for category in ("required_source", "derivable", "optional", "reference"):
        for metric in profile.get(category, []):
            system_column = metric.get("output_column")
            if not system_column or system_column in seen:
                continue
            seen.add(system_column)
            suggestions.append({
                "mapping_id": None,
                "customer_id": customer_id,
                "system_column": system_column,
                "customer_column": system_column,
                "data_type": _mapping_data_type(system_column),
                "column_category": category,
                "confirmed_by_analyst": False,
                "created_at": None,
                "updated_at": None,
                "source": "standard_solar_suggestion",
            })

    return sorted(suggestions, key=lambda item: item["system_column"])


def initialize_standard_solar_mappings(
    customer_id: str,
    report_type: str = "daily_generation",
) -> int:
    """
    Persists unconfirmed standard mapping candidates for a new customer.

    Existing customer-specific mappings are never overwritten.
    """
    suggestions = standard_solar_mapping_suggestions(customer_id, report_type)
    if not suggestions:
        return 0

    conn = get_connection()
    cursor = conn.cursor()
    inserted = 0
    for suggestion in suggestions:
        cursor.execute("""
            INSERT OR IGNORE INTO schema_mappings
            (customer_id, system_column, customer_column, data_type,
             confirmed_by_analyst, updated_at)
            VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
        """, (
            customer_id,
            suggestion["system_column"],
            suggestion["customer_column"],
            suggestion["data_type"],
        ))
        inserted += cursor.rowcount
    conn.commit()
    conn.close()
    return inserted


def get_column_mappings(customer_id: str) -> dict:
    """
    Loads column mappings for a customer.

    Returns:
        {
            "mappings": {system_column: customer_column},
            "confirmed": bool,
            "warnings": list[str]
        }

    If no mappings are confirmed yet, returns saved mappings as suggestions.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT system_column, customer_column, confirmed_by_analyst
        FROM schema_mappings
        WHERE customer_id = ?
        ORDER BY confirmed_by_analyst DESC, updated_at DESC
    """, (customer_id,))

    rows = cursor.fetchall()
    conn.close()

    suggestions = standard_solar_mapping_suggestions(customer_id)
    suggestion_by_system_column = {
        item["system_column"]: item
        for item in suggestions
    }
    profile_system_columns = set(suggestion_by_system_column)
    saved_by_system_column = {
        row["system_column"]: row
        for row in rows
        if not profile_system_columns or row["system_column"] in profile_system_columns
    }
    all_system_columns = sorted(
        set(saved_by_system_column) | set(suggestion_by_system_column)
    )
    blocking_system_columns = {
        system_column
        for system_column, suggestion in suggestion_by_system_column.items()
        if suggestion.get("column_category") != "derivable"
    } or set(all_system_columns)

    if not all_system_columns:
        return {
            "mappings": {},
            "confirmed": False,
            "warnings": [f"No column mappings found for customer '{customer_id}'"],
        }

    merged_mappings = {}
    unconfirmed_columns = []
    for system_column in all_system_columns:
        row = saved_by_system_column.get(system_column)
        if row:
            merged_mappings[system_column] = row["customer_column"]
            if (
                system_column in blocking_system_columns
                and row["confirmed_by_analyst"] != 1
            ):
                unconfirmed_columns.append(system_column)
        else:
            merged_mappings[system_column] = suggestion_by_system_column[system_column]["customer_column"]
            if system_column in blocking_system_columns:
                unconfirmed_columns.append(system_column)

    if not unconfirmed_columns:
        return {
            "mappings": merged_mappings,
            "confirmed": True,
            "warnings": [],
        }

    return {
        "mappings": merged_mappings,
        "confirmed": False,
        "warnings": [
            "Column mappings have not been confirmed by analyst. "
            "Using saved mappings and standard solar suggestions for now."
        ],
    }


def get_saved_mappings(customer_id: str) -> dict:
    """Returns every saved mapping for independent analyst review."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT mapping_id, customer_id, system_column, customer_column,
               data_type, confirmed_by_analyst, created_at, updated_at
        FROM schema_mappings
        WHERE customer_id = ?
        ORDER BY system_column
    """, (customer_id,))
    mappings = []
    for row in cursor.fetchall():
        item = dict(row)
        item["confirmed_by_analyst"] = bool(item["confirmed_by_analyst"])
        mappings.append(item)
    conn.close()

    suggestions = standard_solar_mapping_suggestions(customer_id)
    saved_system_columns = {item["system_column"] for item in mappings}
    mappings.extend(
        suggestion for suggestion in suggestions
        if suggestion["system_column"] not in saved_system_columns
    )
    mappings = sorted(mappings, key=lambda item: item["system_column"])

    return {
        "customer_id": customer_id,
        "mappings": mappings,
        "mapping_count": len(mappings),
        "confirmed_count": sum(item["confirmed_by_analyst"] for item in mappings),
        "all_confirmed": bool(mappings) and all(
            item["confirmed_by_analyst"] for item in mappings
        ),
    }


def reset_mappings(customer_id: str, system_columns: list[str]) -> dict:
    """Marks selected mappings unconfirmed without discarding mapping history."""
    unique_columns = list(dict.fromkeys(system_columns))
    if not unique_columns:
        return {
            "ok": False,
            "reason": "no_system_columns",
            "message": "Select at least one mapping to reset.",
        }

    placeholders = ", ".join("?" for _ in unique_columns)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        UPDATE schema_mappings
        SET confirmed_by_analyst = 0, updated_at = CURRENT_TIMESTAMP
        WHERE customer_id = ? AND system_column IN ({placeholders})
    """, (customer_id, *unique_columns))
    reset_count = cursor.rowcount
    conn.commit()
    conn.close()

    return {
        "ok": True,
        "customer_id": customer_id,
        "system_columns": unique_columns,
        "reset_count": reset_count,
    }


def apply_mapping(df: pd.DataFrame, customer_id: str) -> dict:
    """
    Maps customer column names to standard system column names.

    Returns:
        {
            "df": renamed DataFrame,
            "mapped": list of {"customer_col", "system_col"},
            "missing": list of system columns not found in data,
            "warnings": list[str],
            "confirmed": bool
        }
    """
    mapping_info = get_column_mappings(customer_id)
    mappings = mapping_info["mappings"]
    warnings = list(mapping_info["warnings"])
    confirmed = mapping_info["confirmed"]

    if not mappings:
        return {
            "df": df.copy(),
            "mapped": [],
            "missing": [],
            "warnings": warnings,
            "confirmed": False,
        }

    rename_map = {}
    mapped = []
    missing = []

    for system_col, customer_col in mappings.items():
        if customer_col in df.columns:
            rename_map[customer_col] = system_col
            mapped.append({
                "customer_col": customer_col,
                "system_col": system_col,
            })
        else:
            missing.append(system_col)

    if missing:
        warnings.append(
            "These expected system columns were not found in the uploaded data: "
            + ", ".join(missing)
        )

    renamed_df = df.rename(columns=rename_map).copy()

    return {
        "df": renamed_df,
        "mapped": mapped,
        "missing": missing,
        "warnings": warnings,
        "confirmed": confirmed,
    }


def get_mapping_summary(customer_id: str, df: pd.DataFrame) -> dict:
    """
    Produces a review summary for the analyst.

    Returns:
        {
            "found": list of {"customer_col", "system_col", "confirmed"},
            "not_found": list[str],
            "extra_columns": list[str],
            "confirmed": bool,
            "warnings": list[str]
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT system_column, customer_column, confirmed_by_analyst
        FROM schema_mappings
        WHERE customer_id = ?
        ORDER BY system_column
    """, (customer_id,))

    rows = cursor.fetchall()
    conn.close()

    found = []
    not_found = []
    mapped_customer_cols = []

    for row in rows:
        customer_col = row["customer_column"]
        system_col = row["system_column"]
        is_confirmed = bool(row["confirmed_by_analyst"])

        if customer_col in df.columns:
            found.append({
                "customer_col": customer_col,
                "system_col": system_col,
                "confirmed": is_confirmed,
            })
            mapped_customer_cols.append(customer_col)
        else:
            not_found.append(system_col)

    extra_columns = [
        col for col in df.columns
        if col not in mapped_customer_cols
    ]

    confirmed_count = sum(1 for item in found if item["confirmed"])
    all_confirmed = len(found) > 0 and confirmed_count == len(found)

    warnings = []

    if not rows:
        warnings.append(
            f"No mappings exist for customer '{customer_id}'. "
            "The analyst must map dataset columns before report generation."
        )
    elif not all_confirmed:
        warnings.append(
            f"{len(found) - confirmed_count} found mapping(s) are not yet "
            "confirmed by analyst."
        )

    if not_found:
        warnings.append(
            "These system columns were not found in uploaded data: "
            + ", ".join(not_found)
        )

    return {
        "found": found,
        "not_found": not_found,
        "extra_columns": extra_columns,
        "confirmed": all_confirmed,
        "warnings": warnings,
    }


def confirm_mappings(customer_id: str,
                     confirmed_mappings: list[dict]) -> None:
    """
    Saves analyst-confirmed column mappings.

    confirmed_mappings is a list of:
        {
            "system_column": "...",
            "customer_column": "...",
            "data_type": "numeric"
        }

    If a mapping exists, it is updated.
    If it does not exist, it is inserted.
    """
    conn = get_connection()
    cursor = conn.cursor()

    for mapping in confirmed_mappings:
        cursor.execute("""
            INSERT INTO schema_mappings
            (customer_id, system_column, customer_column, data_type,
             confirmed_by_analyst, updated_at)
            VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(customer_id, system_column)
            DO UPDATE SET
                customer_column = excluded.customer_column,
                data_type = excluded.data_type,
                confirmed_by_analyst = 1,
                updated_at = CURRENT_TIMESTAMP
        """, (
            customer_id,
            mapping["system_column"],
            mapping["customer_column"],
            mapping.get("data_type", "numeric"),
        ))

    conn.commit()
    conn.close()


def confirm_alpha_solar_daily_kpi_mappings() -> None:
    confirmed_mappings = [
        {
            "system_column": "plant_id",
            "customer_column": "plant_id",
            "data_type": "text",
        },
        {
            "system_column": "ac_capacity_kw",
            "customer_column": "ac_capacity_kw",
            "data_type": "numeric",
        },
        {
            "system_column": "date",
            "customer_column": "date",
            "data_type": "date",
        },
        {
            "system_column": "dc_capacity_kwp",
            "customer_column": "dc_capacity_kwp",
            "data_type": "numeric",
        },
        {
            "system_column": "generation_kwh",
            "customer_column": "generation_kwh",
            "data_type": "numeric",
        },
        {
            "system_column": "gti_kwh_m2",
            "customer_column": "gti_kwh_m2",
            "data_type": "numeric",
        },
        {
            "system_column": "pr_percent",
            "customer_column": "pr_percent",
            "data_type": "numeric",
        },
        {
            "system_column": "cuf_percent",
            "customer_column": "cuf_percent",
            "data_type": "numeric",
        },
        {
            "system_column": "expected_generation_kwh",
            "customer_column": "expected_generation_kwh",
            "data_type": "numeric",
        },
        {
            "system_column": "total_loss_kwh",
            "customer_column": "total_loss_kwh",
            "data_type": "numeric",
        },
        {
            "system_column": "outage_loss_kwh",
            "customer_column": "outage_loss_kwh",
            "data_type": "numeric",
        },
        {
            "system_column": "environmental_loss_kwh",
            "customer_column": "environmental_loss_kwh",
            "data_type": "numeric",
        },
        {
            "system_column": "clipping_loss_kwh",
            "customer_column": "clipping_loss_kwh",
            "data_type": "numeric",
        },
        {
            "system_column": "data_availability_percent",
            "customer_column": "data_availability_percent",
            "data_type": "numeric",
        },
        {
            "system_column": "peak_power_kw",
            "customer_column": "peak_power_kw",
            "data_type": "numeric",
        },
        {
            "system_column": "sunshine_hours",
            "customer_column": "sunshine_hours",
            "data_type": "numeric",
        },
        {
            "system_column": "prev_day_generation_kwh",
            "customer_column": "prev_day_generation_kwh",
            "data_type": "numeric",
        },
        {
            "system_column": "prev_day_pr_percent",
            "customer_column": "prev_day_pr_percent",
            "data_type": "numeric",
        },
    ]

    confirm_mappings("alpha_solar", confirmed_mappings)
    print("Confirmed alpha_solar daily_kpis mappings.")


if __name__ == "__main__":
    confirm_alpha_solar_daily_kpi_mappings()

    data_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "data",
        "Alpha_Solar_Dummy_Dataset.xlsx",
    )

    print("Loading dummy dataset...")
    df = pd.read_excel(data_path, sheet_name="daily_kpis")
    print(f"Columns in daily_kpis sheet: {list(df.columns)}")

    print("\nMapping summary for alpha_solar:")
    summary = get_mapping_summary("alpha_solar", df)

    print(f"\nFound and mapped ({len(summary['found'])}):")
    for item in summary["found"]:
        status = "[confirmed]" if item["confirmed"] else "[unconfirmed]"
        print(
            f"  {item['customer_col']:25} -> "
            f"{item['system_col']:25} {status}"
        )

    if summary["not_found"]:
        print(f"\nNot found in data ({len(summary['not_found'])}):")
        for col in summary["not_found"]:
            print(f"  [missing] {col}")

    if summary["extra_columns"]:
        print("\nExtra columns in data:")
        for col in summary["extra_columns"]:
            print(f"  - {col}")

    if summary["warnings"]:
        print("\nWarnings:")
        for warning in summary["warnings"]:
            print(f"  [warning] {warning}")

    print(f"\nAll mappings confirmed: {summary['confirmed']}")

    mapped_result = apply_mapping(df, "alpha_solar")
    print(f"\nApply mapping confirmed: {mapped_result['confirmed']}")
    print(f"Mapped columns: {mapped_result['mapped']}")
    print(f"Missing columns: {mapped_result['missing']}")
