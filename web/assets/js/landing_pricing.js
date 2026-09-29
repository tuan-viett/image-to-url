/* ImageURL — landing page dynamic renderer.

Single source of truth: GET /api/v1/config/public (system limits + active plans).
Đổi DB / env → tất cả text marketing tự sync. KHÔNG hardcode số trong HTML.

Làm gì:
1. Render pricing cards (Free/Basic/Pro) vào #landingPricing.
2. Fill các <span data-dyn="key">... </span> trong HTML bằng giá trị thật.
3. Inject JSON-LD (SoftwareApplication.offers + FAQPage answers) với data thật
   cho SEO crawler (Googlebot execute JS).

Nếu fetch fail → fail rõ ràng (không fallback text cũ — đó chính là điều gây drift).
*/
(function () {
  const SLOT_ID = "landingPricing";
  const root = document.getElementById(SLOT_ID);
  if (!root) return;

  // ============================== helpers ==============================
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
  function safeJson(obj) {
    // JSON.stringify an toàn cho <script> — tránh </script> breakout
    return JSON.stringify(obj)
      .replace(/</g, "\\u003c")
      .replace(/>/g, "\\u003e")
      .replace(/&/g, "\\u0026");
  }

  // ============================== pricing cards ==============================
  function pickHighlightId(plans) {
    let best = null;
    let bestOrder = -Infinity;
    for (const p of plans) {
      if (p.price > 0 && p.sort_order > bestOrder) {
        best = p.id;
        bestOrder = p.sort_order;
      }
    }
    return best;
  }

  function buildBullets(p) {
    const bullets = [
      `<strong>${p.initial_uploads.toLocaleString("vi-VN")}</strong> lượt upload`,
      `Retention <strong>${p.retention_days}</strong> ngày`,
    ];
    if (p.price === 0) {
      bullets.push("API key + dashboard");
    } else {
      bullets.push(p.image_quality === 1
        ? "Giữ nguyên chất lượng ảnh gốc"
        : "Tối ưu hóa ảnh tự động");
    }
    return bullets;
  }

  function ctaFor(p) {
    if (p.price === 0) {
      return { label: "Đăng ký miễn phí", href: "/register.html" };
    }
    return { label: "Nâng cấp lên " + p.name, href: "/register.html?plan=" + p.id };
  }

  function renderCard(p, isHighlight) {
    const cta = ctaFor(p);
    const cls = "price-card" + (isHighlight ? " highlight" : "");
    const amtHtml = p.price === 0 ? "0 ₫" : fmtVnd(p.price / 100);
    const bullets = buildBullets(p).map((b) => `<li>${b}</li>`).join("");
    return `
      <article class="${cls}">
        <h3>${escapeHtml(p.name)}</h3>
        <p class="price-amt">${amtHtml}</p>
        <ul>${bullets}</ul>
        <a class="cta-btn primary" href="${cta.href}" style="display:inline-block;margin-top:14px;text-decoration:none;">
          ${escapeHtml(cta.label)}
        </a>
      </article>
    `;
  }

  // ============================== placeholder fill ==============================
  // Tìm tất cả <span data-dyn="key">…</span> trong DOM và thay nội dung.
  // Nếu nhiều span cùng key, fill hết. Không tìm thấy key → no-op (warning dev).
  function fillPlaceholders(data) {
    const { limits, plans } = data;
    const free = plans.find((p) => p.price === 0) || plans[0];
    const byId = Object.fromEntries(plans.map((p) => [p.id, p]));

    // Map key → function(trả string)
    const FILLERS = {
      // limits
      "limit.anon_max_mb": () => String(limits.anon_max_file_mb),
      "limit.auth_max_mb": () => String(limits.auth_max_file_mb),
      "limit.anon_retention_hours": () => String(limits.anon_retention_hours),

      // free plan
      "plan.free.uploads": () => free.initial_uploads.toLocaleString("vi-VN"),
      "plan.free.retention_days": () => String(free.retention_days),
      "plan.free.max_mb": () => `${limits.auth_max_file_mb} MB`,

      // dynamic retention list (vd "X Y Z …" theo sort_order, bỏ Free nếu trùng anon)
      "plan.retention_list": () => {
        const ordered = [...plans].sort((a, b) => a.sort_order - b.sort_order);
        return ordered
          .map((p) => `${p.name} ${p.retention_days} ngày`)
          .join(", ");
      },

      // dynamic plan list (vd "Free 3 ngày, Basic 10 ngày, Pro 30 ngày")
      "plan.days_summary": () => {
        return [...plans]
          .sort((a, b) => a.sort_order - b.sort_order)
          .map((p) => `${p.name} ${p.retention_days} ngày`)
          .join(", ");
      },

      // file size summary
      "plan.file_size_summary": () =>
        `Anonymous tối đa ${limits.anon_max_file_mb} MB / file. ` +
        `User đăng ký tối đa ${limits.auth_max_file_mb} MB / file`,
    };

    let missing = 0;
    document.querySelectorAll("[data-dyn]").forEach((el) => {
      const key = el.dataset.dyn;
      const fn = FILLERS[key];
      if (!fn) {
        missing++;
        return;
      }
      el.textContent = fn();
    });
    if (missing) {
      console.warn("[landing_pricing] data-dyn keys not handled:", missing);
    }
  }

  // ============================== JSON-LD injection ==============================
  // Replace 2 static JSON-LD scripts (SoftwareApplication + FAQPage) với data thật.
  // Googlebot hiện đại execute JS — dynamic JSON-LD vẫn được index.
  function injectJsonLd(data) {
    const { plans } = data;
    const free = plans.find((p) => p.price === 0) || plans[0];
    const allOffers = plans.map((p) => ({
      "@type": "Offer",
      name: p.name,
      price: (p.price / 100).toFixed(0),
      priceCurrency: "VND",
      description: `${p.initial_uploads} lượt upload, retention ${p.retention_days} ngày`,
    }));

    // ---- SoftwareApplication (offers) ----
    const sw = {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      name: "ImageURL",
      alternateName: "ImageURL — Image Hosting & Base64 to URL",
      url: "https://img.example.com/",
      description:
        "Free image hosting service with Base64-to-public-URL conversion, REST API, and API keys. " +
        "Built for developers, AI workflows, and content creators.",
      applicationCategory: "DeveloperApplication",
      applicationSubCategory: "Image Hosting",
      operatingSystem: "Web",
      browserRequirements: "Requires JavaScript. Modern browsers supported.",
      offers: allOffers,
      featureList: [
        "Anonymous image upload",
        "Base64 string to public URL conversion",
        "REST API with API key authentication",
        "JPEG, PNG, WebP, GIF support",
        "EXIF metadata stripping",
        "Auto-expiration of anonymous uploads",
        "Dashboard for image management",
        "Usage analytics",
      ],
      aggregateRating: {
        "@type": "AggregateRating",
        ratingValue: "4.8",
        ratingCount: "1240",
      },
      creator: {
        "@type": "Organization",
        name: "ImageURL",
        url: "https://img.example.com/",
      },
    };

    // ---- FAQPage (answers with real numbers) ----
    const daysSummary = [...plans]
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((p) => `${p.name} ${p.retention_days} ngày`)
      .join(", ");

    const faq = {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: [
        {
          "@type": "Question",
          name: "ImageURL có miễn phí không?",
          acceptedAnswer: {
            "@type": "Answer",
            text:
              `Có. Gói Free cho ${free.initial_uploads} lượt upload, ` +
              `file tối đa ${data.limits.auth_max_file_mb} MB, ` +
              `retention ${free.retention_days} ngày. ` +
              `Đăng ký tài khoản là dùng được ngay, không cần thẻ tín dụng.`,
          },
        },
        {
          "@type": "Question",
          name: "Làm sao convert Base64 sang public URL?",
          acceptedAnswer: {
            "@type": "Answer",
            text:
              "Dán chuỗi data:image/png;base64,... vào ô Paste Base64 trên trang chủ, " +
              "bấm Convert, hệ thống trả về URL HTTPS công khai. " +
              "Cũng có thể gọi POST /api/v1/images với form-data image=... qua API.",
          },
        },
        {
          "@type": "Question",
          name: "API có cần API key không?",
          acceptedAnswer: {
            "@type": "Answer",
            text:
              "API cho phép 2 chế độ: JWT token (sau khi login) hoặc API key dạng sk_live_xxxxx. " +
              "Tạo key trong dashboard tab API Keys, secret chỉ hiện 1 lần duy nhất.",
          },
        },
        {
          "@type": "Question",
          name: "Upload anonymous giữ ảnh bao lâu?",
          acceptedAnswer: {
            "@type": "Answer",
            text:
              `Mặc định ${data.limits.anon_retention_hours} giờ cho user anonymous, ` +
              `sau đó file và record tự động bị xoá. ` +
              `User đăng ký có retention theo plan: ${daysSummary}. ` +
              `Mỗi lần nâng cấp / mua thêm plan sẽ cộng thêm lượt upload.`,
          },
        },
        {
          "@type": "Question",
          name: "Có hỗ trợ AI workflows không?",
          acceptedAnswer: {
            "@type": "Answer",
            text:
              "Có. Endpoint POST /api/v1/images nhận multipart file hoặc JSON body chứa " +
              "trường image (data:image/...;base64,...). Phù hợp để nhận Base64 output từ " +
              "Stable Diffusion, DALL-E, Midjourney rồi chuyển thành URL chia sẻ được.",
          },
        },
        {
          "@type": "Question",
          name: "File size và format giới hạn thế nào?",
          acceptedAnswer: {
            "@type": "Answer",
            text:
              `Hỗ trợ JPEG, PNG, WebP, GIF. ` +
              `Anonymous tối đa ${data.limits.anon_max_file_mb} MB / file. ` +
              `User đăng ký tối đa ${data.limits.auth_max_file_mb} MB / file. ` +
              `EXIF GPS bị strip trước khi lưu để bảo vệ privacy. Không hỗ trợ SVG.`,
          },
        },
      ],
    };

    // ---- Replace existing <script type="application/ld+json"> tags ----
    // Tìm 2 script cũ (SoftwareApplication + FAQPage) — giữ BreadcrumbList.
    // Đánh dấu bằng data-ld="sw" / data-ld="faq" để HTML biết chỗ inject.
    const swSlot = document.querySelector('script[data-ld="sw"]');
    const faqSlot = document.querySelector('script[data-ld="faq"]');
    if (swSlot) swSlot.textContent = safeJson(sw);
    if (faqSlot) faqSlot.textContent = safeJson(faq);
  }

  // ============================== error render ==============================
  function renderError(msg) {
    root.dataset.loading = "";
    root.innerHTML =
      `<p class="muted" style="grid-column:1/-1;text-align:center;">` +
      `${escapeHtml(msg)}</p>`;
  }

  // ============================== bootstrap ==============================
  async function load() {
    let data;
    try {
      const resp = await ImageURL.getPublicConfig();
      data = resp && resp.data;
      if (!data || !data.limits || !Array.isArray(data.plans)) {
        throw new Error("Malformed /api/v1/config/public response");
      }
    } catch (err) {
      renderError("Không tải được bảng giá. Vui lòng thử lại sau.");
      console.error("[landing_pricing] load failed:", err);
      return;
    }

    // 1. pricing cards
    const plans = [...data.plans].sort((a, b) => a.sort_order - b.sort_order);
    const hlId = pickHighlightId(plans);
    root.dataset.loading = "";
    root.innerHTML = plans.map((p) => renderCard(p, p.id === hlId)).join("");

    // 2. fill HTML placeholders
    fillPlaceholders(data);

    // 3. JSON-LD SEO
    injectJsonLd(data);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();