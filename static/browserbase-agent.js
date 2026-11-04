(() => {
  const panel = document.getElementById("browserbase-agent-panel");
  if (!panel) return;
  const form = document.getElementById("bb-run-form");
  const input = document.getElementById("bb-task");
  const button = document.getElementById("bb-run-button");
  const message = document.getElementById("bb-run-message");
  const history = document.getElementById("bb-run-history");
  const config = document.getElementById("bb-config-status");
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const active = new Set();
  const terminal = new Set(["COMPLETED", "FAILED", "STOPPED", "TIMED_OUT"]);
  async function api(url, options = {}) {
    const response = await fetch(url, {credentials:"same-origin", ...options,
      headers:{...(options.headers || {}), ...(options.method && options.method !== "GET" ? {"X-CSRF-Token":csrf} : {})}});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "The request failed.");
    return data;
  }
  function addText(parent, tag, value, className) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    el.textContent = value == null ? "" : String(value);
    parent.appendChild(el);
    return el;
  }
  function upsert(run) {
    let wrapper = [...history.querySelectorAll("[data-run-id]")].find(el => el.dataset.runId === run.id);
    if (!wrapper) {
      wrapper = document.createElement("article");
      wrapper.className = "card";
      wrapper.dataset.runId = run.id;
      wrapper.style.padding = "14px 16px";
      history.prepend(wrapper);
    }
    wrapper.replaceChildren();
    addText(wrapper, "strong", String(run.status || "UNKNOWN").replaceAll("_", " "));
    addText(wrapper, "p", run.created || "", "small muted");
    const task = addText(wrapper, "p", run.task || "", "small");
    task.style.whiteSpace = "pre-wrap";
    task.style.overflowWrap = "anywhere";
    if (run.error) addText(wrapper, "p", run.error, "small");
    if (run.result != null) {
      const details = document.createElement("details");
      const summary = addText(details, "summary", "View agent result", "text-link");
      summary.style.cursor = "pointer";
      const pre = addText(details, "pre", typeof run.result === "string" ? run.result : JSON.stringify(run.result, null, 2));
      pre.style.cssText = "white-space:pre-wrap;overflow-wrap:anywhere;max-height:520px;overflow:auto;padding:12px;border-radius:8px;font:12px/1.6 ui-monospace,monospace";
      wrapper.appendChild(details);
    }
    if (!terminal.has(String(run.status || "").toUpperCase())) addText(wrapper, "p", "Agent is still working. This page will keep checking its status.", "small muted");
  }
  async function poll(id) {
    if (active.has(id)) return;
    active.add(id);
    try {
      const run = await api("/api/owner/browserbase/runs/" + encodeURIComponent(id));
      upsert(run);
      active.delete(id);
      if (!terminal.has(String(run.status || "").toUpperCase())) window.setTimeout(() => poll(id), 4000);
    } catch (error) {
      active.delete(id);
      message.textContent = error.message;
    }
  }
  async function loadHistory() {
    try {
      const data = await api("/api/owner/browserbase/runs");
      config.textContent = "Agent connection configured on the server";
      history.replaceChildren();
      if (!data.runs?.length) addText(history, "p", "No agent runs yet. Start your first report above.", "small muted");
      for (const run of data.runs || []) {
        upsert(run);
        if (!terminal.has(String(run.status || "").toUpperCase())) poll(run.id);
      }
    } catch (error) {
      config.textContent = "Agent connection unavailable";
      history.textContent = error.message;
    }
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    button.disabled = true;
    message.textContent = "Submitting task to Browserbase…";
    try {
      const run = await api("/api/owner/browserbase/runs", {method:"POST",
        headers:{"Content-Type":"application/json"}, body:JSON.stringify({task:input.value.trim()})});
      upsert(run);
      message.textContent = "Run started. You can leave this page and return later.";
      if (!terminal.has(String(run.status || "").toUpperCase())) poll(run.id);
      await loadHistory();
    } catch (error) {
      message.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  document.getElementById("bb-refresh-button").addEventListener("click", loadHistory);
  loadHistory();
})();
