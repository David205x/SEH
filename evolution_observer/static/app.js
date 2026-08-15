const SELECTED_RUN_STORAGE_KEY = "evolution-observer:selected-run";

const state = {
  runs: [], selectedRun: initialSelectedRun(), journalVisible: false, overview: null,
  selectedGeneration: null, selectedFlowNode: null, turnScope: "run",
};

const elements = {
  runList: document.querySelector("#run-list"), runCount: document.querySelector("#run-count"),
  summary: document.querySelector("#run-summary"), compactFlow: document.querySelector("#compact-flow-track"),
  generationTabs: document.querySelector("#generation-tabs"),
  workList: document.querySelector("#work-list"),
  experimentStats: document.querySelector("#experiment-stats"), timeStats: document.querySelector("#time-stats"),
  roleTimeDonut: document.querySelector("#role-time-donut"), roleTimeTable: document.querySelector("#role-time-table"),
  stageStats: document.querySelector("#stage-stats"), usageSummary: document.querySelector("#usage-summary"),
  roleUsageDonut: document.querySelector("#role-usage-donut"), roleUsageTable: document.querySelector("#role-usage-table"),
  turnScopeToggle: document.querySelector("#turn-scope-toggle"), turnBoxplot: document.querySelector("#turn-boxplot"),
  generationScopeButton: document.querySelector("#generation-scope-button"),
  evolutionMetrics: document.querySelector("#evolution-metrics"),
  journalList: document.querySelector("#journal-list"), category: document.querySelector("#category-filter"),
  status: document.querySelector("#status-filter"), journalToggle: document.querySelector("#journal-toggle"),
  nodeFilterClear: document.querySelector("#node-filter-clear"),
  refreshNow: document.querySelector("#refresh-now"), runTemplate: document.querySelector("#run-template"),
  workTemplate: document.querySelector("#work-template"), journalTemplate: document.querySelector("#journal-template"),
};

elements.refreshNow.addEventListener("click", refreshSelectedRun);
elements.category.addEventListener("change", loadWorks);
elements.status.addEventListener("change", loadWorks);
elements.journalToggle.addEventListener("click", toggleJournal);
elements.nodeFilterClear.addEventListener("click", () => selectFlowNode(null));
elements.turnScopeToggle.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-scope]");
  if (!button) return;
  state.turnScope = button.dataset.scope;
  renderRoleTurns();
});
loadRuns();

async function loadRuns() {
  try {
    const payload = await requestJson("/api/runs");
    state.runs = payload.runs ?? [];
    if (!state.selectedRun || !state.runs.some((run) => run.directory_name === state.selectedRun)) {
      state.selectedRun = state.runs.find((run) => run.read_status === "readable")?.directory_name ?? null;
    }
    persistSelectedRun();
    renderRuns();
    await refreshSelectedRun();
  } catch (error) { elements.runList.replaceChildren(emptyState(`无法读取实验：${error.message}`)); }
}

async function selectRun(runName) {
  if (state.selectedRun !== runName) {
    state.selectedGeneration = null;
    state.selectedFlowNode = null;
    state.turnScope = "run";
  }
  state.selectedRun = runName;
  persistSelectedRun();
  renderRuns();
  await refreshSelectedRun();
}

async function refreshSelectedRun() {
  if (!state.selectedRun) { renderEmptyRun(); return; }
  const current = state.runs.find((run) => run.directory_name === state.selectedRun);
  if (current?.read_status !== "readable") { renderUnreadable(current); return; }
  try {
    const overview = await requestJson(runUrl("overview"));
    renderOverview(overview);
    await loadWorks();
    if (state.journalVisible) await loadJournal();
  } catch (error) { elements.summary.replaceChildren(emptyState(`无法读取 Run：${error.message}`)); }
}

async function loadWorks() {
  if (!state.selectedRun) return;
  const params = new URLSearchParams();
  if (elements.category.value) params.set("category", elements.category.value);
  if (elements.status.value) params.set("status", elements.status.value);
  if (state.selectedFlowNode) {
    params.set("node", state.selectedFlowNode);
    if (state.selectedGeneration != null) {
      params.set("generation", state.selectedGeneration);
    }
  }
  const suffix = params.size ? `?${params}` : "";
  try { const payload = await requestJson(`${runUrl("works")}${suffix}`); renderWorks(payload.works ?? []); }
  catch (error) { elements.workList.replaceChildren(emptyState(`无法读取进展：${error.message}`)); }
}

async function loadJournal() {
  const params = new URLSearchParams();
  if (state.selectedFlowNode) {
    params.set("node", state.selectedFlowNode);
    if (state.selectedGeneration != null) {
      params.set("generation", state.selectedGeneration);
    }
  }
  const suffix = params.size ? `?${params}` : "";
  try { const payload = await requestJson(`${runUrl("journal")}${suffix}`); renderJournal(payload.events ?? []); }
  catch (error) { elements.journalList.replaceChildren(emptyState(`无法读取 Journal：${error.message}`)); }
}

function renderRuns() {
  elements.runCount.textContent = String(state.runs.length);
  const fragment = document.createDocumentFragment();
  if (!state.runs.length) fragment.append(emptyState("目录下没有实验子目录。"));
  for (const run of state.runs) {
    const node = elements.runTemplate.content.firstElementChild.cloneNode(true);
    node.classList.toggle("is-selected", run.directory_name === state.selectedRun);
    node.querySelector(".run-name").textContent = run.directory_name;
    node.querySelector(".run-meta").textContent = `${run.read_status} · ${formatTimestamp(run.modified_at_utc)}`;
    node.querySelector(".run-error").textContent = run.error_summary ?? "";
    node.addEventListener("click", () => selectRun(run.directory_name)); fragment.append(node);
  }
  elements.runList.replaceChildren(fragment);
}

function renderOverview(overview) {
  state.overview = overview;
  const status = statusLabel(overview.journal_status);
  elements.summary.replaceChildren(summaryNode(overview, status));
  const generationFlows = overview.generation_flows ?? [];
  if (!generationFlows.some((item) => item.generation === state.selectedGeneration)) {
    state.selectedGeneration = generationFlows.at(-1)?.generation ?? overview.generation;
  }
  renderGenerationTabs();
  renderSelectedGenerationFlow();
  renderNodeFilter();
  renderStatistics(overview.statistics, overview);
}

function renderGenerationTabs() {
  const fragment = document.createDocumentFragment();
  for (const item of state.overview?.generation_flows ?? []) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `generation-tab status-${item.status}`;
    button.classList.toggle("is-selected", item.generation === state.selectedGeneration);
    button.textContent = `G${item.generation}`;
    button.title = `Generation ${item.generation} · ${generationStatusLabel(item.status)}`;
    button.addEventListener("click", () => selectGeneration(item.generation));
    fragment.append(button);
  }
  elements.generationTabs.replaceChildren(fragment);
}

async function selectGeneration(generation) {
  state.selectedGeneration = generation;
  renderGenerationTabs();
  renderSelectedGenerationFlow();
  renderNodeFilter();
  renderRoleTurns();
  await loadWorks();
  if (state.journalVisible) await loadJournal();
}

function renderSelectedGenerationFlow() {
  const selected = (state.overview?.generation_flows ?? []).find(
    (item) => item.generation === state.selectedGeneration,
  );
  window.CompactEvolutionFlowRenderer.render(
    elements.compactFlow,
    selected?.flow ?? state.overview?.flow ?? [],
    {
      hasNextGeneration: selected?.has_next_generation ?? false,
      selectedKind: state.selectedFlowNode,
      onSelectKind: selectFlowNode,
    },
  );
}

async function selectFlowNode(nodeKind) {
  state.selectedFlowNode = nodeKind === state.selectedFlowNode ? null : nodeKind;
  renderSelectedGenerationFlow();
  renderNodeFilter();
  await loadWorks();
  if (state.journalVisible) await loadJournal();
}

function renderNodeFilter() {
  const selected = (state.overview?.generation_flows ?? [])
    .find((item) => item.generation === state.selectedGeneration)
    ?.flow.find((node) => node.kind === state.selectedFlowNode);
  if (!selected) {
    elements.nodeFilterClear.classList.add("is-hidden");
    elements.nodeFilterClear.textContent = "";
    return;
  }
  elements.nodeFilterClear.textContent = `G${state.selectedGeneration} · ${selected.label} ×`;
  elements.nodeFilterClear.title = "清除节点筛选";
  elements.nodeFilterClear.classList.remove("is-hidden");
}

function renderStatistics(statistics, overview) {
  if (!statistics) return;
  const maxGenerations = overview.run_metadata?.control_config?.max_generations;
  elements.experimentStats.replaceChildren(
    metricStatNode("Current Generation", formatOptionalNumber(overview.generation)),
    metricStatNode("Max Generations", formatOptionalNumber(maxGenerations), maxGenerations == null),
    metricStatNode(
      "Work Items / Completed / Failed",
      [statistics.work_items, statistics.completed_work_items, statistics.failed_work_items]
        .map(formatNumber)
        .join(" / "),
      false,
      "metric-wide",
    ),
  );
  const recordedStageSeconds = Object.values(statistics.stage_time ?? {})
    .reduce((total, stage) => total + stage.seconds, 0);
  elements.timeStats.replaceChildren(
    metricStatNode("Total Time", formatDuration(statistics.elapsed_seconds)),
    metricStatNode("Time Per Generation", formatDuration(statistics.average_generation_seconds)),
    metricStatNode("Current Generation", formatDuration(statistics.current_generation_seconds)),
    metricStatNode("Recorded Work Time", formatDuration(recordedStageSeconds)),
  );

  const roleRows = statistics.role_breakdown ?? [];
  const roleTimeRows = statistics.role_time_breakdown ?? roleRows;
  renderDonut(elements.roleTimeDonut, roleTimeRows, "seconds");
  renderRoleTable(
    elements.roleTimeTable,
    roleTimeRows,
    "seconds",
    ["ROLE", "TIME", "WORK", "CALLS"],
    (row) => [
      row.label,
      `${formatDuration(row.seconds)} (${formatPercent(row.time_share)})`,
      formatNumber(row.work_count),
      row.kind === "evaluate_incumbent" ? "—" : formatOptionalNumber(row.calls),
    ],
  );
  renderDonut(elements.roleUsageDonut, roleRows, "tokens");
  renderRoleTable(
    elements.roleUsageTable,
    roleRows,
    "tokens",
    ["ROLE", "USAGE", "CACHED", "CALLS"],
    (row) => [
      row.label,
      `${formatNumber(row.tokens)} (${formatPercent(row.token_share)})`,
      formatOptionalPercent(row.cache_share),
      formatOptionalNumber(row.calls),
    ],
  );

  const tokens = statistics.token_sources ?? {};
  const calls = statistics.model_calls ?? {};
  const teacherCacheShare = tokens.teacher_role
    ? statistics.recorded_cached_tokens / tokens.teacher_role
    : null;
  elements.usageSummary.replaceChildren(
    usageGroup("Student Model", [
      ["Token Usage", tokens.student],
      ["Cached Token", null, "percent"],
      ["Model Calls", calls.student],
    ]),
    usageGroup("Teacher Role", [
      ["Token Usage", tokens.teacher_role],
      ["Cached Token", teacherCacheShare, "percent"],
      ["Model Calls", calls.teacher_role],
      ["Teacher Judge", tokens.teacher_judge],
    ]),
    usageGroup("Hook Model", [
      ["Token Usage", tokens.hook_model],
      ["Model Calls", calls.hook_model],
    ]),
  );

  const stageLabels = { evaluation: "评估", research: "研究", candidate: "候选构建" };
  elements.stageStats.replaceChildren(
    ...Object.entries(statistics.stage_time ?? {}).map(([name, value]) =>
      stageNode(stageLabels[name] ?? name, value.seconds, value.share),
    ),
  );
  renderRoleTurns();
  window.EvolutionMetricCharts.render(
    elements.evolutionMetrics,
    statistics.evolution_metrics ?? [],
  );
}

function renderRoleTurns() {
  const distribution = state.overview?.statistics?.role_turns;
  elements.generationScopeButton.textContent = `G${state.selectedGeneration ?? "—"}`;
  for (const button of elements.turnScopeToggle.querySelectorAll("button")) {
    button.classList.toggle("is-selected", button.dataset.scope === state.turnScope);
  }
  const rows = state.turnScope === "generation"
    ? distribution?.by_generation?.[String(state.selectedGeneration)] ?? []
    : distribution?.run ?? [];
  if (!rows.length) {
    elements.turnBoxplot.replaceChildren(emptyState("没有可用的角色回合记录。"));
    return;
  }
  const axisMaximum = Math.max(
    1,
    ...rows.map((row) => Math.max(row.maximum, row.turn_limit ?? 0)),
  );
  const roundedMaximum = Math.max(5, Math.ceil(axisMaximum / 5) * 5);
  const fragment = document.createDocumentFragment();
  fragment.append(boxplotAxis(roundedMaximum));
  for (const row of rows) fragment.append(boxplotRow(row, roundedMaximum));
  elements.turnBoxplot.replaceChildren(fragment);
}

function boxplotAxis(maximum) {
  const row = document.createElement("div"); row.className = "boxplot-axis-row";
  const scale = document.createElement("div"); scale.className = "boxplot-axis";
  for (const fraction of [0, .25, .5, .75, 1]) {
    const label = document.createElement("span");
    label.style.left = `${fraction * 100}%`;
    label.textContent = formatDecimal(maximum * fraction);
    scale.append(label);
  }
  row.append(document.createElement("span"), scale, document.createElement("span"));
  return row;
}

function boxplotRow(row, axisMaximum) {
  const line = document.createElement("div"); line.className = "boxplot-row";
  const label = document.createElement("span"); label.className = "boxplot-role"; label.textContent = row.label;
  const plot = document.createElement("div"); plot.className = "boxplot-track";
  const whisker = document.createElement("i"); whisker.className = "boxplot-whisker";
  whisker.style.left = `${row.minimum / axisMaximum * 100}%`;
  whisker.style.width = `${(row.maximum - row.minimum) / axisMaximum * 100}%`;
  const box = document.createElement("i"); box.className = "boxplot-box";
  box.style.left = `${row.q1 / axisMaximum * 100}%`;
  box.style.width = `${Math.max((row.q3 - row.q1) / axisMaximum * 100, .7)}%`;
  const median = boxplotMarker("boxplot-median", row.median, axisMaximum);
  const mean = boxplotMarker("boxplot-mean", row.mean, axisMaximum);
  plot.append(whisker, box, median, mean);
  if (row.turn_limit != null) {
    plot.append(boxplotMarker("boxplot-limit", row.turn_limit, axisMaximum));
  }
  plot.title = `${row.label}: min ${formatDecimal(row.minimum)}, Q1 ${formatDecimal(row.q1)}, median ${formatDecimal(row.median)}, mean ${formatDecimal(row.mean)}, Q3 ${formatDecimal(row.q3)}, max ${formatDecimal(row.maximum)}, limit ${row.turn_limit ?? "未记录"}`;
  const summary = document.createElement("span"); summary.className = "boxplot-summary";
  summary.textContent = `${formatDecimal(row.mean)} / ${row.turn_limit ?? "—"} · n${row.sample_count}`;
  line.append(label, plot, summary); return line;
}

function boxplotMarker(className, value, axisMaximum) {
  const marker = document.createElement("i"); marker.className = className;
  marker.style.left = `${value / axisMaximum * 100}%`; return marker;
}

function usageGroup(title, metrics) {
  const group = document.createElement("section"); group.className = "usage-group";
  const heading = document.createElement("h3"); heading.className = "dashboard-subheading"; heading.textContent = title;
  const grid = document.createElement("div"); grid.className = "dashboard-metric-grid usage-metric-grid";
  grid.replaceChildren(...metrics.map(([label, value, type]) =>
    metricStatNode(
      label,
      type === "percent" ? formatOptionalPercent(value) : formatOptionalNumber(value),
      value == null,
    ),
  ));
  group.append(heading, grid); return group;
}

function summaryNode(overview, status) {
  const wrapper = document.createElement("div");
  const title = document.createElement("h2"); title.textContent = overview.directory_name;
  const subtitle = document.createElement("p");
  subtitle.textContent = `Generation ${overview.generation ?? "—"} · 最近 Journal：${overview.last_event_at_utc ?? "未记录"}`;
  wrapper.append(title, subtitle);
  const stat = document.createElement("div"); stat.className = "summary-stat";
  stat.innerHTML = `<span class="status status-${overview.journal_status}">${status}</span><strong>${overview.completed_generation_count}</strong><span>已完成 Generation</span>`;
  const container = document.createElement("div"); container.className = "run-summary"; container.append(wrapper, stat); return container;
}

function renderWorks(works) {
  const fragment = document.createDocumentFragment();
  if (!works.length) fragment.append(emptyState("没有符合筛选条件的 WorkItem。"));
  for (const work of works) {
    const node = elements.workTemplate.content.firstElementChild.cloneNode(true);
    node.classList.add(`category-${work.category}`);
    const firstSequence = work.events[0]?.sequence;
    const lastSequence = work.events.at(-1)?.sequence;
    const number = node.querySelector(".work-number");
    number.textContent = firstSequence == null ? "#—" : `#${firstSequence}`;
    number.title = firstSequence == null
      ? "未记录 Journal sequence"
      : `Journal #${firstSequence}${lastSequence !== firstSequence ? `–#${lastSequence}` : ""}`;
    node.querySelector(".work-kind").textContent = work.kind;
    node.querySelector(".work-status").innerHTML = `<span class="status status-${work.status}">${statusLabel(work.status)}</span>`;
    node.querySelector(".work-time").textContent = work.ended_at_utc ?? work.started_at_utc ?? work.events.at(-1)?.created_at_utc ?? "未记录";
    node.querySelector(".work-heading").href = `/event.html?run=${encodeURIComponent(state.selectedRun)}&work=${encodeURIComponent(work.work_id)}`; fragment.append(node);
  }
  elements.workList.replaceChildren(fragment);
}

function renderJournal(events) {
  const fragment = document.createDocumentFragment();
  for (const event of events) { const node = elements.journalTemplate.content.firstElementChild.cloneNode(true); node.querySelector(".journal-event-heading").textContent = `#${event.sequence} · ${event.event_type} · ${event.created_at_utc}`; node.querySelector(".journal-event-content").textContent = JSON.stringify(event.payload, null, 2); fragment.append(node); }
  elements.journalList.replaceChildren(fragment);
}

function toggleJournal() { state.journalVisible = !state.journalVisible; elements.journalList.classList.toggle("is-hidden", !state.journalVisible); elements.workList.classList.toggle("is-hidden", state.journalVisible); elements.journalToggle.textContent = state.journalVisible ? "返回 WorkItem 视图" : "查看原始 Journal"; if (state.journalVisible) loadJournal(); }
function renderEmptyRun() { elements.summary.replaceChildren(emptyState("选择一个可读取的实验。")); elements.compactFlow.replaceChildren(); elements.workList.replaceChildren(); }
function renderUnreadable(run) { elements.summary.replaceChildren(emptyState(`${run?.directory_name ?? "实验"} 不可读取：${run?.error_summary ?? "未知错误"}`)); elements.compactFlow.replaceChildren(); elements.workList.replaceChildren(); }
function emptyState(message) { const node = document.createElement("div"); node.className = "empty-state"; node.textContent = message; return node; }
function metricStatNode(label, value, missing = false, className = "") {
  const node = document.createElement("div"); node.className = `stat-item ${className}`.trim();
  const number = document.createElement("strong"); number.textContent = value; number.classList.toggle("is-missing", missing);
  const caption = document.createElement("span"); caption.textContent = label;
  node.append(number, caption); return node;
}
const roleColors = {
  evaluate_incumbent: "#557f89",
  analyze_failure: "#6f8170",
  research_hypothesis: "#b49b54",
  execute_trial: "#8a8b87",
  review_evidence: "#bdc1c0",
  distill_mechanism: "#94a93d",
  compile_candidate: "#657c93",
  verify_conformance: "#b77a61",
  review_candidate: "#7e667b",
};
function renderDonut(container, rows, valueKey) {
  const ranked = [...rows].filter((row) => row[valueKey] > 0).sort((a, b) => b[valueKey] - a[valueKey]);
  const total = ranked.reduce((sum, row) => sum + row[valueKey], 0);
  if (!total) { container.style.background = "#dedbd2"; return; }
  let cursor = 0;
  const segments = ranked.map((row) => {
    const start = cursor; cursor += row[valueKey] / total * 100;
    return `${roleColors[row.kind] ?? "#8c8d88"} ${start}% ${cursor}%`;
  });
  container.style.background = `conic-gradient(${segments.join(", ")})`;
}
function renderRoleTable(container, rows, sortKey, headers, projectRow) {
  const ranked = [...rows].sort((a, b) => b[sortKey] - a[sortKey]);
  const fragment = document.createDocumentFragment();
  const header = document.createElement("div"); header.className = "breakdown-row breakdown-header";
  header.append(tableCell(""), ...headers.map(tableCell)); fragment.append(header);
  ranked.forEach((row, index) => {
    const line = document.createElement("div"); line.className = "breakdown-row";
    const roleValues = projectRow(row);
    const rank = tableCell(String(index + 1)); rank.classList.add("rank-cell");
    const role = tableCell(roleValues[0]); role.classList.add("role-cell");
    const dot = document.createElement("i"); dot.style.background = roleColors[row.kind] ?? "#8c8d88";
    role.prepend(dot);
    line.append(rank, role, ...roleValues.slice(1).map(tableCell)); fragment.append(line);
  });
  container.replaceChildren(fragment);
}
function tableCell(value) { const cell = document.createElement("span"); cell.textContent = value; return cell; }
function shareNode(label, share) {
  const row = document.createElement("div"); row.className = "share-row";
  const heading = document.createElement("div"); heading.className = "share-heading";
  const name = document.createElement("span"); name.textContent = label;
  const value = document.createElement("strong"); value.textContent = `${Math.round(share * 100)}%`;
  const track = document.createElement("div"); track.className = "share-track";
  const fill = document.createElement("span"); fill.className = "share-fill"; fill.style.width = `${share * 100}%`;
  heading.append(name, value); track.append(fill); row.append(heading, track); return row;
}
function stageNode(label, seconds, share) {
  const row = shareNode(label, share);
  row.classList.add("stage-row");
  row.querySelector(".share-heading strong").textContent = `${formatDuration(seconds)} · ${Math.round(share * 100)}%`;
  return row;
}
function statusLabel(status) { return ({ queued: "已排队", running: "运行中", completed: "已完成", failed: "失败", paused: "已暂停", not_reached: "未到达" })[status] ?? status; }
function generationStatusLabel(status) { return ({ accepted: "已接受", running: "运行中", paused: "已暂停", failed: "失败", incomplete: "未完成" })[status] ?? status; }
function formatNumber(value) { return new Intl.NumberFormat("zh-CN").format(value ?? 0); }
function formatDecimal(value) { return Number.isInteger(value) ? String(value) : value.toFixed(1); }
function formatOptionalNumber(value) { return value == null ? "未记录" : formatNumber(value); }
function formatPercent(value) { return `${Math.round((value ?? 0) * 100)}%`; }
function formatOptionalPercent(value) { return value == null ? "未记录" : formatPercent(value); }
function formatDuration(value) {
  if (value == null) return "未记录";
  const seconds = Math.max(0, Math.round(value));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m`;
  return `${seconds}s`;
}
function formatTimestamp(value) {
  if (!value) return "未记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}
function initialSelectedRun() {
  const queryRun = new URLSearchParams(location.search).get("run");
  if (queryRun) return queryRun;
  try { return sessionStorage.getItem(SELECTED_RUN_STORAGE_KEY); }
  catch { return null; }
}
function persistSelectedRun() {
  if (!state.selectedRun) return;
  try { sessionStorage.setItem(SELECTED_RUN_STORAGE_KEY, state.selectedRun); }
  catch { /* URL state remains available when storage is disabled. */ }
  const url = new URL(location.href);
  if (url.searchParams.get("run") === state.selectedRun) return;
  url.searchParams.set("run", state.selectedRun);
  history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}
function runUrl(endpoint) { return `/api/runs/${encodeURIComponent(state.selectedRun)}/${endpoint}`; }
async function requestJson(url) { const response = await fetch(url); const payload = await response.json(); if (!response.ok) throw new Error(payload.error ?? `请求失败 (${response.status})`); return payload; }
