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

// Cookies tab: intercept "Авторизоваться и собрать" submits, then poll /cookies/status
// for live progress (current city, saved / waiting-on-captcha / done) until the job stops.
document.addEventListener("DOMContentLoaded", () => {
  const forms = document.querySelectorAll(".collect-form");
  if (!forms.length) return;

  let polling = false;

  const renderSteps = (mp, job) => {
    const statusEl = document.getElementById(`collect-status-${mp}`);
    const progressEl = document.getElementById(`collect-progress-${mp}`);
    if (statusEl) {
      statusEl.innerHTML = job.running ? '<p class="status status--running">Сбор выполняется</p>' : "";
    }
    if (progressEl) {
      progressEl.innerHTML = job.steps.length
        ? "<ul>" + job.steps.map((s) => `<li>${s.city_code}: ${s.status}${s.detail ? ` (${s.detail})` : ""}</li>`).join("") + "</ul>"
        : "";
    }
  };

  const poll = async () => {
    const response = await fetch("/cookies/status");
    const jobs = await response.json();
    let anyRunning = false;
    for (const [mp, job] of Object.entries(jobs)) {
      renderSteps(mp, job);
      if (job.running) anyRunning = true;
    }
    if (anyRunning) {
      setTimeout(poll, 1500);
    } else {
      polling = false;
    }
  };

  forms.forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const mp = form.dataset.mp;
      const button = form.querySelector("button");
      button.disabled = true;
      const response = await fetch(form.action, { method: "POST" });
      const html = await response.text();
      const statusEl = document.getElementById(`collect-status-${mp}`);
      if (statusEl) statusEl.innerHTML = html;
      if (!polling) {
        polling = true;
        setTimeout(poll, 1500);
      }
    });
  });
});

// Connection tab: "Предпросмотр" posts the current (unsaved) form to /connection/preview
// and renders the returned partial without a page reload.
document.addEventListener("DOMContentLoaded", () => {
  const bindPreview = (buttonId, formId, targetId, target) => {
    const button = document.getElementById(buttonId);
    const form = document.getElementById(formId);
    const output = document.getElementById(targetId);
    if (!button || !form || !output) return;

    button.addEventListener("click", async () => {
      const data = new FormData(form);
      data.set("target", target);
      const response = await fetch("/connection/preview", { method: "POST", body: data });
      output.innerHTML = await response.text();
    });
  };

  bindPreview("preview-source-button", "source-form", "source-preview", "source");
  bindPreview("preview-sink-button", "sink-form", "sink-preview", "sink");
});
