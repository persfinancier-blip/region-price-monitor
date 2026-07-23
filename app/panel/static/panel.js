// Progressive enhancement for "Run now": intercept the form POST with fetch so the
// page doesn't reload; falls back to a plain form submit if JS is disabled.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("run-form");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = document.getElementById("run-button");
    const status = document.getElementById("run-status");
    button.disabled = true;
    const response = await fetch(form.action, { method: "POST" });
    const html = await response.text();
    status.innerHTML = html;
  });
});
