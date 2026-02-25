const TenderHub = {
  categoryNameMap: {
    BIDDING_POINTS: "投标响应要点",
    SCORING_POINTS: "评分要点",
    COMPLIANCE_REQUIREMENTS: "必须满足项",
    BONUS_POINTS: "加分项",
    RISK_ALERTS: "风险警示",
  },

  // Pipeline step labels (ordered)
  pipelineSteps: [
    "RECEIVED", "UNPACKED", "VALIDATED", "SECTIONIZED",
    "PRELIM_EXTRACTED", "FATAL_GATE_CHECKED",
    "SCORING_EXTRACTED", "TECH_EXTRACTED",
    "DEVIATION_BUILT", "FORMAT_SIGNATURE_EXTRACTED",
    "BLUEPRINT_BUILT", "READY_FOR_WRITING",
  ],

  _pollTimer: null,

  init() {
    // v1.0 buttons
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

    // v1.1 buttons
    $("#btnTenderImportZip").addEventListener("click", guarded(() => this.importZip()));
    $("#btnRefreshImportRuns").addEventListener("click", guarded(() => this.loadImportRuns()));
    $("#btnLoadImportDetail").addEventListener("click", guarded(() => {
      const runId = $("#importRunSelect").value;
      if (!runId) {
        Toast.error("请先选择导入记录");
        return;
      }
      return this.loadImportDetail(runId);
    }));
    $("#btnGoToWriting").addEventListener("click", () => {
      document.querySelector('[data-target="panel-bid-hub"]').click();
    });

    guarded(() => this.loadRuns())();
    guarded(() => this.loadImportRuns())();
  },

  // ── v1.0: PDF analysis (unchanged) ──────────────────────────

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

  // ── v1.1: Zip import + pipeline UI ──────────────────────────

  async importZip() {
    const file = $("#tenderZipFile").files[0];
    if (!file) {
      Toast.error("请选择 .tender.zip 文件");
      return;
    }
    if (!file.name.endsWith(".zip")) {
      Toast.error("文件必须是 .zip 格式");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    if (state.projectId.trim()) formData.append("project_id", state.projectId.trim());

    setTaskStatus("导入招标 Zip 包中");

    try {
      const res = await api("/v1/tender/import-zip", {
        method: "POST",
        body: formData,
      });

      state.importRunId = res.run_id;
      Toast.success(`导入已启动: ${res.tender_id}`);
      setTaskStatus("招标导入流水线已启动");

      await this.loadImportRuns();
      this.startPolling(res.run_id);
    } catch (err) {
      Toast.error(`导入失败: ${err.message || err}`);
      setTaskStatus("导入失败");
    }
  },

  async loadImportRuns() {
    const params = new URLSearchParams({ limit: "50" });
    const project = state.projectId.trim();
    if (project) params.set("project_id", project);

    try {
      const res = await api(`/v1/tender/import-runs?${params.toString()}`);
      const select = $("#importRunSelect");
      select.innerHTML = "";

      if (!res.items.length) {
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = "暂无导入记录";
        select.appendChild(empty);
        return;
      }

      res.items.forEach((run) => {
        const opt = document.createElement("option");
        opt.value = run.run_id;
        const step = run.current_step || "RECEIVED";
        opt.textContent = `${run.filename} | ${step} | ${new Date(run.created_at).toLocaleString("zh-CN")}`;
        if (run.run_id === state.importRunId) opt.selected = true;
        select.appendChild(opt);
      });
    } catch {
      // Silently fail on initial load if endpoint not available
    }
  },

  async loadImportDetail(runId) {
    setTaskStatus("加载导入详情");
    try {
      const detail = await api(`/v1/tender/import-runs/${runId}`);
      state.importRunId = runId;
      this.renderImportDetail(detail);
      setTaskStatus("导入详情已加载");
    } catch (err) {
      Toast.error(`加载失败: ${err.message || err}`);
    }
  },

  renderImportDetail(detail) {
    const run = detail.run || {};
    const currentStep = run.current_step || "RECEIVED";
    const derivedFiles = detail.derived_files || [];

    // Update pipeline progress bar
    this.updatePipelineProgress(currentStep);

    // Show/hide FATAL_BLOCKED alert
    const fatalAlert = $("#fatalBlockedAlert");
    const readyBanner = $("#readyForWritingBanner");

    if (currentStep === "FATAL_BLOCKED") {
      fatalAlert.style.display = "block";
      readyBanner.style.display = "none";
      const reasons = (run.fatal_blocked_reason || {}).reasons || [];
      $("#fatalReasonList").innerHTML = reasons
        .map((r) => `<li>${escapeHtml(r)}</li>`)
        .join("");
    } else if (currentStep === "READY_FOR_WRITING") {
      fatalAlert.style.display = "none";
      readyBanner.style.display = "block";
    } else {
      fatalAlert.style.display = "none";
      readyBanner.style.display = "none";
    }

    // Show derived files
    if (derivedFiles.length > 0) {
      $("#derivedFilesPanel").style.display = "block";
      const tenderId = run.tender_id || "";
      $("#derivedFileList").innerHTML = derivedFiles
        .map((f) => `<li><a href="/v1/tender/${encodeURIComponent(tenderId)}/derived/${encodeURIComponent(f)}" target="_blank"><i class="ri-file-text-line"></i> ${escapeHtml(f)}</a></li>`)
        .join("");
    } else {
      $("#derivedFilesPanel").style.display = "none";
    }
  },

  updatePipelineProgress(currentStep) {
    const container = $("#pipelineProgress");
    container.style.display = "block";

    const stepIdx = this.pipelineSteps.indexOf(currentStep);
    const isBlocked = currentStep === "FATAL_BLOCKED";
    const isFailed = currentStep === "FAILED";

    container.querySelectorAll(".step-chip").forEach((chip) => {
      const step = chip.dataset.step;
      const idx = this.pipelineSteps.indexOf(step);

      chip.classList.remove("done", "active", "blocked");

      if (isBlocked && step === "FATAL_GATE_CHECKED") {
        chip.classList.add("blocked");
      } else if (idx < stepIdx) {
        chip.classList.add("done");
      } else if (idx === stepIdx) {
        chip.classList.add(isFailed ? "blocked" : "active");
      }
    });
  },

  startPolling(runId) {
    if (this._pollTimer) clearInterval(this._pollTimer);

    this._pollTimer = setInterval(async () => {
      try {
        const detail = await api(`/v1/tender/import-runs/${runId}`);
        this.renderImportDetail(detail);

        const step = (detail.run || {}).current_step || "";
        // Stop polling on terminal states
        if (["READY_FOR_WRITING", "FATAL_BLOCKED", "FAILED"].includes(step)) {
          clearInterval(this._pollTimer);
          this._pollTimer = null;
          await this.loadImportRuns();

          if (step === "READY_FOR_WRITING") {
            Toast.success("招标文件分析完成，可进入编制阶段");
          } else if (step === "FATAL_BLOCKED") {
            Toast.error("初审不通过 — 存在废标风险");
          } else {
            Toast.error("流水线执行失败");
          }
        }
      } catch {
        // Ignore polling errors
      }
    }, 3000);
  },

  pollImportStatus(runId) {
    return this.startPolling(runId);
  },
};
