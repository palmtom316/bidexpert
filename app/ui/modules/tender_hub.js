const TenderHub = {
  categoryNameMap: {
    BIDDING_POINTS: "投标响应要点",
    SCORING_POINTS: "评分要点",
    COMPLIANCE_REQUIREMENTS: "必须满足项",
    BONUS_POINTS: "加分项",
    RISK_ALERTS: "风险警示",
  },

  init() {
    $("#btnTenderAnalyze").addEventListener("click", guarded(() => this.analyzePdf()));
    $("#btnTenderRuns").addEventListener("click", guarded(() => this.loadRuns()));
    $("#btnTenderDetail").addEventListener("click", guarded(() => {
      const runId = $("#analysisRunSelect").value;
      if (!runId) {
        Toast.error("请先选择分析记录");
        return;
      }
      return this.loadDetail(runId);
    }));

    guarded(() => this.loadRuns())();
  },

  async analyzePdf() {
    const file = $("#analysisPdfFile").files[0];
    if (!file) {
      Toast.error("请选择招标文件 PDF");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    if (state.projectId.trim()) formData.append("project_id", state.projectId.trim());

    setTaskStatus("招标文件分析中");
    $("#tenderAnalyzeResult").textContent = "正在分析，请稍候...";

    const res = await api("/v1/tender/analyze-upload", {
      method: "POST",
      body: formData,
    });

    state.analysisRunId = res.run_id;
    $("#tenderAnalyzeResult").textContent = JSON.stringify(res, null, 2);
    setTaskStatus("招标文件分析完成");
    Toast.success("招标文件拆解完成");

    await this.loadRuns();
    await this.loadDetail(res.run_id);
  },

  async loadRuns() {
    const params = new URLSearchParams({ limit: "50" });
    const project = state.projectId.trim();
    if (project) params.set("project_id", project);

    const res = await api(`/v1/tender/analysis-runs?${params.toString()}`);
    const select = $("#analysisRunSelect");
    select.innerHTML = "";

    if (!res.items.length) {
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "暂无记录";
      select.appendChild(empty);
      return;
    }

    res.items.forEach((run) => {
      const opt = document.createElement("option");
      opt.value = run.run_id;
      opt.textContent = `${run.filename} | ${new Date(run.created_at).toLocaleString("zh-CN")}`;
      if (run.run_id === state.analysisRunId) opt.selected = true;
      select.appendChild(opt);
    });
  },

  async loadDetail(runId) {
    setTaskStatus("加载招标分析详情");
    const detail = await api(`/v1/tender/analysis-runs/${runId}`);
    state.analysisDetail = detail;
    state.analysisRunId = runId;
    this.renderDetail(detail);
    setTaskStatus("招标分析详情已加载");
  },

  renderDetail(detail) {
    const summary = detail.summary || {};
    const categoryCounts = summary.category_counts || {};

    const cards = [
      { k: "总要点", v: summary.total_items || 0 },
      { k: "关键章节", v: (summary.key_sections || []).length },
      { k: "告警数", v: (summary.warnings || []).length },
    ];

    Object.entries(categoryCounts).forEach(([k, v]) => {
      cards.push({ k: this.categoryNameMap[k] || k, v });
    });

    $("#tenderSummaryCards").innerHTML = cards
      .map(
        (item) => `
        <div class="summary-card">
          <div class="k">${escapeHtml(String(item.k))}</div>
          <div class="v">${escapeHtml(String(item.v))}</div>
        </div>
      `,
      )
      .join("");

    const grouped = new Map();
    (detail.key_infos || []).forEach((item) => {
      const key = item.category || "OTHER";
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(item);
    });

    if (!grouped.size) {
      $("#tenderPointsBoard").innerHTML = `<p class="hint">未检测到结构化要点，请人工补充。</p>`;
    } else {
      $("#tenderPointsBoard").innerHTML = [...grouped.entries()]
        .map(([category, items]) => {
          const lines = items
            .slice(0, 12)
            .map((item) => {
              const tag = item.is_must ? "[必须] " : "";
              return `<li>${tag}${escapeHtml(item.content)}</li>`;
            })
            .join("");
          return `
            <section class="points-group">
              <h4>${escapeHtml(this.categoryNameMap[category] || category)} (${items.length})</h4>
              <ul>${lines}</ul>
            </section>
          `;
        })
        .join("");
    }

    const pointText = this.buildPointText(detail);
    $("#tenderPointsText").value = pointText;
  },

  buildPointText(detail) {
    const items = detail.key_infos || [];
    if (!items.length) return "";

    const mustItems = items.filter((item) => item.is_must).map((item) => `- 必须响应：${item.content}`);
    const scoringItems = items
      .filter((item) => item.category === "SCORING_POINTS" || item.category === "BONUS_POINTS")
      .map((item) => `- 评分关注：${item.content}`);
    const riskItems = items
      .filter((item) => item.category === "RISK_ALERTS")
      .map((item) => `- 风险规避：${item.content}`);
    const biddingItems = items
      .filter((item) => item.category === "BIDDING_POINTS")
      .slice(0, 16)
      .map((item) => `- 编写重点：${item.content}`);

    const result = [
      "【投标要点总览】",
      ...mustItems,
      ...scoringItems,
      ...riskItems,
      ...biddingItems,
    ]
      .filter(Boolean)
      .join("\n");

    return result;
  },
};
