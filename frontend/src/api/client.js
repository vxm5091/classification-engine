import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

// --- Transactions ---
export async function getTransactions(params = {}) {
  const { data } = await api.get("/transactions", { params });
  return data;
}

export async function getTransaction(id) {
  const { data } = await api.get(`/transactions/${id}`);
  return data;
}

export async function approveTransaction(id, body) {
  const { data } = await api.post(`/transactions/${id}/approve`, body);
  return data;
}

export async function reclassifyTransaction(id, body) {
  const { data } = await api.post(`/transactions/${id}/reclassify`, body);
  return data;
}

export async function flagTransaction(id, body) {
  const { data } = await api.post(`/transactions/${id}/flag`, body);
  return data;
}

export async function convertToRule(id, body) {
  const { data } = await api.post(`/transactions/${id}/convert-to-rule`, body);
  return data;
}

// --- Rules ---
export async function getRules() {
  const { data } = await api.get("/rules");
  return data;
}

export async function createRule(body) {
  const { data } = await api.post("/rules", body);
  return data;
}

export async function updateRule(id, body) {
  const { data } = await api.put(`/rules/${id}`, body);
  return data;
}

export async function deactivateRule(id) {
  const { data } = await api.post(`/rules/${id}/deactivate`);
  return data;
}

// --- Vendors ---
export async function getVendors(search) {
  const params = search ? { search } : {};
  const { data } = await api.get("/vendors", { params });
  return data;
}

export async function createVendor(body) {
  const { data } = await api.post("/vendors", body);
  return data;
}

export async function confirmVendor(id, body) {
  const { data } = await api.post(`/vendors/${id}/confirm`, body);
  return data;
}

export async function getVendorServices(id) {
  const { data } = await api.get(`/vendors/${id}/services`);
  return data;
}

export async function createVendorService(id, body) {
  const { data } = await api.post(`/vendors/${id}/services`, body);
  return data;
}

// --- GL Codes ---
export async function getGLCodes(level) {
  const params = level ? { level } : {};
  const { data } = await api.get("/gl-codes", { params });
  return data;
}

export async function getGLHierarchy() {
  const { data } = await api.get("/gl-codes");
  return data;
}

// --- Source Files ---
export async function getSourceFiles() {
  const { data } = await api.get("/transactions/source-files");
  return data;
}

// --- Upload & Classify ---
export async function uploadCSV(file) {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post("/upload-csv", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function triggerClassify(body) {
  const { data } = await api.post("/classify", body);
  return data;
}

// --- Stats ---
export async function getStats() {
  const { data } = await api.get("/stats");
  return data;
}

export default api;
