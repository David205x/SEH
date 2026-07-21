const state = {
  logs: [],
  selectedPath: null,
  document: null,
  expandedRoles: new Set([
    "assistant",
    "native-thinking",
    "inband-thinking",
    "tool",
    "hook",
    "error",
  ]),
};

const elements = {
  logList: document.querySelector("#log-list"),
  logCount: document.querySelector("#log-count"),
  logTitle: document.querySelector("#log-title"),
  logSubtitle: document.querySelector("#log-subtitle"),
  result: document.querySelector("#critic-result"),
  conversation: document.querySelector("#conversation"),
  stepList: document.querySelector("#step-list"),
  stepCount: document.querySelector("#step-count"),
  logInfo: document.querySelector("#log-info"),
  reload: document.querySelector("#reload-logs"),
  roleOptions: document.querySelectorAll("[data-role]"),
  messageTemplate: document.querySelector("#message-template"),
};

const timeline = AgentTimeline.create({
  conversation: elements.conversation,
  messageTemplate: elements.messageTemplate,
  expandedRoles: state.expandedRoles,
});

elements.reload.addEventListener("click", loadLogs);
for (const option of elements.roleOptions) {
  option.addEventListener("change", () => {
    const role = option.dataset.role;
    if (!role) return;
    if (option.checked) state.expandedRoles.add(role);
    else state.expandedRoles.delete(role);
    renderSelectedLog();
  });
}
loadLogs();

async function loadLogs() {
  elements.logList.replaceChildren(emptyState("Loading Critic logs..."));
  try {
    const payload = await requestJson("/api/critic-logs");
    state.logs = payload.logs ?? [];
    renderLogList();
    if (state.selectedPath && state.logs.some((item) => item.path === state.selectedPath)) {
      await loadLog(state.selectedPath);
    }
  } catch (error) {
    elements.logList.replaceChildren(emptyState(`Could not load Critic logs: ${error.message}`));
  }
}

async function loadLog(path) {
  state.selectedPath = path;
  state.document = null;
  renderLogList();
  clearLog();
  try {
    state.document = await requestJson(`/api/critic-log?path=${encodeURIComponent(path)}`);
    renderSelectedLog();
  } catch (error) {
    elements.conversation.replaceChildren(emptyState(`Could not load Critic log: ${error.message}`));
  }
}

function renderLogList() {
  elements.logCount.textContent = String(state.logs.length);
  if (!state.logs.length) {
    elements.logList.replaceChildren(emptyState("No Critic JSON logs found."));
    return;
  }
  elements.logList.replaceChildren(...state.logs.map((log) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "file-item";
    button.classList.toggle("selected", log.path === state.selectedPath);
    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = log.path;
    const detail = document.createElement("span");
    detail.className = "file-size";
    detail.textContent = `${log.status} · ${log.proposal_count} proposals`;
    button.append(name, detail);
    button.addEventListener("click", () => loadLog(log.path));
    return button;
  }));
}

function renderSelectedLog() {
  if (!state.document) return;
  const log = state.document.log ?? {};
  const summary = state.document.summary ?? {};
  elements.logTitle.textContent = state.document.source;
  elements.logSubtitle.textContent = `${summary.status ?? "unknown"} · ${summary.created_at ?? "unknown time"}`;
  renderResult(log);
  renderLogInfo(log, summary);
  renderSteps(log.run);
  timeline.render(log.run, {
    missingMessage: "No Critic AgentRun was recorded. Inspect the result error and run details.",
  });
}

function renderResult(log) {
  if (typeof log.result_error === "string" && log.result_error) {
    elements.result.textContent = log.result_error;
    elements.result.classList.add("critic-result-error");
  } else if (log.critic_result && typeof log.critic_result === "object") {
    elements.result.textContent = JSON.stringify(log.critic_result, null, 2);
    elements.result.classList.remove("critic-result-error");
  } else {
    elements.result.textContent = "No Critic result was produced.";
    elements.result.classList.add("critic-result-error");
  }
}

function renderLogInfo(log, summary) {
  const inputs = log.inputs && typeof log.inputs === "object" ? log.inputs : {};
  const run = log.run && typeof log.run === "object" ? log.run : {};
  renderInfo(elements.logInfo, [
    ["Status", summary.status],
    ["Created", summary.created_at],
    ["Report", inputs.report_dir],
    ["Rollout", inputs.rollout_file],
    ["Actor source", inputs.actor_source],
    ["Harness", inputs.harness_version],
    ["Critic plugins", inputs.critic_plugins_root],
    ["Model role", inputs.model_role],
    ["Steps", run.state?.step],
    ["Events", Array.isArray(run.trace) ? run.trace.length : 0],
    ["Run error", run.error],
  ]);
}

function renderSteps(run) {
  const steps = [...new Set((run?.trace ?? []).map((event) => event?.step).filter(Number.isInteger))];
  elements.stepCount.textContent = String(steps.length);
  if (!steps.length) {
    elements.stepList.replaceChildren(emptyState("No execution steps were recorded."));
    return;
  }
  elements.stepList.replaceChildren(...steps.map((step) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "trace-item";
    button.textContent = `Step ${step}`;
    button.addEventListener("click", () => {
      elements.conversation.querySelector(`[data-step-anchor="${step}"]`)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
    return button;
  }));
}

function renderInfo(target, rows) {
  const fragment = document.createDocumentFragment();
  for (const [term, value] of rows) {
    if (value === undefined || value === null || value === "") continue;
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = String(value);
    fragment.append(dt, dd);
  }
  target.replaceChildren(fragment);
}

function clearLog() {
  elements.logTitle.textContent = "Loading Critic log...";
  elements.logSubtitle.textContent = "";
  elements.result.textContent = "";
  elements.logInfo.replaceChildren();
  elements.stepList.replaceChildren();
  elements.stepCount.textContent = "0";
  elements.conversation.replaceChildren(emptyState("Loading Critic log..."));
}

function emptyState(text) {
  const node = document.createElement("div");
  node.className = "empty-state";
  node.textContent = text;
  return node;
}

async function requestJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error ?? `Request failed (${response.status})`);
  return payload;
}
