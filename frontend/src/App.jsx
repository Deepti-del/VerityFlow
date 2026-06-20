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
  const [mappingProfile, setMappingProfile] = useState(null);
  const [mappingDrafts, setMappingDrafts] = useState({});
  const [mappingSearch, setMappingSearch] = useState("");
  const [formulaProfile, setFormulaProfile] = useState(null);
  const [formulaDraft, setFormulaDraft] = useState(null);
  const [formulaValidation, setFormulaValidation] = useState(null);

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
    Promise.all([loadProfile(), loadMappings(), loadFormulas()])
      .catch((e) => setError(e.message));
  }, [customerId, reportType]);

  const customer = customers.find((item) => item.customer_id === customerId);
  const mappings = mappingProfile?.mappings || [];
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

  const pageTitle = STEPS[step][0];
  const ready = Boolean(fileId && validation?.valid);
  const filteredMappings = mappings.filter((item) => {
    const query = mappingSearch.trim().toLowerCase();
    return !query || item.system_column.toLowerCase().includes(query)
      || item.customer_column.toLowerCase().includes(query);
  });

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
        <header className="topbar"><div><p className="eyebrow">Alpha Solar · Daily generation</p><h1>{pageTitle}</h1></div><Status tone={profile?.pending_approval_count ? "warn" : "success"}>{profile?.pending_approval_count || 0} pending approvals</Status></header>
        {error && <div className="alert error">{error}</div>}
        {notice && <div className="alert success">{notice}</div>}

        {step === 0 && (
          <section className="customer-profile">
            <article className="card selector-card"><label>Select customer<select value={customerId} onChange={(e) => setCustomerId(e.target.value)}>{customers.map((item) => <option key={item.customer_id} value={item.customer_id}>{item.customer_name}</option>)}</select></label><Button secondary>＋ Add customer</Button><label>Report type<select value={reportType} onChange={(e) => setReportType(e.target.value)}><option value="daily_generation">Daily Generation Report</option></select></label></article>
            <div className="panel-grid three summary-cards"><article className="card"><span>Last 180 reports</span><strong>{customer?.report_count || 0}</strong><small>Generated successfully</small></article><article className="card"><span>Status</span><strong className="setup-status">{humanize(customer?.status || "setup in progress")}</strong><small>Continue setup to generate reports</small></article><article className="card"><span>Customer memory</span><strong className="memory-saved">✓ Customer memory saved</strong><small>Preferences will be remembered</small></article></div>
            <div className="panel-grid two profile-memory"><article className="card"><h3>Preferred KPIs</h3><div className="tag-list"><span>PR</span><span>Specific Yield</span><span>Curtailment Loss</span></div></article><article className="card"><h3>Standing Questions</h3><ul>{(profile?.customer_questions || []).slice(0, 4).map((item) => <li key={item.question_id || item.question_text}>{item.question_text}</li>)}</ul></article></div>
            <div className="panel-grid two profile-memory"><article className="card"><h3>Approved Formula Store</h3>{(profile?.derivable || []).filter((item) => item.approved_by_analyst).slice(0, 3).map((item) => <div className="memory-row" key={item.metric_name}><span>{item.metric_name}</span><Status tone="success">Approved</Status></div>)}{!(profile?.derivable || []).some((item) => item.approved_by_analyst) && <p className="muted-line">No formulas approved yet</p>}</article><article className="card"><h3>Approved Rules</h3>{(profile?.insight_rules || []).filter((item) => item.approved_by_analyst).slice(0, 3).map((item) => <div className="memory-row" key={item.rule_id || item.rule_name}><span>{item.rule_name}</span><Status tone="success">Approved</Status></div>)}{!(profile?.insight_rules || []).some((item) => item.approved_by_analyst) && <p className="muted-line">No insight rules approved yet</p>}</article></div>
            <div className="info-banner">ⓘ Chart and layout preferences can be configured after draft review.</div>
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
          <section className="panel-grid two"><article className="card"><h2>Standing customer questions</h2><p>Questions recur with every report and determine which evidence components belong in the draft.</p><div className="inline-form"><input aria-label="Standing customer question" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="What caused the PR change?" /><Button onClick={addQuestion}>Add</Button></div>{profile?.customer_questions?.map((item) => <div className="approval-row" key={item.question_id || item.question_text}><div><strong>{item.question_text}</strong><small>{item.answer_purpose || "Recurring report question"}</small></div><Status tone={item.approved_by_analyst ? "success" : "warn"}>{item.approved_by_analyst ? "Approved" : "Suggested"}</Status></div>)}</article><article className="card"><h2>Insight rules</h2><p>Only approved deterministic conditions can trigger findings.</p>{profile?.insight_rules?.map((rule) => <div className="approval-row" key={rule.rule_id || rule.rule_name}><div><strong>{rule.rule_name}</strong><code>{rule.condition}</code><small>Severity · {rule.severity}</small></div>{rule.approved_by_analyst ? <Status tone="success">Approved</Status> : <Button secondary onClick={() => approveRule(rule)}>Approve</Button>}</div>)}<div className="actions"><Button disabled={!ready || busy} onClick={calculateDraft}>{busy ? "Calculating…" : "Generate deterministic draft"}</Button></div></article></section>
        )}

        {step === 5 && (
          <section>
            {!calculation ? <article className="card empty"><h2>No draft yet</h2><p>Complete upload and validation, then generate the report draft.</p><Button onClick={() => setStep(4)}>Return to rules</Button></article> : <><article className="card draft-head"><div><p className="eyebrow">{reportDate} · {humanize(reportType)}</p><h2>{customer?.customer_name || "Alpha Solar"} performance draft</h2><p>Evidence below comes from Python calculations and analyst-approved rules.</p></div><Status tone={draft.status === "draft_ready" ? "success" : "warn"}>{humanize(draft.status || "draft")}</Status></article><div className="kpi-grid"><article><span>Performance ratio</span><strong>{number(kpis.pr_percent, "%")}</strong></article><article><span>Generation</span><strong>{number(kpis.generation_kwh, " kWh")}</strong></article><article><span>Specific yield</span><strong>{number(kpis.specific_yield_kwh_per_kwp)}</strong></article><article><span>Data availability</span><strong>{number(kpis.data_availability_percent, "%")}</strong></article></div><div className="panel-grid two"><article className="card"><h3>Triggered findings</h3>{calculation.findings.length ? calculation.findings.map((finding, index) => <div className="finding" key={finding.finding_id || index}><Status tone={finding.severity === "high" ? "danger" : "warn"}>{finding.severity}</Status><div><strong>{finding.title || humanize(finding.rule_name)}</strong><p>{finding.finding || finding.message || finding.description}</p><small>{finding.suggestion}</small></div></div>) : <Empty>No approved insight rules triggered.</Empty>}</article><article className="card"><h3>Editable narrative</h3>{draft.narrative_blocks?.map((block, index) => <div className="narrative" key={block.block_id || index}><span>{humanize(block.block_type || block.type)}</span><textarea defaultValue={block.text || block.content} /></div>)}{!draft.narrative_blocks?.length && <Empty>The deterministic draft contains no narrative blocks.</Empty>}</article></div><article className="card"><h3>Evidence components</h3><div className="component-grid">{(calculation.chart_specs || []).map((chart, index) => <div key={chart.component_id || index}><span>{humanize(chart.chart_type || chart.type || "chart")}</span><strong>{chart.title || humanize(chart.component_id)}</strong></div>)}</div></article></>}
          </section>
        )}

        <footer><div className="progress-saved">✓ Progress saved. You can return to any previous step.</div><div className="footer-actions"><Button secondary disabled={step === 0} onClick={() => setStep((value) => Math.max(0, value - 1))}>Back</Button><span>Step {step + 1} of {STEPS.length}</span><Button disabled={step === STEPS.length - 1} onClick={() => setStep((value) => Math.min(STEPS.length - 1, value + 1))}>{step === 0 ? "Save & Continue" : "Continue"} →</Button></div></footer>
      </main>
      </div>
    </div>
  );
}

export default App;
