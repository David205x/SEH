const params = new URLSearchParams(location.search);
const runName = params.get("run");
const workId = params.get("work");
const state = { detail: null, selectedTrajectoryId: null };

const elements = {
  document: document.querySelector("#event-document"),
  facts: document.querySelector("#event-facts"),
  trajectories: document.querySelector("#trajectory-list"),
  toolbar: document.querySelector("#event-toolbar"),
  typeFilter: document.querySelector("#block-type-filter"),
  expandAll: document.querySelector("#expand-all"),
  collapseAll: document.querySelector("#collapse-all"),
  collapseSelected: document.querySelector("#collapse-selected"),
  expandSelected: document.querySelector("#expand-selected"),
};

elements.typeFilter.addEventListener("change", applyBlockFilter);
elements.expandAll.addEventListener("click", () => setAllCollapsed(false));
elements.collapseAll.addEventListener("click", () => setAllCollapsed(true));
elements.collapseSelected.addEventListener("click", () => setSelectedTypesCollapsed(true));
elements.expandSelected.addEventListener("click", () => setSelectedTypesCollapsed(false));

if (!runName || !workId) {
  renderMessage("缺少 run 或 work 参数。");
} else {
  loadEvent();
}

async function loadEvent() {
  try {
    const response = await fetch(
      `/api/runs/${encodeURIComponent(runName)}/works/${encodeURIComponent(workId)}`,
    );
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error ?? `请求失败 (${response.status})`);
    state.detail = payload;
    state.selectedTrajectoryId = payload.trajectories?.[0]?.trajectory_id ?? null;
    renderDetail();
  } catch (error) {
    renderMessage(`无法读取事件：${error.message}`);
  }
}

function renderDetail() {
  const work = state.detail.work;
  document.querySelector("#event-run-name").textContent = runName;
  document.querySelector("#event-work-id").textContent = work.work_id;
  document.querySelector("#event-title").textContent = work.kind;
  renderFacts(work);
  renderTrajectories();
  renderSelectedTrajectory();
}

function renderFacts(work) {
  const facts = [
    ["类别", work.category], ["状态", work.status], ["Generation", work.generation],
    ["Attempt", work.attempt], ["开始", work.started_at_utc], ["结束", work.ended_at_utc],
    ["Token", work.total_tokens], ["结果", work.result_ref], ["错误", work.error],
  ];
  const fragment = document.createDocumentFragment();
  for (const [label, value] of facts) {
    if (value == null) continue;
    const term = document.createElement("dt"); term.textContent = label;
    const description = document.createElement("dd"); description.textContent = value;
    fragment.append(term, description);
  }
  elements.facts.replaceChildren(fragment);
}

function renderTrajectories() {
  const trajectories = state.detail.trajectories ?? [];
  if (!trajectories.length) {
    elements.trajectories.replaceChildren(emptyState("没有可转换为对话的轨迹"));
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const trajectory of trajectories) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "trajectory-item";
    button.classList.toggle("is-selected", trajectory.trajectory_id === state.selectedTrajectoryId);
    const label = document.createElement("strong"); label.textContent = trajectory.label;
    const summary = document.createElement("span"); summary.textContent = trajectory.summary;
    button.append(label, summary);
    button.addEventListener("click", () => {
      state.selectedTrajectoryId = trajectory.trajectory_id;
      renderTrajectories();
      renderSelectedTrajectory();
    });
    fragment.append(button);
  }
  elements.trajectories.replaceChildren(fragment);
}

function renderSelectedTrajectory() {
  const trajectory = (state.detail.trajectories ?? []).find(
    (item) => item.trajectory_id === state.selectedTrajectoryId,
  );
  elements.toolbar.classList.toggle("is-hidden", !trajectory);
  if (!trajectory) {
    renderControlFallback();
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const block of trajectory.blocks) fragment.append(blockNode(block));
  elements.document.replaceChildren(fragment);
  elements.typeFilter.value = "";
}

function blockNode(block) {
  const section = document.createElement("section");
  section.className = `conversation-block block-${block.block_type}`;
  section.dataset.blockType = block.block_type;
  section.dataset.defaultCollapsed = String(block.default_collapsed);
  section.classList.toggle("is-collapsed", block.default_collapsed);

  const header = document.createElement("button");
  header.type = "button";
  header.className = "conversation-block-heading";
  header.setAttribute("aria-expanded", String(!block.default_collapsed));
  const identity = document.createElement("span"); identity.className = "block-identity";
  const type = document.createElement("span"); type.className = "block-type"; type.textContent = block.block_type.replace("_", " ");
  const title = document.createElement("strong"); title.textContent = block.title;
  identity.append(type, title);
  const toggle = document.createElement("span"); toggle.className = "block-toggle"; toggle.textContent = "⌄";
  header.append(identity, toggle);

  const body = document.createElement("div");
  body.className = "conversation-block-content";
  body.textContent = block.content;
  header.addEventListener("click", () => toggleBlock(section, header));
  section.append(header, body);
  return section;
}

function toggleBlock(section, header) {
  const collapsed = section.classList.toggle("is-collapsed");
  header.setAttribute("aria-expanded", String(!collapsed));
}

function setAllCollapsed(collapsed) {
  for (const section of elements.document.querySelectorAll(".conversation-block")) {
    section.classList.toggle("is-collapsed", collapsed);
    section.querySelector(".conversation-block-heading").setAttribute("aria-expanded", String(!collapsed));
  }
}

function setSelectedTypesCollapsed(collapsed) {
  const selectedTypes = new Set(
    [...document.querySelectorAll('input[name="fold-type"]:checked')].map(
      (input) => input.value,
    ),
  );
  for (const section of elements.document.querySelectorAll(".conversation-block")) {
    if (!selectedTypes.has(section.dataset.blockType)) continue;
    section.classList.toggle("is-collapsed", collapsed);
    section.querySelector(".conversation-block-heading").setAttribute("aria-expanded", String(!collapsed));
  }
}

function applyBlockFilter() {
  const selectedType = elements.typeFilter.value;
  for (const section of elements.document.querySelectorAll(".conversation-block")) {
    section.classList.toggle("is-hidden", Boolean(selectedType) && section.dataset.blockType !== selectedType);
  }
}

function renderControlFallback() {
  const fragment = document.createDocumentFragment();
  fragment.append(emptyState(state.detail.detail_message ?? "没有可阅读的轨迹产物。"));
  for (const event of state.detail.work.events ?? []) {
    const details = document.createElement("details"); details.className = "control-event";
    const summary = document.createElement("summary");
    summary.textContent = `#${event.sequence} · ${event.event_type} · ${event.created_at_utc}`;
    const content = document.createElement("pre");
    content.className = "notranslate";
    content.setAttribute("translate", "no");
    content.textContent = JSON.stringify(event.payload, null, 2);
    details.append(summary, content); fragment.append(details);
  }
  elements.document.replaceChildren(fragment);
}

function renderMessage(message) { elements.document.replaceChildren(emptyState(message)); }
function emptyState(message) { const node = document.createElement("div"); node.className = "empty-state"; node.textContent = message; return node; }
