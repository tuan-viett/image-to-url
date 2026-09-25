/* ImageURL — Auth helpers for login.html and register.html, plus a global
   requireAuth() guard used by dashboard.html. */
(function () {
  function showError(msg) {
    const box = document.getElementById("err");
    if (box) box.textContent = msg || "";
  }

  async function handleLogin(ev) {
    ev.preventDefault();
    showError("");
    const fd = new FormData(ev.target);
    const email = fd.get("email");
    const password = fd.get("password");
    try {
      const resp = await ImageURL.login(email, password);
      ImageURL.setToken(resp.data.access_token);
      ImageURL.setUser(resp.data.user);
      const dest = readPostLoginDest();
      location.href = dest || "/dashboard.html";
    } catch (err) {
      showError(err.message || "Login failed");
    }
  }

  async function handleRegister(ev) {
    ev.preventDefault();
    showError("");
    const fd = new FormData(ev.target);
    const name = (fd.get("name") || "").toString();
    const email = fd.get("email");
    const password = fd.get("password");
    try {
      const resp = await ImageURL.register(email, password, name);
      ImageURL.setToken(resp.data.access_token);
      ImageURL.setUser(resp.data.user);
      const dest = readPostLoginDest();
      location.href = dest || "/dashboard.html";
    } catch (err) {
      showError(err.message || "Registration failed");
    }
  }

  function readPostLoginDest() {
    try {
      const dest = sessionStorage.getItem("imageurl:postLogin");
      if (dest && (dest.startsWith("/") && !dest.startsWith("//"))) {
        sessionStorage.removeItem("imageurl:postLogin");
        return dest;
      }
    } catch (_) {}
    return null;
  }

  function initLoginPage() {
    const form = document.getElementById("loginForm");
    if (form) form.addEventListener("submit", handleLogin);
    if (ImageURL.getToken()) {
      // already logged in -> skip login
      location.href = "/dashboard.html";
    }
  }

  function initRegisterPage() {
    const form = document.getElementById("registerForm");
    if (form) form.addEventListener("submit", handleRegister);
    if (ImageURL.getToken()) {
      location.href = "/dashboard.html";
    }
  }

  async function requireAuth() {
    if (!ImageURL.getToken()) {
      location.href = "/login.html";
      return null;
    }
    try {
      const r = await ImageURL.me();
      ImageURL.setUser(r.data);
      return r.data;
    } catch (err) {
      ImageURL.logout();
      return null;
    }
  }

  window.initLoginPage = initLoginPage;
  window.initRegisterPage = initRegisterPage;
  window.requireAuth = requireAuth;
})();