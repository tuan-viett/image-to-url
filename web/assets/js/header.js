/* ImageURL — Shared topbar component used by landing + dashboard.
   Renders into <header id="appHeader"></header>. Detects auth state from
   localStorage token + cached user, and fetches /me if needed. */
(function () {
  async function renderTopbar(opts = {}) {
    const host = document.getElementById("appHeader");
    if (!host) return;

    const user = ImageURL.getUser();
    const token = ImageURL.getToken();
    let me = user;
    if (token && !me) {
      try {
        const r = await ImageURL.me();
        ImageURL.setUser(r.data);
        me = r.data;
      } catch (_) {
        ImageURL.setToken(null);
        ImageURL.setUser(null);
      }
    }

    const planBadge = me
      ? `<a href="/payment.html" class="h-chip h-plan"><b>${escapeHtml(me.plan_name)}</b> plan · nâng cấp</a>`
      : "";

    // Credits chip: hiển thị "current / quota" + tooltip "used N · plan max M".
    // quota = plan_initial_uploads của plan hiện tại (không tính top-up).
    // Nếu user đã renewal nhiều lần → upload_credits > quota (do cộng dồn).
    // Trường hợp đó vẫn hiển thị quota max; tooltip sẽ nói rõ.
    let creditsBadge = "";
    if (me) {
      const current = Number(me.upload_credits) || 0;
      const quota = Number(me.plan_initial_uploads) || 0;
      // "Used" chỉ có ý nghĩa khi current <= quota (chưa renewal).
      // Khi renewal cộng dồn, current > quota → không hiển thị "used".
      const used = Math.max(0, quota - current);
      const usedNote = current > quota
        ? `${current - quota} bonus từ renewal`
        : `${used} đã dùng`;
      creditsBadge = `<span class="h-chip h-credits" title="${current} còn lại · ${usedNote} · plan ${me.plan_name} cấp ${quota}/lần grant">${current} / ${quota} credits</span>`;
    }

    const emailPill = me
      ? `<span class="h-email" title="${escapeHtml(me.email)}">${escapeHtml(me.email)}</span>`
      : "";

    const right = me
      ? `<div class="h-right">
           ${planBadge}
           ${creditsBadge}
           ${emailPill}
           <button id="hLogout" class="btn-primary h-btn">Sign out</button>
         </div>`
      : `<div class="h-right">
           <a href="/login.html" class="btn-ghost h-btn" data-postlogin="/dashboard.html">Login</a>
           <a href="/register.html" class="btn-primary h-btn" data-postlogin="/dashboard.html">Sign up</a>
         </div>`;

    host.classList.add("topbar");
    host.innerHTML = `
      <div class="brand">Image<span>URL</span></div>
      <nav class="topnav">${right}</nav>
    `;

    // Auth links chỉ định sẵn nơi cần quay về sau khi login (data-postlogin).
    // Mặc định là /dashboard.html — người dùng vừa đăng nhập thì vào dashboard là đúng.
    host.querySelectorAll("a[data-postlogin]").forEach((a) => {
      a.addEventListener("click", () => {
        try { sessionStorage.setItem("imageurl:postLogin", a.dataset.postlogin); } catch (_) {}
      });
    });

    const lo = document.getElementById("hLogout");
    if (lo) lo.onclick = () => ImageURL.logout();
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Refresh credits shown in the header after an upload completes.
  async function refreshHeaderCredits() {
    if (!ImageURL.getToken()) return;
    try {
      const r = await ImageURL.me();
      ImageURL.setUser(r.data);
      // Re-render just the credit chip without rebuilding the whole bar.
      const chip = document.querySelector(".h-credits");
      if (!chip) return;
      const me = r.data;
      const current = Number(me.upload_credits) || 0;
      const quota = Number(me.plan_initial_uploads) || 0;
      const used = Math.max(0, quota - current);
      const usedNote = current > quota
        ? `${current - quota} bonus từ renewal`
        : `${used} đã dùng`;
      chip.textContent = `${current} / ${quota} credits`;
      chip.title = `${current} còn lại · ${usedNote} · plan ${me.plan_name} cấp ${quota}/lần grant`;
    } catch (_) { /* ignore */ }
  }

  window.renderTopbar = renderTopbar;
  window.refreshHeaderCredits = refreshHeaderCredits;
})();