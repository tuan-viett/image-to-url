/* ImageURL — dashboard behavior. Sidebar tab switching + per-tab loaders. */
(function () {
  const titles = {
    upload: "Turn images into public URLs.",
    overview: "Overview",
    images: "Images",
    aigen: "AI Generate",
    keys: "API Keys",
    usage: "Usage",
    docs: "Documentation",
  };

  // Feature flags (default enabled)
  const FLAGS = { ai_gen: true };

  async function bootstrapFeatureFlags() {
    try {
      const resp = await ImageURL.getAIStatus();
      // Handle boolean true/false hoặc string "true"/"false" từ MySQL TEXT
      const v = resp.data.enabled;
      FLAGS.ai_gen = (v === true || v === "true" || v === 1 || v === "1");
    } catch (_) {
      // Leave defaults — UI still works if /ai/status unavailable
    }
    applyFeatureFlags();
  }

  function applyFeatureFlags() {
    // Hide/show sidebar button + page for AI Generate
    const btn = document.querySelector('.nav button[data-page="aigen"]');
    const page = document.getElementById("aigen");
    if (btn) btn.style.display = FLAGS.ai_gen ? "" : "none";
    if (page) page.style.display = FLAGS.ai_gen ? "" : "none";
    // Nếu hiện tại đang active tab aigen và vừa tắt → redirect về overview
    if (!FLAGS.ai_gen && page) {
      page.classList.remove("active");
      const activeBtn = document.querySelector(".nav button.active");
      if (activeBtn && activeBtn.dataset.page === "aigen") {
        location.href = "/dashboard.html";
      }
    }
  }

  function setupTabs() {
    const buttons = document.querySelectorAll(".nav button");
    const pages = document.querySelectorAll(".page");
    const title = document.getElementById("title");
    buttons.forEach((b) => {
      b.onclick = () => {
        buttons.forEach((x) => x.classList.remove("active"));
        b.classList.add("active");
        pages.forEach((p) => p.classList.remove("active"));
        const id = b.dataset.page;
        const target = document.getElementById(id);
        if (target) target.classList.add("active");
        if (title) title.textContent = titles[id] || "";
        // Lazy-load tab data
        if (id === "overview") loadOverview();
        if (id === "images") loadImages();
        if (id === "keys") loadKeys();
        if (id === "usage") loadUsage();
      };
    });
  }

  function fmtBytes(n) {
    if (n == null) return "—";
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / (1024 * 1024)).toFixed(2) + " MB";
  }

  function fmtDate(s) {
    if (!s) return "—";
    return new Date(s).toLocaleString();
  }

  // ====== Overview ======
  async function loadOverview() {
    try {
      const [me, plans] = await Promise.all([ImageURL.me(), ImageURL.listPlans()]);
      document.getElementById("ovPlan").textContent = me.data.plan_name;
      document.getElementById("ovCredits").textContent = me.data.upload_credits;
      document.getElementById("ovRetention").textContent = me.data.plan_retention_days;
      const planInfo = plans.data.find((p) => p.id === me.data.plan_id);
      document.getElementById("ovPlanSub").textContent =
        planInfo ? `${planInfo.initial_uploads} credits on signup` : "";

      const grid = document.getElementById("ovPlans");
      grid.innerHTML = ImageURLComponents.renderPlanCards({
        plans: plans.data,
        currentPlanId: me.data.plan_id,
        currentSortOrder: me.data.plan_sort_order || 0,
        sepayOk: true,
      });
      grid.querySelectorAll("button[data-plan-id]").forEach((btn) => {
        btn.onclick = () => {
          const pid = parseInt(btn.dataset.planId, 10);
          location.href = "/payment.html?plan=" + pid;
        };
      });

      // Recent images preview (top 3)
      const recent = await ImageURL.listImages(1, 3);
      const slot = document.getElementById("ovRecent");
      if (recent.data.length === 0) {
        slot.innerHTML = `<p class="muted">No uploads yet. Head to the Upload tab to get started.</p>`;
      } else {
        slot.innerHTML =
          '<div class="table">' +
          recent.data.map((img) => `
            <div class="tr">
              <div><img class="thumb" src="${img.public_url}" alt=""></div>
              <div>${escapeHtml(img.original_filename || "image")}</div>
              <div>${fmtBytes(img.size_bytes)}</div>
              <div>${img.mime_type.split('/')[1].toUpperCase()}</div>
              <div>${fmtDate(img.created)}</div>
              <div><a class="link" href="${img.public_url}" target="_blank">Open</a></div>
            </div>
          `).join("") +
          "</div>";
      }
    } catch (err) {
      console.error(err);
    }
  }

  let imPage = 1;
  async function loadImages() {
    try {
      const resp = await ImageURL.listImages(imPage, 10);
      const rows = resp.data;
      const slot = document.getElementById("rows");
      document.getElementById("imCount").textContent =
        `${resp.pagination.total} image${resp.pagination.total === 1 ? "" : "s"}`;
      document.getElementById("imPage").textContent =
        `Page ${resp.pagination.page}`;
      document.getElementById("imPrev").disabled = resp.pagination.page <= 1;
      document.getElementById("imNext").disabled =
        imPage * resp.pagination.page_size >= resp.pagination.total;
      if (rows.length === 0) {
        slot.innerHTML = `<div class="tr"><div></div><div class="muted">No images yet.</div><div></div><div></div><div></div><div></div></div>`;
        return;
      }
      slot.innerHTML = rows.map((img) => `
        <div class="tr">
          <div><img class="thumb" src="${img.public_url}" alt=""></div>
          <div>${escapeHtml(img.original_filename || img.storage_key)}</div>
          <div>${fmtBytes(img.size_bytes)}</div>
          <div>${img.mime_type.split('/')[1].toUpperCase()}</div>
          <div>${fmtDate(img.created)}</div>
          <div>
            <button class="copy" data-copy="${img.public_url}">Copy URL</button>
            <button class="del" data-del="${img.id}">Delete</button>
          </div>
        </div>
      `).join("");
      slot.querySelectorAll("button[data-copy]").forEach((b) => {
        b.onclick = async () => {
          await navigator.clipboard.writeText(b.dataset.copy);
          const old = b.textContent;
          b.textContent = "Copied!";
          setTimeout(() => { b.textContent = old; }, 1000);
        };
      });
      slot.querySelectorAll("button[data-del]").forEach((b) => {
        b.onclick = async () => {
          if (!confirm("Delete this image?")) return;
          try {
            await ImageURL.deleteImage(parseInt(b.dataset.del, 10));
            loadImages();
          } catch (err) {
            alert(err.message || "Delete failed");
          }
        };
      });
    } catch (err) {
      console.error(err);
    }
  }
  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("imPrev")?.addEventListener("click", () => {
      if (imPage > 1) { imPage -= 1; loadImages(); }
    });
    document.getElementById("imNext")?.addEventListener("click", () => {
      imPage += 1; loadImages();
    });
  });

  // ====== API Keys ======
  async function loadKeys() {
    try {
      const resp = await ImageURL.listApiKeys();
      const slot = document.getElementById("keysList");
      if (resp.data.length === 0) {
        slot.innerHTML = `<p class="muted">No API keys yet. Create one to start using the API.</p>`;
        return;
      }
      slot.innerHTML = resp.data.map((k) => `
        <div class="key-row">
          <div>
            <div><code>${k.key_prefix}••••••••••••</code>
              ${k.revoked_at ? '<span class="badge del">revoked</span>' : '<span class="badge">active</span>'}
              <span class="muted">${k.environment === 1 ? "live" : "test"}</span>
            </div>
            <div class="meta">
              ${escapeHtml(k.name)} · Created ${fmtDate(k.created)}
              ${k.last_used_at ? "· Last used " + fmtDate(k.last_used_at) : "· Never used"}
            </div>
          </div>
          <div>
            ${k.revoked_at ? "" : `<button class="btn-ghost" data-revoke="${k.id}">Revoke</button>`}
          </div>
        </div>
      `).join("");
      slot.querySelectorAll("button[data-revoke]").forEach((b) => {
        b.onclick = async () => {
          if (!confirm("Revoke this API key? This cannot be undone.")) return;
          try {
            await ImageURL.revokeApiKey(parseInt(b.dataset.revoke, 10));
            loadKeys();
          } catch (err) {
            alert(err.message || "Revoke failed");
          }
        };
      });
    } catch (err) {
      console.error(err);
    }
  }

  function showKeyModal(secret) {
    const modal = document.getElementById("keyModal");
    const input = document.getElementById("newSecret");
    const copy = document.getElementById("copySecret");
    const close = document.getElementById("closeModal");
    input.value = secret;
    modal.hidden = false;
    copy.onclick = async () => {
      try { await navigator.clipboard.writeText(secret); }
      catch { input.select(); document.execCommand("copy"); }
      copy.textContent = "Copied!";
      setTimeout(() => { copy.textContent = "Copy"; }, 1200);
    };
    close.onclick = () => { modal.hidden = true; };
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("newKey")?.addEventListener("click", async () => {
      const name = prompt("Key name (e.g. 'Production'):", "My key");
      if (!name) return;
      try {
        const resp = await ImageURL.createApiKey(name.trim(), 1);
        showKeyModal(resp.data.secret);
        loadKeys();
      } catch (err) {
        alert(err.message || "Could not create key");
      }
    });
  });

  // ====== Usage ======
  async function loadUsage() {
    try {
      const resp = await ImageURL.getUsage();
      const map = {};
      resp.data.counters.forEach((c) => { map[c.event_type] = c; });
      document.getElementById("uUploads").textContent = (map[1] && map[1].count) || 0;
      document.getElementById("uAiGen").textContent = (map[6] && map[6].count) || 0;
      document.getElementById("uApi").textContent = (map[2] && map[2].count) || 0;
      document.getElementById("uFailed").textContent = (map[4] && map[4].count) || 0;
      document.getElementById("uDeletes").textContent = (map[3] && map[3].count) || 0;
      document.getElementById("uCredits").textContent =
        resp.data.upload_credits_remaining != null ? resp.data.upload_credits_remaining : "—";

      const pays = await ImageURL.listPayments();
      const slot = document.getElementById("paymentsList");
      if (pays.data.length === 0) {
        slot.innerHTML = `<p class="muted">No payments yet.</p>`;
      } else {
        slot.innerHTML = pays.data.map((p) => {
          const statusLabel = ["", "pending", "completed", "refunded", "failed", "expired"][p.status] || "?";
          const typeLabel = p.type === 1 ? "Plan upgrade" : "Credit top-up";
          const meta = [(p.amount/100).toLocaleString("vi-VN") + " ₫", fmtDate(p.created)];
          if (p.code) meta.unshift(p.code);
          return `<div class="key-row">
            <div>
              <b>${typeLabel}</b> · <span class="badge ${p.status === 5 ? "del" : ""}">${statusLabel}</span>
              <div class="meta">${meta.join(" · ")}</div>
            </div>
          </div>`;
        }).join("");
      }
    } catch (err) {
      console.error(err);
    }
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // ====== Bootstrap ======
  window.addEventListener("DOMContentLoaded", async () => {
    const user = await requireAuth();
    if (!user) return;
    await renderTopbar();
    await bootstrapFeatureFlags();
    setupTabs();
    initUpload({ authed: true });
    document.getElementById("logout")?.addEventListener("click", () => ImageURL.logout());
    document.getElementById("ovRefresh")?.addEventListener("click", loadOverview);
    // Pre-render overview eagerly
    loadOverview();
  });
})();