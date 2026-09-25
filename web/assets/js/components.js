/* ImageURL — shared UI components.
   renderPlanCards: dùng chung cho Dashboard Overview + Payment page.
*/
(function () {
  function fmtVnd(n) {
    return Number(n || 0).toLocaleString("vi-VN") + " ₫";
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /**
   * Render danh sách plan cards.
   *
   * @param {Object}   opts
   * @param {Array}    opts.plans            - List plans từ /api/v1/plans.
   * @param {number}   opts.currentPlanId    - Plan hiện tại của user.
   * @param {number}   opts.currentSortOrder - sort_order hiện tại.
   * @param {boolean}  opts.sepayOk          - Đã cấu hình SePay chưa.
   * @returns {string} HTML string. Mỗi card có `data-plan-id` + data attribute
   *                   `data-actionable="1|0"`. Button có `data-plan-id`.
   *                   Caller bind click qua event delegation.
   */
  function renderPlanCards(opts) {
    const {plans, currentPlanId, currentSortOrder, sepayOk} = opts;
    const cur = currentSortOrder || 0;
    return plans.map((p) => {
      const isCurrent = p.id === currentPlanId;
      const isFree = p.price === 0;
      const isDowngrade = !isCurrent && p.sort_order < cur;
      const canBuy = !isFree && !isDowngrade && p.sort_order >= cur;
      const actionable = canBuy && !!sepayOk;

      let label;
      if (isFree)         label = "Miễn phí";
      else if (isCurrent) label = "Gia hạn";
      else if (isDowngrade) label = "Không downgrade";
      else                label = "Nâng cấp";

      const cls = [
        "pay-plan",
        isCurrent ? "is-current" : "",
        actionable ? "is-actionable" : "",
      ].filter(Boolean).join(" ");

      return `
        <div class="${cls}" data-plan-id="${p.id}" data-actionable="${actionable ? "1" : "0"}">
          <h3>${escapeHtml(p.name)}</h3>
          <div class="pay-price">${isFree ? "Miễn phí" : fmtVnd(p.price / 100)}</div>
          <ul>
            <li>${p.initial_uploads} credit upload</li>
            <li>Lưu trữ ${p.retention_days} ngày</li>
            <li>${p.image_quality === 1 ? "Giữ nguyên chất lượng" : "Tối ưu hóa ảnh"}</li>
          </ul>
          <button class="btn-primary w-full" data-plan-id="${p.id}" ${actionable ? "" : "disabled"}>
            ${label}
          </button>
          ${!sepayOk && !isFree && !isDowngrade ? `<small class="muted">SePay chưa cấu hình.</small>` : ""}
        </div>
      `;
    }).join("");
  }

  window.ImageURLComponents = {renderPlanCards, fmtVnd, escapeHtml};
})();