import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import DraftReview from "./DraftReview.jsx";

const STEPS = [
  ["Customer Setup", "Choose the reporting context"],
  ["Upload & Period", "Add the workbook and period"],
  ["Validate", "Review deterministic data checks"],
  ["Mapping & Formulas", "Confirm calculation inputs"],
  ["Questions & Rules", "Approve the reporting logic"],
  ["Draft Review", "Review evidence and narrative"],
];

const fmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const humanize = (value = "") => value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const number = (value, suffix = "") => value == null ? "—" : `${fmt.format(value)}${suffix}`;
const splitMetrics = (value = "") => value.split(",").map((item) => item.trim()).filter(Boolean);
const initialsFor = (value = "Customer") => value.split(/\s+/).map((part) => part[0]).join("").slice(0, 3).toUpperCase() || "CU";

const palette = ["#0c66e4", "#e05a47", "#36b37e", "#f5a623"];
const REPORT_THEMES = [
  ["corporate_blue", "Corporate Blue", "Formal customer-ready reporting"],
  ["minimal", "Minimal", "Clean and focused on the evidence"],
  ["executive", "Executive", "Summary and decisions first"],
  ["operations", "Operations", "Dense technical and operational detail"],
];

function CartesianChart({ spec }) {
  const width = 760; const height = 280; const pad = { left: 58, right: 54, top: 20, bottom: 48 };
  const x = spec.x || []; const series = spec.series || [];
  const leftSeries = series.filter((item) => item.axis !== "right");
  const rightSeries = series.filter((item) => item.axis === "right");
  const maxFor = (items) => Math.max(1, ...items.flatMap((item) => item.y || []).filter((value) => Number.isFinite(Number(value))).map(Number));
  const stacked = spec.type === "stacked_bar";
  const stackedMax = stacked
    ? Math.max(1, ...x.map((_, index) => leftSeries.reduce(
      (total, item) => total + Math.max(0, Number(item.y?.[index] || 0)),
      0,
    )))
    : 1;
  const leftMax = stacked ? stackedMax : maxFor(leftSeries); const rightMax = maxFor(rightSeries);
  const plotW = width - pad.left - pad.right; const plotH = height - pad.top - pad.bottom;
  const pointX = (index) => pad.left + (x.length <= 1 ? plotW / 2 : (index / (x.length - 1)) * plotW);
  const pointY = (value, right = false) => pad.top + plotH - (Number(value || 0) / (right ? rightMax : leftMax)) * plotH;
  const barSeries = series.filter((item) => item.type === "bar");
  const barWidth = Math.max(3, Math.min(30, plotW / Math.max(x.length, 1) / (stacked ? 1.4 : Math.max(barSeries.length + 1, 2))));
  const tickIndexes = [...new Set([0, Math.floor((x.length - 1) / 2), x.length - 1])].filter((index) => index >= 0);
  return <div className="chart-canvas"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={spec.title}>
    {[0, .25, .5, .75, 1].map((ratio) => <line key={ratio} x1={pad.left} x2={width - pad.right} y1={pad.top + plotH * ratio} y2={pad.top + plotH * ratio} className="grid-line" />)}
    <text x={pad.left - 8} y={pad.top + 4} textAnchor="end" className="axis-label">{fmt.format(leftMax)}</text><text x={pad.left - 8} y={pad.top + plotH} textAnchor="end" className="axis-label">0</text>
    {rightSeries.length > 0 && <><text x={width - pad.right + 8} y={pad.top + 4} className="axis-label">{fmt.format(rightMax)}</text><text x={width - pad.right + 8} y={pad.top + plotH} className="axis-label">0</text></>}
    {series.map((item, seriesIndex) => item.type === "bar" ? (item.y || []).map((value, index) => {
      const prior = stacked
        ? series.slice(0, seriesIndex).filter((candidate) => candidate.type === "bar").reduce(
          (total, candidate) => total + Math.max(0, Number(candidate.y?.[index] || 0)),
          0,
        )
        : 0;
      const topValue = prior + Number(value || 0);
      const y = pointY(topValue, item.axis === "right");
      const bottom = stacked ? pointY(prior, item.axis === "right") : pad.top + plotH;
      const offset = stacked ? 0 : (seriesIndex - (barSeries.length - 1) / 2) * barWidth;
      return <rect key={`${item.metric}-${index}`} x={pointX(index) + offset - barWidth / 2} y={y} width={barWidth} height={Math.max(0, bottom - y)} rx="2" fill={palette[seriesIndex % palette.length]} opacity=".85" />;
    }) : <polyline key={item.metric || item.name} points={(item.y || []).map((value, index) => `${pointX(index)},${pointY(value, item.axis === "right")}`).join(" ")} fill="none" stroke={palette[seriesIndex % palette.length]} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />)}
    {tickIndexes.map((index) => <text key={index} x={pointX(index)} y={height - 17} textAnchor="middle" className="axis-label">{String(x[index] ?? "").replace("T", " ").slice(0, 16)}</text>)}
  </svg><div className="chart-legend">{series.map((item, index) => <span key={item.metric || item.name}><i style={{ background: palette[index % palette.length] }} />{item.name} ({item.unit})</span>)}</div></div>;
}

function WaterfallChart({ spec }) {
  const steps = spec.steps || [];
  const width = 760; const height = 290; const pad = { left: 58, right: 24, top: 24, bottom: 64 };
  let running = 0;
  const segments = steps.map((step) => {
    const value = Number(step.value || 0);
    let start = 0; let end = value;
    if (step.type === "relative") {
      start = running;
      end = running + value;
    }
    if (step.type !== "total") running = end;
    return { ...step, value, start, end };
  });
  const max = Math.max(1, ...segments.flatMap((step) => [step.start, step.end]));
  const min = Math.min(0, ...segments.flatMap((step) => [step.start, step.end]));
  const plotH = height - pad.top - pad.bottom;
  const plotW = width - pad.left - pad.right;
  const y = (value) => pad.top + ((max - value) / Math.max(max - min, 1)) * plotH;
  const slot = plotW / Math.max(segments.length, 1);
  const barWidth = Math.min(72, slot * .58);
  return <div className="chart-canvas waterfall-svg"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={spec.title}>
    {[0, .25, .5, .75, 1].map((ratio) => <line key={ratio} x1={pad.left} x2={width - pad.right} y1={pad.top + plotH * ratio} y2={pad.top + plotH * ratio} className="grid-line" />)}
    {segments.map((step, index) => {
      const x = pad.left + slot * index + slot / 2;
      const top = y(Math.max(step.start, step.end));
      const bottom = y(Math.min(step.start, step.end));
      const tone = step.value < 0 ? "#e05a47" : step.type === "total" ? "#36b37e" : "#0c66e4";
      const nextX = pad.left + slot * (index + 1) + slot / 2;
      return <g key={`${step.metric}-${index}`}>
        <rect x={x - barWidth / 2} y={top} width={barWidth} height={Math.max(2, bottom - top)} rx="3" fill={tone} opacity=".9" />
        <text x={x} y={Math.max(14, top - 7)} textAnchor="middle" className="axis-label">{fmt.format(step.value)}</text>
        <text x={x} y={height - 26} textAnchor="middle" className="axis-label">{step.label}</text>
        {index < segments.length - 1 && <line x1={x + barWidth / 2} x2={nextX - barWidth / 2} y1={y(step.end)} y2={y(step.end)} stroke="#9aa8bc" strokeDasharray="4 3" />}
      </g>;
    })}
  </svg></div>;
}

function HeatmapPreview({ spec }) {
  const rows = spec.row_labels || [];
  const cols = spec.column_labels || [];
  const values = spec.values || [];
  const flat = values.flat().filter((value) => Number.isFinite(Number(value))).map(Number);
  const min = flat.length ? Math.min(...flat) : 0;
  const max = flat.length ? Math.max(...flat) : 1;
  const toneFor = (value) => {
    const ratio = (Number(value) - min) / Math.max(max - min, 1);
    return ratio < .34 ? "low" : ratio < .67 ? "mid" : "high";
  };
  if (!rows.length || !cols.length) return <Empty>No backend heatmap values are available.</Empty>;
  return <div className="heatmap-preview"><div className="heatmap-note"><strong>{humanize(spec.metric)} by {humanize(spec.row_dimension)}</strong><span>{spec.start_date} to {spec.end_date} · Backend-generated from approved data.</span></div><div className="heatmap-grid" style={{ gridTemplateColumns: `112px repeat(${cols.length}, minmax(90px, 1fr))` }}><span />{cols.map((col) => <b key={col}>{col}</b>)}{rows.flatMap((row, rowIndex) => [<b key={`${row}-label`}>{row}</b>, ...cols.map((col, colIndex) => { const value = values[rowIndex]?.[colIndex]; return <span className={toneFor(value)} key={`${row}-${col}`}>{value == null ? "—" : `${fmt.format(value)}${spec.unit ? ` ${spec.unit}` : ""}`}</span>; })])}</div></div>;
}

function ChartRenderer({ spec }) {
  if (spec.type === "waterfall") return <WaterfallChart spec={spec} />;
  if (spec.type === "heatmap") return <HeatmapPreview spec={spec} />;
  if (["line", "bar", "dual_axis_line", "bar_line", "stacked_bar"].includes(spec.type)) return <CartesianChart spec={spec} />;
  return <Empty>Unsupported chart type: {humanize(spec.type)}</Empty>;
}

function Status({ children, tone = "neutral" }) {
  return <span className={`status ${tone}`}>{children}</span>;
}

function Button({ children, secondary = false, ...props }) {
  return <button className={secondary ? "button secondary" : "button"} {...props}>{children}</button>;
}

function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

function ValidationIssueCard({ issue }) {
  const severity = issue.severity || "warning";
  const tone = severity === "critical" ? "danger" : severity === "warning" ? "warn" : "neutral";
  const examples = Array.isArray(issue.examples) ? issue.examples : [];

  return (
    <div className={`validation-issue-card ${severity}`}>
      <div className="validation-issue-head">
        <Status tone={tone}>{severity === "critical" ? "Needs correction" : "Review"}</Status>
        <strong>{issue.title || "Data-quality issue"}</strong>
      </div>
      {issue.message && <p>{issue.message}</p>}
      <div className="validation-issue-meta">
        {issue.location && <span><b>Where:</b> {issue.location}</span>}
        {Array.isArray(issue.affects) && issue.affects.length > 0 && <span><b>Affects:</b> {issue.affects.join(", ")}</span>}
        {issue.suggested_action && <span><b>Suggested correction:</b> {issue.suggested_action}</span>}
      </div>
      {examples.length > 0 && (
        <details>
          <summary>Show example rows</summary>
          <pre>{JSON.stringify(examples, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}

function App() {
  const [step, setStep] = useState(0);
  const [customers, setCustomers] = useState([]);
  const [customerId, setCustomerId] = useState("alpha_solar");
  const [reportType, setReportType] = useState("daily_generation");
  const [customerMode, setCustomerMode] = useState("existing");
  const [customerSearch, setCustomerSearch] = useState("");
  const [customerContext, setCustomerContext] = useState(null);
  const [selectedConfigId, setSelectedConfigId] = useState("");
  const [newCustomer, setNewCustomer] = useState({
    customer_name: "",
    parent_company: "",
    customer_reference: "",
    customer_logo_label: "",
    company_logo_label: "RG",
    logo_placement: "both_header",
    site_name: "",
    location: "",
    timezone: "Asia/Kolkata",
    dc_capacity_kwp: "",
    ac_capacity_kw: "",
    report_type: "daily_generation",
    reporting_period: "daily",
    configuration_name: "Daily Generation Report",
  });
  const [reportDate, setReportDate] = useState("2025-06-14");
  const [profile, setProfile] = useState(null);
  const [file, setFile] = useState(null);
  const [fileId, setFileId] = useState("");
  const [sourceType, setSourceType] = useState("excel");
  const [sourceLabel, setSourceLabel] = useState("");
  const [bigQueryConfig, setBigQueryConfig] = useState({
    project_id: "demo",
    dataset_id: "reportgen_demo",
    plant_id: "alpha_plant",
    use_demo_data: true,
    table_map: {
      daily_kpis: "reportgen_daily_kpis",
      daily_timeseries: "reportgen_daily_timeseries",
      inverter_performance: "reportgen_inverter_performance",
      loss_events: "reportgen_loss_events",
      plant_metadata: "reportgen_plant_metadata",
      historical_performance: "reportgen_historical_performance",
    },
  });
  const [validation, setValidation] = useState(null);
  const [calculation, setCalculation] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [question, setQuestion] = useState("");
  const [mappingProfile, setMappingProfile] = useState(null);
  const [mappingDrafts, setMappingDrafts] = useState({});
  const [mappingSearch, setMappingSearch] = useState("");
  const [formulaProfile, setFormulaProfile] = useState(null);
  const [formulaDraft, setFormulaDraft] = useState(null);
  const [formulaValidation, setFormulaValidation] = useState(null);
  const [chartReview, setChartReview] = useState({});
  const [findingReview, setFindingReview] = useState({});
  const [narrativeReview, setNarrativeReview] = useState({});
  const [draftApproved, setDraftApproved] = useState(false);
  const [reportTitle, setReportTitle] = useState("Daily Solar Performance Report");
  const [reportSubtitle, setReportSubtitle] = useState("Daily generation, irradiance, PR, losses, and inverter performance");
  const [preparedBy, setPreparedBy] = useState("Deepti · Analyst");
  const [preparedFor, setPreparedFor] = useState("Alpha Solar Operations");
  const [brandScope, setBrandScope] = useState("customer_report_type");
  const [customerLogoLabel, setCustomerLogoLabel] = useState("AS");
  const [companyLogoLabel, setCompanyLogoLabel] = useState("RG");
  const [logoPlacement, setLogoPlacement] = useState("both_header");
  const [profileEditorOpen, setProfileEditorOpen] = useState(false);
  const [profileDraft, setProfileDraft] = useState(null);
  const [pendingProfileOpenCustomerId, setPendingProfileOpenCustomerId] = useState("");
  const [reportTheme, setReportTheme] = useState("corporate_blue");
  const [summaryPosition, setSummaryPosition] = useState("top");
  const [reportLayout, setReportLayout] = useState(null);

  const loadProfile = async () => {
    const data = await api.profile(customerId, reportType);
    setProfile(data);
    return data;
  };

  const loadMappings = async () => {
    const data = await api.mappings(customerId);
    setMappingProfile(data);
    setMappingDrafts(Object.fromEntries(
      (data.mappings || []).map((item) => [item.system_column, item.customer_column]),
    ));
    return data;
  };

  const loadFormulas = async () => {
    const data = await api.formulas(customerId, reportType);
    setFormulaProfile(data);
    return data;
  };

  useEffect(() => {
    api.customers().then((data) => setCustomers(data.customers || [])).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!customerId) return;
    api.customerContext(customerId).then((data) => {
      setCustomerContext(data);
      const contextCustomer = data.customer || {};
      setPreparedFor(contextCustomer.parent_company || contextCustomer.customer_name || preparedFor);
      setCustomerLogoLabel(contextCustomer.customer_logo_label || initialsFor(contextCustomer.customer_name));
      setCompanyLogoLabel(contextCustomer.company_logo_label || "RG");
      setLogoPlacement(contextCustomer.logo_placement || "both_header");
      const configuration = data.report_configurations?.find((item) => item.report_type === reportType)
        || data.report_configurations?.[0];
      if (configuration) {
        setSelectedConfigId(configuration.config_id);
        setReportType(configuration.report_type);
      }
      if (pendingProfileOpenCustomerId === customerId) {
        const primarySite = (data.sites || [])[0] || {};
        setProfileDraft({
          customer_name: contextCustomer.customer_name || "",
          parent_company: contextCustomer.parent_company || "",
          customer_reference: contextCustomer.customer_reference || "",
          customer_logo_label: contextCustomer.customer_logo_label || initialsFor(contextCustomer.customer_name),
          company_logo_label: contextCustomer.company_logo_label || "RG",
          logo_placement: contextCustomer.logo_placement || "both_header",
          site_id: primarySite.site_id || "",
          site_name: primarySite.site_name || "",
          location: primarySite.location || "",
          timezone: primarySite.timezone || "Asia/Kolkata",
          dc_capacity_kwp: primarySite.dc_capacity_kwp ?? "",
          ac_capacity_kw: primarySite.ac_capacity_kw ?? "",
        });
        setProfileEditorOpen(true);
        setPendingProfileOpenCustomerId("");
      }
    }).catch((e) => setError(e.message));
  }, [customerId, pendingProfileOpenCustomerId]);

  useEffect(() => {
    if (!selectedConfigId) {
      setReportLayout(null);
      return;
    }
    api.reportLayout(selectedConfigId).then((data) => {
      const saved = data.layout;
      setReportLayout(saved);
      if (saved) {
        setReportTheme(saved.theme || "corporate_blue");
        setSummaryPosition(saved.summary_position || "top");
        const identity = saved.layout_json?.identity || {};
        if (identity.reportTitle) setReportTitle(identity.reportTitle);
        if (identity.reportSubtitle) setReportSubtitle(identity.reportSubtitle);
        if (identity.preparedBy) setPreparedBy(identity.preparedBy);
        if (identity.preparedFor) setPreparedFor(identity.preparedFor);
      }
    }).catch((e) => setError(e.message));
  }, [selectedConfigId]);

  useEffect(() => {
    if (!customerId) return;
    Promise.all([loadProfile(), loadMappings(), loadFormulas()])
      .catch((e) => setError(e.message));
  }, [customerId, reportType]);

  const customer = customers.find((item) => item.customer_id === customerId);
  const formulaFingerprint = JSON.stringify(
    (formulaProfile?.formulas || [])
      .filter((formula) => formula.approved_by_analyst)
      .map((formula) => ({
        output: formula.output_column,
        formula: formula.formula,
        scope: formula.scope,
      }))
      .sort((a, b) => String(a.output).localeCompare(String(b.output))),
  );
  const selectedConfiguration = customerContext?.report_configurations?.find(
    (item) => item.config_id === selectedConfigId,
  );
  const mappings = mappingProfile?.mappings || [];
  const run = async (action, success) => {
    setBusy(true); setError(""); setNotice("");
    try { await action(); if (success) setNotice(success); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const uploadWorkbook = () => run(async () => {
    if (!file) throw new Error("Choose an Excel workbook first.");
    const result = await api.upload(file);
    setFileId(result.file_id); setSourceType("excel"); setSourceLabel(result.filename || file.name); setValidation(null); setCalculation(null);
    setStep(2);
  }, "Workbook uploaded and ready for validation.");

  const updateBigQueryConfig = (changes) => {
    setBigQueryConfig((current) => ({ ...current, ...changes }));
    setFileId(""); setValidation(null); setCalculation(null); setDraftApproved(false);
  };

  const updateBigQueryView = (key, value) => {
    setBigQueryConfig((current) => ({
      ...current,
      table_map: { ...current.table_map, [key]: value },
    }));
    setFileId(""); setValidation(null); setCalculation(null); setDraftApproved(false);
  };

  const connectBigQuery = () => run(async () => {
    const result = await api.connectBigQuery({
      ...bigQueryConfig,
      start_date: reportDate,
      end_date: reportDate,
    });
    setFile(null);
    setSourceType("bigquery");
    setFileId(result.file_id);
    setSourceLabel(result.mode === "demo" ? "BigQuery demo source" : `${bigQueryConfig.project_id}.${bigQueryConfig.dataset_id}`);
    setValidation(null);
    setCalculation(null);
    setStep(2);
  }, "BigQuery source connected and ready for validation.");

  const validateWorkbook = () => run(async () => {
    if (!fileId) throw new Error("Connect a data source before validation.");
    setValidation(await api.validate({ customer_id: customerId, report_type: reportType, report_date: reportDate, file_id: fileId }));
  }, "Deterministic validation completed.");

  const calculateDraft = () => run(async () => {
    if (!fileId) throw new Error("Connect a data source before creating a draft.");
    const result = await api.calculate({ customer_id: customerId, report_type: reportType, report_date: reportDate, file_id: fileId });
    const savedComponents = reportLayout?.layout_json?.components || [];
    const availableBreakdowns = result.draft?.available_breakdowns || ["site_total"];
    const resolveBreakdown = (chartType, requested = "site_total") => {
      if (availableBreakdowns.includes(requested)) return requested;
      if (chartType === "heatmap") {
        if (availableBreakdowns.includes("inverter")) return "inverter";
        if (availableBreakdowns.includes("block")) return "block";
      }
      return "site_total";
    };
    let components = [...(result.draft?.chart_specs || []), ...(result.draft?.tables || [])];
    if (savedComponents.length) {
      const generated = [];
      for (const configuration of savedComponents) {
        if (configuration.included === false || !configuration.metrics?.length) continue;
        try {
          const response = await api.generateReportComponent({
            customer_id: customerId,
            report_type: reportType,
            report_date: reportDate,
            file_id: fileId,
            component_id: configuration.componentId,
            title: configuration.title,
            metrics: configuration.metrics,
            start_date: configuration.startDate || reportDate,
            end_date: configuration.endDate || reportDate,
            breakdown: resolveBreakdown(
              configuration.chartType || "line",
              configuration.breakdown || "site_total",
            ),
            chart_type: configuration.chartType || "line",
            aggregation: "auto",
            aggregations: configuration.aggregations || {},
            time_grain: configuration.timeGrain || "daily",
          });
          generated.push(response.component);
        } catch {
          const fallback = components.find((item) => item.component_id === configuration.componentId);
          if (fallback) generated.push(fallback);
        }
      }
      if (generated.length) components = generated;
    }
    const chartSpecs = components.filter((item) => item.type !== "table");
    const tables = components.filter((item) => item.type === "table");
    const hydratedResult = {
      ...result,
      draft: { ...result.draft, chart_specs: chartSpecs, tables },
    };
    setCalculation(hydratedResult);
    const savedById = Object.fromEntries(savedComponents.map((item) => [item.componentId, item]));
    setChartReview(Object.fromEntries(components.map((item) => {
      const metrics = item.series?.map((series) => series.metric).filter(Boolean).join(", ")
        || (item.metrics || []).join(", ")
        || item.metric
        || "";
      const saved = savedById[item.component_id] || {};
      return [item.component_id, {
        included: saved.included ?? true,
        title: saved.title || item.title || humanize(item.component_id),
        metrics: saved.metrics?.join(", ") || metrics,
        startDate: saved.startDate || String(item.start_date || item.x?.[0] || reportDate).slice(0, 10),
        endDate: saved.endDate || String(item.end_date || item.x?.[item.x.length - 1] || reportDate).slice(0, 10),
        chartType: saved.chartType || item.type,
        breakdown: resolveBreakdown(
          saved.chartType || item.type,
          saved.breakdown || item.breakdown || "site_total",
        ),
        aggregations: saved.aggregations || item.aggregation_overrides || {},
        timeGrain: saved.timeGrain || item.time_grain || "daily",
        textPosition: saved.textPosition || "beside",
        explanationStatus: saved.explanationStatus || "suggested",
        explanationSignature: saved.explanationSignature || "",
        explanationEditedText: "",
        formulaFingerprint,
        width: saved.width || "full",
        section: saved.section || "performance",
      }];
    })));
    setFindingReview(Object.fromEntries((result.draft?.triggered_findings || []).map((item, index) => [item.finding_id || item.rule_id || index, true])));
    setNarrativeReview(Object.fromEntries((result.draft?.narrative_blocks || []).map((item, index) => [item.block_id || index, item.text || item.content || ""])));
    setDraftApproved(false);
    setStep(5);
  }, "Draft assembled from approved calculations and rules.");

  const generateReportComponent = async (configuration) => {
    if (!fileId) throw new Error("Connect a data source before adding report components.");
    const response = await api.generateReportComponent({
      customer_id: customerId,
      report_type: reportType,
      report_date: reportDate,
      file_id: fileId,
      component_id: configuration.componentId,
      title: configuration.title,
      metrics: configuration.metrics,
      start_date: configuration.startDate,
      end_date: configuration.endDate,
      breakdown: configuration.breakdown,
      chart_type: configuration.chartType,
      aggregation: "auto",
      aggregations: configuration.aggregations || {},
      time_grain: configuration.timeGrain || "daily",
    });
    const component = response.component;
    setCalculation((current) => {
      const draft = current?.draft || {};
      const all = [...(draft.chart_specs || []), ...(draft.tables || [])];
      const next = all.some((item) => item.component_id === component.component_id)
        ? all.map((item) => item.component_id === component.component_id ? component : item)
        : [...all, component];
      return {
        ...current,
        draft: {
          ...draft,
          chart_specs: next.filter((item) => item.type !== "table"),
          tables: next.filter((item) => item.type === "table"),
        },
      };
    });
    return component;
  };

  const saveReportLayout = async (layout, createRevision = false) => {
    if (!selectedConfigId) throw new Error("Choose a report configuration first.");
    const response = await api.saveReportLayout(selectedConfigId, {
      config_id: selectedConfigId,
      customer_id: customerId,
      report_type: reportType,
      theme: reportTheme,
      summary_position: summaryPosition,
      layout,
      create_revision: createRevision,
      created_by: preparedBy || "Analyst",
    });
    setReportLayout(response.layout);
    return response.layout;
  };

  const approveCurrentLayout = async (layoutId) => {
    const response = await api.approveReportLayout(layoutId, {
      layout_id: layoutId,
      approved_by: preparedBy || "Analyst",
    });
    setReportLayout(response.layout);
    return response.layout;
  };

  const approveReportSnapshot = async (layoutId, report) => {
    const response = await api.approveReportSnapshot({
      config_id: selectedConfigId,
      customer_id: customerId,
      report_type: reportType,
      report_date: reportDate,
      layout_id: layoutId,
      approved_by: preparedBy || "Analyst",
      report,
    });
    return response.snapshot;
  };

  const approveFormula = (metric) => run(async () => {
    await api.approveFormula({
      customer_id: customerId, report_type: reportType, metric_name: metric.metric_name,
      output_column: metric.output_column, input_columns: metric.input_columns || [], scope: "customer_report_type",
    });
    await Promise.all([loadProfile(), loadFormulas()]);
  }, `${metric.metric_name} approved.`);

  const saveMapping = (mapping) => run(async () => {
    const customerColumn = (mappingDrafts[mapping.system_column] || "").trim();
    if (!customerColumn) throw new Error("Customer column cannot be blank.");
    await api.approveMappings({
      customer_id: customerId,
      mappings: [{
        system_column: mapping.system_column,
        customer_column: customerColumn,
        data_type: mapping.data_type,
      }],
    });
    await loadMappings();
  }, `${mapping.system_column} mapping saved and confirmed.`);

  const resetMapping = (mapping) => run(async () => {
    await api.resetMappings({
      customer_id: customerId,
      system_columns: [mapping.system_column],
    });
    await loadMappings();
  }, `${mapping.system_column} now needs analyst confirmation.`);

  const openFormulaEditor = (metric = null) => {
    setFormulaValidation(null);
    setFormulaDraft(metric ? {
      metric_name: metric.metric_name || "",
      output_column: metric.output_column || "",
      formula: metric.formula || "",
      input_columns: (metric.input_columns || []).join(", "),
      unit: metric.unit || "",
      good_range: metric.good_range || "",
      poor_threshold: metric.poor_threshold || "",
      scope: metric.scope || "customer_report_type",
    } : {
      metric_name: "", output_column: "", formula: "", input_columns: "",
      unit: "", good_range: "", poor_threshold: "", scope: "customer_report_type",
    });
  };

  const formulaInputs = () => (formulaDraft?.input_columns || "")
    .split(",").map((item) => item.trim()).filter(Boolean);

  const validateFormulaDraft = async () => {
    setBusy(true); setError(""); setFormulaValidation(null);
    try {
      const result = await api.validateFormula({
        customer_id: customerId,
        report_type: reportType,
        metric_name: formulaDraft.metric_name,
        formula: formulaDraft.formula,
        input_columns: formulaInputs(),
      });
      setFormulaValidation(result);
      return result;
    } catch (e) {
      setError(e.message);
      return null;
    } finally { setBusy(false); }
  };

  const saveFormula = async () => {
    const validationResult = await validateFormulaDraft();
    if (!validationResult?.valid) return;
    await run(async () => {
      await api.approveFormula({
        customer_id: customerId,
        report_type: reportType,
        metric_name: formulaDraft.metric_name.trim(),
        output_column: formulaDraft.output_column.trim(),
        formula: formulaDraft.formula.trim(),
        input_columns: formulaInputs(),
        unit: formulaDraft.unit.trim() || null,
        good_range: formulaDraft.good_range.trim() || null,
        poor_threshold: formulaDraft.poor_threshold.trim() || null,
        scope: formulaDraft.scope,
      });
      await Promise.all([loadProfile(), loadFormulas()]);
      setFormulaDraft(null); setFormulaValidation(null);
    }, `${formulaDraft.metric_name} formula saved and approved.`);
  };

  const approveRule = (rule) => run(async () => {
    await api.approveRule({
      rule_id: rule.rule_id, customer_id: customerId, report_type: reportType,
      severity: rule.severity || "medium", scope: "customer_report_type",
    });
    await loadProfile();
  }, `${rule.rule_name} approved.`);

  const addQuestion = () => run(async () => {
    if (!question.trim()) throw new Error("Enter a standing customer question.");
    await api.approveQuestion({
      question_text: question.trim(), customer_id: customerId, report_type: reportType,
      scope: "customer_report_type", required_metrics: [], preferred_components: [],
    });
    setQuestion(""); await loadProfile();
  }, "Standing question approved and saved.");

  const approveSuggestedQuestion = (item) => run(async () => {
    await api.approveQuestion({
      question_text: item.question_text,
      customer_id: customerId,
      report_type: reportType,
      scope: item.scope || "customer_report_type",
      required_metrics: item.required_metrics || [],
      preferred_components: item.preferred_components || [],
    });
    await loadProfile();
  }, "Standing question approved and saved.");

  const openCustomerProfile = (event) => {
    event?.stopPropagation?.();
    const contextCustomer = customerContext?.customer || customer || {};
    const primarySite = (customerContext?.sites || [])[0] || {};
    setProfileDraft({
      customer_name: contextCustomer.customer_name || "",
      parent_company: contextCustomer.parent_company || "",
      customer_reference: contextCustomer.customer_reference || "",
      customer_logo_label: contextCustomer.customer_logo_label || initialsFor(contextCustomer.customer_name),
      company_logo_label: contextCustomer.company_logo_label || "RG",
      logo_placement: contextCustomer.logo_placement || "both_header",
      site_id: primarySite.site_id || "",
      site_name: primarySite.site_name || "",
      location: primarySite.location || "",
      timezone: primarySite.timezone || "Asia/Kolkata",
      dc_capacity_kwp: primarySite.dc_capacity_kwp ?? "",
      ac_capacity_kw: primarySite.ac_capacity_kw ?? "",
    });
    setProfileEditorOpen(true);
  };

  const updateProfileDraft = (changes) => {
    setProfileDraft((current) => ({ ...current, ...changes }));
  };

  const saveCustomerProfile = () => run(async () => {
    if (!customerId || !profileDraft) throw new Error("Choose a customer first.");
    if (!profileDraft.customer_name.trim() || !profileDraft.site_name.trim()) {
      throw new Error("Customer name and site name are required.");
    }
    await api.updateCustomerProfile(customerId, {
      ...profileDraft,
      customer_name: profileDraft.customer_name.trim(),
      parent_company: profileDraft.parent_company.trim() || null,
      customer_reference: profileDraft.customer_reference.trim() || null,
      customer_logo_label: profileDraft.customer_logo_label.trim() || initialsFor(profileDraft.customer_name),
      company_logo_label: profileDraft.company_logo_label.trim() || "RG",
      site_name: profileDraft.site_name.trim(),
      location: profileDraft.location.trim() || null,
      dc_capacity_kwp: profileDraft.dc_capacity_kwp ? Number(profileDraft.dc_capacity_kwp) : null,
      ac_capacity_kw: profileDraft.ac_capacity_kw ? Number(profileDraft.ac_capacity_kw) : null,
    });
    const [refreshedCustomers, refreshedContext] = await Promise.all([
      api.customers(),
      api.customerContext(customerId),
    ]);
    setCustomers(refreshedCustomers.customers || []);
    setCustomerContext(refreshedContext);
    const savedCustomer = refreshedContext.customer || {};
    setPreparedFor(savedCustomer.parent_company || savedCustomer.customer_name);
    setCustomerLogoLabel(savedCustomer.customer_logo_label || initialsFor(savedCustomer.customer_name));
    setCompanyLogoLabel(savedCustomer.company_logo_label || "RG");
    setLogoPlacement(savedCustomer.logo_placement || "both_header");
    setProfileEditorOpen(false);
  }, "Customer profile and branding saved.");

  const selectCustomer = (item) => {
    setCustomerId(item.customer_id);
    setCustomerMode("existing");
    setPreparedFor(item.parent_company || item.customer_name);
    setCustomerLogoLabel(item.customer_logo_label || initialsFor(item.customer_name));
    setCompanyLogoLabel(item.company_logo_label || "RG");
    setLogoPlacement(item.logo_placement || "both_header");
    setProfileEditorOpen(false);
    setFile(null); setFileId(""); setValidation(null); setCalculation(null);
  };

  const chooseConfiguration = (configuration) => {
    setSelectedConfigId(configuration.config_id);
    setReportType(configuration.report_type);
    setFile(null); setFileId(""); setValidation(null); setCalculation(null);
  };

  const updateNewCustomer = (changes) => {
    setNewCustomer((current) => ({ ...current, ...changes }));
  };

  const createCustomer = () => run(async () => {
    if (!newCustomer.customer_name.trim() || !newCustomer.site_name.trim()) {
      throw new Error("Customer name and site name are required.");
    }
    const result = await api.createCustomer({
      ...newCustomer,
      customer_name: newCustomer.customer_name.trim(),
      parent_company: newCustomer.parent_company.trim() || null,
      customer_reference: newCustomer.customer_reference.trim() || null,
      site_name: newCustomer.site_name.trim(),
      location: newCustomer.location.trim() || null,
      dc_capacity_kwp: newCustomer.dc_capacity_kwp ? Number(newCustomer.dc_capacity_kwp) : null,
      ac_capacity_kw: newCustomer.ac_capacity_kw ? Number(newCustomer.ac_capacity_kw) : null,
    });
    const refreshed = await api.customers();
    setCustomers(refreshed.customers || []);
    setCustomerId(result.customer_id);
    setReportType(result.report_type);
    setSelectedConfigId(result.config_id);
    setPreparedFor(newCustomer.parent_company.trim() || newCustomer.customer_name.trim());
    setCustomerLogoLabel(newCustomer.customer_logo_label || initialsFor(newCustomer.customer_name));
    setCompanyLogoLabel(newCustomer.company_logo_label || "RG");
    setLogoPlacement(newCustomer.logo_placement || "both_header");
    setCustomerMode("existing");
    setStep(1);
  }, "Customer, first site, and Daily Generation Report configuration created.");

  const pageTitle = STEPS[step][0];
  const ready = Boolean(fileId && validation?.valid);
  const hasExistingContext = Boolean(customerId && selectedConfigId);
  const hasNewCustomerBasics = Boolean(newCustomer.customer_name.trim() && newCustomer.site_name.trim());
  const canContinue = step === 0
    ? customerMode === "existing" ? hasExistingContext : hasNewCustomerBasics
    : step === 1 ? Boolean(fileId)
      : step === 2 ? Boolean(validation)
        : step !== STEPS.length - 1;
  const continueHelp = step === 1 && !fileId
    ? "Connect a data source before validation."
    : step === 2 && !validation
      ? "Run validation before continuing."
      : "";
  const filteredMappings = mappings.filter((item) => {
    const query = mappingSearch.trim().toLowerCase();
    return !query || item.system_column.toLowerCase().includes(query)
      || item.customer_column.toLowerCase().includes(query);
  });
  const filteredCustomers = customers.filter((item) => {
    const query = customerSearch.trim().toLowerCase();
    return !query || [
      item.customer_name,
      item.parent_company,
      item.customer_reference,
    ].some((value) => String(value || "").toLowerCase().includes(query));
  });
  const contextLabel = customerMode === "new" && step === 0
    ? "New customer · First report setup"
    : `${customer?.customer_name || "Select customer"} · ${selectedConfiguration?.configuration_name || humanize(reportType)}`;
  const dataQualityIssues = validation?.summary?.data_quality_issues || [];
  const validationFallbackMessages = validation
    ? [...(validation.errors || []), ...(validation.warnings || [])]
    : [];

  return (
    <div className="product-shell">
      <header className="product-header">
        <div className="product-brand"><span className="product-logo">▥</span><strong>ReportGen</strong></div>
        <div className="analyst-menu"><button aria-label="Help">?</button><span className="avatar">DP</span><span><strong>Deepti</strong><small>Analyst</small></span><b>⌄</b></div>
      </header>
      <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">RG</span><div><strong>ReportGen</strong><small>Analyst workspace</small></div></div>
        <nav aria-label="Workflow steps">
          {STEPS.map(([title, subtitle], index) => (
            <button key={title} className={`step ${step === index ? "active" : ""} ${step > index ? "done" : ""}`} onClick={() => setStep(index)}>
              <span className="step-number">{step > index ? "✓" : index + 1}</span>
              <span><strong>{title}</strong><small>{subtitle}</small></span>
            </button>
          ))}
        </nav>
        <div className="principle"><strong>Analyst defines and approves.</strong><span>Python calculates and checks. AI may explain later.</span></div>
      </aside>

      <main>
        <header className="topbar"><div><p className="eyebrow">{contextLabel}</p><h1>{pageTitle}</h1></div>{step > 0 && <Status tone={profile?.pending_approval_count ? "warn" : "success"}>{profile?.pending_approval_count || 0} pending approvals</Status>}</header>
        {error && <div className="alert error">{error}</div>}
        {notice && <div className="alert success">{notice}</div>}

        {step === 0 && (
          <section className="customer-setup">
            <div className="setup-intro"><h2>Who is this report for?</h2><p>Select an existing customer or create a new customer profile.</p></div>
            <div className="customer-mode-grid">
              <button className={`customer-mode-card ${customerMode === "existing" ? "active" : ""}`} onClick={() => setCustomerMode("existing")}><span className="choice-radio" /><span><strong>Existing customer</strong><small>Load saved sites, report configurations, and reporting memory.</small></span></button>
              <button className={`customer-mode-card ${customerMode === "new" ? "active" : ""}`} onClick={() => setCustomerMode("new")}><span className="choice-radio" /><span><strong>New customer</strong><small>Create the customer and configure their first report.</small></span></button>
            </div>

            {customerMode === "existing" ? (
              <div className="existing-customer-flow">
                <label className="customer-search">Find customer<div className="search-field"><input value={customerSearch} onChange={(event) => setCustomerSearch(event.target.value)} placeholder="Search by customer, company, or plant…" /><span>⌕</span></div></label>
                <div className="customer-results">
                  {filteredCustomers.map((item) => <button key={item.customer_id} className={`customer-result ${customerId === item.customer_id ? "selected" : ""}`} onClick={() => selectCustomer(item)}><span className="customer-building">{item.customer_logo_label || initialsFor(item.customer_name)}</span><span><strong>{item.customer_name}</strong><small>{item.parent_company ? `Parent company: ${item.parent_company}` : "Independent customer"}</small><em>{item.site_count || 0} site{item.site_count === 1 ? "" : "s"} · {item.configuration_count || 0} active report configuration{item.configuration_count === 1 ? "" : "s"}</em></span><span className="profile-link" onClick={(event) => { event.stopPropagation(); selectCustomer(item); setPendingProfileOpenCustomerId(item.customer_id); }}>View / edit profile ↗</span></button>)}
                  {!filteredCustomers.length && <Empty>No customer matches this search.</Empty>}
                </div>

                {customer && <div className="configuration-picker"><h3>Choose site and report configuration</h3>{(customerContext?.report_configurations || []).map((configuration) => {
                  const selected = selectedConfigId === configuration.config_id;
                  const pending = profile?.pending_approval_count || 0;
                  return <button key={configuration.config_id} className={`configuration-option ${selected ? "selected" : ""}`} onClick={() => chooseConfiguration(configuration)}><span className="choice-radio" /><span><small>Site</small><strong>{configuration.site_name}</strong></span><span><small>Report</small><strong>{configuration.configuration_name}</strong></span><span><small>Frequency</small><strong>{humanize(configuration.reporting_period)}</strong></span><Status tone={pending ? "warn" : "success"}>{pending ? "Setup required" : "Ready"}</Status><span className="memory-count">{mappingProfile?.confirmed_count || 0} mappings · {formulaProfile?.approved_count || 0} formulas · {(profile?.customer_questions || []).filter((item) => item.approved_by_analyst).length} questions · {(profile?.insight_rules || []).filter((item) => item.approved_by_analyst).length} rules</span></button>;
                })}{!customerContext?.report_configurations?.length && <div className="empty-configuration">No report configuration exists for this customer yet.</div>}
                  <button className="create-configuration" onClick={() => setNotice("Additional report configurations will follow the Daily Generation MVP.")}>＋ <span>Create another report configuration</span></button>
                  <div className="context-actions"><button onClick={() => setNotice("Additional site setup will follow the Daily Generation MVP.")}>＋ Add new site</button><button onClick={openCustomerProfile}>✎ Edit customer profile</button></div>
                </div>}
                {profileEditorOpen && profileDraft && <article className="card customer-profile-editor"><div className="card-title-row"><div><h3>Customer profile memory</h3><p>Changes saved here become the default context and branding for this customer.</p></div><button className="close-editor" onClick={() => setProfileEditorOpen(false)}>×</button></div><div className="setup-form-grid three"><label>Customer name*<input value={profileDraft.customer_name} onChange={(event) => updateProfileDraft({ customer_name: event.target.value })} /></label><label>Parent company<input value={profileDraft.parent_company} onChange={(event) => updateProfileDraft({ parent_company: event.target.value })} /></label><label>Customer reference<input value={profileDraft.customer_reference} onChange={(event) => updateProfileDraft({ customer_reference: event.target.value })} /></label><label>Site name*<input value={profileDraft.site_name} onChange={(event) => updateProfileDraft({ site_name: event.target.value })} /></label><label>Location<input value={profileDraft.location} onChange={(event) => updateProfileDraft({ location: event.target.value })} /></label><label>Timezone<select value={profileDraft.timezone} onChange={(event) => updateProfileDraft({ timezone: event.target.value })}><option value="Asia/Kolkata">Asia/Kolkata (IST)</option><option value="UTC">UTC</option></select></label><label>DC capacity (kWp)<input type="number" min="0" value={profileDraft.dc_capacity_kwp} onChange={(event) => updateProfileDraft({ dc_capacity_kwp: event.target.value })} /></label><label>AC capacity (kW)<input type="number" min="0" value={profileDraft.ac_capacity_kw} onChange={(event) => updateProfileDraft({ ac_capacity_kw: event.target.value })} /></label><label>Logo placement<select value={profileDraft.logo_placement} onChange={(event) => updateProfileDraft({ logo_placement: event.target.value })}><option value="both_header">Both logos in header</option><option value="customer_header_company_footer">Customer header / Company footer</option><option value="company_header_customer_footer">Company header / Customer footer</option><option value="both_footer">Both logos in footer</option><option value="customer_only_header">Customer logo only</option><option value="company_only_header">Company logo only</option></select></label><label>Customer logo label<input maxLength="12" value={profileDraft.customer_logo_label} onChange={(event) => updateProfileDraft({ customer_logo_label: event.target.value.toUpperCase() })} /></label><label>Company logo label<input maxLength="12" value={profileDraft.company_logo_label} onChange={(event) => updateProfileDraft({ company_logo_label: event.target.value.toUpperCase() })} /></label></div><div className="logo-placement-preview"><span className="preview-logo customer">{profileDraft.customer_logo_label || "CU"}</span><span>{humanize(profileDraft.logo_placement)}</span><span className="preview-logo company">{profileDraft.company_logo_label || "RG"}</span></div><div className="actions"><Button secondary onClick={() => setProfileEditorOpen(false)}>Cancel</Button><Button disabled={busy} onClick={saveCustomerProfile}>Save customer profile</Button></div></article>}
              </div>
            ) : (
              <article className="card new-customer-form">
                <section><div className="form-section-title"><span>1</span><h3>Customer details</h3><button type="button" onClick={() => setNotice("Image upload will be added when hosted storage is ready. Use logo labels for the MVP.")}>↥ Upload logo later</button></div><div className="setup-form-grid three"><label>Customer name*<input value={newCustomer.customer_name} onChange={(event) => updateNewCustomer({ customer_name: event.target.value, customer_logo_label: newCustomer.customer_logo_label || initialsFor(event.target.value) })} placeholder="e.g. Alpha Solar Operations" /></label><label>Parent company<input value={newCustomer.parent_company} onChange={(event) => updateNewCustomer({ parent_company: event.target.value })} placeholder="Optional" /></label><label>Customer reference<input value={newCustomer.customer_reference} onChange={(event) => updateNewCustomer({ customer_reference: event.target.value })} placeholder="Optional internal ID" /></label><label>Customer logo label<input maxLength="12" value={newCustomer.customer_logo_label} onChange={(event) => updateNewCustomer({ customer_logo_label: event.target.value.toUpperCase() })} placeholder="e.g. AS" /></label><label>Company logo label<input maxLength="12" value={newCustomer.company_logo_label} onChange={(event) => updateNewCustomer({ company_logo_label: event.target.value.toUpperCase() })} placeholder="e.g. RG" /></label><label>Logo placement<select value={newCustomer.logo_placement} onChange={(event) => updateNewCustomer({ logo_placement: event.target.value })}><option value="both_header">Both logos in header</option><option value="customer_header_company_footer">Customer header / Company footer</option><option value="company_header_customer_footer">Company header / Customer footer</option><option value="both_footer">Both logos in footer</option><option value="customer_only_header">Customer logo only</option><option value="company_only_header">Company logo only</option></select></label></div></section>
                <section><div className="form-section-title"><span>2</span><h3>First plant or site</h3></div><div className="setup-form-grid three"><label>Site name*<input value={newCustomer.site_name} onChange={(event) => updateNewCustomer({ site_name: event.target.value })} placeholder="e.g. Alpha Solar Power Plant" /></label><label>Location<input value={newCustomer.location} onChange={(event) => updateNewCustomer({ location: event.target.value })} placeholder="City, region, country" /></label><label>Timezone*<select value={newCustomer.timezone} onChange={(event) => updateNewCustomer({ timezone: event.target.value })}><option value="Asia/Kolkata">Asia/Kolkata (IST)</option><option value="UTC">UTC</option></select></label><label>DC capacity (kWp)<input type="number" min="0" value={newCustomer.dc_capacity_kwp} onChange={(event) => updateNewCustomer({ dc_capacity_kwp: event.target.value })} placeholder="Required for capacity-based KPIs" /></label><label>AC capacity (kW)<input type="number" min="0" value={newCustomer.ac_capacity_kw} onChange={(event) => updateNewCustomer({ ac_capacity_kw: event.target.value })} placeholder="Optional for initial setup" /></label></div><p className="section-helper">Additional equipment and source details can be completed before calculation.</p></section>
                <section><div className="form-section-title"><span>3</span><h3>First report configuration</h3></div><div className="setup-form-grid three"><label>Report type*<div className="locked-field"><strong>Solar Performance Report</strong><small>Only report pack available in this MVP</small></div></label><label>Reporting period*<div className="locked-field"><strong>Daily</strong><small>Daily generation is the current supported period</small></div></label><label>Configuration name<input value={newCustomer.configuration_name} onChange={(event) => updateNewCustomer({ configuration_name: event.target.value })} /></label></div><div className="setup-callout">ⓘ Mappings, formulas, questions, rules, and report components will be configured and approved in the next steps. More report types can be added later as report packs.</div></section>
              </article>
            )}
          </section>
        )}

        {step === 1 && (
          <section className="panel-grid two">
            <article className="card upload-card source-card">
              <div className="upload-icon">{sourceType === "bigquery" ? "BQ" : "↥"}</div>
              <h2>Connect source data</h2>
              <p>ReportGen accepts clean report-ready data, then stores approved configuration separately as product memory.</p>

              <div className="source-choice-grid" role="group" aria-label="Data source">
                <button
                  className={`source-choice-card ${sourceType === "excel" ? "active" : ""}`}
                  onClick={() => { setSourceType("excel"); setFileId(""); setSourceLabel(""); setValidation(null); setCalculation(null); }}
                  type="button"
                >
                  <strong>Excel workbook</strong>
                  <small>Upload the daily solar workbook for this report run.</small>
                </button>
                <button
                  className={`source-choice-card ${sourceType === "bigquery" ? "active" : ""}`}
                  onClick={() => { setSourceType("bigquery"); setFileId(""); setSourceLabel(""); setValidation(null); setCalculation(null); }}
                  type="button"
                >
                  <strong>BigQuery views</strong>
                  <small>Read clean, pre-joined views prepared in BigQuery.</small>
                </button>
              </div>

              {sourceType === "excel" ? (
                <>
                  <label className="file-picker">
                    <input
                      aria-label="Source workbook"
                      type="file"
                      accept=".xlsx,.xls"
                      onChange={(e) => {
                        const selected = e.target.files?.[0] || null;
                        setFile(selected);
                        setFileId("");
                        setSourceLabel("");
                        setValidation(null);
                        setCalculation(null);
                      }}
                    />
                    <span>{file ? file.name : "Choose Excel workbook"}</span>
                  </label>
                  <Button disabled={busy || !file} onClick={uploadWorkbook}>{busy ? "Uploading…" : fileId ? "Upload again" : "Upload workbook"}</Button>
                  {file && !fileId && <div className="upload-hint">File selected. Click <b>Upload workbook</b> to send it to ReportGen before validation.</div>}
                </>
              ) : (
                <div className="bigquery-form">
                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={bigQueryConfig.use_demo_data}
                      onChange={(event) => updateBigQueryConfig({ use_demo_data: event.target.checked })}
                    />
                    Use demo BigQuery source for local prototype
                  </label>
                  <div className="setup-form-grid three">
                    <label>Project ID
                      <input value={bigQueryConfig.project_id} onChange={(event) => updateBigQueryConfig({ project_id: event.target.value })} placeholder="gcp-project-id" />
                    </label>
                    <label>Dataset ID
                      <input value={bigQueryConfig.dataset_id} onChange={(event) => updateBigQueryConfig({ dataset_id: event.target.value })} placeholder="reporting_dataset" />
                    </label>
                    <label>Plant/site ID
                      <input value={bigQueryConfig.plant_id || ""} onChange={(event) => updateBigQueryConfig({ plant_id: event.target.value })} placeholder="Optional plant_id filter" />
                    </label>
                  </div>
                  <div className="bigquery-view-grid">
                    {Object.entries(bigQueryConfig.table_map).map(([key, value]) => (
                      <label key={key}>{humanize(key)} view
                        <input value={value} onChange={(event) => updateBigQueryView(key, event.target.value)} placeholder={`reportgen_${key}`} />
                      </label>
                    ))}
                  </div>
                  <div className="callout">Joins and source-specific transforms should happen in BigQuery. ReportGen reads clean views/tables and then validates, maps, calculates, and generates evidence exactly like Excel.</div>
                  <Button disabled={busy || !bigQueryConfig.project_id || !bigQueryConfig.dataset_id} onClick={connectBigQuery}>{busy ? "Connecting…" : "Connect BigQuery source"}</Button>
                </div>
              )}

              {fileId && <div className="source-status"><Status tone="success">Connected · {sourceType === "bigquery" ? "BigQuery" : "Excel"} · {sourceLabel || fileId.slice(0, 8)}</Status></div>}
            </article>
            <article className="card form-card">
              <h3>Report context</h3>
              <label>Report date<input type="date" value={reportDate} onChange={(e) => { setReportDate(e.target.value); if (sourceType === "bigquery") { setFileId(""); setValidation(null); setCalculation(null); } }} /></label>
              <label>Calculation policy<input value="Approved Python / pandas formulas" disabled /></label>
              <label>Connected source<input value={fileId ? `${sourceType === "bigquery" ? "BigQuery" : "Excel"} · ${sourceLabel || fileId.slice(0, 8)}` : "No source connected yet"} disabled /></label>
              <div className="callout">KPI values are never generated by AI. The calculation engine uses approved deterministic formulas.</div>
              <Button secondary disabled={!fileId} onClick={() => setStep(2)}>{fileId ? "Review validation" : "Connect source first"}</Button>
            </article>
          </section>
        )}

        {step === 2 && (
          <section>
            <article className="card section-head"><div><h2>Data validation</h2><p>Check structure, data types, completeness, duplicates, and mapping coverage before calculation.</p>{!fileId && <p className="validation-helper">No data source connected yet. Go back to Upload, choose Excel or BigQuery, then connect the source.</p>}</div><Button disabled={busy || !fileId} onClick={validateWorkbook}>{busy ? "Checking…" : fileId ? "Run validation" : "Connect source first"}</Button></article>
            {!validation ? <Empty>{fileId ? "Data source connected. Run deterministic validation." : "Connect a data source before running validation."}</Empty> : <div className="panel-grid three summary-cards"><article className="card"><span>Result</span><strong className={validation.valid ? "good" : "bad"}>{validation.valid ? "Passed" : "Needs attention"}</strong></article><article className="card"><span>Errors</span><strong>{validation.errors.length}</strong></article><article className="card"><span>Warnings</span><strong>{validation.warnings.length}</strong></article></div>}
            {validation && (
              <article className="card">
                <h3>Data-quality guidance</h3>
                {dataQualityIssues.length === 0 && validationFallbackMessages.length === 0 ? (
                  <p className="checkline">✓ No blocking data-quality issues were found.</p>
                ) : dataQualityIssues.length > 0 ? (
                  <div className="validation-issue-list">
                    {dataQualityIssues.map((issue, index) => <ValidationIssueCard issue={issue} key={`${issue.title || "issue"}-${index}`} />)}
                  </div>
                ) : (
                  validationFallbackMessages.map((item, index) => <p className="issue" key={index}>{typeof item === "string" ? item : JSON.stringify(item)}</p>)
                )}
                <div className="validation-note">ReportGen does not repair source data. It flags issues that may affect calculations, charts, narratives, or analyst approval so the source can be corrected upstream.</div>
                <div className="actions"><Button secondary onClick={() => setStep(3)}>Review mappings & formulas</Button></div>
              </article>
            )}
          </section>
        )}

        {step === 3 && (
          <section className="configuration-workspace">
            <article className="card section-head"><div><h2>Mapping & formula approval</h2><p>Review saved customer mappings independently of an upload, and validate every formula before it becomes trusted calculation logic.</p></div><div className="configuration-summary"><Status tone={mappingProfile?.all_confirmed ? "success" : "warn"}>{mappingProfile?.confirmed_count || 0}/{mappingProfile?.mapping_count || 0} mappings confirmed</Status><Status tone={(formulaProfile?.approved_count || 0) === (formulaProfile?.formula_count || 0) ? "success" : "warn"}>{formulaProfile?.approved_count || 0}/{formulaProfile?.formula_count || 0} formulas approved</Status></div></article>
            <div className="panel-grid config-grid"><article className="card mapping-editor"><div className="card-title-row"><div><h3>Customer column mappings</h3><p>Changes are saved only when you explicitly confirm them.</p></div><input aria-label="Search mappings" value={mappingSearch} onChange={(e) => setMappingSearch(e.target.value)} placeholder="Search mappings" /></div>{filteredMappings.length ? <div className="mapping-table"><div className="mapping-table-head"><span>Standard metric</span><span>Customer column</span><span>Type</span><span>Status</span><span>Actions</span></div>{filteredMappings.map((item) => { const changed = mappingDrafts[item.system_column] !== item.customer_column; return <div className="mapping-edit-row" key={item.system_column}><strong>{item.system_column}</strong><input aria-label={`${item.system_column} customer column`} value={mappingDrafts[item.system_column] ?? ""} onChange={(e) => setMappingDrafts((current) => ({ ...current, [item.system_column]: e.target.value }))} /><span>{item.data_type}</span><Status tone={item.confirmed_by_analyst ? "success" : "warn"}>{item.confirmed_by_analyst ? "Confirmed" : "Needs review"}</Status><div className="row-actions"><button disabled={busy || (!changed && item.confirmed_by_analyst)} onClick={() => saveMapping(item)}>Save</button><button className="quiet" disabled={busy || !item.confirmed_by_analyst} onClick={() => resetMapping(item)}>Reset</button></div></div>; })}</div> : <Empty>No saved mappings match this search.</Empty>}</article>
              <article className="card formula-library"><div className="card-title-row"><div><h3>Derived KPI formulas</h3><p>System suggestions remain inactive until an analyst approves them.</p></div><Button secondary onClick={() => openFormulaEditor()}>＋ New formula</Button></div>{(formulaProfile?.formulas || []).map((metric) => <div className="formula-row" key={metric.output_column}><div><strong>{metric.metric_name}</strong><code>{metric.formula}</code><small>{(metric.input_columns || []).join(" + ")} · {metric.unit || "No unit"} · {humanize(metric.scope)}</small></div><div className="formula-actions"><Status tone={metric.approved_by_analyst ? "success" : "warn"}>{metric.approved_by_analyst ? "Approved" : "Suggested"}</Status><button onClick={() => openFormulaEditor(metric)}>Edit</button>{!metric.approved_by_analyst && <button className="approve-link" onClick={() => approveFormula(metric)}>Approve</button>}</div></div>)}</article>
            </div>
            {formulaDraft && <article className="card formula-editor"><div className="card-title-row"><div><h3>{formulaDraft.output_column ? `Edit ${formulaDraft.metric_name}` : "Create a new calculated KPI"}</h3><p>The formula is parsed safely and checked against available mapped metrics before saving.</p></div><button className="close-editor" onClick={() => { setFormulaDraft(null); setFormulaValidation(null); }}>×</button></div><div className="formula-form"><label>KPI name<input value={formulaDraft.metric_name} onChange={(e) => setFormulaDraft({ ...formulaDraft, metric_name: e.target.value })} /></label><label>Output column<input value={formulaDraft.output_column} onChange={(e) => setFormulaDraft({ ...formulaDraft, output_column: e.target.value })} /></label><label className="formula-field">Formula<input value={formulaDraft.formula} onChange={(e) => { setFormulaDraft({ ...formulaDraft, formula: e.target.value }); setFormulaValidation(null); }} placeholder="generation_kwh / dc_capacity_kwp" /></label><label className="formula-field">Input columns<input value={formulaDraft.input_columns} onChange={(e) => { setFormulaDraft({ ...formulaDraft, input_columns: e.target.value }); setFormulaValidation(null); }} placeholder="generation_kwh, dc_capacity_kwp" /></label><label>Unit<input value={formulaDraft.unit} onChange={(e) => setFormulaDraft({ ...formulaDraft, unit: e.target.value })} /></label><label>Good range<input value={formulaDraft.good_range} onChange={(e) => setFormulaDraft({ ...formulaDraft, good_range: e.target.value })} /></label><label>Poor threshold<input value={formulaDraft.poor_threshold} onChange={(e) => setFormulaDraft({ ...formulaDraft, poor_threshold: e.target.value })} /></label><label>Remember for<select value={formulaDraft.scope} onChange={(e) => setFormulaDraft({ ...formulaDraft, scope: e.target.value })}><option value="customer_report_type">This customer + report type</option><option value="customer">This customer</option><option value="report_type">All Daily Generation reports</option><option value="global">Global</option></select></label></div><div className="available-columns"><span>Available metrics</span>{(formulaProfile?.available_columns || []).map((column) => <code key={column}>{column}</code>)}</div>{formulaValidation && <div className={`formula-validation ${formulaValidation.valid ? "valid" : "invalid"}`}>{formulaValidation.valid ? "✓" : "!"} {formulaValidation.message}</div>}<div className="actions"><Button secondary disabled={busy} onClick={validateFormulaDraft}>Validate formula</Button><Button disabled={busy || !formulaDraft.metric_name.trim() || !formulaDraft.output_column.trim() || !formulaDraft.formula.trim()} onClick={saveFormula}>Validate & save approval</Button></div></article>}
            <div className="actions"><Button secondary onClick={() => setStep(4)}>Continue to questions & rules</Button></div>
          </section>
        )}

        {step === 4 && (
          <section className="questions-workspace">
            <div className="panel-grid two"><article className="card"><h2>Standing customer questions</h2><p>Questions recur with every report and determine which evidence components belong in the draft.</p><div className="inline-form"><input aria-label="Standing customer question" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="What caused the PR change?" /><Button onClick={addQuestion}>Add</Button></div>{profile?.customer_questions?.map((item) => <div className="approval-row" key={item.question_id || item.question_text}><div><strong>{item.question_text}</strong><small>{item.answer_purpose || "Recurring report question"}</small></div>{item.approved_by_analyst ? <Status tone="success">Approved</Status> : <Button secondary disabled={busy} onClick={() => approveSuggestedQuestion(item)}>Approve</Button>}</div>)}</article><article className="card"><h2>Insight rules</h2><p>Only approved deterministic conditions can trigger findings.</p>{profile?.insight_rules?.map((rule) => <div className="approval-row" key={rule.rule_id || rule.rule_name}><div><strong>{rule.rule_name}</strong><code>{rule.condition}</code><small>Severity · {rule.severity}</small></div>{rule.approved_by_analyst ? <Status tone="success">Approved</Status> : <Button secondary onClick={() => approveRule(rule)}>Approve</Button>}</div>)}</article></div>
            <article className="card theme-selector"><div className="card-title-row"><div><h2>Choose report presentation</h2><p>The theme controls presentation only. Calculations, findings, and evidence remain unchanged.</p></div>{reportLayout && <Status tone={reportLayout.status === "approved" ? "success" : "warn"}>Layout v{reportLayout.version} · {humanize(reportLayout.status)}</Status>}</div><div className="theme-options">{REPORT_THEMES.map(([value, label, description]) => <button key={value} className={`theme-option ${reportTheme === value ? "active" : ""}`} onClick={() => { setReportTheme(value); setDraftApproved(false); }}><span className={`theme-swatch ${value}`}><i /><i /><i /></span><strong>{label}</strong><small>{description}</small></button>)}</div><label className="summary-position">Executive summary position<select value={summaryPosition} onChange={(event) => setSummaryPosition(event.target.value)}><option value="top">Top of report</option><option value="after_kpis">After KPI scorecards</option></select></label><div className="actions"><Button disabled={!ready || busy} onClick={calculateDraft}>{busy ? "Calculating…" : "Generate deterministic draft"}</Button></div></article>
          </section>
        )}

        {step === 5 && (
          <section className="draft-review-workspace">
            <DraftReview
              calculation={calculation}
              customer={customer}
              reportDate={reportDate}
              reportType={reportType}
              configId={selectedConfigId}
              reportIdentity={{ reportTitle, reportSubtitle, preparedBy, preparedFor, customerLogoLabel, companyLogoLabel, logoPlacement, brandScope }}
              reportTheme={reportTheme}
              setReportTheme={setReportTheme}
              summaryPosition={summaryPosition}
              setSummaryPosition={setSummaryPosition}
              reportLayout={reportLayout}
              formulaFingerprint={formulaFingerprint}
              chartReview={chartReview}
              setChartReview={setChartReview}
              findingReview={findingReview}
              setFindingReview={setFindingReview}
              narrativeReview={narrativeReview}
              setNarrativeReview={setNarrativeReview}
              draftApproved={draftApproved}
              setDraftApproved={setDraftApproved}
              setNotice={setNotice}
              generateComponent={generateReportComponent}
              saveLayout={saveReportLayout}
              approveLayout={approveCurrentLayout}
              approveSnapshot={approveReportSnapshot}
              goBack={() => setStep(4)}
              ChartRenderer={ChartRenderer}
            />
          </section>
        )}

        <footer><div className="progress-saved">{step === 0 ? "Customer context controls all downstream report decisions." : "✓ Progress saved. You can return to any previous step."}</div><div className="footer-actions"><Button secondary disabled={step === 0} onClick={() => setStep((value) => Math.max(0, value - 1))}>Back</Button><span>{continueHelp || `Step ${step + 1} of ${STEPS.length}`}</span><Button disabled={!canContinue || busy} onClick={() => { if (step === 0 && customerMode === "new") createCustomer(); else setStep((value) => Math.min(STEPS.length - 1, value + 1)); }}>{step === 0 ? customerMode === "new" ? busy ? "Creating customer…" : "Create customer & continue" : "Continue to Upload & Period" : "Continue"} →</Button></div></footer>
      </main>
      </div>
    </div>
  );
}

export default App;
