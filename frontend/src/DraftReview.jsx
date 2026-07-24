import React, { useMemo, useState } from "react";

const fmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const palette = ["#0c66e4", "#e05a47", "#36b37e", "#f5a623"];
const humanize = (value = "") => value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const number = (value, suffix = "") => value == null ? "—" : `${fmt.format(value)}${suffix}`;
const splitMetrics = (value = "") => value.split(",").map((item) => item.trim()).filter(Boolean);
const WATERFALL_METRICS = [
  "expected_generation_kwh",
  "outage_loss_kwh",
  "environmental_loss_kwh",
  "clipping_loss_kwh",
  "generation_kwh",
];
const themeNames = {
  corporate_blue: "Corporate Blue",
  minimal: "Minimal",
  executive: "Executive",
  operations: "Operations",
};

function componentDefaultMetrics(component) {
  return component.series?.map((series) => series.metric).filter(Boolean).join(", ")
    || (component.metrics || []).join(", ")
    || component.metric
    || "";
}

function componentHasPendingChanges(component, review, reportDate) {
  const defaultMetrics = componentDefaultMetrics(component);
  const metrics = review.metrics ?? review.metric ?? defaultMetrics;
  const startDate = review.startDate || review.analysisDate || String(component.start_date || component.x?.[0] || reportDate).slice(0, 10);
  const endDate = review.endDate || review.analysisDate || String(component.end_date || component.x?.[component.x?.length - 1] || reportDate).slice(0, 10);
  const generatedStart = String(component.start_date || component.x?.[0] || startDate).slice(0, 10);
  const generatedEnd = String(component.end_date || component.x?.[component.x?.length - 1] || endDate).slice(0, 10);
  return (review.chartType || component.type || "line") !== component.type
    || (review.breakdown || "site_total") !== (component.breakdown || "site_total")
    || (review.timeGrain || component.time_grain || "daily") !== (component.time_grain || "daily")
    || JSON.stringify(review.aggregations || component.aggregation_overrides || {}) !== JSON.stringify(component.aggregation_overrides || {})
    || metrics !== defaultMetrics
    || startDate !== generatedStart
    || endDate !== generatedEnd;
}

function Status({ children, tone = "neutral" }) {
  return <span className={`status ${tone}`}>{children}</span>;
}

function Button({ children, ...props }) {
  return <button className="button" {...props}>{children}</button>;
}

function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

function Toggle({ checked, onChange, label }) {
  return <label className="toggle"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /><span aria-hidden="true" /><em>{label}</em></label>;
}

function Evidence({ evidence = {} }) {
  const entries = Object.entries(evidence).filter(([key]) => !["thresholds", "row_index"].includes(key));
  if (!entries.length) return <small className="evidence-empty">No structured evidence was supplied.</small>;
  return <div className="evidence-list">{entries.map(([key, value]) => <span key={key}><b>{humanize(key)}</b>{typeof value === "number" ? fmt.format(value) : String(value)}</span>)}</div>;
}

function DataTable({ spec }) {
  return <div className="report-table-wrap"><table className="report-table"><thead><tr>{(spec.columns || []).map((column) => <th key={column}>{humanize(column)}</th>)}</tr></thead><tbody>{(spec.rows || []).map((row, index) => <tr key={index}>{spec.columns.map((column) => <td key={column}>{typeof row[column] === "number" ? fmt.format(row[column]) : String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table></div>;
}

function ChartDataTable({ spec }) {
  const series = spec.series || [];
  const columns = ["date_time", ...series.map((item) => item.metric || item.name)];
  const rows = (spec.x || []).map((xValue, index) => {
    const row = { date_time: String(xValue).replace("T", " ") };
    series.forEach((item) => { row[item.metric || item.name] = item.y?.[index]; });
    return row;
  });
  if (!series.length || !rows.length) return <Empty>No table preview is available for this chart request yet.</Empty>;
  return <div className="report-table-wrap"><table className="report-table"><thead><tr>{columns.map((column) => <th key={column}>{humanize(column)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{typeof row[column] === "number" ? fmt.format(row[column]) : String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table></div>;
}

function dedupeFindings(findings) {
  const seen = new Set();
  return findings.filter((finding) => {
    const key = [
      finding.rule_name,
      finding.condition,
      finding.message,
    ].join("|");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function relatedFindingsFor(component, review, findings, findingReview, reportDate) {
  const metrics = splitMetrics(review.metrics || review.metric || component.metric || component.series?.map((item) => item.metric).join(", ") || "");
  const textFor = (finding) => JSON.stringify(finding).toLowerCase();
  const startDate = review.startDate || component.start_date || reportDate;
  const endDate = review.endDate || component.end_date || reportDate;
  const uniqueFindings = dedupeFindings(findings);
  const matches = uniqueFindings.filter((finding, index) => {
    const key = finding.finding_id || finding.rule_id || index;
    if ((findingReview[key] ?? true) === false) return false;
    const findingDate = String(finding.evidence?.date || "").slice(0, 10);
    if (findingDate && (findingDate < startDate || findingDate > endDate)) {
      return false;
    }
    const haystack = textFor(finding);
    return metrics.some((metric) => haystack.includes(metric.toLowerCase()) || haystack.includes(humanize(metric).toLowerCase()))
      || haystack.includes(String(component.component_id || "").toLowerCase())
      || haystack.includes(String(component.title || "").toLowerCase());
  });
  return matches.slice(0, 2);
}

function ComponentFindings({ findings }) {
  if (!findings.length) return <div className="component-findings empty-rail"><strong>No linked finding yet</strong><p>This evidence can remain as supporting context, or the analyst can add a narrative note.</p></div>;
  return <aside className="component-findings"><span>Decision notes</span>{findings.map((finding, index) => <div className="component-finding" key={finding.finding_id || finding.rule_id || index}><Status tone={finding.severity === "high" ? "danger" : "warn"}>{finding.severity || "review"}</Status><strong>{finding.title || humanize(finding.rule_name || "Finding")}</strong><p>{finding.finding || finding.message || finding.description}</p>{finding.suggestion && <small>{finding.suggestion}</small>}</div>)}</aside>;
}

function evidenceSignature(component, review, findings) {
  const metrics = splitMetrics(
    review.metrics
    || review.metric
    || (component.metrics || []).join(", ")
    || (component.series || []).map((item) => item.metric).join(", ")
    || component.metric
    || "",
  ).sort();
  const rules = findings.map((finding) => ({
    rule: finding.rule_name || "",
    condition: finding.condition || "",
    evidence: Object.keys(finding.evidence || {})
      .filter((key) => !["date", "row_index", "thresholds"].includes(key))
      .sort(),
    thresholds: finding.evidence?.thresholds || {},
    severity: finding.severity || "",
  })).sort((a, b) => a.rule.localeCompare(b.rule));
  return JSON.stringify({
    metrics,
    rules,
    componentEvidence: component.evidence_summary || {},
    formulas: review.formulaFingerprint || "unavailable",
  });
}

function metricEvidencePhrase(key, value) {
  const label = humanize(key);
  if (typeof value === "number") return `${label} ${fmt.format(value)}${key.includes("percent") ? "%" : ""}`;
  return `${label} ${value}`;
}

function suggestedExplanation(component, review, findings) {
  const evidenceSummary = component.evidence_summary?.summary;
  if (!findings.length) {
    return evidenceSummary
      || `No approved business rule triggered a finding for ${review.title || component.title}; the chart is included as supporting evidence.`;
  }
  const findingText = findings.map((finding) => {
    const evidence = Object.entries(finding.evidence || {})
      .filter(([key, value]) => !["thresholds", "row_index", "date"].includes(key) && value != null)
      .slice(0, 4)
      .map(([key, value]) => metricEvidencePhrase(key, value));
    const message = finding.message || `${humanize(finding.rule_name || "The approved rule")} was triggered.`;
    return evidence.length
      ? `${message} Evidence: ${evidence.join(", ")}.`
      : message;
  }).join(" ");
  return evidenceSummary
    ? `${evidenceSummary} ${findingText}`
    : findingText;
}

function componentEvidenceLabels(component) {
  const labels = [];
  for (const [metric, values] of Object.entries(component.evidence_summary?.metrics || {})) {
    if (values.period_value != null) {
      labels.push(`${humanize(metric)} · ${fmt.format(values.period_value)}`);
    }
    if (values.previous_value != null) {
      labels.push(`Previous ${humanize(metric)} · ${fmt.format(values.previous_value)}`);
    }
    if (values.fleet_average != null) {
      labels.push(`Fleet average · ${fmt.format(values.fleet_average)}`);
    }
    if (values.lowest_equipment) {
      labels.push(`Lowest · ${values.lowest_equipment} (${fmt.format(values.lowest_value)})`);
    }
  }
  const relationship = component.evidence_summary?.relationship;
  if (relationship?.correlation != null) {
    labels.push(`Power–GTI correlation · ${relationship.correlation}`);
  }
  if (relationship?.high_irradiance_low_power_intervals != null) {
    labels.push(`Mismatch intervals · ${relationship.high_irradiance_low_power_intervals}`);
  }
  return labels;
}

function ChartPlanEditor({
  component,
  review,
  reportDate,
  supportedBreakdowns,
  chartCapabilities,
  onChange,
  onRegenerate,
  busy,
  locked,
}) {
  const chartType = review.chartType || component.type || "line";
  const defaultMetrics = componentDefaultMetrics(component);
  const metrics = review.metrics ?? review.metric ?? defaultMetrics;
  const metricList = splitMetrics(metrics);
  const startDate = review.startDate || review.analysisDate || String(component.start_date || component.x?.[0] || reportDate).slice(0, 10);
  const endDate = review.endDate || review.analysisDate || String(component.end_date || component.x?.[component.x?.length - 1] || reportDate).slice(0, 10);
  const requestedBreakdown = review.breakdown || "site_total";
  const equipmentBreakdown = supportedBreakdowns.includes("inverter")
    ? "inverter"
    : supportedBreakdowns.includes("block")
      ? "block"
      : "site_total";
  const breakdown = supportedBreakdowns.includes(requestedBreakdown)
    ? requestedBreakdown
    : chartType === "heatmap"
      ? equipmentBreakdown
      : "site_total";
  const timeGrain = review.timeGrain || component.time_grain || "daily";
  const aggregations = review.aggregations || component.aggregation_overrides || {};
  const sourceCapability = (chartCapabilities?.sources || []).find((source) => (
    source.breakdown === breakdown
    && metricList.every((metric) => source.metrics.includes(metric))
  ));
  const availableTimeGrains = sourceCapability?.time_grains || ["raw", "daily"];
  const compatibilityIssues = [];
  if (!sourceCapability) {
    compatibilityIssues.push(
      `No approved ${humanize(breakdown)} source contains all selected metrics.`,
    );
  } else {
    if (startDate && startDate < sourceCapability.start_date) {
      compatibilityIssues.push(
        `Start date is before the available data (${sourceCapability.start_date}).`,
      );
    }
    if (endDate && endDate > sourceCapability.end_date) {
      compatibilityIssues.push(
        `End date is after the available data (${sourceCapability.end_date}).`,
      );
    }
    if (!availableTimeGrains.includes(timeGrain)) {
      compatibilityIssues.push(
        `${humanize(timeGrain)} cannot be generated from ${sourceCapability.native_grain} data.`,
      );
    }
  }
  if (startDate && endDate && startDate > endDate) {
    compatibilityIssues.push("Start date must not be after end date.");
  }
  if (chartType === "heatmap" && metricList.length !== 1) {
    compatibilityIssues.push("A heatmap requires exactly one metric.");
  }
  if (["bar_line", "dual_axis_line", "stacked_bar"].includes(chartType) && metricList.length < 2) {
    compatibilityIssues.push(`${humanize(chartType)} requires at least two metrics.`);
  }
  const pending = componentHasPendingChanges(component, {
    ...review,
    breakdown,
  }, reportDate);
  const selectChartType = (value) => {
    if (value === "waterfall") {
      onChange({
        chartType: value,
        metrics: WATERFALL_METRICS.join(", "),
        metric: WATERFALL_METRICS.join(", "),
        breakdown: "site_total",
        timeGrain: "daily",
        aggregations: Object.fromEntries(
          WATERFALL_METRICS.map((metric) => [metric, "sum"]),
        ),
      });
      return;
    }
    if (value === "heatmap" && !["inverter", "block"].includes(breakdown)) {
      onChange({
        chartType: value,
        metrics: metricList.slice(0, 1).join(", "),
        metric: metricList[0] || "",
        breakdown: equipmentBreakdown,
        timeGrain: "daily",
      });
      return;
    }
    onChange({ chartType: value });
  };
  return <div className="chart-plan-editor"><div className="chart-plan-grid"><label className="metrics-field">Metrics / KPIs<input disabled={locked} value={metrics} onChange={(event) => onChange({ metrics: event.target.value, metric: event.target.value })} placeholder="generation_kwh, gti_kwh_m2" /><small>Use comma-separated approved metrics for combined charts.</small></label><label>Start date<input disabled={locked} type="date" min={sourceCapability?.start_date} max={sourceCapability?.end_date} value={startDate} onChange={(event) => onChange({ startDate: event.target.value })} /></label><label>End date<input disabled={locked} type="date" min={sourceCapability?.start_date} max={sourceCapability?.end_date} value={endDate} onChange={(event) => onChange({ endDate: event.target.value })} /></label><label>Breakdown<select disabled={locked} value={breakdown} onChange={(event) => onChange({ breakdown: event.target.value })}><option value="site_total">Site total</option><option value="inverter" disabled={!supportedBreakdowns.includes("inverter")}>By inverter{supportedBreakdowns.includes("inverter") ? "" : " · unavailable"}</option><option value="block" disabled={!supportedBreakdowns.includes("block")}>By block{supportedBreakdowns.includes("block") ? "" : " · unavailable"}</option><option value="loss_type" disabled={!supportedBreakdowns.includes("loss_type")}>By loss type{supportedBreakdowns.includes("loss_type") ? "" : " · unavailable"}</option></select></label><label>Time grain<select disabled={locked} value={timeGrain} onChange={(event) => onChange({ timeGrain: event.target.value })}><option value="raw" disabled={!availableTimeGrains.includes("raw")}>Source interval</option><option value="15_minute" disabled={!availableTimeGrains.includes("15_minute")}>15 minute</option><option value="hourly" disabled={!availableTimeGrains.includes("hourly")}>Hourly</option><option value="daily" disabled={!availableTimeGrains.includes("daily")}>Daily</option></select></label><label>Chart type<select disabled={locked} value={chartType} onChange={(event) => selectChartType(event.target.value)}><option value="line">Line</option><option value="bar">Bar</option><option value="bar_line">Bar + line</option><option value="dual_axis_line">Dual-axis line</option><option value="stacked_bar">Stacked bar</option><option value="waterfall">Waterfall</option><option value="heatmap" disabled={equipmentBreakdown === "site_total"}>Heatmap</option><option value="table">Table</option></select></label><label>Explanation placement<select disabled={locked} value={review.textPosition || "beside"} onChange={(event) => onChange({ textPosition: event.target.value })}><option value="above">Above chart</option><option value="beside">Beside chart</option><option value="below">Below chart</option></select></label><label>Component width<select disabled={locked} value={review.width || "full"} onChange={(event) => onChange({ width: event.target.value })}><option value="full">Full width</option><option value="half">Half width</option></select></label></div>{sourceCapability && <div className="data-coverage-note"><strong>Available approved data</strong><span>{sourceCapability.start_date} to {sourceCapability.end_date} · {humanize(sourceCapability.native_grain)} · {humanize(sourceCapability.source)}</span></div>}<div className="aggregation-policy"><div><strong>Aggregation policy</strong><small>Stored with this customer’s report layout.</small></div>{metricList.map((metric) => <label key={metric}><span>{humanize(metric)}</span><select disabled={locked} value={aggregations[metric] || "auto"} onChange={(event) => onChange({ aggregations: { ...aggregations, [metric]: event.target.value } })}><option value="auto">Automatic</option><option value="average">Average</option><option value="sum">Sum</option></select></label>)}</div>{chartType === "heatmap" && <div className="compatibility-note">Heatmap uses the equipment dimensions available in this workbook. ReportGen will never invent unavailable block or inverter data.</div>}{compatibilityIssues.length > 0 && <div className="chart-request-error"><strong>Request cannot be generated</strong>{compatibilityIssues.map((issue) => <span key={issue}>{issue}</span>)}</div>}{review.regenerationError && <div className="chart-request-error"><strong>Regeneration failed</strong><span>{review.regenerationError}</span></div>}{pending && <div className="pending-chart-change"><Status tone="warn">Changes not applied</Status><span>The last valid chart remains {humanize(component.type)} until backend regeneration succeeds.</span></div>}<div className="chart-regenerate-row"><span>Values are always regenerated by the backend from approved data.</span><Button disabled={locked || busy || !metricList.length || compatibilityIssues.length > 0 || (chartType === "heatmap" && equipmentBreakdown === "site_total")} onClick={() => onRegenerate({ metrics: metricList, startDate, endDate, breakdown, chartType, aggregations, timeGrain })}>{busy ? "Regenerating…" : "Apply & regenerate"}</Button></div></div>;
}

function ExplanationApproval({ component, review, findings, locked, onChange }) {
  const signature = evidenceSignature(component, review, findings);
  const suggestion = suggestedExplanation(component, review, findings);
  const signatureMatches = review.explanationSignature === signature;
  const status = signatureMatches
    ? (review.explanationStatus || "suggested")
    : (review.explanationSignature ? "needs_review" : "suggested");
  const editing = status === "editing";
  const displayedText = (
    signatureMatches && review.explanationEditedText
      ? review.explanationEditedText
      : suggestion
  );
  const tone = status === "approved" ? "success" : status === "rejected" ? "danger" : "warn";
  const statusLabel = {
    approved: "Approved pattern",
    rejected: "Rejected",
    editing: "Analyst editing",
    needs_review: "Evidence changed · approval needed",
    suggested: "System suggested",
  }[status] || "System suggested";
  const evidenceLabels = [
    ...componentEvidenceLabels(component),
    ...findings.flatMap((finding) => Object.entries(finding.evidence || {})
    .filter(([key, value]) => !["thresholds", "row_index", "date"].includes(key) && value != null)
    .map(([key, value]) => metricEvidencePhrase(key, value))),
  ];

  return <section className={`explanation-approval ${status}`}>
    <div className="explanation-heading"><div><span>System-suggested explanation</span><Status tone={tone}>{statusLabel}</Status></div><small>Generated only from approved rules and deterministic evidence.</small></div>
    {editing
      ? <textarea disabled={locked} value={displayedText} onChange={(event) => onChange({ explanationEditedText: event.target.value, explanationStatus: "editing" })} />
      : <p className={status === "rejected" ? "rejected-text" : ""}>{status === "rejected" ? "This explanation has been excluded from the report." : displayedText}</p>}
    <div className="explanation-evidence"><strong>Evidence used</strong>{evidenceLabels.length ? [...new Set(evidenceLabels)].map((label) => <span key={label}>{label}</span>) : <span>No rule-triggered exception</span>}</div>
    {!locked && <div className="explanation-actions">
      {editing
        ? <><Button onClick={() => onChange({ explanation: displayedText, explanationEditedText: displayedText, explanationStatus: "approved", explanationSignature: signature })}>Save edit & approve</Button><button className="button secondary" onClick={() => onChange({ explanationEditedText: "", explanationStatus: "suggested" })}>Cancel</button></>
        : <><Button onClick={() => onChange({ explanation: suggestion, explanationEditedText: "", explanationStatus: "approved", explanationSignature: signature })}>{status === "approved" ? "✓ Approved" : "Approve"}</Button><button className="button secondary" onClick={() => onChange({ explanationEditedText: suggestion, explanationStatus: "editing" })}>Edit</button><button className="button secondary reject" onClick={() => onChange({ explanation: "", explanationEditedText: "", explanationStatus: "rejected", explanationSignature: signature })}>Reject</button></>}
      <small>Remembered for this customer + report type when the layout is approved.</small>
    </div>}
  </section>;
}

function ReportEvidence({ component, review, findings, ChartRenderer }) {
  if (review.regenerationError) {
    return <Empty>Chart not shown because the requested configuration failed: {review.regenerationError}</Empty>;
  }
  const visual = component.type === "table"
    ? <DataTable spec={component} />
    : <ChartRenderer spec={{ ...component, title: review.title }} />;
  const signature = evidenceSignature(component, review, findings);
  const approved = review.explanationStatus === "approved"
    && review.explanationSignature === signature;
  const explanationText = review.explanationEditedText
    || suggestedExplanation(component, review, findings);
  const explanation = approved
    ? <div className="approved-explanation"><span>Approved explanation</span><p>{explanationText}</p></div>
    : null;
  const notes = <ComponentFindings findings={findings} />;
  const position = review.textPosition || "beside";
  return <div className={`component-story position-${position}`}>
    {position === "above" && <div className="component-story-text">{explanation}{notes}</div>}
    <div className="component-visual">{visual}</div>
    {position !== "above" && <div className="component-story-text">{explanation}{notes}</div>}
  </div>;
}

function AddComponentPanel({
  reportDate,
  availableMetrics,
  supportedBreakdowns,
  chartCapabilities,
  onCancel,
  onAdd,
  busy,
}) {
  const [draft, setDraft] = useState({
    title: "Additional report evidence",
    metrics: availableMetrics[0] || "pr_percent",
    startDate: reportDate,
    endDate: reportDate,
    breakdown: "site_total",
    chartType: "line",
    timeGrain: "daily",
    aggregations: {},
    textPosition: "beside",
    width: "full",
  });
  const update = (changes) => setDraft((current) => ({ ...current, ...changes }));
  const metrics = splitMetrics(draft.metrics);
  const sourceCapability = (chartCapabilities?.sources || []).find((source) => (
    source.breakdown === draft.breakdown
    && metrics.every((metric) => source.metrics.includes(metric))
  ));
  const availableTimeGrains = sourceCapability?.time_grains || ["raw", "daily"];
  const invalidDates = Boolean(
    sourceCapability
    && (
      draft.startDate < sourceCapability.start_date
      || draft.endDate > sourceCapability.end_date
      || draft.startDate > draft.endDate
    )
  );
  const invalidShape = (
    (draft.chartType === "heatmap" && metrics.length !== 1)
    || (["bar_line", "dual_axis_line", "stacked_bar"].includes(draft.chartType) && metrics.length < 2)
  );
  const equipmentBreakdown = supportedBreakdowns.includes("inverter")
    ? "inverter"
    : supportedBreakdowns.includes("block")
      ? "block"
      : "site_total";
  const selectChartType = (value) => {
    if (value === "waterfall") {
      update({
        chartType: value,
        metrics: WATERFALL_METRICS.join(", "),
        breakdown: "site_total",
        timeGrain: "daily",
        aggregations: Object.fromEntries(
          WATERFALL_METRICS.map((metric) => [metric, "sum"]),
        ),
      });
      return;
    }
    if (value === "heatmap") {
      update({
        chartType: value,
        metrics: metrics.slice(0, 1).join(", "),
        breakdown: ["inverter", "block"].includes(draft.breakdown)
          ? draft.breakdown
          : equipmentBreakdown,
        timeGrain: "daily",
      });
      return;
    }
    update({ chartType: value });
  };
  return <article className="card add-component-panel"><div className="card-title-row"><div><p className="eyebrow">Controlled report builder</p><h2>Add report component</h2><p>Select approved data and let the backend generate the evidence and suggested explanation.</p></div><button className="close-editor" onClick={onCancel}>×</button></div><div className="add-component-grid"><label>Component title<input value={draft.title} onChange={(event) => update({ title: event.target.value })} /></label><label>Metrics / KPIs<input list="approved-metrics" value={draft.metrics} onChange={(event) => update({ metrics: event.target.value })} placeholder="generation_kwh, gti_kwh_m2" /><datalist id="approved-metrics">{availableMetrics.map((metric) => <option key={metric} value={metric} />)}</datalist><small>Use commas to combine metrics.</small></label><label>Start date<input type="date" min={sourceCapability?.start_date} max={sourceCapability?.end_date} value={draft.startDate} onChange={(event) => update({ startDate: event.target.value })} /></label><label>End date<input type="date" min={sourceCapability?.start_date} max={sourceCapability?.end_date} value={draft.endDate} onChange={(event) => update({ endDate: event.target.value })} /></label><label>Breakdown<select value={draft.breakdown} onChange={(event) => update({ breakdown: event.target.value })}><option value="site_total">Site total</option><option value="inverter" disabled={!supportedBreakdowns.includes("inverter")}>By inverter{supportedBreakdowns.includes("inverter") ? "" : " · unavailable"}</option><option value="block" disabled={!supportedBreakdowns.includes("block")}>By block{supportedBreakdowns.includes("block") ? "" : " · unavailable"}</option><option value="loss_type" disabled={!supportedBreakdowns.includes("loss_type")}>By loss type{supportedBreakdowns.includes("loss_type") ? "" : " · unavailable"}</option></select></label><label>Time grain<select value={draft.timeGrain} onChange={(event) => update({ timeGrain: event.target.value })}><option value="raw" disabled={!availableTimeGrains.includes("raw")}>Source interval</option><option value="15_minute" disabled={!availableTimeGrains.includes("15_minute")}>15 minute</option><option value="hourly" disabled={!availableTimeGrains.includes("hourly")}>Hourly</option><option value="daily" disabled={!availableTimeGrains.includes("daily")}>Daily</option></select></label><label>Visual<select value={draft.chartType} onChange={(event) => selectChartType(event.target.value)}><option value="line">Line</option><option value="bar">Bar</option><option value="bar_line">Bar + line</option><option value="dual_axis_line">Dual-axis line</option><option value="stacked_bar">Stacked bar</option><option value="heatmap" disabled={equipmentBreakdown === "site_total"}>Heatmap</option><option value="table">Table</option><option value="waterfall">Waterfall</option></select></label><label>Explanation placement<select value={draft.textPosition} onChange={(event) => update({ textPosition: event.target.value })}><option value="above">Above chart</option><option value="beside">Beside chart</option><option value="below">Below chart</option></select></label><label>Width<select value={draft.width} onChange={(event) => update({ width: event.target.value })}><option value="full">Full width</option><option value="half">Half width</option></select></label></div>{sourceCapability && <div className="data-coverage-note"><strong>Available approved data</strong><span>{sourceCapability.start_date} to {sourceCapability.end_date} · {humanize(sourceCapability.native_grain)}</span></div>}<div className="aggregation-policy"><div><strong>Aggregation policy</strong><small>Defaults: Generation sum; PR and CUF average; GTI follows its approved unit/policy.</small></div>{metrics.map((metric) => <label key={metric}><span>{humanize(metric)}</span><select value={draft.aggregations[metric] || "auto"} onChange={(event) => update({ aggregations: { ...draft.aggregations, [metric]: event.target.value } })}><option value="auto">Automatic</option><option value="average">Average</option><option value="sum">Sum</option></select></label>)}</div>{draft.chartType === "heatmap" && <div className="compatibility-note">Heatmap selected: ReportGen will use an equipment dimension present in the uploaded data.</div>}{(!sourceCapability || invalidDates || invalidShape || !availableTimeGrains.includes(draft.timeGrain)) && <div className="chart-request-error"><strong>This component cannot be generated yet.</strong><span>Choose metrics, dates, grain, and a chart shape supported by one approved source.</span></div>}<div className="actions"><Button onClick={() => onAdd({ ...draft, breakdown: draft.chartType === "heatmap" ? equipmentBreakdown : draft.breakdown, metrics })} disabled={busy || !draft.title.trim() || !metrics.length || !sourceCapability || invalidDates || invalidShape || !availableTimeGrains.includes(draft.timeGrain) || (draft.chartType === "heatmap" && equipmentBreakdown === "site_total")}>{busy ? "Generating…" : "Generate & add"}</Button><button className="button secondary" onClick={onCancel}>Cancel</button></div></article>;
}

export default function DraftReview({
  calculation,
  customer,
  reportDate,
  reportType,
  configId,
  reportIdentity = {},
  reportTheme,
  setReportTheme,
  summaryPosition,
  setSummaryPosition,
  reportLayout,
  formulaFingerprint,
  chartReview,
  setChartReview,
  findingReview,
  setFindingReview,
  narrativeReview,
  setNarrativeReview,
  draftApproved,
  setDraftApproved,
  setNotice,
  generateComponent,
  saveLayout,
  approveLayout,
  approveSnapshot,
  goBack,
  ChartRenderer,
}) {
  const [mode, setMode] = useState("build");
  const [showAddComponent, setShowAddComponent] = useState(false);
  const [workingComponent, setWorkingComponent] = useState("");
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState("");
  const [layoutDirty, setLayoutDirty] = useState(() => Boolean(
    reportLayout
    && (
      reportLayout.theme !== reportTheme
      || reportLayout.summary_position !== summaryPosition
    )
  ));
  const initialDraft = calculation?.draft || {};
  const initialCards = initialDraft.kpi_cards || [];
  const [kpiReview, setKpiReview] = useState(() => Object.fromEntries(
    (reportLayout?.layout_json?.kpiCards?.length
      ? reportLayout.layout_json.kpiCards
      : initialCards
    ).map((card, index) => [
      card.metric,
      {
        included: card.included ?? true,
        order: card.order ?? index,
        label: card.label,
      },
    ]),
  ));

  if (!calculation) return <article className="card empty"><h2>No draft yet</h2><p>Complete upload and validation, then generate the report draft.</p><Button onClick={goBack}>Return to rules</Button></article>;
  const draft = calculation.draft || {};
  const identity = {
    reportTitle: "Daily Solar Performance Report",
    reportSubtitle: "Daily generation, irradiance, PR, losses, and inverter performance",
    preparedBy: "Analyst",
    preparedFor: customer?.customer_name || "Customer",
    customerLogoLabel: "AS",
    companyLogoLabel: "RG",
    ...reportIdentity,
  };
  const components = [...(draft.chart_specs || []), ...(draft.tables || [])];
  const pending = draft.pending_approvals || [];
  const fallbackCards = [
    ["generation_kwh", "Generation", "kWh"],
    ["gti_kwh_m2", "GTI", "kWh/m2"],
    ["pr_percent", "PR", "%"],
    ["specific_yield_kwh_per_kwp", "Specific Yield", "kWh/kWp"],
    ["total_loss_kwh", "Total Loss", "kWh"],
    ["data_availability_percent", "Data Availability", "%"],
  ].filter(([metric]) => draft.latest_kpis?.[metric] != null).map(([metric, label, unit]) => ({ metric, label, unit, value: draft.latest_kpis[metric] }));
  const suppliedCards = (draft.kpi_cards || []).length ? draft.kpi_cards : fallbackCards;
  const suppliedMetrics = new Set(suppliedCards.map((card) => card.metric));
  const extraCards = Object.entries(draft.latest_kpis || {})
    .filter(([metric, value]) => !suppliedMetrics.has(metric) && typeof value === "number")
    .map(([metric, value]) => ({ metric, label: humanize(metric), unit: "", value }));
  const kpiCards = [...suppliedCards, ...extraCards]
    .filter((card) => kpiReview[card.metric]?.included ?? suppliedMetrics.has(card.metric))
    .sort((a, b) => (kpiReview[a.metric]?.order ?? 999) - (kpiReview[b.metric]?.order ?? 999));
  const includedEvidence = Object.values(chartReview).filter((item) => item.included).length;
  const includedFindings = Object.values(findingReview).filter(Boolean).length;
  const findings = draft.triggered_findings || [];
  const orderedComponents = components
    .map((component, index) => ({ component, index, order: chartReview[component.component_id]?.order ?? index }))
    .sort((a, b) => a.order - b.order)
    .map(({ component }) => component);
  const availableMetrics = [...new Set([
    ...Object.keys(draft.latest_kpis || {}),
    ...components.flatMap((component) => [
      ...(component.metrics || []),
      ...(component.series || []).map((series) => series.metric),
      component.metric,
      ...(component.columns || []).filter((column) => !["date", "timestamp", "inverter_id", "status"].includes(column)),
    ]),
  ].filter(Boolean))].sort();
  const availableDimensions = new Set(components.flatMap((component) => [
    component.row_dimension,
    component.breakdown,
    ...(component.columns || []),
  ].filter(Boolean)));
  const supportedBreakdowns = draft.available_breakdowns?.length
    ? draft.available_breakdowns
    : [
      "site_total",
      ...(availableDimensions.has("inverter_id") || availableDimensions.has("inverter") ? ["inverter"] : []),
      ...(availableDimensions.has("block_id") || availableDimensions.has("block") ? ["block"] : []),
      ...(availableDimensions.has("loss_type") ? ["loss_type"] : []),
    ];
  const chartCapabilities = draft.chart_capabilities || { sources: [] };
  const updateComponent = (id, changes) => {
    if (draftApproved) return;
    setDraftApproved(false);
    setLayoutDirty(true);
    setChartReview((current) => ({ ...current, [id]: { ...current[id], ...changes } }));
  };
  const executiveBlock = (draft.narrative_blocks || []).find((block) => block.type === "executive_summary");
  const executiveKey = executiveBlock?.block_id || (executiveBlock ? (draft.narrative_blocks || []).indexOf(executiveBlock) : null);
  const executiveSummary = executiveKey == null ? "" : narrativeReview[executiveKey] ?? executiveBlock?.text ?? "";

  const componentConfiguration = (component, index) => {
    const review = chartReview[component.component_id] || {};
    return {
      componentId: component.component_id,
      included: review.included ?? true,
      order: review.order ?? index,
      title: review.title || component.title,
      metrics: splitMetrics(review.metrics || review.metric || (component.metrics || []).join(", ") || (component.series || []).map((series) => series.metric).join(", ") || component.metric || ""),
      startDate: review.startDate || component.start_date || String(component.x?.[0] || reportDate).slice(0, 10),
      endDate: review.endDate || component.end_date || String(component.x?.[component.x?.length - 1] || reportDate).slice(0, 10),
      breakdown: review.breakdown || component.breakdown || "site_total",
      chartType: review.chartType || component.type,
      aggregations: review.aggregations || component.aggregation_overrides || {},
      timeGrain: review.timeGrain || component.time_grain || "daily",
      textPosition: review.textPosition || "beside",
      explanationStatus: review.explanationStatus || "suggested",
      explanationSignature: review.explanationSignature || "",
      width: review.width || "full",
      section: review.section || "performance",
    };
  };
  const unresolvedExplanations = orderedComponents.filter((component) => {
    const review = chartReview[component.component_id] || {};
    if ((review.included ?? true) === false) return false;
    if (review.regenerationError || componentHasPendingChanges(component, review, reportDate)) return false;
    const linked = relatedFindingsFor(
      component,
      review,
      findings,
      findingReview,
      reportDate,
    );
    const signature = evidenceSignature(component, review, linked);
    return !(
      review.explanationSignature === signature
      && ["approved", "rejected"].includes(review.explanationStatus)
    );
  }).length;
  const componentsNeedingRegeneration = orderedComponents.filter((component) => {
    const review = chartReview[component.component_id] || {};
    if ((review.included ?? true) === false) return false;
    return Boolean(review.regenerationError) || componentHasPendingChanges(component, review, reportDate);
  });

  const layoutPayload = () => ({
    identity,
    theme: reportTheme,
    summaryPosition,
    kpiCards: [...suppliedCards, ...extraCards].map((card, index) => ({
      metric: card.metric,
      label: kpiReview[card.metric]?.label || card.label,
      included: kpiReview[card.metric]?.included ?? suppliedMetrics.has(card.metric),
      order: kpiReview[card.metric]?.order ?? index,
    })),
    components: orderedComponents.map(componentConfiguration),
  });

  const regenerate = async (component, request) => {
    setLocalError("");
    setWorkingComponent(component.component_id);
    try {
      const review = chartReview[component.component_id] || {};
      const generated = await generateComponent({
        componentId: component.component_id,
        title: review.title || component.title,
        metrics: request.metrics,
        startDate: request.startDate,
        endDate: request.endDate,
        breakdown: request.breakdown,
        chartType: request.chartType,
        aggregations: request.aggregations,
        timeGrain: request.timeGrain,
      });
      updateComponent(component.component_id, {
        chartType: generated.type,
        metrics: (generated.metrics || request.metrics).join(", "),
        startDate: request.startDate,
        endDate: request.endDate,
        breakdown: request.breakdown,
        aggregations: request.aggregations,
        timeGrain: request.timeGrain,
        regenerationError: "",
      });
      setNotice(`${review.title || component.title} regenerated from approved backend data.`);
    } catch (error) {
      setLocalError(error.message);
      updateComponent(component.component_id, {
        regenerationError: error.message,
      });
    } finally {
      setWorkingComponent("");
    }
  };

  const addComponent = async (configuration) => {
    setLocalError("");
    setWorkingComponent("new");
    try {
      const componentId = `custom_${Date.now()}`;
      const generated = await generateComponent({ ...configuration, componentId });
      setChartReview((current) => ({
        ...current,
        [componentId]: {
          included: true,
          order: Object.keys(current).length,
          title: configuration.title,
          metrics: (generated.metrics || configuration.metrics).join(", "),
          startDate: configuration.startDate,
          endDate: configuration.endDate,
          breakdown: generated.breakdown || configuration.breakdown,
          chartType: generated.type,
          aggregations: generated.aggregation_overrides || configuration.aggregations || {},
          timeGrain: generated.time_grain || configuration.timeGrain || "daily",
          textPosition: configuration.textPosition,
          width: configuration.width,
          explanationStatus: "suggested",
          explanationSignature: "",
          explanationEditedText: "",
          formulaFingerprint,
          section: "performance",
        },
      }));
      setLayoutDirty(true);
      setShowAddComponent(false);
      setNotice("New report component generated from approved backend data.");
    } catch (error) {
      setLocalError(error.message);
    } finally {
      setWorkingComponent("");
    }
  };

  const moveComponent = (componentId, direction) => {
    const ids = orderedComponents.map((component) => component.component_id);
    const index = ids.indexOf(componentId);
    const target = index + direction;
    if (target < 0 || target >= ids.length) return;
    const targetId = ids[target];
    setChartReview((current) => ({
      ...current,
      [componentId]: { ...current[componentId], order: target },
      [targetId]: { ...current[targetId], order: index },
    }));
    setDraftApproved(false);
    setLayoutDirty(true);
  };

  const persistLayout = async () => {
    if (componentsNeedingRegeneration.length) {
      setLocalError("Regenerate changed or failed charts before saving the customer layout.");
      return;
    }
    setSaving(true);
    setLocalError("");
    try {
      const creatingRevision = reportLayout?.status === "approved";
      const saved = await saveLayout(layoutPayload(), creatingRevision);
      setLayoutDirty(false);
      setNotice(creatingRevision ? `Layout v${saved.version} created for review.` : `Layout v${saved.version} saved.`);
    } catch (error) {
      setLocalError(error.message);
    } finally {
      setSaving(false);
    }
  };

  const approveSavedLayout = async () => {
    if (!reportLayout?.layout_id) return;
    if (componentsNeedingRegeneration.length) {
      setLocalError("Regenerate changed or failed charts before approving this layout.");
      return;
    }
    setSaving(true);
    setLocalError("");
    try {
      const approved = await approveLayout(reportLayout.layout_id);
      setNotice(`Layout v${approved.version} approved. Future reports can reuse it.`);
    } catch (error) {
      setLocalError(error.message);
    } finally {
      setSaving(false);
    }
  };

  const approveFinalReport = async () => {
    if (!reportLayout || reportLayout.status !== "approved") {
      setLocalError("Save and approve the customer layout before approving the final report.");
      return;
    }
    if (unresolvedExplanations) {
      setLocalError(
        `Approve or reject the ${unresolvedExplanations} outstanding system explanation(s) before final approval.`
      );
      return;
    }
    if (componentsNeedingRegeneration.length) {
      setLocalError("Regenerate all changed or failed charts before final report approval.");
      return;
    }
    setSaving(true);
    setLocalError("");
    const includedComponents = orderedComponents
      .filter((component) => chartReview[component.component_id]?.included ?? true)
      .map((component, index) => {
        const review = chartReview[component.component_id] || {};
        const linked = relatedFindingsFor(
          component,
          review,
          findings,
          findingReview,
          reportDate,
        );
        return {
          configuration: componentConfiguration(component, index),
          explanation: review.explanationStatus === "approved"
            ? (review.explanationEditedText || suggestedExplanation(component, review, linked))
            : null,
          explanation_status: review.explanationStatus,
          evidence_signature: evidenceSignature(component, review, linked),
          spec: component,
        };
      });
    const finalReport = {
      status: "approved",
      config_id: configId,
      report_date: reportDate,
      identity,
      theme: reportTheme,
      summary_position: summaryPosition,
      executive_summary: executiveSummary,
      kpi_cards: kpiCards,
      components: includedComponents,
      findings: findings.filter((finding, index) => findingReview[finding.finding_id || finding.rule_id || index] ?? true),
      narrative_blocks: (draft.narrative_blocks || []).map((block, index) => ({
        ...block,
        text: narrativeReview[block.block_id || index] ?? block.text ?? "",
      })),
      pending_approvals: pending,
    };
    try {
      const snapshot = await approveSnapshot(reportLayout.layout_id, finalReport);
      setDraftApproved(true);
      setMode("preview");
      setNotice(`Report approved and locked as revision ${snapshot.revision}.`);
    } catch (error) {
      setLocalError(error.message);
    } finally {
      setSaving(false);
    }
  };

  const summaryPanel = executiveSummary
    ? <section className="customer-summary"><span>Executive summary</span><p>{executiveSummary}</p></section>
    : null;
  const kpiPanel = <div className="kpi-grid dynamic-kpis">{kpiCards.map((card) => <article key={card.metric}><span>{kpiReview[card.metric]?.label || card.label}</span><strong>{number(card.value, card.unit ? ` ${card.unit}` : "")}</strong></article>)}</div>;

  if (mode === "preview") {
    return <div className={`customer-report theme-${reportTheme}`}>
      <div className="builder-mode-bar"><div><Status tone={draftApproved ? "success" : "warn"}>{draftApproved ? "Approved and locked" : "Customer preview"}</Status><span>{themeNames[reportTheme]} · Layout v{reportLayout?.version || "unsaved"}</span></div><Button onClick={() => setMode("build")}>{draftApproved ? "View approved configuration" : "Back to builder"}</Button></div>
      {componentsNeedingRegeneration.length > 0 && <div className="alert error">Preview is showing the last valid charts. Regenerate {componentsNeedingRegeneration.length} changed component(s) before saving or approving this report.</div>}
      <article className="report-preview-header"><div className="preview-logo customer">{identity.customerLogoLabel || "AS"}</div><div className="preview-title-block"><span>{customer?.customer_name || "Alpha Solar"} · {humanize(reportType)}</span><h1>{identity.reportTitle}</h1><p>{identity.reportSubtitle}</p><div className="preview-meta"><small>Prepared for <b>{identity.preparedFor}</b></small><small>Prepared by <b>{identity.preparedBy}</b></small><small>Report date <b>{reportDate}</b></small></div></div><div className="preview-logo company">{identity.companyLogoLabel || "RG"}</div></article>
      {summaryPosition === "top" && summaryPanel}
      {kpiPanel}
      {summaryPosition === "after_kpis" && summaryPanel}
      <div className="customer-component-grid">{orderedComponents.filter((component) => chartReview[component.component_id]?.included ?? true).map((component, index) => { const review = chartReview[component.component_id] || { title: component.title }; const linked = relatedFindingsFor(component, review, findings, findingReview, reportDate); return <section className={`customer-report-component width-${review.width || "full"}`} key={component.component_id || index}><h2>{review.title || component.title}</h2><ReportEvidence component={component} review={review} findings={linked} ChartRenderer={ChartRenderer} /></section>; })}</div>
      <footer className="report-lock-note">Approved report snapshot · Values calculated deterministically · Narrative approved by {identity.preparedBy}</footer>
    </div>;
  }

  return <>
    <div className="builder-mode-bar"><div><button className="active">Build report</button><button disabled={componentsNeedingRegeneration.length > 0} onClick={() => setMode("preview")}>Customer preview</button></div><span>{themeNames[reportTheme]} · {reportLayout ? `Layout v${reportLayout.version} ${humanize(reportLayout.status)}` : "Unsaved layout"}</span></div>
    {localError && <div className="alert error">{localError}</div>}
    <article className="card draft-head"><div><p className="eyebrow">{reportDate} · {humanize(reportType)}</p><h2>Report Builder & Review</h2><p>Compose the report from approved metrics, evidence, findings, and analyst-controlled wording.</p></div><div className="draft-head-status"><Status tone={draftApproved ? "success" : reportLayout?.status === "approved" ? "success" : "warn"}>{draftApproved ? "Approved and locked" : reportLayout ? `Layout ${humanize(reportLayout.status)}` : "Layout not saved"}</Status><small>{draftApproved ? "Create a revised report to make changes." : "Changes remain editable until final approval."}</small></div></article>

    <article className="card builder-controls"><div><label>Report theme<select disabled={draftApproved} value={reportTheme} onChange={(event) => { setReportTheme(event.target.value); setDraftApproved(false); setLayoutDirty(true); }}><option value="corporate_blue">Corporate Blue</option><option value="minimal">Minimal</option><option value="executive">Executive</option><option value="operations">Operations</option></select></label><label>Executive summary<select disabled={draftApproved} value={summaryPosition} onChange={(event) => { setSummaryPosition(event.target.value); setLayoutDirty(true); }}><option value="top">Top of report</option><option value="after_kpis">After KPI scorecards</option></select></label></div><div className="builder-actions"><Button disabled={draftApproved || saving || componentsNeedingRegeneration.length > 0 || (!layoutDirty && reportLayout?.status === "approved")} onClick={persistLayout}>{reportLayout?.status === "approved" ? "Create new layout version" : saving ? "Saving…" : "Save layout"}</Button>{reportLayout?.status === "draft" && <Button disabled={saving || layoutDirty || componentsNeedingRegeneration.length > 0} onClick={approveSavedLayout}>Approve layout v{reportLayout.version}</Button>}<Button disabled={draftApproved || saving || layoutDirty || componentsNeedingRegeneration.length > 0 || unresolvedExplanations > 0 || pending.length > 0 || reportLayout?.status !== "approved"} onClick={approveFinalReport}>{draftApproved ? "✓ Report approved" : "Approve final report"}</Button><button className="button secondary" disabled={componentsNeedingRegeneration.length > 0} onClick={() => setMode("preview")}>Customer preview</button></div></article>

    <article className="card approval-summary"><div><span>Pending approvals</span><strong>{pending.length}</strong><small>{pending.length ? "Resolve configuration items before delivery." : "Required configuration is approved."}</small></div><div><span>Included evidence</span><strong>{includedEvidence}/{components.length}</strong><small>Charts and tables in this draft.</small></div><div><span>Explanations to review</span><strong>{unresolvedExplanations}</strong><small>Approve or reject each new evidence pattern.</small></div><div><span>Layout memory</span><strong>{reportLayout ? `v${reportLayout.version}` : "—"}</strong><small>{reportLayout ? humanize(reportLayout.status) : "Save for this customer and report type."}</small></div></article>

    <article className="card executive-summary-review"><div className="draft-section-title"><div><h2>{draftApproved ? "Approved executive summary" : "Executive summary"}</h2><p>{draftApproved ? "This customer-facing summary is locked in the approved report snapshot." : "Edit the report-level story once. Chart explanations below carry the detailed evidence."}</p></div><Status tone={executiveBlock ? "success" : "warn"}>{executiveBlock ? "Customer-facing" : "Not generated"}</Status></div>{executiveBlock ? <label>Summary shown in customer preview<textarea disabled={draftApproved} value={executiveSummary} onChange={(event) => { setDraftApproved(false); setNarrativeReview((current) => ({ ...current, [executiveKey]: event.target.value })); }} /></label> : <Empty>No executive summary was generated for this draft.</Empty>}</article>

    {pending.length > 0 && <article className="card pending-list"><h3>Pending-approval detail</h3>{pending.map((item, index) => <div key={`${item.type}-${index}`}><Status tone="warn">{humanize(item.type || "review")}</Status><span>{item.message || item.metric_name || item.rule_name || "Analyst review required"}</span></div>)}</article>}
    {componentsNeedingRegeneration.length > 0 && <article className="card pending-list"><h3>Charts needing regeneration</h3>{componentsNeedingRegeneration.map((component) => { const review = chartReview[component.component_id] || {}; return <div key={component.component_id}><Status tone="warn">{review.regenerationError ? "Failed" : "Changed"}</Status><span>{review.title || component.title}: {review.regenerationError || "Apply & regenerate before saving, previewing, or approving."}</span></div>; })}</article>}
    <article className="card scorecard-builder"><div className="card-title-row"><div><h2>KPI scorecards</h2><p>Choose which approved values appear in the report. Calculated values remain locked.</p></div></div><div className="scorecard-options">{[...suppliedCards, ...extraCards].map((card, index) => { const included = kpiReview[card.metric]?.included ?? suppliedMetrics.has(card.metric); return <label className={included ? "included" : ""} key={card.metric}><input disabled={draftApproved} type="checkbox" checked={included} onChange={(event) => { setKpiReview((current) => ({ ...current, [card.metric]: { ...current[card.metric], included: event.target.checked, order: current[card.metric]?.order ?? index, label: current[card.metric]?.label || card.label } })); setDraftApproved(false); setLayoutDirty(true); }} /><span><strong>{kpiReview[card.metric]?.label || card.label}</strong><small>{number(card.value, card.unit ? ` ${card.unit}` : "")}</small></span></label>; })}</div></article>
    {kpiPanel}

    <div className="draft-section-title"><div><h2>Report evidence</h2><p>Add, regenerate, order, include, or retitle report components.</p></div><Button disabled={draftApproved} onClick={() => setShowAddComponent(true)}>＋ Add report component</Button></div>
    {showAddComponent && <AddComponentPanel reportDate={reportDate} availableMetrics={availableMetrics} supportedBreakdowns={supportedBreakdowns} chartCapabilities={chartCapabilities} onCancel={() => setShowAddComponent(false)} onAdd={addComponent} busy={workingComponent === "new"} />}
    <div className="chart-stack">{orderedComponents.map((component, index) => {
      const review = chartReview[component.component_id] || { included: true, title: component.title, order: index };
      const linkedFindings = relatedFindingsFor(component, review, findings, findingReview, reportDate);
      const needsRegeneration = Boolean(review.regenerationError) || componentHasPendingChanges(component, review, reportDate);
      return <article className={`card report-component ${review.included ? "" : "excluded"}`} key={component.component_id || index}>
        <header>
          <div>
            <Status>{humanize(component.type)}</Status>
            <input aria-label={`${component.title} title`} value={review.title || ""} disabled={draftApproved || !review.included} onChange={(event) => updateComponent(component.component_id, { title: event.target.value })} />
          </div>
          <div className="component-header-actions">
            <button disabled={draftApproved || index === 0} onClick={() => moveComponent(component.component_id, -1)}>↑</button>
            <button disabled={draftApproved || index === orderedComponents.length - 1} onClick={() => moveComponent(component.component_id, 1)}>↓</button>
            <Toggle checked={review.included} label={review.included ? "Included" : "Excluded"} onChange={(included) => updateComponent(component.component_id, { included })} />
          </div>
        </header>
        {review.included && <>
          <ChartPlanEditor component={component} review={review} reportDate={reportDate} supportedBreakdowns={supportedBreakdowns} chartCapabilities={chartCapabilities} onChange={(changes) => updateComponent(component.component_id, { ...changes, regenerationError: "" })} onRegenerate={(request) => regenerate(component, request)} busy={workingComponent === component.component_id} locked={draftApproved} />
          {needsRegeneration
            ? <div className="chart-request-error"><strong>Explanation approval paused</strong><span>Regenerate this chart from backend-approved data before approving the explanation or saving this layout.</span></div>
            : <ExplanationApproval component={component} review={review} findings={linkedFindings} locked={draftApproved} onChange={(changes) => updateComponent(component.component_id, changes)} />}
          <ReportEvidence component={component} review={review} findings={linkedFindings} ChartRenderer={ChartRenderer} />
        </>}
      </article>;
    })}</div>

    <details className="card findings-review analyst-finding-panel"><summary><div><h2>Analyst-only finding control panel</h2><p>Use this to include or exclude triggered rules. Customer-facing wording is reviewed in each chart explanation above.</p></div><Status tone="warn">{findings.length} triggered</Status></summary>{findings.length ? findings.map((finding, index) => { const key = finding.finding_id || finding.rule_id || index; const included = findingReview[key] ?? true; return <div className={`review-finding ${included ? "" : "excluded"}`} key={key}><div className="finding-heading"><Status tone={finding.severity === "high" ? "danger" : "warn"}>{finding.severity}</Status><Toggle checked={included} label={included ? "Included" : "Excluded"} onChange={(checked) => { setDraftApproved(false); setFindingReview((current) => ({ ...current, [key]: checked })); }} /></div><strong>{finding.title || humanize(finding.rule_name)}</strong><p>{finding.finding || finding.message || finding.description}</p>{finding.suggestion && <small className="suggestion">Suggested action · {finding.suggestion}</small>}<Evidence evidence={finding.evidence} /></div>; }) : <Empty>No approved insight rules triggered.</Empty>}</details>
  </>;
}
