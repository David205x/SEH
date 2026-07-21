const state = {
  overview: null,
  selectedIteration: null,
  selectedVersion: null,
  view: "evolution",
};

const elements = {
  iterationList: document.querySelector("#iteration-list"),
  iterationCount: document.querySelector("#iteration-count"),
  versionList: document.querySelector("#version-list"),
  versionCount: document.querySelector("#version-count"),
  title: document.querySelector("#iteration-title"),
  subtitle: document.querySelector("#iteration-subtitle"),
  timeline: document.querySelector("#evolution-timeline"),
  detail: document.querySelector("#evolution-detail"),
  reload: document.querySelector("#reload-evolution"),
  eventTemplate: document.querySelector("#evolution-event-template"),
  viewButtons: [...document.querySelectorAll(".view-switch-button")],
};

elements.reload.addEventListener("click", loadOverview);
elements.viewButtons.forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});
loadOverview();

async function loadOverview() {
  setLoading();
  try {
    state.overview = await requestJson("/api/harness-store");
    renderOverview();
    if (!state.overview.configured) {
      showEmpty("Start the viewer with --harness-store-dir to inspect evolution history.");
      return;
    }
    if (!state.overview.initialized) {
      showEmpty(`No initialized Version Store found at ${state.overview.root}.`);
      return;
    }
    const iterations = state.overview.iterations ?? [];
    const versions = state.overview.versions ?? [];
    const iterationId = iterations.some((item) => item.iteration_id === state.selectedIteration)
      ? state.selectedIteration
      : iterations.at(-1)?.iteration_id;
    const versionId = versions.some((item) => item.version_id === state.selectedVersion)
      ? state.selectedVersion
      : versions.at(-1)?.version_id;
    if (iterationId) await selectIteration(iterationId);
    else showEmpty("This Version Store has no iteration events yet.");
    if (versionId) await selectVersion(versionId);
  } catch (error) {
    elements.timeline.replaceChildren(emptyState(`Could not load Harness history: ${error.message}`));
  }
}

function renderOverview() {
  const iterations = state.overview?.iterations ?? [];
  const versions = state.overview?.versions ?? [];
  elements.iterationCount.textContent = String(iterations.length);
  elements.versionCount.textContent = String(versions.length);
  elements.iterationList.replaceChildren(...iterations.slice().reverse().map(iterationButton));
  elements.versionList.replaceChildren(...versions.slice().reverse().map(versionButton));
}

function iterationButton(item) {
  const button = document.createElement("button");
  button.className = "iteration-item";
  button.classList.toggle("selected", item.iteration_id === state.selectedIteration);
  const top = document.createElement("span");
  top.className = "iteration-item-top";
  const id = document.createElement("span");
  id.className = "iteration-id";
  id.textContent = shortIterationId(item.iteration_id);
  const status = document.createElement("span");
  status.className = `status-badge status-${item.status}`;
  status.textContent = item.status;
  top.append(id, status);
  const parent = document.createElement("span");
  parent.className = "iteration-parent";
  parent.textContent = `${item.parent_version} · ${item.patch_count} patch${item.patch_count === 1 ? "" : "es"}`;
  button.append(top, parent);
  button.addEventListener("click", () => selectIteration(item.iteration_id));
  return button;
}

function versionButton(item) {
  const button = document.createElement("button");
  button.className = "version-item";
  button.classList.toggle("selected", item.version_id === state.selectedVersion);
  const id = document.createElement("span");
  id.className = "version-id";
  id.textContent = item.version_id;
  const summary = document.createElement("span");
  summary.className = "version-summary";
  summary.textContent = item.summary;
  button.append(id, summary);
  button.addEventListener("click", () => selectVersion(item.version_id));
  return button;
}

async function selectIteration(iterationId) {
  state.selectedIteration = iterationId;
  renderOverview();
  if (state.view !== "evolution") return;
  const payload = await requestJson(`/api/harness-iteration?id=${encodeURIComponent(iterationId)}`);
  const summary = payload.summary;
  elements.title.textContent = shortIterationId(summary.iteration_id);
  elements.subtitle.textContent = `${summary.status} · parent ${summary.parent_version} · ${summary.patch_count} patch event${summary.patch_count === 1 ? "" : "s"}`;
  elements.timeline.replaceChildren(...payload.events.map(renderEvent));
  renderIterationDetail(summary);
}

async function selectVersion(versionId) {
  state.selectedVersion = versionId;
  renderOverview();
  const payload = await requestJson(`/api/harness-version?id=${encodeURIComponent(versionId)}`);
  elements.detail.textContent = JSON.stringify({
    version: payload.version,
    changes: payload.changes,
    manifest: payload.manifest,
    files: payload.files,
  }, null, 2);
  if (state.view === "topology") await renderTopology(versionId);
}

async function setView(view) {
  if (!['evolution', 'topology'].includes(view)) return;
  state.view = view;
  elements.viewButtons.forEach((button) => {
    button.classList.toggle("selected", button.dataset.view === view);
  });
  if (view === "topology") {
    if (state.selectedVersion) await renderTopology(state.selectedVersion);
    else showEmpty("Select an accepted version to inspect its topology.");
    return;
  }
  if (state.selectedIteration) await selectIteration(state.selectedIteration);
  else showEmpty("This Version Store has no iteration events yet.");
}

async function renderTopology(versionId) {
  elements.title.textContent = `Topology · ${versionId}`;
  elements.subtitle.textContent = "Declared components, lifecycle placement and Hook capabilities";
  elements.timeline.replaceChildren(emptyState("Assembling Harness topology..."));
  try {
    const payload = await requestJson(`/api/harness-topology?id=${encodeURIComponent(versionId)}`);
    const topology = payload.topology;
    elements.subtitle.textContent = `${topology.harness_id} · ${shortDigest(payload.digest)}`;
    elements.timeline.replaceChildren(topologyView(topology));
    elements.detail.textContent = JSON.stringify({
      version_id: payload.version_id,
      digest: payload.digest,
      harness_id: topology.harness_id,
      component_counts: {
        tools: topology.tools.length,
        extensions: topology.extensions.length,
        hooks: topology.extensions.flatMap((extension) => extension.hooks ?? []).length,
      },
    }, null, 2);
  } catch (error) {
    elements.timeline.replaceChildren(emptyState(`Could not assemble topology: ${error.message}`));
  }
}

function topologyView(topology) {
  const root = document.createElement("div");
  root.className = "topology-view";

  const componentBand = document.createElement("section");
  componentBand.className = "topology-component-band";
  componentBand.append(
    topologyComponent("Prompt", topology.prompt.instance_id, topology.prompt, topology.prompt.evolution_policy),
  );
  topology.tools.forEach((tool) => {
    componentBand.append(
      topologyComponent("Tool", tool.tool_name ?? tool.instance_id, tool, tool.evolution_policy),
    );
  });

  const hooks = topology.extensions.flatMap((extension) =>
    (extension.hooks ?? []).map((hook) => ({ ...hook, extension })),
  );
  const lifecycle = document.createElement("section");
  lifecycle.className = "topology-lifecycle";
  topology.phase_order.forEach((phase, index) => {
    const row = document.createElement("div");
    row.className = "topology-phase-row";
    const marker = document.createElement("div");
    marker.className = "topology-phase-marker";
    const phaseName = document.createElement("strong");
    phaseName.textContent = phase.replaceAll("_", " ");
    const order = document.createElement("span");
    order.textContent = String(index + 1).padStart(2, "0");
    marker.append(order, phaseName);

    const lane = document.createElement("div");
    lane.className = "topology-hook-lane";
    const phaseHooks = hooks.filter((hook) => hook.phases.includes(phase));
    if (!phaseHooks.length) {
      const empty = document.createElement("span");
      empty.className = "topology-lane-empty";
      empty.textContent = "No registered Hook";
      lane.append(empty);
    } else {
      phaseHooks.forEach((hook) => lane.append(topologyHook(hook)));
    }
    row.append(marker, lane);
    lifecycle.append(row);
  });

  const disabled = topology.extensions.filter((extension) => !extension.enabled);
  if (disabled.length) {
    const disabledBand = document.createElement("section");
    disabledBand.className = "topology-disabled-band";
    const heading = document.createElement("h3");
    heading.textContent = "Disabled extensions";
    disabledBand.append(heading);
    disabled.forEach((extension) => {
      disabledBand.append(
        topologyComponent("Extension", extension.instance_id, extension, extension.evolution_policy),
      );
    });
    root.append(componentBand, lifecycle, disabledBand);
  } else {
    root.append(componentBand, lifecycle);
  }
  return root;
}

function topologyComponent(kind, name, detail, policy) {
  const button = document.createElement("button");
  button.className = "topology-component";
  button.type = "button";
  const label = document.createElement("span");
  label.className = "topology-kind";
  label.textContent = kind;
  const title = document.createElement("strong");
  title.textContent = name;
  const badge = document.createElement("span");
  badge.className = `topology-policy policy-${policy}`;
  badge.textContent = policy;
  button.append(label, title, badge);
  button.addEventListener("click", () => {
    elements.detail.textContent = JSON.stringify(detail, null, 2);
  });
  return button;
}

function topologyHook(hook) {
  const button = document.createElement("button");
  button.className = "topology-hook";
  button.type = "button";
  const top = document.createElement("span");
  top.className = "topology-hook-top";
  const order = document.createElement("span");
  order.textContent = `#${hook.execution_order}`;
  const title = document.createElement("strong");
  title.textContent = hook.hook_id;
  top.append(order, title);
  const meta = document.createElement("span");
  meta.className = "topology-hook-meta";
  const profiles = hook.model_profiles.length ? ` · model ${hook.model_profiles.join(", ")}` : "";
  meta.textContent = `${hook.extension.instance_id} · ${hook.extension.evolution_policy}${profiles}`;
  button.append(top, meta);
  button.addEventListener("click", () => {
    elements.detail.textContent = JSON.stringify({
      extension: hook.extension,
      hook: {
        hook_id: hook.hook_id,
        execution_order: hook.execution_order,
        phases: hook.phases,
        state_refs: hook.state_refs,
        writable_stage_keys: hook.writable_stage_keys,
        model_profiles: hook.model_profiles,
        max_model_calls_per_invocation: hook.max_model_calls_per_invocation,
      },
    }, null, 2);
  });
  return button;
}

function renderEvent(event) {
  const node = elements.eventTemplate.content.firstElementChild.cloneNode(true);
  node.classList.add(`event-${event.event_type.replaceAll("_", "-")}`);
  node.querySelector(".event-sequence").textContent = `#${event.sequence}`;
  node.querySelector(".event-name").textContent = event.event_type.replaceAll("_", " ");
  node.querySelector(".event-time").textContent = formatTimestamp(event.timestamp);
  node.querySelector(".evolution-event-content").textContent = formatEventPayload(event);
  node.querySelector(".evolution-event-heading").addEventListener("click", () => {
    node.classList.toggle("collapsed");
  });
  return node;
}

function formatEventPayload(event) {
  if (event.event_type === "patch_applied") {
    const edits = Array.isArray(event.payload?.edits) ? event.payload.edits : [];
    const rendered = edits.map((edit) => {
      const heading = `${String(edit.operation).toUpperCase()} ${edit.path}`;
      return edit.operation === "write" ? `${heading}\n${edit.content ?? ""}` : heading;
    });
    return [
      `revision: ${event.payload?.workspace_revision}`,
      `digest: ${event.payload?.candidate_digest}`,
      "",
      ...rendered,
    ].join("\n\n");
  }
  if (event.event_type === "validation_completed") {
    return JSON.stringify({
      passed: event.payload?.passed,
      added_paths: event.payload?.added_paths,
      modified_paths: event.payload?.modified_paths,
      removed_paths: event.payload?.removed_paths,
      errors: event.payload?.errors,
      candidate_digest: event.payload?.candidate_digest,
    }, null, 2);
  }
  return JSON.stringify(event.payload ?? {}, null, 2);
}

function renderIterationDetail(summary) {
  elements.detail.textContent = JSON.stringify({
    iteration_id: summary.iteration_id,
    status: summary.status,
    parent_version: summary.parent_version,
    accepted_version: summary.accepted_version,
    patch_count: summary.patch_count,
    candidate_digest: summary.candidate_digest,
    rejection_reason: summary.rejection_reason,
  }, null, 2);
}

function setLoading() {
  elements.iterationList.replaceChildren(emptyState("Loading iterations..."));
  elements.versionList.replaceChildren(emptyState("Loading versions..."));
  elements.timeline.replaceChildren(emptyState("Loading Harness history..."));
}

function showEmpty(message) {
  elements.title.textContent = "Harness evolution";
  elements.subtitle.textContent = state.overview?.root ?? "No Version Store configured";
  elements.timeline.replaceChildren(emptyState(message));
  elements.detail.textContent = "";
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

function shortIterationId(value) {
  return value.replace(/^iteration_/, "").replace(/_[a-f0-9]{8}$/, "");
}

function formatTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

function shortDigest(value) {
  return typeof value === "string" ? value.slice(0, 12) : "unknown digest";
}
