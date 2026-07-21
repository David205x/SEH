const state = {
  runs: [],
  document: null,
  artifact: null,
  selectedRun: null,
  selectedIteration: null,
  selectedArtifact: null,
  selectedRecord: 0,
  expandedRoles: new Set([
    "assistant", "native-thinking", "inband-thinking", "tool", "hook", "error",
  ]),
};

const elements = {
  runList: document.querySelector("#run-list"),
  runCount: document.querySelector("#run-count"),
  title: document.querySelector("#experiment-title"),
  subtitle: document.querySelector("#experiment-subtitle"),
  eventList: document.querySelector("#event-list"),
  eventCount: document.querySelector("#event-count"),
  iterationList: document.querySelector("#iteration-list"),
  iterationCount: document.querySelector("#iteration-count"),
  artifactList: document.querySelector("#artifact-list"),
  artifactCount: document.querySelector("#artifact-count"),
  artifactTitle: document.querySelector("#artifact-title"),
  artifactSubtitle: document.querySelector("#artifact-subtitle"),
  artifactSummary: document.querySelector("#artifact-summary"),
  recordSelect: document.querySelector("#record-select"),
  conversation: document.querySelector("#conversation"),
  runInfo: document.querySelector("#run-info"),
  reload: document.querySelector("#reload-runs"),
  roleOptions: document.querySelectorAll("[data-role]"),
  messageTemplate: document.querySelector("#message-template"),
};

const timeline = AgentTimeline.create({
  conversation: elements.conversation,
  messageTemplate: elements.messageTemplate,
  expandedRoles: state.expandedRoles,
});

elements.reload.addEventListener("click", loadRuns);
elements.recordSelect.addEventListener("change", () => {
  state.selectedRecord = Number(elements.recordSelect.value);
  renderArtifactRecord();
});
for (const option of elements.roleOptions) {
  option.addEventListener("change", () => {
    const role = option.dataset.role;
    if (!role) return;
    if (option.checked) state.expandedRoles.add(role);
    else state.expandedRoles.delete(role);
    renderArtifactRecord();
  });
}

loadRuns();

async function loadRuns() {
  elements.runList.replaceChildren(emptyState("Loading experiments..."));
  try {
    const payload = await requestJson("/api/experiments");
    state.runs = payload.runs ?? [];
    renderRuns();
    if (state.selectedRun && state.runs.some((run) => run.path === state.selectedRun)) {
      await loadRun(state.selectedRun);
    } else if (state.runs.length) {
      await loadRun(state.runs[0].path);
    }
  } catch (error) {
    elements.runList.replaceChildren(emptyState(`Could not load experiments: ${error.message}`));
  }
}

async function loadRun(path) {
  state.selectedRun = path;
  state.document = null;
  state.artifact = null;
  state.selectedArtifact = null;
  renderRuns();
  elements.eventList.replaceChildren(emptyState("Loading experiment..."));
  try {
    state.document = await requestJson(`/api/experiment?path=${encodeURIComponent(path)}`);
    const iterations = state.document.iterations ?? [];
    state.selectedIteration = iterations.length ? iterations[0].iteration : null;
    renderDocument();
  } catch (error) {
    elements.eventList.replaceChildren(emptyState(`Could not load experiment: ${error.message}`));
  }
}

function renderRuns() {
  elements.runCount.textContent = String(state.runs.length);
  const fragment = document.createDocumentFragment();
  if (!state.runs.length) fragment.append(emptyState("No experiment runs found."));
  for (const run of state.runs) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "file-item experiment-run-item";
    button.classList.toggle("selected", run.path === state.selectedRun);
    button.addEventListener("click", () => loadRun(run.path));
    button.append(
      textSpan(run.path, "file-name"),
      textSpan(`${run.status ?? "running"} · ${run.iteration_count ?? 0} iter`, "file-size"),
    );
    fragment.append(button);
  }
  elements.runList.replaceChildren(fragment);
}

function renderDocument() {
  const summary = state.document.summary ?? {};
  elements.title.textContent = state.document.source;
  elements.subtitle.textContent = `${summary.status ?? "running"} · ${summary.iteration_count ?? 0} iterations`;
  renderRunInfo();
  renderIterations();
  renderSelectedIteration();
}

function selectIteration(iteration) {
  state.selectedIteration = iteration;
  state.selectedArtifact = null;
  state.artifact = null;
  renderIterations();
  renderSelectedIteration();
}

function renderIterations() {
  const iterations = state.document?.iterations ?? [];
  elements.iterationCount.textContent = String(iterations.length);
  const fragment = document.createDocumentFragment();
  if (!iterations.length) fragment.append(emptyState("No iterations."));
  for (const iteration of iterations) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "trace-item";
    button.classList.toggle("selected", iteration.iteration === state.selectedIteration);
    button.addEventListener("click", () => selectIteration(iteration.iteration));
    const decision = iterationOutcome(iteration);
    button.append(
      textSpan(`#${iteration.iteration}`, "trace-ordinal"),
      textSpan(decision, "trace-label"),
    );
    fragment.append(button);
  }
  elements.iterationList.replaceChildren(fragment);
}

function renderSelectedIteration() {
  const iteration = selectedIteration();
  if (!iteration) {
    elements.eventList.replaceChildren(emptyState("This run has no iterations."));
    elements.artifactList.replaceChildren(emptyState("No artifacts."));
    clearArtifact("Choose an experiment artifact.");
    return;
  }
  renderEvents(iteration.events ?? []);
  renderArtifacts(iteration.artifacts ?? []);
}

function renderEvents(events) {
  elements.eventCount.textContent = String(events.length);
  const fragment = document.createDocumentFragment();
  if (!events.length) fragment.append(emptyState("No iteration events."));
  for (const event of events) {
    const article = document.createElement("article");
    article.className = `experiment-event event-${eventTone(event.event_type)}`;
    const heading = document.createElement("div");
    heading.className = "experiment-event-heading";
    heading.append(
      textSpan(`#${event.sequence} ${formatEventName(event.event_type)}`, "experiment-event-name"),
      textSpan(formatTimestamp(event.timestamp), "experiment-event-time"),
    );
    const summary = document.createElement("p");
    summary.className = "experiment-event-summary";
    summary.textContent = eventSummary(event);
    article.append(heading, summary);
    fragment.append(article);
  }
  elements.eventList.replaceChildren(fragment);
}

function renderArtifacts(artifacts) {
  elements.artifactCount.textContent = String(artifacts.length);
  const fragment = document.createDocumentFragment();
  if (!artifacts.length) fragment.append(emptyState("No artifacts for this iteration."));
  for (const artifact of artifacts) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "trace-item artifact-item";
    button.classList.toggle("selected", artifact.path === state.selectedArtifact);
    button.addEventListener("click", () => loadArtifact(artifact));
    button.append(
      textSpan(artifactKindLabel(artifact.kind), "trace-ordinal"),
      textSpan(artifact.label, "trace-label"),
    );
    fragment.append(button);
  }
  elements.artifactList.replaceChildren(fragment);
}

async function loadArtifact(metadata) {
  state.selectedArtifact = metadata.path;
  state.artifact = null;
  state.selectedRecord = 0;
  renderArtifacts(selectedIteration()?.artifacts ?? []);
  clearArtifact("Loading artifact...");
  try {
    state.artifact = await requestJson(
      `/api/experiment-artifact?run=${encodeURIComponent(state.selectedRun)}&path=${encodeURIComponent(metadata.path)}`,
    );
    elements.artifactTitle.textContent = metadata.label;
    elements.artifactSubtitle.textContent = metadata.path;
    configureRecordSelector();
    renderArtifactRecord();
  } catch (error) {
    clearArtifact(`Could not load artifact: ${error.message}`);
  }
}

function configureRecordSelector() {
  const artifact = state.artifact;
  let records = [];
  if (artifact?.kind === "actor") records = artifact.entries ?? [];
  if (artifact?.kind === "evaluation") records = artifact.items ?? [];
  elements.recordSelect.replaceChildren();
  elements.recordSelect.hidden = records.length === 0;
  records.forEach((record, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = artifact.kind === "actor"
      ? `#${index + 1} ${record.label}`
      : `#${index + 1} ${record.example_id ?? "case"}`;
    elements.recordSelect.append(option);
  });
}

function renderArtifactRecord() {
  const artifact = state.artifact;
  if (!artifact) return;
  elements.artifactSummary.replaceChildren();
  if (artifact.kind === "actor") {
    const entry = artifact.entries?.[state.selectedRecord];
    renderKeyValues([
      ["Example", entry?.example?.example_id], ["Question", entry?.example?.question],
      ["Golden", entry?.example?.answer], ["Answer", entry?.run?.answer],
      ["Status", entry?.run?.status], ["Error", entry?.run?.error ?? entry?.runner_error?.message],
    ]);
    timeline.render(entry?.run, { missingMessage: "No Actor trajectory in this record." });
    return;
  }
  if (artifact.kind === "evaluation") {
    const item = artifact.items?.[state.selectedRecord];
    renderJsonBlock(artifact.summary, "Evaluation metrics", elements.artifactSummary);
    renderJsonBlock(item, "Selected evaluation case", elements.conversation);
    return;
  }
  if (artifact.kind === "critic" || artifact.kind === "compiler") {
    const payload = artifact.payload ?? {};
    const result = artifact.kind === "critic" ? payload.critic_result : payload.compiler_result;
    renderResult(result, artifact.kind);
    timeline.render(payload.run, { missingMessage: `No ${artifact.kind} AgentRun recorded.` });
    return;
  }
  renderJsonBlock(artifact.payload ?? artifact.values, "Artifact content", elements.conversation);
}

function renderResult(result, kind) {
  if (!result) {
    elements.artifactSummary.replaceChildren(emptyState(`No parsed ${kind} result.`));
    return;
  }
  const block = document.createElement("div");
  block.className = "experiment-result-text";
  block.textContent = result.analysis ?? result.summary ?? JSON.stringify(result, null, 2);
  elements.artifactSummary.replaceChildren(block);
}

function renderJsonBlock(value, label, target) {
  target.replaceChildren();
  if (value === undefined || value === null) {
    target.append(emptyState(`No ${label.toLowerCase()}.`));
    return;
  }
  const article = document.createElement("article");
  article.className = "message role-context expanded";
  const heading = document.createElement("button");
  heading.type = "button";
  heading.className = "message-meta";
  heading.textContent = label;
  const content = document.createElement("div");
  content.className = "message-content technical-text";
  content.translate = false;
  content.textContent = JSON.stringify(value, null, 2);
  heading.addEventListener("click", () => article.classList.toggle("expanded"));
  article.append(heading, content);
  target.append(article);
}

function renderRunInfo() {
  const summary = state.document?.summary ?? {};
  const config = state.document?.config ?? {};
  const values = [
    ["Status", summary.status], ["Reason", summary.reason],
    ["Initial version", summary.initial_version], ["Latest version", summary.latest_version],
    ["Iterations", summary.iteration_count], ["Accepted", summary.accepted_iterations],
    ["Experience cases", summary.experience_count], ["Checkpoint", config.checkpoint_store_id],
    ["Updated", formatTimestamp(summary.updated_at)],
  ];
  const fragment = document.createDocumentFragment();
  for (const [term, value] of values) {
    if (value === undefined || value === null || value === "") continue;
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = String(value);
    fragment.append(dt, dd);
  }
  elements.runInfo.replaceChildren(fragment);
}

function renderKeyValues(values) {
  const list = document.createElement("dl");
  list.className = "trace-info artifact-key-values";
  for (const [term, value] of values) {
    if (value === undefined || value === null || value === "") continue;
    const dt = document.createElement("dt"); dt.textContent = term;
    const dd = document.createElement("dd"); dd.textContent = String(value);
    list.append(dt, dd);
  }
  elements.artifactSummary.replaceChildren(list);
}

function clearArtifact(message) {
  elements.artifactTitle.textContent = "Artifact";
  elements.artifactSubtitle.textContent = "Choose an artifact from the right.";
  elements.recordSelect.hidden = true;
  elements.artifactSummary.replaceChildren();
  elements.conversation.replaceChildren(emptyState(message));
}

function selectedIteration() {
  return state.document?.iterations?.find((item) => item.iteration === state.selectedIteration);
}

function iterationOutcome(iteration) {
  const decision = iteration.decision;
  if (!decision) return "in progress";
  if (decision.event_type === "run_completed") return decision.payload?.status ?? "completed";
  return decision.event_type?.replace("candidate_", "") ?? "completed";
}

function eventSummary(event) {
  const payload = event.payload ?? {};
  if (event.event_type === "iteration_started") return `Parent ${payload.parent_version ?? "unknown"}`;
  if (event.event_type.endsWith("evaluated")) {
    const accuracy = payload.metrics?.answers?.accuracy;
    return accuracy === undefined ? "Evaluation completed" : `Accuracy ${formatPercent(accuracy)}`;
  }
  if (event.event_type === "failure_critic_completed") {
    return `${payload.result?.proposals?.length ?? 0} proposals`;
  }
  if (event.event_type === "compiler_completed") {
    return payload.summary ?? "Candidate compiled";
  }
  if (event.event_type === "candidate_reviewed") {
    return payload.result?.review?.reason ?? "Candidate reviewed";
  }
  if (event.event_type === "candidate_rejected" || event.event_type === "candidate_accepted") {
    return payload.reason ?? payload.compiler_summary ?? formatEventName(event.event_type);
  }
  return payload.reason ?? formatEventName(event.event_type);
}

function eventTone(type) {
  if (type?.includes("rejected") || type?.includes("failed")) return "negative";
  if (type?.includes("accepted")) return "positive";
  if (type?.includes("critic")) return "critic";
  if (type?.includes("compiler")) return "compiler";
  return "neutral";
}

function artifactKindLabel(kind) {
  return { actor: "A", evaluation: "E", critic: "C", compiler: "P", decision: "D" }[kind] ?? "J";
}

function formatEventName(value) {
  return String(value ?? "event").replaceAll("_", " ");
}

function formatTimestamp(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString();
}

function formatPercent(value) { return `${(Number(value) * 100).toFixed(1)}%`; }
function textSpan(text, className) {
  const node = document.createElement("span"); node.className = className; node.textContent = text; return node;
}
function emptyState(text) {
  const node = document.createElement("div"); node.className = "empty-state"; node.textContent = text; return node;
}
async function requestJson(url) {
  const response = await fetch(url); const payload = await response.json();
  if (!response.ok) throw new Error(payload.error ?? `Request failed (${response.status})`);
  return payload;
}
