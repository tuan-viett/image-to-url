/* ImageURL — Documentation tab behavior:
   - Set the base URL from window.location.origin
   - Substitute localhost placeholders inside cURL examples
   - Wire up "Copy" buttons for each code block and the base URL pill */
(function () {
  const BASE_PLACEHOLDER = "http://localhost";

  function baseUrl() {
    return window.location.origin || BASE_PLACEHOLDER;
  }

  function substituteBase() {
    document.querySelectorAll("code[data-curl]").forEach((el) => {
      const raw = el.textContent;
      if (raw.includes(BASE_PLACEHOLDER)) {
        el.dataset.orig = raw;
        el.textContent = raw.split(BASE_PLACEHOLDER).join(baseUrl());
      }
    });
    const pill = document.getElementById("docsBaseUrl");
    if (pill) pill.textContent = baseUrl();
  }

  async function copyText(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Fallback: select hidden textarea
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch {}
      document.body.removeChild(ta);
    }
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = "Copied!";
      btn.classList.add("copied");
      setTimeout(() => {
        btn.textContent = orig;
        btn.classList.remove("copied");
      }, 1200);
    }
  }

  function wireCopyButtons() {
    document.querySelectorAll("button[data-copy-code]").forEach((btn) => {
      btn.onclick = () => {
        const code = btn.previousElementSibling;
        const text = code ? code.textContent : "";
        copyText(text, btn);
      };
    });
    document.querySelectorAll("button[data-copy-target]").forEach((btn) => {
      btn.onclick = () => {
        const id = btn.dataset.copyTarget;
        const el = document.getElementById(id);
        if (el) copyText(el.textContent || "", btn);
      };
    });
  }

  function activate() {
    substituteBase();
    wireCopyButtons();
  }

  // Run when docs tab is opened (also once on load if it's the default tab).
  document.addEventListener("DOMContentLoaded", activate);

  // Hook into the dashboard tab switcher: dashboard.js toggles .active on
  // .page sections. When #docs becomes active we re-bind.
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".nav button");
    if (!btn) return;
    if (btn.dataset && btn.dataset.page === "docs") {
      // Defer so the section is visible before we measure/code-substitute.
      setTimeout(activate, 0);
    }
  });
})();