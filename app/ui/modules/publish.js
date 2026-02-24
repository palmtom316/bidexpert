const PublishHub = {
  init() {
    $("#btnRenderWord").addEventListener("click", guarded(() => this.renderWord()));
    $("#btnFinalCheck").addEventListener("click", guarded(() => this.runFinalCheck()));
    $("#btnLockDelivery").addEventListener("click", guarded(() => this.lockDelivery()));
    this.bindCoverOptions();
  },

  bindCoverOptions() {
    $$("#coverTemplateOptions .cover-option").forEach((node) => {
      node.addEventListener("click", () => {
        $$("#coverTemplateOptions .cover-option").forEach((opt) => opt.classList.remove("active"));
        node.classList.add("active");
        state.coverTemplate = node.dataset.coverTemplate || "none";
      });
    });
  },

  collectTypesetConfig() {
    const parseNumber = (id, fallback = 0) => {
      const raw = Number.parseFloat($(id)?.value ?? "");
      return Number.isFinite(raw) ? raw : fallback;
    };

    const page = {
      coverTemplate: state.coverTemplate || "none",
      headerText: $("#typesetHeaderText")?.value?.trim() || "",
      headerOffset: parseNumber("#typesetHeaderOffset", 1.5),
      footerText: $("#typesetFooterText")?.value?.trim() || "",
      footerOffset: parseNumber("#typesetFooterOffset", 0),
      marginTop: parseNumber("#typesetMarginTop", 2.54),
      marginBottom: parseNumber("#typesetMarginBottom", 2.54),
      marginLeft: parseNumber("#typesetMarginLeft", 3.17),
      marginRight: parseNumber("#typesetMarginRight", 3.17),
    };

    const generateTOC = $("#typesetGenerateTOC")?.checked ?? false;

    const styles = Array.from(document.querySelectorAll("#typesetTable .typeset-row[data-style-key]")).map((row) => ({
      key: row.dataset.styleKey || "",
      font: row.querySelector(".fmt-font")?.value || "",
      size: row.querySelector(".fmt-size")?.value || "",
      align: row.querySelector(".fmt-align")?.value || "",
      bold: Boolean(row.querySelector(".fmt-bold")?.checked),
      italic: Boolean(row.querySelector(".fmt-italic")?.checked),
      lineMode: row.querySelector(".fmt-line-mode")?.value || "",
      lineValue: Number.parseFloat(row.querySelector(".fmt-line-value")?.value || "0") || 0,
      indent: Number.parseInt(row.querySelector(".fmt-indent")?.value || "0", 10) || 0,
    }));

    return { page, styles, generateTOC };
  },

  buildTypesetSummary(config) {
    const page = config.page;
    const tocLine = config.generateTOC ? " | 已启用目录生成" : "";
    const pageLine = `封面=${page.coverTemplate} | 页眉="${page.headerText}"(${page.headerOffset}cm) | 页边距 上${page.marginTop}/下${page.marginBottom}/左${page.marginLeft}/右${page.marginRight} cm${tocLine}`;
    const styleLine = config.styles
      .map((item) => `${item.key}:${item.font}/${item.size}/${item.align}/${item.lineMode}${item.lineValue}/首行${item.indent}`)
      .join("；");
    return `【排版配置】\n${pageLine}\n【段落样式】\n${styleLine}`;
  },

  async renderWord() {
    const finalDraft = $("#publishFinalDraft").value.trim();
    if (!finalDraft) {
      Toast.error("请先形成最终稿并同步到排版区");
      return;
    }

    const filename = normalizeOutputName($("#exportFileName").value);
    const typesetConfig = this.collectTypesetConfig();
    const formatLine = this.buildTypesetSummary(typesetConfig);
    const middle = Math.ceil(finalDraft.length / 2);
    const technicalPlan = `${formatLine}\n\n${finalDraft.slice(0, middle)}`;
    const implementationPlan = finalDraft.slice(middle);

    setTaskStatus("排版导出中");
    $("#renderResult").textContent = "正在生成 docx，请稍候...";

    const res = await api("/v1/render/word", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        output_path: filename,
        style_config: typesetConfig, // Send style config
        placeholders: {
          project_name: state.projectId || "未命名项目",
          technical_plan: technicalPlan,
          implementation_plan: implementationPlan,
        },
      }),
    });

    $("#renderResult").textContent = `导出完成：${res.output_path}`;
    setTaskStatus("排版导出完成");
    Toast.success("排版稿已生成");
  },

  async runFinalCheck() {
    const finalDraft = $("#publishFinalDraft").value.trim();
    if (!finalDraft) {
      Toast.error("终审前请先准备最终稿");
      return;
    }

    setTaskStatus("终审检查中");

    const pricing = await api("/v1/policy/pricing-fuse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: finalDraft }),
    });

    const mustItems = (state.analysisDetail?.key_infos || []).filter((item) => item.is_must);
    const matchedMust = mustItems.filter((item) => {
      const key = shortText(item.content, 24).replace(/[\s。；，,]/g, "");
      return key && finalDraft.replace(/\s/g, "").includes(key);
    }).length;

    const mustRatio = mustItems.length ? matchedMust / mustItems.length : 1;
    const confirmed = state.sections.filter((section) => section.status === "SECTION_CONFIRMED").length;
    const sectionReady = state.sections.length ? confirmed / state.sections.length : 0;
    const typesetConfig = this.collectTypesetConfig();
    const typesetReady =
      Boolean(typesetConfig.page.headerText) &&
      Boolean(typesetConfig.page.footerText) &&
      typesetConfig.styles.length >= 4;

    state.finalCheck = {
      pricingBlocked: Boolean(pricing.blocked),
      pricingReasons: pricing.reasons || [],
      mustTotal: mustItems.length,
      mustMatched: matchedMust,
      mustRatio,
      sectionConfirmed: confirmed,
      sectionTotal: state.sections.length,
      sectionReady,
      typesetReady,
    };

    this.renderFinalCheck();
    setTaskStatus("终审检查完成");
    Toast.success("终审检查已完成");
  },

  renderFinalCheck() {
    const board = $("#finalCheckBoard");
    const check = state.finalCheck;
    if (!check) {
      board.innerHTML = `<p class="hint">执行终审后显示符合性结果。</p>`;
      return;
    }

    board.innerHTML = `
      <div class="review-line"><span>报价内容合规</span><strong>${check.pricingBlocked ? "未通过" : "通过"}</strong></div>
      <div class="review-line"><span>必须项覆盖</span><strong>${check.mustMatched}/${check.mustTotal} (${(check.mustRatio * 100).toFixed(1)}%)</strong></div>
      <div class="review-line"><span>章节确认完成度</span><strong>${check.sectionConfirmed}/${check.sectionTotal} (${(check.sectionReady * 100).toFixed(1)}%)</strong></div>
      <div class="review-line"><span>排版配置完整度</span><strong>${check.typesetReady ? "通过" : "未通过"}</strong></div>
      <div class="review-line"><span>终审建议</span><strong>${!check.pricingBlocked && check.mustRatio >= 0.85 && check.sectionReady >= 1 && check.typesetReady ? "可锁定交付" : "请先按提示调整"
      }</strong></div>
      <div class="review-line"><span>告警原因</span><strong>${escapeHtml(check.pricingReasons.join("；") || "无")}</strong></div>
    `;
  },

  lockDelivery() {
    if (!state.finalCheck) {
      Toast.error("请先执行终审检查");
      return;
    }

    const pass =
      !state.finalCheck.pricingBlocked &&
      state.finalCheck.mustRatio >= 0.85 &&
      state.finalCheck.sectionReady >= 1 &&
      state.finalCheck.typesetReady;
    if (!pass) {
      $("#deliveryStatus").textContent = "状态：未锁定（终审未通过）";
      $("#deliveryStatus").style.color = "var(--danger)";
      Toast.error("终审未通过，暂不能锁定交付");
      return;
    }

    state.finalLocked = true;
    $("#deliveryStatus").textContent = `状态：已锁定（${new Date().toLocaleString("zh-CN")}）`;
    $("#deliveryStatus").style.color = "var(--success)";
    setTaskStatus("最终投标文件已锁定交付");
    Toast.success("最终交付已锁定，可执行专家库回灌");
  },
};

const CompletedBidHub = {
  init() {
    this.resetForm();
    this.syncProjectIdInput();
    this.renderTable();

    $("#btnSaveCompletedBid").addEventListener("click", guarded(() => this.saveRecord()));
    $("#btnResetCompletedBid").addEventListener("click", () => this.resetForm());
    $("#completedBidTable").addEventListener(
      "click",
      guarded((event) => {
        const button = event.target.closest("button[data-action='delete-completed']");
        if (!button) return;
        const recordId = button.dataset.id;
        if (!recordId) return;
        return this.deleteRecord(recordId);
      }),
    );
    guarded(() => this.loadRecords())();
  },

  normalizeRecords(raw) {
    if (!Array.isArray(raw)) return [];
    return raw
      .filter((item) => item && typeof item === "object")
      .map((item) => ({
        id: String(item.id || "").trim(),
        projectName: String(item.project_name || item.projectName || "").trim(),
        projectId: String(item.project_id || item.projectId || "").trim(),
        tenderer: String(item.tenderer || "").trim(),
        result: String(item.bid_result || item.result || "WON").toUpperCase() === "LOST" ? "LOST" : "WON",
        fileName: String(item.file_name || item.fileName || "").trim(),
        completedDate: String(item.completed_date || item.completedDate || "").trim(),
        fileInfo: String(item.file_info || item.fileInfo || "").trim(),
        engineeringCategory: String(item.engineering_category || item.engineeringCategory || "").trim(),
        createdAt: String(item.created_at || item.createdAt || new Date().toISOString()),
      }))
      .filter((item) => item.id && item.projectName && item.fileName)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  },

  async loadRecords() {
    const params = new URLSearchParams({ limit: "300" });
    const res = await api(`/api/completed-bids?${params.toString()}`);
    state.completedBids = this.normalizeRecords(res.items || []);
    this.renderTable();
  },

  syncProjectIdInput() {
    const input = $("#completedBidProjectId");
    if (!input) return;
    if (!input.value.trim()) {
      input.value = state.projectId || "";
    }
  },

  resetForm() {
    $("#completedBidProjectName").value = "";
    $("#completedBidProjectId").value = state.projectId || "";
    $("#completedBidTenderer").value = "";
    $("#completedBidResult").value = "WON";
    $("#completedBidFileName").value = "";
    $("#completedBidDate").value = new Date().toISOString().slice(0, 10);
    $("#completedBidFileInfo").value = "";
  },

  async saveRecord() {
    const projectName = $("#completedBidProjectName").value.trim();
    const projectId = $("#completedBidProjectId").value.trim();
    const tenderer = $("#completedBidTenderer").value.trim();
    const result = $("#completedBidResult").value === "LOST" ? "LOST" : "WON";
    const fileName = $("#completedBidFileName").value.trim();
    const completedDate = $("#completedBidDate").value || new Date().toISOString().slice(0, 10);
    const fileInfo = $("#completedBidFileInfo").value.trim();

    if (!projectName) throw new Error("请填写工程名称");
    if (!fileName) throw new Error("请填写投标文件名");
    if (projectId && !isValidUuid(projectId)) throw new Error("项目 ID 必须是 UUID 格式");

    const payload = {
      project_id: projectId || null,
      project_name: projectName,
      engineering_category: state.industryTag || null,
      tenderer: tenderer || null,
      bid_result: result,
      file_name: fileName,
      file_info: fileInfo || null,
      completed_date: completedDate || null,
      created_by: "ui",
    };
    const record = await api("/api/completed-bids", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    $("#completedBidResultLog").textContent = JSON.stringify(record, null, 2);
    await this.loadRecords();
    Toast.success("已完成投标记录已保存");
    this.resetForm();
  },

  async deleteRecord(recordId) {
    await api(`/api/completed-bids/${encodeURIComponent(recordId)}`, { method: "DELETE" });
    await this.loadRecords();
    Toast.success("记录已删除");
  },

  renderTable() {
    const container = $("#completedBidTable");
    const rows = this.normalizeRecords(state.completedBids);
    state.completedBids = rows;

    if (!rows.length) {
      container.innerHTML = `<p class="hint" style="padding:0.7rem;">暂无完成记录。</p>`;
      return;
    }

    const head = `
      <div class="completed-bid-head">
        <span>工程名称</span>
        <span>项目 ID</span>
        <span>工程类别</span>
        <span>投标文件</span>
        <span>招标单位</span>
        <span>完成日期</span>
        <span>结果</span>
        <span>操作</span>
      </div>
    `;

    const body = rows
      .map(
        (item) => `
          <div class="completed-bid-row">
            <span title="${escapeHtml(item.projectName)}">${escapeHtml(shortText(item.projectName, 26))}</span>
            <span title="${escapeHtml(item.projectId || "-")}">${escapeHtml(item.projectId || "-")}</span>
            <span title="${escapeHtml(item.engineeringCategory || "-")}">${escapeHtml(item.engineeringCategory || "-")}</span>
            <span title="${escapeHtml(item.fileInfo || item.fileName)}">${escapeHtml(shortText(item.fileName, 26))}</span>
            <span title="${escapeHtml(item.tenderer || "-")}">${escapeHtml(shortText(item.tenderer || "-", 20))}</span>
            <span>${escapeHtml(item.completedDate || "-")}</span>
            <span><span class="completed-bid-tag ${item.result === "WON" ? "won" : "lost"}">${item.result === "WON" ? "已中标" : "未中标"}</span></span>
            <span><button class="btn btn-outline btn-sm" data-action="delete-completed" data-id="${escapeHtml(item.id)}" type="button">删除</button></span>
          </div>
        `,
      )
      .join("");

    container.innerHTML = head + body;
  },
};
