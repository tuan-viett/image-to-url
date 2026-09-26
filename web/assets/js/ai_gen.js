/* ImageURL — AI Generate tab.
   Form: prompt + size/quality/format → POST /ai/generations → preview + URL.
*/
(function () {
  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function showErr(msg) {
    const box = document.getElementById("aigenErr");
    if (!box) return;
    box.textContent = msg || "";
    box.hidden = !msg;
  }

  function setBusy(busy) {
    const btn = document.getElementById("aigenSubmit");
    if (!btn) return;
    btn.disabled = !!busy;
    btn.textContent = busy ? "⏳ Generating…" : "✨ Generate";
  }

  function fmtBytes(n) {
    if (n == null) return "—";
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / (1024 * 1024)).toFixed(2) + " MB";
  }

  async function initAigen() {
    const form = document.getElementById("aigenForm");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      showErr("");

      const prompt = (document.getElementById("aigenPrompt").value || "").trim();
      if (!prompt) {
        showErr("Please enter a prompt.");
        return;
      }

      const sizeVal = document.getElementById("aigenSize").value || null;
      const qualityVal = document.getElementById("aigenQuality").value || null;
      const formatVal = document.getElementById("aigenFormat").value || "png";

      const payload = {
        prompt,
        output_format: formatVal,
      };
      if (sizeVal) payload.size = sizeVal;
      if (qualityVal) payload.quality = qualityVal;

      setBusy(true);
      try {
        const resp = await ImageURL.aiGenerate(payload);
        const data = resp.data;

        // Render preview + URL
        const resultBox = document.getElementById("aigenResult");
        const img = document.getElementById("aigenImg");
        const urlInput = document.getElementById("aigenUrl");
        const meta = document.getElementById("aigenMeta");
        const creditsRem = document.getElementById("aigenCreditsRem");

        img.src = data.url;
        img.alt = prompt.slice(0, 80);
        urlInput.value = data.url;
        meta.textContent = `${fmtBytes(data.size)} · ${data.mime_type} · expires ${new Date(data.expires_at).toLocaleDateString()}`;
        creditsRem.textContent = data.credits_remaining != null ? data.credits_remaining : "—";
        resultBox.hidden = false;

        // Refresh header credit chip
        if (typeof refreshHeaderCredits === "function") {
          refreshHeaderCredits();
        }

        // Auto-scroll to result
        resultBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } catch (err) {
        console.error("AI gen failed", err);
        let msg = err.message || "AI generation failed";
        if (err.code === "QUOTA_EXCEEDED") {
          const need = (err.details && err.details.required) || 5;
          const have = (err.details && err.details.available) || 0;
          msg = `Not enough credits — need ${need}, have ${have}. Top up or upgrade your plan.`;
        } else if (err.code === "AI_CONTENT_BLOCKED") {
          msg = "Your prompt was rejected by the AI provider's content policy. Try rewording it.";
        } else if (err.code === "AI_TIMEOUT") {
          msg = "AI provider took too long to respond. Please try again.";
        } else if (err.code === "AI_PROVIDER_ERROR") {
          msg = "AI provider is temporarily unavailable. Please retry in a moment.";
        } else if (err.code === "RATE_LIMITED") {
          msg = "You're generating too fast — wait a minute before retrying.";
        } else if (err.code === "AI_DISABLED") {
          msg = "AI image generation is currently disabled by the operator.";
          // Lock the form so user can't keep retrying.
          document.getElementById("aigenSubmit")?.setAttribute("disabled", "true");
          const banner = document.getElementById("aigenDisabledBanner");
          if (banner) banner.hidden = false;
        }
        showErr(msg);
      } finally {
        setBusy(false);
      }
    });

    // Copy URL
    const copyBtn = document.getElementById("aigenCopy");
    const urlInput = document.getElementById("aigenUrl");
    if (copyBtn && urlInput) {
      copyBtn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(urlInput.value);
        } catch (_) {
          urlInput.select();
          document.execCommand("copy");
        }
        const old = copyBtn.textContent;
        copyBtn.textContent = "Copied!";
        setTimeout(() => { copyBtn.textContent = old; }, 1200);
      });
    }
  }

  // Auto-init when DOM is ready.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAigen);
  } else {
    initAigen();
  }
})();