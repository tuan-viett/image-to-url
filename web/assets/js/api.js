/* ImageURL — API client wrapper.

Uses fetch() + JWT from localStorage. Same-origin since nginx proxies
both /api/* and the static files.
*/
window.ImageURL = (function () {
  const TOKEN_KEY = "imageurl:token";
  const USER_KEY = "imageurl:user";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setToken(t) {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  }

  function getUser() {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); }
    catch { return null; }
  }

  function setUser(u) {
    if (u) localStorage.setItem(USER_KEY, JSON.stringify(u));
    else localStorage.removeItem(USER_KEY);
  }

  function logout() {
    setToken(null);
    setUser(null);
    location.href = "/login.html";
  }

  async function request(path, opts = {}) {
    const headers = Object.assign({}, opts.headers || {});
    const token = getToken();
    if (token && !opts.skipAuth) headers["Authorization"] = "Bearer " + token;

    let body = opts.body;
    if (body && !(body instanceof FormData) && typeof body !== "string") {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }

    const res = await fetch(path, {
      method: opts.method || "GET",
      headers,
      body,
      credentials: "same-origin",
    });

    let data = null;
    try { data = await res.json(); } catch (_) { /* may be empty */ }

    if (!res.ok) {
      if (res.status === 401 && getToken() && !opts.skipAuth) {
        // Token expired -> force re-login.
        logout();
        throw new Error("Session expired");
      }
      const code = (data && data.error && data.error.code) || `HTTP_${res.status}`;
      const msg = (data && data.error && data.error.message) || res.statusText;
      const err = new Error(msg);
      err.code = code;
      err.details = (data && data.error && data.error.details) || {};
      err.status = res.status;
      throw err;
    }
    return data;
  }

  // High-level helpers --------------------------------------------------
  async function anonymousUpload(file) {
    const fd = new FormData();
    fd.append("file", file);
    return request("/api/v1/anonymous/images", {
      method: "POST",
      body: fd,
      skipAuth: true,
    });
  }

  async function anonymousUploadBase64(b64, filename) {
    const fd = new FormData();
    fd.append("image", b64);
    if (filename) fd.append("filename", filename);
    return request("/api/v1/anonymous/images", {
      method: "POST",
      body: fd,
      skipAuth: true,
    });
  }

  async function login(email, password) {
    return request("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
      skipAuth: true,
    });
  }

  async function register(email, password, name) {
    return request("/api/v1/auth/register", {
      method: "POST",
      body: { email, password, name },
      skipAuth: true,
    });
  }

  async function me() {
    return request("/api/v1/auth/me");
  }

  async function uploadFile(file) {
    const fd = new FormData();
    fd.append("file", file);
    return request("/api/v1/images", { method: "POST", body: fd });
  }

  async function uploadBase64(b64, filename) {
    const fd = new FormData();
    fd.append("image", b64);
    if (filename) fd.append("filename", filename);
    return request("/api/v1/images", { method: "POST", body: fd });
  }

  async function listImages(page = 1, pageSize = 20) {
    return request(`/api/v1/images?page=${page}&page_size=${pageSize}`);
  }

  async function deleteImage(id) {
    return request(`/api/v1/images/${id}`, { method: "DELETE" });
  }

  async function listApiKeys(page = 1, pageSize = 50) {
    return request(`/api/v1/api-keys?page=${page}&page_size=${pageSize}`);
  }

  async function createApiKey(name, environment = 1) {
    return request("/api/v1/api-keys", {
      method: "POST",
      body: { name, environment },
    });
  }

  async function revokeApiKey(id) {
    return request(`/api/v1/api-keys/${id}`, { method: "DELETE" });
  }

  async function getUsage() {
    return request("/api/v1/usage");
  }

  async function listPlans() {
    return request("/api/v1/plans", { skipAuth: true });
  }

  // Single source cho landing page: system limits (MB/hours) + active plans.
  // Đổi env hoặc DB là tất cả client pick up — không sửa HTML.
  async function getPublicConfig() {
    return request("/api/v1/config/public", { skipAuth: true });
  }

  async function upgradePlan(planId) {
    return request("/api/v1/payments/upgrade", {
      method: "POST",
      body: { plan_id: planId },
    });
  }

  async function topupCredits(amountCredits, amountVnd) {
    return request("/api/v1/payments/topup", {
      method: "POST",
      body: { amount_credits: amountCredits, amount_vnd: amountVnd },
    });
  }

  async function getSepayConfig() {
    return request("/api/v1/payments/sepay-config", { skipAuth: true });
  }

  async function getPaymentStatus(paymentId) {
    return request(`/api/v1/payments/${paymentId}/status`);
  }

  async function listPayments() {
    return request("/api/v1/payments");
  }

  async function aiGenerate({ prompt, size, quality, output_format }) {
    return request("/api/v1/ai/generations", {
      method: "POST",
      body: { prompt, size, quality, output_format },
    });
  }

  async function getAIStatus() {
    return request("/api/v1/ai/status", { skipAuth: true });
  }

  return {
    getToken, setToken, getUser, setUser, logout, request,
    anonymousUpload, anonymousUploadBase64,
    login, register, me,
    uploadFile, uploadBase64, listImages, deleteImage,
    listApiKeys, createApiKey, revokeApiKey,
    getUsage, listPlans, getPublicConfig, upgradePlan, topupCredits, listPayments,
    getSepayConfig, getPaymentStatus,
    aiGenerate, getAIStatus,
  };
})();