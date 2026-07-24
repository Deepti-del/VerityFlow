const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "The request could not be completed.");
  return data;
}

export const api = {
  customers: () => request("/customers"),
  customerContext: (customerId) => request(`/customers/${customerId}/context`),
  createCustomer: (body) => request("/customers", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  profile: (customerId, reportType) => request(`/profile/${customerId}/${reportType}`),
  upload: (file) => {
    const body = new FormData();
    body.append("file", file);
    return request("/upload", { method: "POST", body });
  },
  connectBigQuery: (body) => request("/sources/bigquery/connect", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  validate: (body) => request("/validate", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  calculate: (body) => request("/calculate", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  generateReportComponent: (body) => request("/report-components/generate", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  reportLayout: (configId) => request(`/report-layouts/${configId}`),
  saveReportLayout: (configId, body) => request(`/report-layouts/${configId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  approveReportLayout: (layoutId, body) => request(`/report-layouts/${layoutId}/approve`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  approveReportSnapshot: (body) => request("/report-snapshots/approve", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  mappings: (customerId) => request(`/mappings/${customerId}`),
  approveMappings: (body) => request("/approve/mappings", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  resetMappings: (body) => request("/mappings/reset", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  formulas: (customerId, reportType) => request(`/formulas/${customerId}/${reportType}`),
  validateFormula: (body) => request("/formulas/validate", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  approveFormula: (body) => request("/approve/formula", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  approveQuestion: (body) => request("/approve/question", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  approveRule: (body) => request("/approve/insight-rule", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
};
