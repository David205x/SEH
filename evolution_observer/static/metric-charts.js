(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const CHARTS = [
    {
      title: "Student 平均回合数",
      unit: "turns",
      series: [
        { key: "mean_turns", label: "平均回合", color: "#657d73" },
      ],
    },
    {
      title: "Student Token 长度",
      unit: "tokens",
      series: [
        { key: "token_minimum", label: "最小值", color: "#8a9b99" },
        { key: "token_mean", label: "平均值", color: "#b48b4f" },
        { key: "token_maximum", label: "最大值", color: "#c57668" },
      ],
    },
    {
      title: "正确率",
      unit: "percent",
      series: [
        { key: "matching_accuracy", label: "匹配正确率", color: "#7f9b76" },
        { key: "teacher_judge_accuracy", label: "Teacher Judge", color: "#c57668" },
      ],
    },
    {
      title: "稳定性",
      unit: "percent",
      series: [
        { key: "stability", label: "答案一致性", color: "#817488" },
      ],
    },
  ];

  function render(container, points) {
    if (!Array.isArray(points) || !points.length) {
      container.replaceChildren(emptyState("没有可比较的 Generation 指标。"));
      return;
    }
    container.replaceChildren(...CHARTS.map((chart) => chartCard(chart, points)));
  }

  function chartCard(chart, points) {
    const card = document.createElement("article");
    card.className = "metric-chart-card";
    const header = document.createElement("div");
    header.className = "metric-chart-header";
    const title = document.createElement("h3");
    title.textContent = chart.title;
    const legend = document.createElement("div");
    legend.className = "metric-chart-legend";
    legend.append(...chart.series.map(legendItem));
    header.append(title, legend);
    const svg = chartSvg(chart, points);
    const source = document.createElement("p");
    source.className = "metric-chart-source";
    source.textContent = points.map((point) =>
      `G${point.generation} ${point.source === "candidate" ? "Candidate" : "Incumbent"}`,
    ).join(" · ");
    card.append(header, svg, source);
    return card;
  }

  function legendItem(series) {
    const item = document.createElement("span");
    const dot = document.createElement("i");
    dot.style.background = series.color;
    item.append(dot, document.createTextNode(series.label));
    return item;
  }

  function chartSvg(chart, points) {
    const width = 420;
    const height = 176;
    const plot = { left: 42, top: 14, right: 12, bottom: 28 };
    const plotWidth = width - plot.left - plot.right;
    const plotHeight = height - plot.top - plot.bottom;
    const maximum = axisMaximum(chart, points);
    const svg = createSvg("svg", {
      class: "metric-line-chart",
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-label": `${chart.title}随 Generation 的变化`,
    });

    for (const fraction of [0, .25, .5, .75, 1]) {
      const y = plot.top + plotHeight * (1 - fraction);
      svg.append(createSvg("line", {
        class: "metric-grid-line",
        x1: plot.left,
        x2: width - plot.right,
        y1: y,
        y2: y,
      }));
      const label = createSvg("text", {
        class: "metric-axis-label",
        x: plot.left - 7,
        y: y + 3,
        "text-anchor": "end",
      });
      label.textContent = formatAxis(maximum * fraction, chart.unit);
      svg.append(label);
    }

    const xCoordinates = points.map((_, index) =>
      points.length === 1
        ? plot.left + plotWidth / 2
        : plot.left + plotWidth * index / (points.length - 1),
    );
    for (const [index, point] of points.entries()) {
      const label = createSvg("text", {
        class: "metric-axis-label metric-generation-label",
        x: xCoordinates[index],
        y: height - 8,
        "text-anchor": "middle",
      });
      label.textContent = `G${point.generation}`;
      svg.append(label);
    }

    for (const series of chart.series) {
      const coordinates = points.map((point, index) => {
        const value = numeric(point[series.key]);
        if (value == null) return null;
        return {
          generation: point.generation,
          value,
          x: xCoordinates[index],
          y: plot.top + plotHeight * (1 - value / maximum),
        };
      });
      appendSeries(svg, coordinates, series, chart.unit);
    }
    return svg;
  }

  function appendSeries(svg, coordinates, series, unit) {
    let segment = [];
    const flush = () => {
      if (!segment.length) return;
      const path = createSvg("path", {
        class: "metric-series-line",
        d: segment.map((point, index) =>
          `${index ? "L" : "M"} ${point.x} ${point.y}`,
        ).join(" "),
        stroke: series.color,
      });
      svg.append(path);
      segment = [];
    };
    for (const point of coordinates) {
      if (point == null) {
        flush();
        continue;
      }
      segment.push(point);
    }
    flush();
    for (const point of coordinates.filter(Boolean)) {
      const marker = createSvg("circle", {
        class: "metric-series-point",
        cx: point.x,
        cy: point.y,
        r: 4,
        fill: series.color,
      });
      const title = createSvg("title", {});
      title.textContent = `G${point.generation} · ${series.label}: ${formatValue(point.value, unit)}`;
      marker.append(title);
      svg.append(marker);
    }
  }

  function axisMaximum(chart, points) {
    if (chart.unit === "percent") return 1;
    const values = chart.series.flatMap((series) =>
      points.map((point) => numeric(point[series.key])).filter((value) => value != null),
    );
    const maximum = Math.max(1, ...values);
    if (chart.unit === "tokens") return niceMaximum(maximum);
    return Math.max(5, Math.ceil(maximum));
  }

  function niceMaximum(value) {
    const magnitude = 10 ** Math.floor(Math.log10(value));
    return Math.ceil(value / magnitude) * magnitude;
  }

  function formatAxis(value, unit) {
    if (unit === "percent") return `${Math.round(value * 100)}%`;
    if (unit === "tokens" && value >= 1000) return `${Math.round(value / 1000)}k`;
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
  }

  function formatValue(value, unit) {
    if (unit === "percent") return `${(value * 100).toFixed(1)}%`;
    if (unit === "tokens") return new Intl.NumberFormat("zh-CN").format(Math.round(value));
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }

  function numeric(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  }

  function createSvg(name, attributes) {
    const element = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attributes)) {
      element.setAttribute(key, value);
    }
    return element;
  }

  function emptyState(message) {
    const node = document.createElement("div");
    node.className = "empty-state";
    node.textContent = message;
    return node;
  }

  window.EvolutionMetricCharts = { render };
})();
