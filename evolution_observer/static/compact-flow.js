(function () {
  "use strict";

  const mainLoop = [
    station("promote_candidate", "Promotion", 235, 100, -2.5, -85, 170),
    station("evaluate_incumbent", "Incumbent Evaluation", 400, 100, -2.5, 30, 220),
    station("analyze_failure", "Failure Analyst", 650, 100, -2.5, -85, 190),
    station("research_hypothesis", "Hypothesis Researcher", 750, 220, -2.5, -85, 240),
    station("review_evidence", "Evidence Reviewer", 750, 440, -2.5, 30, 210),
    station("distill_mechanism", "Mechanism Distiller", 650, 575, -2.5, 30, 220),
    station("compile_candidate", "Mechanism Compiler", 425, 575, -2.5, -85, 220),
    station("verify_conformance", "Conformance Reviewer", 220, 575, -2.5, 30, 240),
    station("evaluate_candidate", "Candidate Evaluation", 100, 440, 25, -80, 215),
    station("review_candidate", "Candidate Reviewer", 100, 220, 25, 20, 215),
  ];

  const branches = [
    station("execute_trial", "Intervention", 825, 275, 25, -25, 155, true),
    station("trial_reviewer", "Trial Reviewer", 825, 390, 25, -25, 160, true),
    station("stage_candidate", "Candidate Validation", 320, 510, -2.5, -85, 220, true),
  ];

  const mainEdges = mainLoop.map((item, index) => [item.kind, mainLoop[(index + 1) % mainLoop.length].kind]);
  const branchEdges = [
    ["research_hypothesis", "execute_trial"],
    ["execute_trial", "trial_reviewer"],
    ["trial_reviewer", "review_evidence"],
    ["compile_candidate", "stage_candidate"],
    ["stage_candidate", "verify_conformance"],
  ];

  function render(container, nodeStates, options = {}) {
    const states = new Map(nodeStates.map((item) => [item.kind, item]));
    const allStations = [...mainLoop, ...branches];
    const points = new Map(allStations.map((item) => [item.kind, item]));
    const svg = create("svg", {
      viewBox: "0 0 1100 800",
      class: "compact-evolution-svg",
      role: "img",
      "aria-label": "Square evolution role loop",
    });

    const lines = create("g", { class: "compact-lines" });
    for (const [source, target] of [...mainEdges, ...branchEdges]) {
      const from = points.get(source); const to = points.get(target);
      const isBranch = branchEdges.some((edge) => edge[0] === source && edge[1] === target);
      const active = isEdgeActive(source, target, states, options);
      lines.append(create("line", {
        x1: from.x, y1: from.y, x2: to.x, y2: to.y,
        class: `compact-line${isBranch ? " is-branch" : ""}${active ? " is-active" : ""}`,
      }));
    }
    svg.append(lines);

    const stopGroup = create("g", { class: "compact-stops" });
    for (const item of allStations) {
      const state = states.get(item.kind) ?? { status: "not_reached", count: 0 };
      const selected = options.selectedKind === item.kind;
      const group = create("g", {
        class: `compact-stop status-${state.status}${item.branch ? " is-branch" : ""}${selected ? " is-selected" : ""}`,
        role: "button",
        tabindex: "0",
        focusable: "true",
        "aria-label": `筛选 ${item.label} 相关事件`,
        "aria-pressed": selected ? "true" : "false",
      });
      group.append(create("circle", { cx: item.x, cy: item.y, r: item.branch ? 23 : 28, class: "station-halo" }));
      if (state.budget) group.append(...budgetRing(item, state.budget));
      group.append(create("circle", { cx: item.x, cy: item.y, r: item.branch ? 13 : 17, class: "station-ring" }));
      group.append(create("circle", { cx: item.x, cy: item.y, r: item.branch ? 6 : 8, class: "station-core" }));
      group.append(labelGroup(item, state));
      if (state.budget) {
        const title = create("title", {});
        title.textContent = `${state.budget.label}: ${state.budget.used} / ${state.budget.limit} (${Math.round(state.budget.share * 100)}%)`;
        group.append(title);
      }
      group.addEventListener("click", () => options.onSelectKind?.(item.kind));
      group.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        options.onSelectKind?.(item.kind);
      });
      stopGroup.append(group);
    }
    svg.append(stopGroup);
    container.replaceChildren(svg);
  }

  function labelGroup(item, state) {
    const group = create("g", { class: "station-label" });
    const labelX = item.x + item.labelOffsetX;
    const labelY = item.y + item.labelOffsetY;
    group.append(create("rect", { x: labelX, y: labelY, width: item.labelWidth, height: 54, class: "station-label-bg" }));
    group.append(create("rect", { x: labelX, y: labelY, width: 7, height: 54, class: "station-label-rule" }));
    const title = create("text", { x: labelX + 17, y: labelY + 23, class: "compact-stop-title" });
    title.textContent = item.label;
    const detail = create("text", { x: labelX + 17, y: labelY + 43, class: "compact-stop-detail" });
    const statusDetail = state.status === "not_reached" ? "未激活" : `${statusLabel(state.status)} · ${state.count}`;
    const budgetDetail = state.budget ? ` · ${Math.round(state.budget.share * 100)}%` : "";
    detail.textContent = `${statusDetail}${budgetDetail}`;
    group.append(title, detail);
    return group;
  }

  // Label offsets are relative to the station center: +X moves right, +Y moves down.
  function station(kind, label, x, y, labelOffsetX, labelOffsetY, labelWidth, branch = false) {
    return { kind, label, x, y, labelOffsetX, labelOffsetY, labelWidth, branch };
  }

  function budgetRing(item, budget) {
    const radius = item.branch ? 19 : 24;
    const circumference = 2 * Math.PI * radius;
    const common = { cx: item.x, cy: item.y, r: radius };
    return [
      create("circle", { ...common, class: "route-budget-track" }),
      create("circle", {
        ...common,
        class: `route-budget-progress${budget.exhausted ? " is-exhausted" : ""}`,
        "stroke-dasharray": `${circumference * budget.share} ${circumference}`,
        transform: `rotate(-90 ${item.x} ${item.y})`,
      }),
    ];
  }

  function isActive(state) { return state && state.status !== "not_reached"; }
  function isEdgeActive(source, target, states, options) {
    const sourceState = states.get(source);
    const targetState = states.get(target);
    if (source === "promote_candidate" && target === "evaluate_incumbent") {
      return sourceState?.status === "completed" && options.hasNextGeneration;
    }
    return isActive(sourceState) && isActive(targetState);
  }
  function create(name, attributes) { const value = document.createElementNS("http://www.w3.org/2000/svg", name); for (const [key, item] of Object.entries(attributes)) value.setAttribute(key, item); return value; }
  function statusLabel(status) { return ({ queued: "已排队", running: "运行中", completed: "已完成", failed: "失败" })[status] ?? status; }
  window.CompactEvolutionFlowRenderer = { render };
}());
