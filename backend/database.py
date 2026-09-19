import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "reportgen.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS customers (
        customer_id         TEXT PRIMARY KEY,
        customer_name       TEXT NOT NULL,
        parent_company      TEXT,
        customer_reference  TEXT,
        logo_path           TEXT,
        customer_logo_label TEXT,
        company_logo_label  TEXT,
        logo_placement      TEXT DEFAULT 'both_header',
        pr_target_pct       REAL DEFAULT 75.0,
        recipients          TEXT DEFAULT '[]',
        delivery_schedule   TEXT,
        status              TEXT DEFAULT 'pending_first_approval',
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS customer_sites (
        site_id             TEXT PRIMARY KEY,
        customer_id         TEXT NOT NULL,
        site_name           TEXT NOT NULL,
        location            TEXT,
        timezone            TEXT NOT NULL DEFAULT 'Asia/Kolkata',
        dc_capacity_kwp     REAL,
        ac_capacity_kw      REAL,
        status              TEXT DEFAULT 'active',
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );

    CREATE TABLE IF NOT EXISTS report_configurations (
        config_id            TEXT PRIMARY KEY,
        customer_id          TEXT NOT NULL,
        site_id              TEXT NOT NULL,
        report_type          TEXT NOT NULL,
        configuration_name   TEXT NOT NULL,
        reporting_period     TEXT NOT NULL DEFAULT 'daily',
        active               INTEGER DEFAULT 1,
        created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY (site_id) REFERENCES customer_sites(site_id),
        UNIQUE(site_id, report_type, configuration_name)
    );

    CREATE TABLE IF NOT EXISTS schema_mappings (
        mapping_id           INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id          TEXT NOT NULL,
        system_column        TEXT NOT NULL,
        customer_column      TEXT NOT NULL,
        data_type            TEXT DEFAULT 'numeric',
        confirmed_by_analyst INTEGER DEFAULT 0,
        created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
        UNIQUE(customer_id, system_column)
    );

    CREATE TABLE IF NOT EXISTS custom_requirements (
        req_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id     TEXT NOT NULL,
        report_type     TEXT,
        req_type        TEXT NOT NULL,
        description     TEXT,
        config          TEXT DEFAULT '{}',
        active          INTEGER DEFAULT 1,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );

    CREATE TABLE IF NOT EXISTS global_template (
        template_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        report_type       TEXT NOT NULL UNIQUE,
        kpi_definitions   TEXT DEFAULT '{}',
        chart_definitions TEXT DEFAULT '{}',
        insight_rules     TEXT DEFAULT '{}',
        layout_config     TEXT DEFAULT '{}',
        version           INTEGER DEFAULT 1,
        updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS report_history (
        report_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id        TEXT NOT NULL,
        report_date        DATE NOT NULL,
        report_type        TEXT NOT NULL,
        status             TEXT DEFAULT 'draft',
        pdf_path           TEXT,
        qa_score           REAL,
        sent_at            DATETIME,
        analyst_approved   INTEGER DEFAULT 0,
        created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );

    CREATE TABLE IF NOT EXISTS report_layouts (
        layout_id           TEXT PRIMARY KEY,
        config_id           TEXT NOT NULL,
        customer_id         TEXT NOT NULL,
        report_type         TEXT NOT NULL,
        version             INTEGER NOT NULL DEFAULT 1,
        status              TEXT NOT NULL DEFAULT 'draft',
        theme               TEXT NOT NULL DEFAULT 'corporate_blue',
        summary_position    TEXT NOT NULL DEFAULT 'top',
        layout_json         TEXT NOT NULL DEFAULT '{}',
        created_by          TEXT NOT NULL DEFAULT 'analyst',
        approved_by         TEXT,
        approved_at         DATETIME,
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (config_id) REFERENCES report_configurations(config_id),
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
        UNIQUE(config_id, version)
    );

    CREATE TABLE IF NOT EXISTS report_snapshots (
        snapshot_id          TEXT PRIMARY KEY,
        config_id            TEXT NOT NULL,
        customer_id          TEXT NOT NULL,
        report_type          TEXT NOT NULL,
        report_date          DATE NOT NULL,
        layout_id            TEXT NOT NULL,
        layout_version       INTEGER NOT NULL,
        revision             INTEGER NOT NULL DEFAULT 1,
        snapshot_json        TEXT NOT NULL,
        approved_by          TEXT NOT NULL,
        approved_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        supersedes_snapshot_id TEXT,
        FOREIGN KEY (config_id) REFERENCES report_configurations(config_id),
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY (layout_id) REFERENCES report_layouts(layout_id),
        FOREIGN KEY (supersedes_snapshot_id) REFERENCES report_snapshots(snapshot_id),
        UNIQUE(config_id, report_date, revision)
    );

    CREATE TABLE IF NOT EXISTS metric_dictionary (
        metric_id            INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name          TEXT NOT NULL,
        output_column        TEXT,
        column_category      TEXT DEFAULT 'derivable',
        formula              TEXT NOT NULL,
        input_columns        TEXT DEFAULT '[]',
        unit                 TEXT,
        good_range           TEXT,
        poor_threshold       TEXT,
        scope                TEXT DEFAULT 'global',
        customer_id          TEXT,
        report_type          TEXT,
        approved_by_analyst  INTEGER DEFAULT 0,
        created_by           TEXT DEFAULT 'system',
        created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );

    CREATE TABLE IF NOT EXISTS insight_rules (
        rule_id              INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_name            TEXT NOT NULL,
        rule_type            TEXT DEFAULT 'row_condition',
        description          TEXT,
        condition            TEXT NOT NULL,
        input_columns        TEXT DEFAULT '[]',
        thresholds           TEXT DEFAULT '{}',
        severity             TEXT DEFAULT 'medium',
        message_template     TEXT,
        suggestion_template  TEXT,
        scope                TEXT DEFAULT 'global',
        customer_id          TEXT,
        report_type          TEXT,
        approved_by_analyst  INTEGER DEFAULT 0,
        active               INTEGER DEFAULT 1,
        created_by           TEXT DEFAULT 'system',
        created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );

    CREATE TABLE IF NOT EXISTS customer_questions (
        question_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        question_text        TEXT NOT NULL,
        answer_purpose       TEXT,
        required_metrics     TEXT DEFAULT '[]',
        preferred_components TEXT DEFAULT '[]',
        scope                TEXT DEFAULT 'customer_report_type',
        customer_id          TEXT,
        report_type          TEXT,
        approved_by_analyst  INTEGER DEFAULT 0,
        active               INTEGER DEFAULT 1,
        created_by           TEXT DEFAULT 'system',
        created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );

    CREATE TABLE IF NOT EXISTS approved_context (
        context_id            TEXT PRIMARY KEY,
        customer_id           TEXT NOT NULL,
        report_type           TEXT NOT NULL,
        kpi                   TEXT NOT NULL DEFAULT 'general',
        context_type          TEXT NOT NULL,
        content               TEXT NOT NULL,
        source                TEXT,
        version               INTEGER NOT NULL DEFAULT 1,
        approved_by_analyst   INTEGER NOT NULL DEFAULT 0,
        active                INTEGER NOT NULL DEFAULT 1,
        created_by            TEXT NOT NULL DEFAULT 'system',
        created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_metric_dictionary_unique
    ON metric_dictionary (
        metric_name,
        scope,
        COALESCE(customer_id, ''),
        COALESCE(report_type, '')
    );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_insight_rules_unique
    ON insight_rules (
        rule_name,
        scope,
        COALESCE(customer_id, ''),
        COALESCE(report_type, '')
    );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_questions_unique
    ON customer_questions (
        question_text,
        scope,
        COALESCE(customer_id, ''),
        COALESCE(report_type, '')
    );

    CREATE INDEX IF NOT EXISTS idx_report_layouts_current
    ON report_layouts (config_id, status, version DESC);

    CREATE INDEX IF NOT EXISTS idx_report_snapshots_report
    ON report_snapshots (config_id, report_date, revision DESC);

    CREATE INDEX IF NOT EXISTS idx_approved_context_scope
    ON approved_context (
        customer_id,
        report_type,
        kpi,
        approved_by_analyst,
        active
    );
    """)

    ensure_customer_columns(cursor)
    ensure_metric_dictionary_columns(cursor)

    conn.commit()
    conn.close()
    print("All tables created successfully")


def ensure_customer_columns(cursor):
    cursor.execute("PRAGMA table_info(customers)")
    existing_columns = {row["name"] for row in cursor.fetchall()}

    migrations = {
        "parent_company": "ALTER TABLE customers ADD COLUMN parent_company TEXT",
        "customer_reference": (
            "ALTER TABLE customers ADD COLUMN customer_reference TEXT"
        ),
        "customer_logo_label": (
            "ALTER TABLE customers ADD COLUMN customer_logo_label TEXT"
        ),
        "company_logo_label": (
            "ALTER TABLE customers ADD COLUMN company_logo_label TEXT"
        ),
        "logo_placement": (
            "ALTER TABLE customers ADD COLUMN logo_placement TEXT DEFAULT 'both_header'"
        ),
    }

    for column, statement in migrations.items():
        if column not in existing_columns:
            cursor.execute(statement)


def ensure_metric_dictionary_columns(cursor):
    cursor.execute("PRAGMA table_info(metric_dictionary)")
    existing_columns = {row["name"] for row in cursor.fetchall()}

    migrations = {
        "output_column": "ALTER TABLE metric_dictionary ADD COLUMN output_column TEXT",
        "column_category": (
            "ALTER TABLE metric_dictionary "
            "ADD COLUMN column_category TEXT DEFAULT 'derivable'"
        ),
        "input_columns": (
            "ALTER TABLE metric_dictionary "
            "ADD COLUMN input_columns TEXT DEFAULT '[]'"
        ),
    }

    for column, statement in migrations.items():
        if column not in existing_columns:
            cursor.execute(statement)


def _decode_json_fields(row: sqlite3.Row | dict | None, *fields: str):
    if row is None:
        return None
    result = dict(row)
    for field in fields:
        value = result.get(field)
        if isinstance(value, str):
            try:
                result[field] = json.loads(value)
            except json.JSONDecodeError:
                result[field] = {}
    return result


def get_report_layout(config_id: str, include_draft: bool = True) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    status_filter = "" if include_draft else "AND status = 'approved'"
    cursor.execute(f"""
        SELECT *
        FROM report_layouts
        WHERE config_id = ? {status_filter}
        ORDER BY CASE status WHEN 'draft' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END,
                 version DESC
        LIMIT 1
    """, (config_id,))
    row = cursor.fetchone()
    conn.close()
    return _decode_json_fields(row, "layout_json")


def save_report_layout_draft(
    *,
    layout_id: str,
    config_id: str,
    customer_id: str,
    report_type: str,
    theme: str,
    summary_position: str,
    layout: dict,
    create_revision: bool = False,
    created_by: str = "analyst",
) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM report_layouts
        WHERE config_id = ?
        ORDER BY version DESC
        LIMIT 1
    """, (config_id,))
    latest = cursor.fetchone()

    if latest and latest["status"] == "draft":
        cursor.execute("""
            UPDATE report_layouts
            SET theme = ?, summary_position = ?, layout_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE layout_id = ?
        """, (
            theme,
            summary_position,
            json.dumps(layout),
            latest["layout_id"],
        ))
        saved_layout_id = latest["layout_id"]
    else:
        if latest and not create_revision:
            conn.close()
            raise ValueError(
                "The approved layout is locked. Create a new layout version to make changes."
            )
        version = int(latest["version"]) + 1 if latest else 1
        cursor.execute("""
            INSERT INTO report_layouts
            (layout_id, config_id, customer_id, report_type, version, status,
             theme, summary_position, layout_json, created_by)
            VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)
        """, (
            layout_id,
            config_id,
            customer_id,
            report_type,
            version,
            theme,
            summary_position,
            json.dumps(layout),
            created_by,
        ))
        saved_layout_id = layout_id

    conn.commit()
    cursor.execute(
        "SELECT * FROM report_layouts WHERE layout_id = ?",
        (saved_layout_id,),
    )
    saved = cursor.fetchone()
    conn.close()
    return _decode_json_fields(saved, "layout_json")


def approve_report_layout(layout_id: str, approved_by: str) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM report_layouts WHERE layout_id = ?",
        (layout_id,),
    )
    layout = cursor.fetchone()
    if layout is None:
        conn.close()
        raise ValueError("Report layout not found.")
    if layout["status"] == "approved":
        conn.close()
        return _decode_json_fields(layout, "layout_json")

    cursor.execute("""
        UPDATE report_layouts
        SET status = 'superseded', updated_at = CURRENT_TIMESTAMP
        WHERE config_id = ? AND status = 'approved'
    """, (layout["config_id"],))
    cursor.execute("""
        UPDATE report_layouts
        SET status = 'approved', approved_by = ?,
            approved_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE layout_id = ?
    """, (approved_by, layout_id))
    conn.commit()
    cursor.execute(
        "SELECT * FROM report_layouts WHERE layout_id = ?",
        (layout_id,),
    )
    approved = cursor.fetchone()
    conn.close()
    return _decode_json_fields(approved, "layout_json")


def create_report_snapshot(
    *,
    snapshot_id: str,
    config_id: str,
    customer_id: str,
    report_type: str,
    report_date: str,
    layout: dict,
    snapshot: dict,
    approved_by: str,
) -> dict:
    if layout.get("status") != "approved":
        raise ValueError("Approve the report layout before approving the report.")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT snapshot_id, revision
        FROM report_snapshots
        WHERE config_id = ? AND report_date = ?
        ORDER BY revision DESC
        LIMIT 1
    """, (config_id, report_date))
    previous = cursor.fetchone()
    revision = int(previous["revision"]) + 1 if previous else 1
    cursor.execute("""
        INSERT INTO report_snapshots
        (snapshot_id, config_id, customer_id, report_type, report_date,
         layout_id, layout_version, revision, snapshot_json, approved_by,
         supersedes_snapshot_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        snapshot_id,
        config_id,
        customer_id,
        report_type,
        report_date,
        layout["layout_id"],
        layout["version"],
        revision,
        json.dumps(snapshot),
        approved_by,
        previous["snapshot_id"] if previous else None,
    ))
    conn.commit()
    cursor.execute(
        "SELECT * FROM report_snapshots WHERE snapshot_id = ?",
        (snapshot_id,),
    )
    saved = cursor.fetchone()
    conn.close()
    return _decode_json_fields(saved, "snapshot_json")


def save_metric_definition(cursor, metric: dict):
    customer_key = metric.get("customer_id") or ""
    report_key = metric.get("report_type") or ""

    cursor.execute("""
        SELECT metric_id
        FROM metric_dictionary
        WHERE metric_name = ?
          AND scope = ?
          AND IFNULL(customer_id, '') = ?
          AND IFNULL(report_type, '') = ?
        LIMIT 1
    """, (
        metric["metric_name"],
        metric.get("scope", "global"),
        customer_key,
        report_key,
    ))
    existing = cursor.fetchone()

    values = (
        metric.get("output_column"),
        metric.get("column_category", "derivable"),
        metric.get("formula", ""),
        json.dumps(metric.get("input_columns", [])),
        metric.get("unit"),
        metric.get("good_range"),
        metric.get("poor_threshold"),
        metric.get("scope", "global"),
        metric.get("customer_id"),
        metric.get("report_type"),
        metric.get("approved_by_analyst", 0),
        metric.get("created_by", "system"),
    )

    if existing:
        cursor.execute("""
            UPDATE metric_dictionary
            SET output_column = ?,
                column_category = ?,
                formula = ?,
                input_columns = ?,
                unit = ?,
                good_range = ?,
                poor_threshold = ?,
                scope = ?,
                customer_id = ?,
                report_type = ?,
                approved_by_analyst = ?,
                created_by = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE metric_id = ?
        """, values + (existing["metric_id"],))
    else:
        cursor.execute("""
            INSERT INTO metric_dictionary
            (metric_name, output_column, column_category, formula,
             input_columns, unit, good_range, poor_threshold, scope,
             customer_id, report_type, approved_by_analyst, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            metric["metric_name"],
            *values,
        ))


def save_insight_rule(cursor, rule: dict):
    customer_key = rule.get("customer_id") or ""
    report_key = rule.get("report_type") or ""

    cursor.execute("""
        SELECT rule_id
        FROM insight_rules
        WHERE rule_name = ?
          AND scope = ?
          AND IFNULL(customer_id, '') = ?
          AND IFNULL(report_type, '') = ?
        LIMIT 1
    """, (
        rule["rule_name"],
        rule.get("scope", "global"),
        customer_key,
        report_key,
    ))
    existing = cursor.fetchone()

    values = (
        rule.get("rule_type", "row_condition"),
        rule.get("description"),
        rule["condition"],
        json.dumps(rule.get("input_columns", [])),
        json.dumps(rule.get("thresholds", {})),
        rule.get("severity", "medium"),
        rule.get("message_template"),
        rule.get("suggestion_template"),
        rule.get("scope", "global"),
        rule.get("customer_id"),
        rule.get("report_type"),
        rule.get("approved_by_analyst", 0),
        rule.get("active", 1),
        rule.get("created_by", "system"),
    )

    if existing:
        cursor.execute("""
            UPDATE insight_rules
            SET rule_type = ?,
                description = ?,
                condition = ?,
                input_columns = ?,
                thresholds = ?,
                severity = ?,
                message_template = ?,
                suggestion_template = ?,
                scope = ?,
                customer_id = ?,
                report_type = ?,
                approved_by_analyst = ?,
                active = ?,
                created_by = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE rule_id = ?
        """, values + (existing["rule_id"],))
    else:
        cursor.execute("""
            INSERT INTO insight_rules
            (rule_name, rule_type, description, condition, input_columns,
             thresholds, severity, message_template, suggestion_template,
             scope, customer_id, report_type, approved_by_analyst, active,
             created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rule["rule_name"],
            *values,
        ))


def save_customer_question(cursor, question: dict):
    customer_key = question.get("customer_id") or ""
    report_key = question.get("report_type") or ""

    cursor.execute("""
        SELECT question_id
        FROM customer_questions
        WHERE question_text = ?
          AND scope = ?
          AND IFNULL(customer_id, '') = ?
          AND IFNULL(report_type, '') = ?
        LIMIT 1
    """, (
        question["question_text"],
        question.get("scope", "customer_report_type"),
        customer_key,
        report_key,
    ))
    existing = cursor.fetchone()

    values = (
        question.get("answer_purpose"),
        json.dumps(question.get("required_metrics", [])),
        json.dumps(question.get("preferred_components", [])),
        question.get("scope", "customer_report_type"),
        question.get("customer_id"),
        question.get("report_type"),
        question.get("approved_by_analyst", 0),
        question.get("active", 1),
        question.get("created_by", "system"),
    )

    if existing:
        cursor.execute("""
            UPDATE customer_questions
            SET answer_purpose = ?,
                required_metrics = ?,
                preferred_components = ?,
                scope = ?,
                customer_id = ?,
                report_type = ?,
                approved_by_analyst = ?,
                active = ?,
                created_by = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE question_id = ?
        """, values + (existing["question_id"],))
    else:
        cursor.execute("""
            INSERT INTO customer_questions
            (question_text, answer_purpose, required_metrics,
             preferred_components, scope, customer_id, report_type,
             approved_by_analyst, active, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            question["question_text"],
            *values,
        ))


def save_approved_context(cursor, item: dict):
    """Create or update one governed context document."""
    cursor.execute("""
        INSERT INTO approved_context
        (context_id, customer_id, report_type, kpi, context_type, content,
         source, version, approved_by_analyst, active, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(context_id) DO UPDATE SET
            customer_id = excluded.customer_id,
            report_type = excluded.report_type,
            kpi = excluded.kpi,
            context_type = excluded.context_type,
            content = excluded.content,
            source = excluded.source,
            version = excluded.version,
            approved_by_analyst = excluded.approved_by_analyst,
            active = excluded.active,
            created_by = excluded.created_by,
            updated_at = CURRENT_TIMESTAMP
    """, (
        item["context_id"],
        item["customer_id"],
        item["report_type"],
        item.get("kpi", "general"),
        item["context_type"],
        item["content"],
        item.get("source"),
        item.get("version", 1),
        int(bool(item.get("approved_by_analyst", False))),
        int(bool(item.get("active", True))),
        item.get("created_by", "system"),
    ))


def get_approved_context(
    customer_id: str | None = None,
    report_type: str | None = None,
    kpis: list[str] | None = None,
    *,
    approved_only: bool = True,
) -> list[dict]:
    """
    Return active context records within the requested governance boundary.

    KPI-specific queries always include ``general`` context because reporting
    guidance and customer preferences commonly apply across all KPIs.
    """
    conn = get_connection()
    cursor = conn.cursor()
    clauses = ["active = 1"]
    params: list = []
    if customer_id is not None:
        clauses.append("customer_id = ?")
        params.append(customer_id)
    if report_type is not None:
        clauses.append("report_type = ?")
        params.append(report_type)
    if approved_only:
        clauses.append("approved_by_analyst = 1")
    if kpis:
        values = list(dict.fromkeys(["general", *kpis]))
        placeholders = ", ".join("?" for _ in values)
        clauses.append(f"kpi IN ({placeholders})")
        params.extend(values)

    cursor.execute(f"""
        SELECT *
        FROM approved_context
        WHERE {' AND '.join(clauses)}
        ORDER BY
            CASE WHEN kpi = 'general' THEN 1 ELSE 0 END,
            context_type,
            context_id
    """, tuple(params))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    for row in rows:
        row["approved_by_analyst"] = bool(row["approved_by_analyst"])
        row["active"] = bool(row["active"])
    return rows


DEMO_APPROVED_CONTEXT = [
    {
        "context_id": "alpha-pr-definition-v1",
        "customer_id": "alpha_solar",
        "report_type": "daily_generation",
        "kpi": "pr_percent",
        "context_type": "kpi_definition",
        "content": (
            "Performance ratio compares actual generation with the energy "
            "available from irradiation and installed DC capacity. Interpret "
            "PR together with irradiation, availability, losses, and inverter performance."
        ),
        "source": "Alpha Solar approved KPI definition",
        "approved_by_analyst": 1,
        "created_by": "demo_seed",
    },
    {
        "context_id": "alpha-pr-investigation-v1",
        "customer_id": "alpha_solar",
        "report_type": "daily_generation",
        "kpi": "pr_percent",
        "context_type": "interpretation_rule",
        "content": (
            "When PR is below target, compare generation against GTI, data "
            "availability, outage losses, and inverter-level performance. State a "
            "cause only when the calculated evidence supports that relationship; "
            "otherwise ask the analyst to investigate."
        ),
        "source": "Alpha Solar approved reporting rule",
        "approved_by_analyst": 1,
        "created_by": "demo_seed",
    },
    {
        "context_id": "alpha-loss-priority-v1",
        "customer_id": "alpha_solar",
        "report_type": "daily_generation",
        "kpi": "total_loss_kwh",
        "context_type": "customer_priority",
        "content": (
            "Highlight the largest loss category, its share of total loss, and "
            "the affected time or equipment when that evidence is available."
        ),
        "source": "Alpha Solar approved reporting preference",
        "approved_by_analyst": 1,
        "created_by": "demo_seed",
    },
    {
        "context_id": "alpha-reporting-guidance-v1",
        "customer_id": "alpha_solar",
        "report_type": "daily_generation",
        "kpi": "general",
        "context_type": "reporting_guideline",
        "content": (
            "Lead with the operational exception that most affected customer "
            "performance. Keep calculated facts separate from possible causes and "
            "make every material claim traceable to evidence."
        ),
        "source": "Alpha Solar approved reporting guidance",
        "approved_by_analyst": 1,
        "created_by": "demo_seed",
    },
]


def seed_demo_approved_context() -> int:
    """Upsert the demo-approved context without modifying other saved memory."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM customers WHERE customer_id = 'alpha_solar' LIMIT 1"
    )
    if cursor.fetchone() is None:
        conn.close()
        return 0
    for item in DEMO_APPROVED_CONTEXT:
        save_approved_context(cursor, item)
    conn.commit()
    conn.close()
    return len(DEMO_APPROVED_CONTEXT)


def seed_default_data():
    """
    Seeds starter data.

    Important:
    - Seeded formulas are suggestions only.
    - approved_by_analyst = 0 means the analyst has not confirmed them.
    - The calculator should warn when using unapproved formulas.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO customers
        (customer_id, customer_name, pr_target_pct, status)
        VALUES (?, ?, ?, ?)
    """, ("alpha_solar", "Alpha Solar Power Plant", 75.0, "pending_first_approval"))
    cursor.execute("""
        UPDATE customers
        SET parent_company = COALESCE(parent_company, ?)
        WHERE customer_id = ?
    """, ("Alpha Solar Operations", "alpha_solar"))
    cursor.execute("""
        INSERT OR IGNORE INTO customer_sites
        (site_id, customer_id, site_name, location, timezone, dc_capacity_kwp,
         ac_capacity_kw)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "alpha_solar_alpha_plant",
        "alpha_solar",
        "Alpha Plant",
        "India",
        "Asia/Kolkata",
        135000.0,
        110000.0,
    ))
    cursor.execute("""
        INSERT OR IGNORE INTO report_configurations
        (config_id, customer_id, site_id, report_type, configuration_name,
         reporting_period)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "alpha_solar_alpha_plant_daily_generation",
        "alpha_solar",
        "alpha_solar_alpha_plant",
        "daily_generation",
        "Daily Generation Report",
        "daily",
    ))

    mappings = [
        ("alpha_solar", "inv_power_kw", "inv_power_kw", "numeric", 0),
        ("alpha_solar", "gti_wm2", "gti_wm2", "numeric", 0),
        ("alpha_solar", "generation_kwh", "generation_kwh", "numeric", 0),
        ("alpha_solar", "gti_kwh_m2", "gti_kwh_m2", "numeric", 0),
        ("alpha_solar", "pr_percent", "pr_percent", "numeric", 0),
        ("alpha_solar", "dc_capacity_kwp", "dc_capacity_kwp", "numeric", 0),
        ("alpha_solar", "ac_capacity_kw", "ac_capacity_kw", "numeric", 0),
        ("alpha_solar", "temperature_c", "temperature_c", "numeric", 0),
        ("alpha_solar", "timestamp", "timestamp", "datetime", 0),
        ("alpha_solar", "date", "date", "date", 0),
        ("alpha_solar", "inverter_id", "inverter_id", "text", 0),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO schema_mappings
        (customer_id, system_column, customer_column, data_type, confirmed_by_analyst)
        VALUES (?, ?, ?, ?, ?)
    """, mappings)

    kpi_definitions = {
        "generation_kwh": {
            "label": "Generation",
            "unit": "kWh",
            "formula": "sum(generation_kwh)"
        },
        "gti_kwh_m2": {
            "label": "GTI",
            "unit": "kWh/m²",
            "formula": "mean(gti_kwh_m2)"
        },
        "pr_percent": {
            "label": "PR",
            "unit": "%",
            "formula": "generation_kwh / (gti_kwh_m2 * dc_capacity_kwp) * 100"
        },
        "cuf_percent": {
            "label": "CUF",
            "unit": "%",
            "formula": "generation_kwh / (ac_capacity_kw * 24) * 100"
        },
        "total_loss_kwh": {
            "label": "Total Losses",
            "unit": "kWh",
            "formula": "expected_generation_kwh - generation_kwh"
        },
        "specific_yield": {
            "label": "Specific Yield",
            "unit": "kWh/kWp",
            "formula": "generation_kwh / dc_capacity_kwp"
        }
    }

    chart_definitions = {
        "inv_pow_gti": {
            "type": "dual_axis_line",
            "x": "timestamp",
            "y1": "inv_power_kw",
            "y2": "gti_wm2",
            "title": "Inverter Power vs GTI"
        },
        "inverter_pr_table": {
            "type": "table",
            "rows": "inverter_id",
            "value": "pr_percent",
            "title": "Inverter PR Table"
        },
        "historical_bar": {
            "type": "bar_line",
            "x": "date",
            "bar": "generation_kwh",
            "line": "gti_kwh_m2",
            "title": "Historical Generation vs GTI"
        },
        "waterfall_losses": {
            "type": "waterfall",
            "categories": [
                "expected_generation_kwh",
                "outage_loss_kwh",
                "environmental_loss_kwh",
                "clipping_loss_kwh",
                "generation_kwh"
            ],
            "title": "Generation vs Losses Waterfall"
        }
    }

    insight_rules = {
        "pr_drop": {
            "condition": "pr_percent < prev_day_pr_percent * 0.90",
            "severity": "high",
            "message": "PR dropped more than 10% vs previous day"
        },
        "plant_side_event": {
            "condition": "inv_power_drop_pct > 50 AND gti_drop_pct < 20",
            "severity": "high",
            "message": "Inv_Pow dropped while GTI stayed stable, suggesting a possible plant-side event"
        },
        "weather_event": {
            "condition": "inv_power_drop_pct > 50 AND gti_drop_pct > 40",
            "severity": "low",
            "message": "Both Inv_Pow and GTI dropped, suggesting likely weather impact"
        },
        "inverter_underperformance": {
            "condition": "inv_pr < fleet_avg_pr * 0.90",
            "severity": "medium",
            "message": "Inverter PR is more than 10% below fleet average"
        },
        "empty_loss_note": {
            "condition": "(loss_event_exists = 1) AND (note IS NULL OR note = '')",
            "severity": "medium",
            "message": "Loss event recorded but no explanation note added"
        }
    }

    cursor.execute("""
        INSERT OR IGNORE INTO global_template
        (report_type, kpi_definitions, chart_definitions, insight_rules)
        VALUES (?, ?, ?, ?)
    """, (
        "daily_generation",
        json.dumps(kpi_definitions),
        json.dumps(chart_definitions),
        json.dumps(insight_rules),
    ))

    metrics = [
        {
            "metric_name": "Date",
            "output_column": "date",
            "column_category": "required_source",
            "formula": "",
            "input_columns": [],
            "unit": None,
            "good_range": None,
            "poor_threshold": None,
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "Plant ID",
            "output_column": "plant_id",
            "column_category": "required_source",
            "formula": "",
            "input_columns": [],
            "unit": None,
            "good_range": None,
            "poor_threshold": None,
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "AC Capacity",
            "output_column": "ac_capacity_kw",
            "column_category": "required_source",
            "formula": "",
            "input_columns": [],
            "unit": "kW",
            "good_range": None,
            "poor_threshold": None,
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "DC Capacity",
            "output_column": "dc_capacity_kwp",
            "column_category": "required_source",
            "formula": "",
            "input_columns": [],
            "unit": "kWp",
            "good_range": None,
            "poor_threshold": None,
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "Generation",
            "output_column": "generation_kwh",
            "column_category": "required_source",
            "formula": "",
            "input_columns": [],
            "unit": "kWh",
            "good_range": None,
            "poor_threshold": None,
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "GTI",
            "output_column": "gti_kwh_m2",
            "column_category": "required_source",
            "formula": "",
            "input_columns": [],
            "unit": "kWh/m²",
            "good_range": "5.0-8.0",
            "poor_threshold": "<3.0",
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "Expected Generation",
            "output_column": "expected_generation_kwh",
            "column_category": "derivable",
            "formula": "gti_kwh_m2 * dc_capacity_kwp * 0.80",
            "input_columns": ["gti_kwh_m2", "dc_capacity_kwp"],
            "unit": "kWh",
            "good_range": None,
            "poor_threshold": None,
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "PR",
            "output_column": "pr_percent",
            "column_category": "derivable",
            "formula": "generation_kwh / (gti_kwh_m2 * dc_capacity_kwp) * 100",
            "input_columns": ["generation_kwh", "gti_kwh_m2", "dc_capacity_kwp"],
            "unit": "%",
            "good_range": "70-85%",
            "poor_threshold": "<65%",
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "CUF",
            "output_column": "cuf_percent",
            "column_category": "derivable",
            "formula": "generation_kwh / (ac_capacity_kw * 24) * 100",
            "input_columns": ["generation_kwh", "ac_capacity_kw"],
            "unit": "%",
            "good_range": "18-25%",
            "poor_threshold": "<15%",
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "Specific Yield",
            "output_column": "specific_yield_kwh_per_kwp",
            "column_category": "derivable",
            "formula": "generation_kwh / dc_capacity_kwp",
            "input_columns": ["generation_kwh", "dc_capacity_kwp"],
            "unit": "kWh/kWp",
            "good_range": "3.5-5.0",
            "poor_threshold": "<3.0",
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "Total Losses",
            "output_column": "total_loss_kwh",
            "column_category": "derivable",
            "formula": "expected_generation_kwh - generation_kwh",
            "input_columns": ["expected_generation_kwh", "generation_kwh"],
            "unit": "kWh",
            "good_range": "0",
            "poor_threshold": ">5000",
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "Outage Loss",
            "output_column": "outage_loss_kwh",
            "column_category": "optional",
            "formula": "",
            "input_columns": [],
            "unit": "kWh",
            "good_range": None,
            "poor_threshold": None,
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "Environmental Loss",
            "output_column": "environmental_loss_kwh",
            "column_category": "optional",
            "formula": "",
            "input_columns": [],
            "unit": "kWh",
            "good_range": None,
            "poor_threshold": None,
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "Clipping Loss",
            "output_column": "clipping_loss_kwh",
            "column_category": "optional",
            "formula": "",
            "input_columns": [],
            "unit": "kWh",
            "good_range": None,
            "poor_threshold": None,
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "Data Availability",
            "output_column": "data_availability_percent",
            "column_category": "optional",
            "formula": "",
            "input_columns": [],
            "unit": "%",
            "good_range": None,
            "poor_threshold": "<98%",
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
        {
            "metric_name": "Sunshine Hours",
            "output_column": "sunshine_hours",
            "column_category": "optional",
            "formula": "",
            "input_columns": [],
            "unit": "hours",
            "good_range": None,
            "poor_threshold": None,
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "created_by": "system",
        },
    ]

    for metric in metrics:
        save_metric_definition(cursor, metric)

    rules = [
        {
            "rule_name": "PR drop vs previous day",
            "rule_type": "row_condition",
            "description": "Flags a PR drop compared with the previous day.",
            "condition": "pr_percent < prev_day_pr_percent * (1 - pr_drop_threshold_pct / 100)",
            "input_columns": ["pr_percent", "prev_day_pr_percent"],
            "thresholds": {"pr_drop_threshold_pct": 10},
            "severity": "high",
            "message_template": "PR dropped more than {pr_drop_threshold_pct}% vs previous day.",
            "suggestion_template": "Check irradiation, grid events, curtailment, and inverter availability before publishing.",
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "active": 1,
            "created_by": "system",
        },
        {
            "rule_name": "PR below minimum",
            "rule_type": "row_condition",
            "description": "Flags a day where PR is below the analyst-approved minimum.",
            "condition": "pr_percent < min_pr_percent",
            "input_columns": ["pr_percent"],
            "thresholds": {"min_pr_percent": 65},
            "severity": "high",
            "message_template": "PR is below the minimum target of {min_pr_percent}%.",
            "suggestion_template": "Add an explanation if the low PR is weather, grid, or plant-side related.",
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "active": 1,
            "created_by": "system",
        },
        {
            "rule_name": "Data availability below target",
            "rule_type": "row_condition",
            "description": "Flags poor data availability.",
            "condition": "data_availability_percent < min_data_availability_percent",
            "input_columns": ["data_availability_percent"],
            "thresholds": {"min_data_availability_percent": 98},
            "severity": "medium",
            "message_template": "Data availability is below {min_data_availability_percent}%.",
            "suggestion_template": "Mention the data gap or investigate missing telemetry before publishing.",
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "active": 1,
            "created_by": "system",
        },
        {
            "rule_name": "Total loss above target",
            "rule_type": "row_condition",
            "description": "Flags high total loss.",
            "condition": "total_loss_kwh > max_total_loss_kwh",
            "input_columns": ["total_loss_kwh"],
            "thresholds": {"max_total_loss_kwh": 250000},
            "severity": "medium",
            "message_template": "Total loss is above {max_total_loss_kwh} kWh.",
            "suggestion_template": "Add a loss breakdown or note explaining the dominant loss category.",
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "active": 1,
            "created_by": "system",
        },
        {
            "rule_name": "Specific yield below target",
            "rule_type": "row_condition",
            "description": "Flags low specific yield when that KPI is available.",
            "condition": "specific_yield_kwh_per_kwp < min_specific_yield_kwh_per_kwp",
            "input_columns": ["specific_yield_kwh_per_kwp"],
            "thresholds": {"min_specific_yield_kwh_per_kwp": 3.0},
            "severity": "medium",
            "message_template": "Specific Yield is below {min_specific_yield_kwh_per_kwp} kWh/kWp.",
            "suggestion_template": "Compare generation against GTI and plant availability before classifying the issue.",
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "active": 1,
            "created_by": "system",
        },
    ]

    for rule in rules:
        save_insight_rule(cursor, rule)

    questions = [
        {
            "question_text": "How much energy did the plant generate today?",
            "answer_purpose": "Summarise daily generation performance.",
            "required_metrics": ["date", "generation_kwh"],
            "preferred_components": ["kpi_cards", "generation_vs_gti_chart"],
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "active": 1,
            "created_by": "system",
        },
        {
            "question_text": "Did PR meet the expected target today?",
            "answer_purpose": "Compare daily PR against the analyst-approved target or rule.",
            "required_metrics": ["date", "pr_percent"],
            "preferred_components": ["kpi_cards", "pr_trend_chart"],
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "active": 1,
            "created_by": "system",
        },
        {
            "question_text": "Was generation aligned with irradiation?",
            "answer_purpose": "Compare energy generation against GTI to separate weather-driven and plant-side effects.",
            "required_metrics": ["date", "generation_kwh", "gti_kwh_m2"],
            "preferred_components": ["generation_vs_gti_chart"],
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "active": 1,
            "created_by": "system",
        },
        {
            "question_text": "Were there any major losses today?",
            "answer_purpose": "Show whether total losses or known loss categories need explanation.",
            "required_metrics": ["date", "total_loss_kwh"],
            "preferred_components": ["loss_breakdown_chart"],
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "active": 1,
            "created_by": "system",
        },
        {
            "question_text": "Was data availability acceptable?",
            "answer_purpose": "Confirm whether telemetry quality is good enough to trust the report.",
            "required_metrics": ["date", "data_availability_percent"],
            "preferred_components": ["data_availability_trend_chart"],
            "scope": "global",
            "customer_id": None,
            "report_type": "daily_generation",
            "approved_by_analyst": 0,
            "active": 1,
            "created_by": "system",
        },
    ]

    for question in questions:
        save_customer_question(cursor, question)

    # Small, explicitly approved demo corpus for the Moss vertical slice.
    # These records are business context only; operational measurements remain
    # in the deterministic calculation pipeline.
    for item in DEMO_APPROVED_CONTEXT:
        save_approved_context(cursor, item)

    conn.commit()
    conn.close()
    print("Default data seeded. All formulas are pending analyst approval.")


def get_approved_formula(metric_name, customer_id=None, report_type=None):
    """
    Returns the best available formula for a metric.

    Priority:
    1. Analyst-approved formula for this customer + report type
    2. Analyst-approved formula for this customer
    3. Analyst-approved global formula for this report type
    4. Analyst-approved global formula for any report type
    5. System suggestion for this report type, with warning
    6. System suggestion for any report type, with warning
    """
    conn = get_connection()
    cursor = conn.cursor()

    if customer_id and report_type:
        cursor.execute("""
            SELECT * FROM metric_dictionary
            WHERE metric_name = ?
              AND customer_id = ?
              AND report_type = ?
              AND approved_by_analyst = 1
            ORDER BY updated_at DESC
            LIMIT 1
        """, (metric_name, customer_id, report_type))
        row = cursor.fetchone()
        if row:
            conn.close()
            return dict(row)

    if customer_id:
        cursor.execute("""
            SELECT * FROM metric_dictionary
            WHERE metric_name = ?
              AND customer_id = ?
              AND report_type IS NULL
              AND approved_by_analyst = 1
            ORDER BY updated_at DESC
            LIMIT 1
        """, (metric_name, customer_id))
        row = cursor.fetchone()
        if row:
            conn.close()
            return dict(row)

    if report_type:
        cursor.execute("""
            SELECT * FROM metric_dictionary
            WHERE metric_name = ?
              AND scope = 'global'
              AND customer_id IS NULL
              AND report_type = ?
              AND approved_by_analyst = 1
            ORDER BY updated_at DESC
            LIMIT 1
        """, (metric_name, report_type))
        row = cursor.fetchone()
        if row:
            conn.close()
            return dict(row)

    cursor.execute("""
        SELECT * FROM metric_dictionary
        WHERE metric_name = ?
          AND scope = 'global'
          AND customer_id IS NULL
          AND report_type IS NULL
          AND approved_by_analyst = 1
        ORDER BY updated_at DESC
        LIMIT 1
    """, (metric_name,))
    row = cursor.fetchone()
    if row:
        conn.close()
        return dict(row)

    if report_type:
        cursor.execute("""
            SELECT * FROM metric_dictionary
            WHERE metric_name = ?
              AND scope = 'global'
              AND customer_id IS NULL
              AND report_type = ?
              AND approved_by_analyst = 0
            ORDER BY updated_at DESC
            LIMIT 1
        """, (metric_name, report_type))
        row = cursor.fetchone()
        if row:
            conn.close()
            result = dict(row)
            result["warning"] = (
                f"Using system-suggested formula for {metric_name}. "
                "Not yet approved by analyst."
            )
            return result

    cursor.execute("""
        SELECT * FROM metric_dictionary
        WHERE metric_name = ?
          AND scope = 'global'
          AND customer_id IS NULL
          AND approved_by_analyst = 0
        ORDER BY updated_at DESC
        LIMIT 1
    """, (metric_name,))
    row = cursor.fetchone()
    conn.close()

    if row:
        result = dict(row)
        result["warning"] = (
            f"Using system-suggested formula for {metric_name}. "
            "Not yet approved by analyst."
        )
        return result

    return None


def _metric_row_to_dict(row):
    metric = dict(row)
    try:
        metric["input_columns"] = json.loads(metric.get("input_columns") or "[]")
    except json.JSONDecodeError:
        metric["input_columns"] = []
    metric["approved_by_analyst"] = bool(metric.get("approved_by_analyst"))
    return metric


def _profile_priority(metric):
    if metric.get("customer_id") and metric.get("report_type"):
        scope_score = 4
    elif metric.get("customer_id"):
        scope_score = 3
    elif metric.get("report_type"):
        scope_score = 2
    else:
        scope_score = 1

    approval_score = 10 if metric.get("approved_by_analyst") else 0
    return approval_score + scope_score


def _insight_rule_row_to_dict(row):
    rule = dict(row)

    try:
        rule["input_columns"] = json.loads(rule.get("input_columns") or "[]")
    except json.JSONDecodeError:
        rule["input_columns"] = []

    try:
        rule["thresholds"] = json.loads(rule.get("thresholds") or "{}")
    except json.JSONDecodeError:
        rule["thresholds"] = {}

    rule["approved_by_analyst"] = bool(rule.get("approved_by_analyst"))
    rule["active"] = bool(rule.get("active"))
    return rule


def _customer_question_row_to_dict(row):
    question = dict(row)

    try:
        question["required_metrics"] = json.loads(
            question.get("required_metrics") or "[]"
        )
    except json.JSONDecodeError:
        question["required_metrics"] = []

    try:
        question["preferred_components"] = json.loads(
            question.get("preferred_components") or "[]"
        )
    except json.JSONDecodeError:
        question["preferred_components"] = []

    question["approved_by_analyst"] = bool(question.get("approved_by_analyst"))
    question["active"] = bool(question.get("active"))
    return question


def _rule_priority(rule):
    if rule.get("customer_id") and rule.get("report_type"):
        scope_score = 4
    elif rule.get("customer_id"):
        scope_score = 3
    elif rule.get("report_type"):
        scope_score = 2
    else:
        scope_score = 1

    approval_score = 10 if rule.get("approved_by_analyst") else 0
    return approval_score + scope_score


def _scoped_config_priority(item):
    if item.get("customer_id") and item.get("report_type"):
        scope_score = 4
    elif item.get("customer_id"):
        scope_score = 3
    elif item.get("report_type"):
        scope_score = 2
    else:
        scope_score = 1

    approval_score = 10 if item.get("approved_by_analyst") else 0
    return approval_score + scope_score


def get_calculation_profile(customer_id, report_type):
    """
    Returns the best metric definitions for a customer/report type.

    The profile is grouped by the analyst-controlled column category:
    required_source, derivable, optional, and reference.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM metric_dictionary
        WHERE (customer_id = ? OR customer_id IS NULL)
          AND (report_type = ? OR report_type IS NULL)
        ORDER BY updated_at DESC
    """, (customer_id, report_type))

    rows = [_metric_row_to_dict(row) for row in cursor.fetchall()]
    conn.close()

    best_by_output = {}
    for metric in rows:
        output_column = metric.get("output_column") or metric.get("metric_name")
        current = best_by_output.get(output_column)
        if current is None or _profile_priority(metric) > _profile_priority(current):
            best_by_output[output_column] = metric

    grouped = {
        "required_source": [],
        "derivable": [],
        "optional": [],
        "reference": [],
    }

    for metric in best_by_output.values():
        category = metric.get("column_category") or "derivable"
        if category not in grouped:
            grouped["reference"].append(metric)
        else:
            grouped[category].append(metric)

    return {
        "customer_id": customer_id,
        "report_type": report_type,
        "required_source": sorted(
            grouped["required_source"],
            key=lambda item: item.get("output_column") or "",
        ),
        "derivable": sorted(
            grouped["derivable"],
            key=lambda item: item.get("output_column") or "",
        ),
        "optional": sorted(
            grouped["optional"],
            key=lambda item: item.get("output_column") or "",
        ),
        "reference": sorted(
            grouped["reference"],
            key=lambda item: item.get("output_column") or "",
        ),
    }


def get_insight_rules(customer_id, report_type, include_unapproved=True):
    """
    Returns the best insight rules for a customer/report type.

    Rules are generic. A rule can target any KPI or derived field as long as the
    analyst defines its input columns, condition, thresholds, and scope.
    """
    conn = get_connection()
    cursor = conn.cursor()

    approval_filter = "" if include_unapproved else "AND approved_by_analyst = 1"

    cursor.execute(f"""
        SELECT *
        FROM insight_rules
        WHERE active = 1
          AND (customer_id = ? OR customer_id IS NULL)
          AND (report_type = ? OR report_type IS NULL)
          {approval_filter}
        ORDER BY updated_at DESC
    """, (customer_id, report_type))

    rows = [_insight_rule_row_to_dict(row) for row in cursor.fetchall()]
    conn.close()

    best_by_name = {}
    for rule in rows:
        current = best_by_name.get(rule["rule_name"])
        if current is None or _rule_priority(rule) > _rule_priority(current):
            best_by_name[rule["rule_name"]] = rule

    return {
        "customer_id": customer_id,
        "report_type": report_type,
        "rules": sorted(
            best_by_name.values(),
            key=lambda item: (item.get("severity") or "", item.get("rule_name") or ""),
        ),
    }


def get_customer_questions(customer_id, report_type, include_unapproved=True):
    """
    Returns standing report questions for a customer/report type.

    These are the questions the daily report should answer even when no unusual
    insight rule is triggered.
    """
    conn = get_connection()
    cursor = conn.cursor()

    approval_filter = "" if include_unapproved else "AND approved_by_analyst = 1"

    cursor.execute(f"""
        SELECT *
        FROM customer_questions
        WHERE active = 1
          AND (customer_id = ? OR customer_id IS NULL)
          AND (report_type = ? OR report_type IS NULL)
          {approval_filter}
        ORDER BY updated_at DESC
    """, (customer_id, report_type))

    rows = [_customer_question_row_to_dict(row) for row in cursor.fetchall()]
    conn.close()

    best_by_text = {}
    for question in rows:
        current = best_by_text.get(question["question_text"])
        if (
            current is None
            or _scoped_config_priority(question) > _scoped_config_priority(current)
        ):
            best_by_text[question["question_text"]] = question

    return {
        "customer_id": customer_id,
        "report_type": report_type,
        "questions": sorted(
            best_by_text.values(),
            key=lambda item: item.get("question_text") or "",
        ),
    }


def approve_formula(metric_name, formula, unit=None, good_range=None,
                    poor_threshold=None, scope="customer",
                    customer_id=None, report_type=None,
                    created_by="analyst", output_column=None,
                    column_category="derivable", input_columns=None):
    """
    Saves an analyst-approved formula.

    Use scope:
    - report_only
    - customer
    - report_type
    - global
    """
    conn = get_connection()
    cursor = conn.cursor()

    save_metric_definition(cursor, {
        "metric_name": metric_name,
        "output_column": output_column,
        "column_category": column_category,
        "formula": formula,
        "input_columns": input_columns or [],
        "unit": unit,
        "good_range": good_range,
        "poor_threshold": poor_threshold,
        "scope": scope,
        "customer_id": customer_id,
        "report_type": report_type,
        "approved_by_analyst": 1,
        "created_by": created_by,
    })

    conn.commit()
    conn.close()


def approve_insight_rule(rule_name, condition, input_columns,
                         thresholds=None, severity="medium",
                         message_template=None, suggestion_template=None,
                         scope="customer_report_type", customer_id=None,
                         report_type=None, rule_type="row_condition",
                         description=None, created_by="analyst", active=1):
    """
    Saves an analyst-approved insight rule.

    This supports any KPI, not only solar-specific metrics. The later insights
    engine will execute approved rules against calculated report data.
    """
    conn = get_connection()
    cursor = conn.cursor()

    save_insight_rule(cursor, {
        "rule_name": rule_name,
        "rule_type": rule_type,
        "description": description,
        "condition": condition,
        "input_columns": input_columns or [],
        "thresholds": thresholds or {},
        "severity": severity,
        "message_template": message_template,
        "suggestion_template": suggestion_template,
        "scope": scope,
        "customer_id": customer_id,
        "report_type": report_type,
        "approved_by_analyst": 1,
        "active": active,
        "created_by": created_by,
    })

    conn.commit()
    conn.close()

    return get_insight_rules(
        customer_id=customer_id,
        report_type=report_type,
        include_unapproved=True,
    )


def approve_customer_question(question_text, required_metrics,
                              preferred_components=None, answer_purpose=None,
                              scope="customer_report_type", customer_id=None,
                              report_type=None, created_by="analyst", active=1):
    """
    Saves an analyst-approved standing report question.
    """
    conn = get_connection()
    cursor = conn.cursor()

    save_customer_question(cursor, {
        "question_text": question_text,
        "answer_purpose": answer_purpose,
        "required_metrics": required_metrics or [],
        "preferred_components": preferred_components or [],
        "scope": scope,
        "customer_id": customer_id,
        "report_type": report_type,
        "approved_by_analyst": 1,
        "active": active,
        "created_by": created_by,
    })

    conn.commit()
    conn.close()

    return get_customer_questions(
        customer_id=customer_id,
        report_type=report_type,
        include_unapproved=True,
    )


if __name__ == "__main__":
    create_tables()
    seed_default_data()
