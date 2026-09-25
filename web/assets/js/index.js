/* ImageURL — index.html (landing) init. */
window.addEventListener("DOMContentLoaded", async () => {
  await renderTopbar();
  if (document.getElementById("uploadBox")) {
    initUpload({ authed: false });
  }
});