import React, { useEffect, useState } from "react";
import { api } from "./api.js";

const STEPS = [
  ["Customer Profile", "Choose the reporting context"],
  ["Upload & Report", "Add the workbook and period"],
  ["Validate", "Review deterministic data checks"],
  ["Mapping & Formulas", "Confirm calculation inputs"],
  ["Questions & Rules", "Approve the reporting logic"],
  ["Draft Review", "Review evidence and narrative"],
];

const fmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const humanize = (value = "") => value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const number = (value, suffix = "") => value == null ? "—" : `${fmt.format(value)}${suffix}`;

function Status({ children, tone = "neutral" }) {
  return <span className={`status ${tone}`}>{children}</span>;
}

function Button({ children, secondary = false, ...props }) {
  return <button className={secondary ? "button secondary" : "button"} {...props}>{children}</button>;
}

function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

function App() {
  const [step, setStep] = useState(0);
  const [customers, setCustomers] = useState([]);
  const [customerId, setCustomerId] = useState("alpha_solar");
  const [reportType, setReportType] = useState("daily_generation");
  const [reportDate, setReportDate] = useState("2025-06-14");
  const [profile, setProfile] = useState(null);
  const [file, setFile] = useState(null);
  const [fileId, setFileId] = useState("");
  const [validation, setValidation] = useState(null);
  const [calculation, setCalculation] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [question, setQuestion] = useState("");

  const loadProfile = async () => {
    const data = await api.profile(customerId, reportType);
    setProfile(data);
    return data;
  };

  useEffect(() => {
    api.customers().then((data) => setCustomers(data.customers || [])).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    loadProfile().catch((e) => setError(e.message));
  }, [customerId, reportType]);

  const customer = customers.find((item) => item.customer_id === customerId);
  const mappings = validation?.summary?.sheets?.daily_kpis?.mapping?.mapped || [];
  const draft = calculation?.draft || {};
  const kpis = calculation?.kpis || {};

  const run = async (action, success) => {
    setBusy(true); setError(""); setNotice("");
    try { await action(); if (success) setNotice(success); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const uploadWorkbook = () => run(async () => {
    if (!file) throw new Error("Choose an Excel workbook first.");
    const result = await api.upload(file);
    setFileId(result.file_id); setValidation(null); setCalculation(null);
  }, "Workbook uploaded and ready for validation.");

  const validateWorkbook = () => run(async () => {
    if (!fileId) throw new Error("Upload the workbook before validation.");
    setValidation(await api.validate({ customer_id: customerId, report_type: reportType, report_date: reportDate, file_id: fileId }));
  }, "Deterministic validation completed.");

  const calculateDraft = () => run(async () => {
    if (!fileId) throw new Error("Upload the workbook before creating a draft.");
    setCalculation(await api.calculate({ customer_id: customerId, report_type: reportType, report_date: reportDate, file_id: fileId }));
    setStep(5);
  }, "Draft assembled from approved calculations and rules.");

  const confirmMappings = () => run(async () => {
    const payload = mappings.map((item) => ({
      system_column: item.system_col, customer_column: item.customer_col, data_type: "numeric",
    }));
    await api.approveMappings({ customer_id: customerId, mappings: payload });
    await validateWorkbook();
  }, "Mappings confirmed by analyst.");

  const approveFormula = (metric) => run(async () => {
    await api.approveFormula({
      customer_id: customerId, report_type: reportType, metric_name: metric.metric_name,
      output_column: metric.output_column, input_columns: metric.input_columns || [], scope: "customer_report_type",
    });
    await loadProfile();
  }, `${metric.metric_name} approved.`);

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

  const pageTitle = STEPS[step][0];
  const ready = Boolean(fileId && validation?.valid);

  return (
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
        <header className="topbar"><div><p className="eyebrow">Alpha Solar · Daily generation</p><h1>{pageTitle}</h1></div><Status tone={profile?.pending_approval_count ? "warn" : "success"}>{profile?.pending_approval_count || 0} pending approvals</Status></header>
        {error && <div className="alert error">{error}</div>}
        {notice && <div className="alert success">{notice}</div>}

        {step === 0 && (
          <section className="panel-grid two">
            <article className="card hero-card"><p className="eyebrow">Reporting account</p><h2>{customer?.customer_name || "Alpha Solar"}</h2><p>Configure the customer and report type that own mappings, formulas, questions, and insight rules.</p><div className="metric-strip"><div><span>Customer ID</span><strong>{customerId}</strong></div><div><span>Status</span><strong>{humanize(customer?.status || "ready")}</strong></div><div><span>Reports</span><strong>{customer?.report_count || 0}</strong></div></div></article>
            <article className="card form-card"><label>Customer<select value={customerId} onChange={(e) => setCustomerId(e.target.value)}>{customers.map((item) => <option key={item.customer_id} value={item.customer_id}>{item.customer_name}</option>)}</select></label><label>Report type<select value={reportType} onChange={(e) => setReportType(e.target.value)}><option value="daily_generation">Daily generation</option></select></label><Button onClick={() => setStep(1)}>Continue to upload</Button></article>
          </section>
        )}

        {step === 1 && (
          <section className="panel-grid two">
            <article className="card upload-card"><div className="upload-icon">↥</div><h2>Upload source workbook</h2><p>Excel remains the source input. ReportGen stores approved configuration separately as product memory.</p><label className="file-picker"><input aria-label="Source workbook" type="file" accept=".xlsx,.xls" onChange={(e) => setFile(e.target.files?.[0] || null)} /><span>{file ? file.name : "Choose Excel workbook"}</span></label><Button disabled={busy || !file} onClick={uploadWorkbook}>{busy ? "Uploading…" : "Upload workbook"}</Button>{fileId && <Status tone="success">Uploaded · {fileId.slice(0, 8)}</Status>}</article>
            <article className="card form-card"><h3>Report context</h3><label>Report date<input type="date" value={reportDate} onChange={(e) => setReportDate(e.target.value)} /></label><label>Calculation policy<input value="Approved Python / pandas formulas" disabled /></label><div className="callout">KPI values are never generated by AI. The calculation engine uses approved deterministic formulas.</div><Button secondary disabled={!fileId} onClick={() => setStep(2)}>Review validation</Button></article>
          </section>
        )}

        {step === 2 && (
          <section>
            <article className="card section-head"><div><h2>Workbook validation</h2><p>Check structure, data types, completeness, duplicates, and mapping coverage before calculation.</p></div><Button disabled={busy || !fileId} onClick={validateWorkbook}>{busy ? "Checking…" : "Run validation"}</Button></article>
            {!validation ? <Empty>Upload a workbook and run deterministic validation.</Empty> : <div className="panel-grid three summary-cards"><article className="card"><span>Result</span><strong className={validation.valid ? "good" : "bad"}>{validation.valid ? "Passed" : "Needs attention"}</strong></article><article className="card"><span>Errors</span><strong>{validation.errors.length}</strong></article><article className="card"><span>Warnings</span><strong>{validation.warnings.length}</strong></article></div>}
            {validation && <article className="card"><h3>Validation detail</h3>{[...validation.errors, ...validation.warnings].length === 0 ? <p className="checkline">✓ No blocking data-quality issues were found.</p> : [...validation.errors, ...validation.warnings].map((item, index) => <p className="issue" key={index}>{typeof item === "string" ? item : JSON.stringify(item)}</p>)}<div className="actions"><Button secondary onClick={() => setStep(3)}>Review mappings & formulas</Button></div></article>}
          </section>
        )}

        {step === 3 && (
          <section>
            <article className="card section-head"><div><h2>Mapping & formula approval</h2><p>The analyst owns how customer columns become standard metrics and how derived KPIs are calculated.</p></div>{mappings.length > 0 && <Button onClick={confirmMappings}>Confirm {mappings.length} mappings</Button>}</article>
            <div className="panel-grid two"><article className="card"><h3>Column mappings</h3>{mappings.length ? <div className="table-list">{mappings.map((item) => <div className="table-row" key={item.system_col}><span>{item.customer_col}</span><b>→</b><strong>{item.system_col}</strong><Status tone={item.confirmed ? "success" : "warn"}>{item.confirmed ? "Confirmed" : "Review"}</Status></div>)}</div> : <Empty>Run validation to inspect workbook mappings.</Empty>}</article><article className="card"><h3>Derived KPI formulas</h3>{profile?.derivable?.map((metric) => <div className="approval-row" key={metric.metric_name}><div><strong>{metric.metric_name}</strong><code>{metric.formula}</code></div>{metric.approved_by_analyst ? <Status tone="success">Approved</Status> : <Button secondary onClick={() => approveFormula(metric)}>Approve</Button>}</div>)}</article></div>
            <div className="actions"><Button secondary onClick={() => setStep(4)}>Continue to questions & rules</Button></div>
          </section>
        )}

        {step === 4 && (
          <section className="panel-grid two"><article className="card"><h2>Standing customer questions</h2><p>Questions recur with every report and determine which evidence components belong in the draft.</p><div className="inline-form"><input aria-label="Standing customer question" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="What caused the PR change?" /><Button onClick={addQuestion}>Add</Button></div>{profile?.customer_questions?.map((item) => <div className="approval-row" key={item.question_id || item.question_text}><div><strong>{item.question_text}</strong><small>{item.answer_purpose || "Recurring report question"}</small></div><Status tone={item.approved_by_analyst ? "success" : "warn"}>{item.approved_by_analyst ? "Approved" : "Suggested"}</Status></div>)}</article><article className="card"><h2>Insight rules</h2><p>Only approved deterministic conditions can trigger findings.</p>{profile?.insight_rules?.map((rule) => <div className="approval-row" key={rule.rule_id || rule.rule_name}><div><strong>{rule.rule_name}</strong><code>{rule.condition}</code><small>Severity · {rule.severity}</small></div>{rule.approved_by_analyst ? <Status tone="success">Approved</Status> : <Button secondary onClick={() => approveRule(rule)}>Approve</Button>}</div>)}<div className="actions"><Button disabled={!ready || busy} onClick={calculateDraft}>{busy ? "Calculating…" : "Generate deterministic draft"}</Button></div></article></section>
        )}

        {step === 5 && (
          <section>
            {!calculation ? <article className="card empty"><h2>No draft yet</h2><p>Complete upload and validation, then generate the report draft.</p><Button onClick={() => setStep(4)}>Return to rules</Button></article> : <><article className="card draft-head"><div><p className="eyebrow">{reportDate} · {humanize(reportType)}</p><h2>{customer?.customer_name || "Alpha Solar"} performance draft</h2><p>Evidence below comes from Python calculations and analyst-approved rules.</p></div><Status tone={draft.status === "draft_ready" ? "success" : "warn"}>{humanize(draft.status || "draft")}</Status></article><div className="kpi-grid"><article><span>Performance ratio</span><strong>{number(kpis.pr_percent, "%")}</strong></article><article><span>Generation</span><strong>{number(kpis.generation_kwh, " kWh")}</strong></article><article><span>Specific yield</span><strong>{number(kpis.specific_yield_kwh_per_kwp)}</strong></article><article><span>Data availability</span><strong>{number(kpis.data_availability_percent, "%")}</strong></article></div><div className="panel-grid two"><article className="card"><h3>Triggered findings</h3>{calculation.findings.length ? calculation.findings.map((finding, index) => <div className="finding" key={finding.finding_id || index}><Status tone={finding.severity === "high" ? "danger" : "warn"}>{finding.severity}</Status><div><strong>{finding.title || humanize(finding.rule_name)}</strong><p>{finding.finding || finding.message || finding.description}</p><small>{finding.suggestion}</small></div></div>) : <Empty>No approved insight rules triggered.</Empty>}</article><article className="card"><h3>Editable narrative</h3>{draft.narrative_blocks?.map((block, index) => <div className="narrative" key={block.block_id || index}><span>{humanize(block.block_type || block.type)}</span><textarea defaultValue={block.text || block.content} /></div>)}{!draft.narrative_blocks?.length && <Empty>The deterministic draft contains no narrative blocks.</Empty>}</article></div><article className="card"><h3>Evidence components</h3><div className="component-grid">{(calculation.chart_specs || []).map((chart, index) => <div key={chart.component_id || index}><span>{humanize(chart.chart_type || chart.type || "chart")}</span><strong>{chart.title || humanize(chart.component_id)}</strong></div>)}</div></article></>}
          </section>
        )}

        <footer><Button secondary disabled={step === 0} onClick={() => setStep((value) => Math.max(0, value - 1))}>Back</Button><span>Step {step + 1} of {STEPS.length}</span><Button secondary disabled={step === STEPS.length - 1} onClick={() => setStep((value) => Math.min(STEPS.length - 1, value + 1))}>Next</Button></footer>
      </main>
    </div>
  );
}

export default App;
