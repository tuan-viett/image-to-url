/* ImageURL — payment.html logic.
   Step 1: load plans + SePay config → render plan cards.
   Step 2: click "Chọn gói" → call /payments/upgrade → render QR + countdown + poll status.
   Step 3: when paid → success screen.
*/
(function () {
  const POLL_INTERVAL_MS = 2500;

  // ---------- DOM helpers ----------
  const $ = (id) => document.getElementById(id);
  const stages = {
    choose: $("payChoose"),
    qr: $("payQr"),
    done: $("payDone"),
  };
  const errBox = $("payError");

  function showStage(name) {
    Object.entries(stages).forEach(([k, el]) => {
      el.classList.toggle("active", k === name);
    });
  }

  function showError(msg) {
    errBox.textContent = msg;
    errBox.hidden = !msg;
  }

  function fmtVnd(n) {
    return Number(n || 0).toLocaleString("vi-VN") + " ₫";
  }

  function fmtTime(sec) {
    sec = Math.max(0, Math.floor(sec));
    const m = String(Math.floor(sec / 60)).padStart(2, "0");
    const s = String(sec % 60).padStart(2, "0");
    return `${m}:${s}`;
  }

  function copyText(s) {
    return navigator.clipboard.writeText(s || "");
  }

  function copyFromAttr(btn) {
    const target = $(btn.dataset.copyTarget);
    if (target) copyText(target.textContent.trim());
    const old = btn.textContent;
    btn.textContent = "Copied";
    setTimeout(() => (btn.textContent = old), 1200);
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-copy-target]");
    if (btn) copyFromAttr(btn);
  });

  // ---------- Auth gate ----------
  const token = ImageURL.getToken();
  if (!token) {
    sessionStorage.setItem("postLoginDest", "/payment.html");
    location.href = "/login.html";
    return;
  }

  // ---------- Step 1: render plans ----------
  async function loadPlans() {
    try {
      const [plansResp, sepayResp] = await Promise.all([
        ImageURL.listPlans(),
        ImageURL.getSepayConfig().catch(() => null),
      ]);
      const me = ImageURL.getUser() || {};
      const currentPlanId = me.plan_id;
      const plans = plansResp.data || [];
      const sepayOk = sepayResp && sepayResp.data && sepayResp.data.account_number;

      const grid = $("plansGrid");
      if (!plans.length) {
        grid.innerHTML = '<div class="muted">Không có gói nào khả dụng.</div>';
        return;
      }
      grid.innerHTML = ImageURLComponents.renderPlanCards({
        plans,
        currentPlanId,
        currentSortOrder: me.plan_sort_order || 0,
        sepayOk,
      });

      // Hook click handlers (event delegation)
      grid.querySelectorAll("button[data-plan-id]").forEach((btn) => {
        btn.onclick = () => {
          const planId = parseInt(btn.dataset.planId, 10);
          createOrder(planId);
        };
      });
    } catch (e) {
      showError("Không tải được danh sách gói: " + e.message);
    }
  }

  // ---------- Step 2: create order + show QR ----------
  let pollTimer = null;
  let countdownTimer = null;
  let initialSecondsLeft = 0;

  async function createOrder(planId) {
    showError(null);
    try {
      const resp = await ImageURL.upgradePlan(planId);
      const order = resp.data;
      const p = order.payment;

      // Fill info panel
      $("infoBank").textContent = order.bank_code;
      $("infoAcc").textContent = order.account_number;
      $("infoName").textContent = order.account_name || "—";
      $("infoAmount").textContent = fmtVnd(order.amount_vnd);
      $("infoCode").textContent = order.description;
      $("qrImg").src = order.qr_image_url;

      // Lưu seconds_remaining từ server — không parse ISO naive (lệch timezone).
      initialSecondsLeft = order.seconds_remaining;
      $("tipMinutes").textContent = Math.max(1, Math.round(initialSecondsLeft / 60));

      showStage("qr");
      startCountdown();
      startPolling(p.id);
    } catch (e) {
      showError("Không tạo được đơn thanh toán: " + e.message);
    }
  }

  function startCountdown() {
    clearInterval(countdownTimer);
    // Dùng seconds_remaining từ server làm nguồn chính xác (tránh lệch timezone khi parse ISO naive).
    let secondsLeft = initialSecondsLeft;
    const tick = () => {
      $("qrCountdown").textContent = fmtTime(secondsLeft);
      if (secondsLeft <= 0) {
        clearInterval(countdownTimer);
        $("qrCountdown").classList.add("expired");
        $("qrCountdown").textContent = "Hết hạn";
        return;
      }
      secondsLeft -= 1;
    };
    tick();
    countdownTimer = setInterval(tick, 1000);
  }

  function startPolling(paymentId) {
    clearInterval(pollTimer);
    const setState = (cls, text) => {
      const st = $("payState");
      st.className = "pay-state " + cls;
      $("payStateText").textContent = text;
    };
    setState("pending", "Đang chờ thanh toán…");

    pollTimer = setInterval(async () => {
      try {
        const resp = await ImageURL.getPaymentStatus(paymentId);
        const s = resp.data;
        if (s.is_paid) {
          clearInterval(pollTimer);
          clearInterval(countdownTimer);
          setState("ok", "Đã nhận thanh toán");
          await celebrate();
          return;
        }
        if (s.is_expired) {
          clearInterval(pollTimer);
          clearInterval(countdownTimer);
          setState("expired", "Đơn đã hết hạn");
          return;
        }
      } catch (e) {
        // network blip → continue polling silently
      }
    }, POLL_INTERVAL_MS);
  }

  async function celebrate() {
    const me = ImageURL.getUser() || {};
    try {
      const fresh = await ImageURL.me();
      ImageURL.setUser(fresh.data);
      $("doneEmail").textContent = fresh.data.email;
      $("donePlan").textContent = fresh.data.plan_name;
    } catch (_) {
      $("doneEmail").textContent = me.email || "—";
      $("donePlan").textContent = "—";
    }
    showStage("done");
    if (window.renderTopbar) window.renderTopbar();
  }

  // ---------- Cancel ----------
  $("payCancel").onclick = () => {
    clearInterval(pollTimer);
    clearInterval(countdownTimer);
    showStage("choose");
  };

  // ---------- Helpers ----------

  // ---------- Boot ----------
  renderTopbar().then(async () => {
    await loadPlans();
    // Auto-trigger nếu ?plan=X trên URL
    const params = new URLSearchParams(location.search);
    const autoPlan = parseInt(params.get("plan") || "0", 10);
    if (autoPlan) {
      const btn = document.querySelector(`button[data-plan-id="${autoPlan}"]:not([disabled])`);
      if (btn) btn.click();
    }
  });
})();