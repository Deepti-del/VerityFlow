const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "The request could not be completed.");
  return data;
}

export const api = {
  customers: () => request("/customers"),
  profile: (customerId, reportType) => request(`/profile/${customerId}/${reportType}`),
  upload: (file) => {
    const body = new FormData();
    body.append("file", file);
    return request("/upload", { method: "POST", body });
  },
  validate: (body) => request("/validate", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  calculate: (body) => request("/calculate", {
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
