/* ImageURL — Upload widget logic, shared by landing page and dashboard.
   Uses a function that takes a configuration object so we can switch between
   anonymous (landing) and authenticated (dashboard) modes.

   Anonymous mode is for marketing/demo only — the actual public surface
   limits anonymous uploads via the backend's IP rate limit (10/day). For
   real usage (>=10 uploads, larger files, persistent URLs), we ask anon
   visitors to sign in before any upload completes. */
(function () {
  function initUpload(cfg) {
    const authed = !!(cfg && cfg.authed);
    const requireLogin = !authed;  // landing always requires login

    function gateOnLogin() {
      // Stash the intended action so login.html can resume after auth.
      try { sessionStorage.setItem("imageurl:postLogin", location.pathname); } catch (_) {}
      location.href = "/login.html";
    }

    const uploadTab = document.getElementById("uploadTab");
    const base64Tab = document.getElementById("base64Tab");
    const uploadBox = document.getElementById("uploadBox");
    const base64Box = document.getElementById("base64Box");
    const result = document.getElementById("result");
    const urlInput = document.getElementById("url");
    const copyBtn = document.getElementById("copy");
    const convertBtn = document.getElementById("convert");
    const base64Input = document.getElementById("base64");
    const fileInput = document.getElementById("file");
    const preview = document.getElementById("preview");
    const errorBox = document.getElementById("errorBox");

    if (!uploadBox) return; // not on this page

    function showError(msg) {
      if (!errorBox) { alert(msg); return; }
      errorBox.hidden = !msg;
      errorBox.textContent = msg || "";
    }

    function showResult(data) {
      urlInput.value = data.data.url;
      result.style.display = "block";
      if (preview && fileInput && fileInput.files && fileInput.files[0]) {
        preview.src = URL.createObjectURL(fileInput.files[0]);
      } else {
        preview.removeAttribute("src");
      }
      showError("");
      refreshHeaderCredits();
    }

    uploadTab.onclick = () => {
      uploadTab.classList.add("active");
      base64Tab.classList.remove("active");
      uploadBox.style.display = "block";
      base64Box.style.display = "none";
    };
    base64Tab.onclick = () => {
      base64Tab.classList.add("active");
      uploadTab.classList.remove("active");
      uploadBox.style.display = "none";
      base64Box.style.display = "block";
    };

    uploadBox.onclick = (e) => {
      if (e.target.id !== "file") fileInput.click();
    };
    fileInput.onchange = async (e) => {
      if (requireLogin) { gateOnLogin(); return; }
      const f = e.target.files && e.target.files[0];
      if (!f) return;
      try {
        const resp = authed
          ? await ImageURL.uploadFile(f)
          : await ImageURL.anonymousUpload(f);
        showResult(resp);
      } catch (err) {
        showError(err.message || "Upload failed");
      }
    };

    ["dragenter", "dragover"].forEach((ev) =>
      uploadBox.addEventListener(ev, (e) => {
        e.preventDefault();
        uploadBox.classList.add("drag");
      })
    );
    ["dragleave", "drop"].forEach((ev) =>
      uploadBox.addEventListener(ev, (e) => {
        e.preventDefault();
        uploadBox.classList.remove("drag");
      })
    );
    uploadBox.addEventListener("drop", async (e) => {
      if (requireLogin) { e.preventDefault(); gateOnLogin(); return; }
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (!f) return;
      fileInput.files = e.dataTransfer.files;
      try {
        const resp = authed
          ? await ImageURL.uploadFile(f)
          : await ImageURL.anonymousUpload(f);
        showResult(resp);
      } catch (err) {
        showError(err.message || "Upload failed");
      }
    });

    convertBtn.onclick = async () => {
      const v = (base64Input.value || "").trim();
      if (!v) { showError("Paste Base64 first"); return; }
      if (requireLogin) { gateOnLogin(); return; }
      try {
        const resp = authed
          ? await ImageURL.uploadBase64(v)
          : await ImageURL.anonymousUploadBase64(v);
        showResult(resp);
      } catch (err) {
        showError(err.message || "Conversion failed");
      }
    };

    copyBtn.onclick = async () => {
      if (!urlInput.value) return;
      try {
        await navigator.clipboard.writeText(urlInput.value);
      } catch {
        urlInput.select();
        document.execCommand("copy");
      }
      const old = copyBtn.textContent;
      copyBtn.textContent = "Copied!";
      setTimeout(() => { copyBtn.textContent = old; }, 1200);
    };
  }

  window.initUpload = initUpload;
})();