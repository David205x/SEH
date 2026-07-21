const state = { reports: [], report: null, selectedReport: null, selectedItem: null };

const elements = {
  reportList: document.querySelector("#report-list"),
  reportCount: document.querySelector("#report-count"),
  itemList: document.querySelector("#evaluation-item-list"),
  itemCount: document.querySelector("#item-count"),
  reportTitle: document.querySelector("#report-title"),
  reportSubtitle: document.querySelector("#report-subtitle"),
  metrics: document.querySelector("#report-metrics"),
  detail: document.querySelector("#evaluation-detail"),
  reload: document.querySelector("#reload-reports"),
};

elements.reload.addEventListener("click", loadReports);
loadReports();

async function loadReports() {
  try {
    const payload = await requestJson("/api/reports");
    state.reports = payload.reports ?? [];
    renderReports();
    if (state.selectedReport && state.reports.some((item) => item.path === state.selectedReport)) {
      await loadReport(state.selectedReport);
    }
  } catch (error) {
    elements.reportList.textContent = `Could not load reports: ${error.message}`;
  }
}

async function loadReport(path) {
  state.selectedReport = path;
  state.selectedItem = null;
  renderReports();
  const payload = await requestJson(`/api/report?path=${encodeURIComponent(path)}`);
  state.report = payload;
  elements.reportTitle.textContent = path;
  elements.reportSubtitle.textContent = `${payload.items.length} evaluated examples`;
  elements.metrics.textContent = JSON.stringify(payload.summary.metrics, null, 2);
  renderItems();
  if (payload.items.length) selectItem(0);
}

function renderReports() {
  elements.reportCount.textContent = String(state.reports.length);
  elements.reportList.replaceChildren(...state.reports.map((report) => {
    const button = document.createElement("button");
    button.className = "file-item";
    button.classList.toggle("selected", report.path === state.selectedReport);
    button.textContent = report.path;
    button.addEventListener("click", () => loadReport(report.path));
    return button;
  }));
}

function renderItems() {
  const items = state.report?.items ?? [];
  elements.itemCount.textContent = String(items.length);
  elements.itemList.replaceChildren(...items.map((item, index) => {
    const button = document.createElement("button");
    button.className = "evaluation-item";
    button.classList.toggle("selected", index === state.selectedItem);
    const score = item.score === null ? "unresolved" : String(item.score);
    button.textContent = `${score} · ${item.example_id}`;
    button.addEventListener("click", () => selectItem(index));
    return button;
  }));
}

function selectItem(index) {
  state.selectedItem = index;
  renderItems();
  const item = state.report?.items[index];
  if (!item) return;
  elements.detail.textContent = JSON.stringify({
    question: item.question,
    golden_answer: item.golden_answer,
    predicted_answer: item.predicted_answer,
    score: item.score,
    score_source: item.score_source,
    static: item.static,
    teacher: item.teacher,
    execution: item.execution,
  }, null, 2);
}

async function requestJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error ?? "Request failed");
  return payload;
}
