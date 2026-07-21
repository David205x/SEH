const state = {
  files: [],
  document: null,
  selectedFile: null,
  selectedTraceIndex: null,
  expandedRoles: new Set([
    "system",
    "user",
    "assistant",
    "native-thinking",
    "inband-thinking",
    "tool",
    "hook",
    "context",
    "error",
  ]),
};

const elements = {
  fileList: document.querySelector("#file-list"),
  fileCount: document.querySelector("#file-count"),
  traceList: document.querySelector("#trace-list"),
  traceCount: document.querySelector("#trace-count"),
  conversation: document.querySelector("#conversation"),
  conversationTitle: document.querySelector("#conversation-title"),
  conversationSubtitle: document.querySelector("#conversation-subtitle"),
  traceInfo: document.querySelector("#trace-info"),
  reload: document.querySelector("#reload-files"),
  roleOptions: document.querySelectorAll("[data-role]"),
  messageTemplate: document.querySelector("#message-template"),
};

const timeline = AgentTimeline.create({
  conversation: elements.conversation,
  messageTemplate: elements.messageTemplate,
  expandedRoles: state.expandedRoles,
});

elements.reload.addEventListener("click", loadFiles);
for (const option of elements.roleOptions) {
  option.addEventListener("change", () => {
    const role = option.dataset.role;
    if (!role) return;
    if (option.checked) state.expandedRoles.add(role);
    else state.expandedRoles.delete(role);
    const entry = state.document?.entries[state.selectedTraceIndex];
    if (entry) renderSelectedTrace(entry);
  });
}
loadFiles();

async function loadFiles() {
  elements.fileList.replaceChildren(emptyState("Loading files..."));
  try {
    const payload = await requestJson("/api/files");
    state.files = payload.files;
    renderFiles();
    if (state.selectedFile && state.files.some((file) => file.path === state.selectedFile)) {
      await loadFile(state.selectedFile);
    }
  } catch (error) {
    elements.fileList.replaceChildren(emptyState(`Could not load files: ${error.message}`));
  }
}

async function loadFile(path) {
  state.selectedFile = path;
  state.document = null;
  state.selectedTraceIndex = null;
  renderFiles();
  elements.conversation.replaceChildren(emptyState("Loading trace file..."));
  elements.traceList.replaceChildren();
  elements.traceInfo.replaceChildren();
  try {
    state.document = await requestJson(`/api/file?path=${encodeURIComponent(path)}`);
    selectTrace(0);
  } catch (error) {
    elements.conversation.replaceChildren(emptyState(`Could not load trace: ${error.message}`));
  }
}

function renderFiles() {
  elements.fileCount.textContent = String(state.files.length);
  const fragment = document.createDocumentFragment();
  if (!state.files.length) fragment.append(emptyState("No JSON or JSONL files found."));
  for (const file of state.files) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "file-item";
    button.classList.toggle("selected", file.path === state.selectedFile);
    button.addEventListener("click", () => loadFile(file.path));
    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = file.path;
    const size = document.createElement("span");
    size.className = "file-size";
    size.textContent = formatSize(file.size_bytes);
    button.append(name, size);
    fragment.append(button);
  }
  elements.fileList.replaceChildren(fragment);
}

function selectTrace(index) {
  if (!state.document?.entries[index]) return;
  state.selectedTraceIndex = index;
  renderTraceList();
  renderSelectedTrace(state.document.entries[index]);
}

function renderTraceList() {
  const entries = state.document?.entries ?? [];
  elements.traceCount.textContent = String(entries.length);
  const fragment = document.createDocumentFragment();
  if (!entries.length) fragment.append(emptyState("No trajectories in this file."));
  for (const entry of entries) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "trace-item";
    button.classList.toggle("selected", entry.index === state.selectedTraceIndex);
    button.addEventListener("click", () => selectTrace(entry.index));
    const ordinal = document.createElement("span");
    ordinal.className = "trace-ordinal";
    ordinal.textContent = `#${entry.index + 1}`;
    const label = document.createElement("span");
    label.className = "trace-label";
    label.textContent = entry.label;
    button.append(ordinal, label);
    fragment.append(button);
  }
  elements.traceList.replaceChildren(fragment);
}

function renderSelectedTrace(entry) {
  const run = entry.run;
  elements.conversationTitle.textContent = state.document.source;
  elements.conversationSubtitle.textContent = `${state.document.format.toUpperCase()} · trajectory ${entry.index + 1}`;
  renderTraceInfo(entry);
  timeline.render(run, {
    missingMessage: entry.runner_error
      ? `${entry.runner_error.type}: ${entry.runner_error.message}`
      : "This entry does not contain a runnable trajectory.",
    modelInputs: "initial",
    showStepMarkers: false,
    showToolCalls: false,
  });
}

function renderTraceInfo(entry) {
  const run = entry.run;
  const info = [
    ["Source", state.document.source],
    ["Trajectory", `#${entry.index + 1}`],
    ["Example ID", entry.example?.example_id],
    ["Status", run?.status],
    ["Steps", run?.state?.step],
    ["Events", Array.isArray(run?.trace) ? run.trace.length : 0],
    ["Question", entry.example?.question ?? run?.question],
    ["Golden Answer", entry.example?.answer],
    ["Answer", run?.answer],
    ["Error", run?.error],
  ];
  const fragment = document.createDocumentFragment();
  for (const [term, value] of info) {
    if (value === undefined || value === null || value === "") continue;
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = String(value);
    fragment.append(dt, dd);
  }
  elements.traceInfo.replaceChildren(fragment);
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

function formatSize(value) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
