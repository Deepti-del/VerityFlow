# VerityFlow demo narration

Target duration: approximately 3 minutes.

## 0:00–0:15 — Problem and product

Recurring operational reporting is not simply a writing task. Analysts must validate incoming data, apply customer-specific calculations, investigate exceptions, and explain every conclusion before a report can be trusted. VerityFlow brings those decisions into one governed workflow.

## 0:15–0:30 — Customer reporting memory

I begin by selecting Alpha Solar and its daily generation report. VerityFlow loads the customer’s saved sites, report configuration, mappings, formulas, questions, rules, and presentation preferences, so these decisions do not have to be recreated for every report.

## 0:30–0:45 — Source and validation

The product accepts Excel or clean BigQuery views. Before any calculations are performed, it validates structure, data types, completeness, duplicates, and mapping coverage. It does not silently repair source data; it identifies problems that require correction upstream.

## 0:45–1:05 — Deterministic calculations

Customer columns are mapped to standard metrics, and KPI values are calculated using analyst-approved deterministic formulas. Questions and business rules are also approved explicitly. AI is never responsible for inventing KPI values or deciding whether a numerical rule has been triggered.

## 1:05–1:45 — Moss retrieval and grounded context

This is the governed retrieval layer. On the left are findings calculated from approved data and rules. On the right, Moss retrieves only the business context relevant to this customer, report type, and KPI—such as an approved KPI definition, interpretation rule, customer priority, or reporting guideline.

Operational measurements remain in the deterministic analytics layer. Moss stores and retrieves the approved knowledge surrounding those measurements. The interface exposes the retrieved sources, relevance scores, filters, and measured retrieval latency so the analyst can see exactly what influenced the wording.

## 1:45–2:05 — Reviewable narrative

VerityFlow combines the calculated evidence with the retrieved approved context to assemble a grounded draft. The narrative remains awaiting analyst approval. Retrieved context can never bypass review, and the analyst can accept, edit, or reject the wording before it enters the customer report.

## 2:05–2:35 — Evidence and chart builder

The report builder keeps every visual tied to approved backend data. Analysts can choose compatible chart types, periods, breakdowns, aggregation methods, and explanation placement. The report can include inverter heatmaps, generation and irradiation comparisons, dual-axis diagnostics, data-availability trends, and a waterfall showing how individual losses bridge expected and actual generation.

## 2:35–2:50 — Customer-ready output

Once the evidence and wording are approved, VerityFlow creates a customer-facing report with an executive summary, KPI scorecards, charts, and explanations. The approved report can then be exported as a PDF while preserving the analyst’s decisions and evidence trail.

## 2:50–3:05 — Closing

VerityFlow is not an AI report writer. It is an evidence-grounded reporting agent: deterministic engines establish what happened, Moss retrieves the approved context needed to interpret it, and the analyst controls what is ultimately published.

## Recording notes

- Speak slowly and conversationally rather than reading quickly.
- Pause briefly when the Moss Retrieved panel appears.
- Keep the cursor still while explaining evidence and retrieved context.
- Do not claim a specific latency number aloud; let the measured value appear in the UI.
- End on the customer-ready report or a simple VerityFlow closing slide.
