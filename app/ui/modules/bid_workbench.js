const BidWorkbench = {
  init() {
    $("#btnLoadTenderPoints").addEventListener("click", guarded(() => this.loadTenderPointsToOutline()));
    $("#btnCreateOutline").addEventListener("click", guarded(() => this.createOutline()));
    $("#btnConfirmOutline").addEventListener("click", guarded(() => this.confirmOutline()));

    $("#btnRetrieveEvidence").addEventListener("click", guarded(() => this.retrieveEvidence()));
    $("#btnGenerateSection").addEventListener("click", guarded(() => this.generateSection()));
    $("#btnGenerateAll").addEventListener("click", guarded(() => this.generateAllSections()));
    $("#btnExportGenerationResult").addEventListener("click", guarded(() => this.exportGenerationResult()));
    $("#btnComposeDraft").addEventListener("click", guarded(() => this.composeSectionDraft()));
    $("#btnSaveSection").addEventListener("click", guarded(() => this.confirmSection()));

    $("#btnStepUpload").addEventListener("click", () => {
      this.setStep("upload");
      focusPanel("panel-expert-hub");
    });
    $("#btnStepParse").addEventListener("click", () => {
      this.setStep("parse");
      focusPanel("panel-tender-hub");
    });
    $("#btnStepOutline").addEventListener("click", () => {
      this.setStep("outline");
      focusPanel("panel-bid-hub");
    });
    $("#btnStepGenerate").addEventListener("click", () => {
      this.setStep("generate");
      focusPanel("panel-bid-hub");
    });
    $("#btnStepExport").addEventListener("click", () => {
      this.setStep("export");
      focusPanel("panel-publish-hub");
    });

    $("#sectionUserInput").addEventListener("input", () => this.syncEditorInputs());
    $("#sectionFinalDraft").addEventListener("input", () => this.syncEditorInputs());

    this.setStep("outline");
    this.renderSectionList();
  },

  setStep(step) {
    const mapping = {
      upload: "#btnStepUpload",
      parse: "#btnStepParse",
      outline: "#btnStepOutline",
      generate: "#btnStepGenerate",
      export: "#btnStepExport",
    };
    Object.values(mapping).forEach((id) => {
      const node = $(id);
      if (node) node.classList.remove("active");
    });
    const target = mapping[step];
    if (target && $(target)) $(target).classList.add("active");
  },

  loadTenderPointsToOutline() {
    const points = $("#tenderPointsText").value.trim();
    if (!points) {
      Toast.error("请先在招标分析中生成投标要点");
      return;
    }
    $("#outlineRequirementText").value = points;
    this.setStep("outline");
    Toast.success("投标要点已载入目录生成区");
  },

  async createOutline() {
    const text = $("#outlineRequirementText").value.trim();
    if (!text) {
      Toast.error("请输入招标拆解输入");
      return;
    }

    const projectId = ensureProjectId();
    setTaskStatus("目录框架生成中");

    const res = await api("/v1/workflow/outline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: projectId,
        tender_text: text,
      }),
    });

    state.outlineId = res.outline_id;
    state.outlineConfirmed = false;
    state.sections = (res.sections || []).map((item) => ({
      ...item,
      userInput: "",
      evidenceHits: [],
      aiDraft: "",
      finalDraft: "",
      status: "NEW",
      review: null,
      reviewDecision: "PASS",
    }));

    state.selectedSectionKey = state.sections[0]?.section_key || "";
    $("#feedbackOutlineId").value = state.outlineId;

    this.renderOutlineTable();
    this.renderSectionList();
    this.renderSectionEditor();
    ReviewWorkbench.refreshSectionSelect();

    updateOutlineBadge(`已生成 ${state.sections.length} 章，待确认`, "warn");
    this.setStep("outline");
    setTaskStatus("目录框架已生成，等待确认");
    Toast.success("目录框架生成完成，请先确认再逐章生成");
  },

  renderOutlineTable() {
    const container = $("#outlineSectionTable");
    if (!state.sections.length) {
      container.innerHTML = `<p class="hint">目录生成后会显示在这里。</p>`;
      return;
    }

    const head = `
      <div class="outline-head">
        <div>章节号</div>
        <div>章节标题</div>
        <div>章节要求（可调整）</div>
      </div>
    `;

    const rows = state.sections
      .map(
        (section, idx) => `
          <div class="outline-row" data-index="${idx}">
            <div class="outline-key">${escapeHtml(section.section_key)}</div>
            <div>
              <input data-field="title" data-index="${idx}" type="text" value="${escapeHtml(section.section_title)}" />
            </div>
            <div>
              <textarea data-field="req" data-index="${idx}" rows="2">${escapeHtml(section.requirement_texts.join("\n"))}</textarea>
            </div>
          </div>
        `,
      )
      .join("");

    container.innerHTML = head + rows;

    container.querySelectorAll("[data-field='title']").forEach((node) => {
      node.addEventListener("change", (event) => {
        const idx = Number(event.target.dataset.index);
        state.sections[idx].section_title = event.target.value.trim() || state.sections[idx].section_title;
        this.renderSectionList();
        ReviewWorkbench.refreshSectionSelect();
      });
    });

    container.querySelectorAll("[data-field='req']").forEach((node) => {
      node.addEventListener("change", (event) => {
        const idx = Number(event.target.dataset.index);
        state.sections[idx].requirement_texts = splitLines(event.target.value);
      });
    });
  },

  async confirmOutline() {
    if (!state.outlineId) {
      Toast.error("请先生成目录框架");
      return;
    }

    setTaskStatus("目录确认中");
    const res = await api("/v1/workflow/outline/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        outline_id: state.outlineId,
        approved: true,
      }),
    });

    state.outlineConfirmed = String(res.status || "").includes("CONFIRMED");
    if (state.outlineConfirmed) {
      updateOutlineBadge("目录已确认，可逐章生成", "ok");
      this.setStep("generate");
      Toast.success("目录已锁定，进入逐章编写");
      setTaskStatus("目录确认完成");
    } else {
      updateOutlineBadge(`目录状态：${res.status}`, "warn");
    }
  },

  renderSectionList() {
    const list = $("#editorSectionList");
    if (!state.sections.length) {
      list.innerHTML = `<li class="empty-hint">请先生成并确认目录</li>`;
      return;
    }

    list.innerHTML = state.sections
      .map((section) => {
        const active = section.section_key === state.selectedSectionKey ? "active" : "";
        return `
          <li class="section-item ${active}" data-section-key="${escapeHtml(section.section_key)}">
            <div>${escapeHtml(section.section_key)} ${escapeHtml(section.section_title)}</div>
            <div class="sec-meta">${escapeHtml(sectionStatusLabel(section.status))}</div>
          </li>
        `;
      })
      .join("");

    list.querySelectorAll(".section-item").forEach((node) => {
      node.addEventListener("click", () => {
        this.syncEditorInputs();
        state.selectedSectionKey = node.dataset.sectionKey;
        this.renderSectionList();
        this.renderSectionEditor();
      });
    });
  },

  renderSectionEditor() {
    const section = getSectionByKey(state.selectedSectionKey);
    if (!section) {
      $("#currentSectionTitle").textContent = "未选择章节";
      $("#currentSectionMeta").textContent = "请先在左侧选择章节";
      $("#sectionUserInput").value = "";
      $("#sectionFinalDraft").value = "";
      $("#sectionAiDraftPane").textContent = "请点击“AI 逐章生成”。";
      $("#sectionEvidencePane").textContent = "请先检索专家资料。";
      $("#generationPreviewTitle").textContent = "内容预览";
      $("#generationPreviewMeta").textContent = "选择目录节点后查看预览";
      $("#generationPreviewPane").textContent = "尚未生成内容。";
      return;
    }

    $("#currentSectionTitle").textContent = `${section.section_key} ${section.section_title}`;
    $("#currentSectionMeta").textContent = `${sectionStatusLabel(section.status)} | 要求 ${section.requirement_texts.length} 条`;
    $("#sectionUserInput").value = section.userInput || "";
    $("#sectionFinalDraft").value = section.finalDraft || "";
    $("#sectionAiDraftPane").textContent = section.aiDraft || "请点击“AI 逐章生成”。";
    this.renderEvidencePane(section.evidenceHits || []);

    $("#feedbackSectionKey").value = section.section_key;
    $("#feedbackSectionTitle").value = section.section_title;
    this.updateGenerationPreview(section);
  },

  updateGenerationPreview(section) {
    if (!section) {
      $("#generationPreviewPane").textContent = "尚未生成内容。";
      return;
    }
    const preview =
      section.finalDraft.trim() ||
      section.aiDraft.trim() ||
      (section.requirement_texts || []).join("\n") ||
      "尚未生成内容。";
    $("#generationPreviewTitle").textContent = `${section.section_key} ${section.section_title}`;
    $("#generationPreviewMeta").textContent = `${sectionStatusLabel(section.status)} | 预览优先显示“章节最终稿”`;
    $("#generationPreviewPane").textContent = preview;
  },

  syncEditorInputs() {
    const section = getSectionByKey(state.selectedSectionKey);
    if (!section) return;
    section.userInput = $("#sectionUserInput").value;
    section.finalDraft = $("#sectionFinalDraft").value;
    this.updateGenerationPreview(section);
  },

  renderEvidencePane(hits) {
    const pane = $("#sectionEvidencePane");
    if (!hits || !hits.length) {
      pane.textContent = "请先检索专家资料。";
      return;
    }
    pane.innerHTML = hits
      .map(
        (hit, idx) => `
          <div class="chunk" style="margin-bottom: 0.5rem;">
            <div class="chunk-header">#${idx + 1} | score=${Number(hit.score || 0).toFixed(3)} | ${escapeHtml(hit.chunk_id)}</div>
            <div>${escapeHtml(hit.text)}</div>
          </div>
        `,
      )
      .join("");
  },

  async retrieveEvidence() {
    const section = getSectionByKey(state.selectedSectionKey);
    if (!section) {
      Toast.error("请先选择章节");
      return;
    }

    this.syncEditorInputs();
    const query = [section.section_title, section.requirement_texts.join("；"), section.userInput]
      .map((item) => item.trim())
      .filter(Boolean)
      .join("；");

    if (!query) {
      Toast.error("章节检索条件为空，请先补充需求");
      return;
    }

    setTaskStatus(`检索专家库：${section.section_key}`);
    const res = await api("/v1/evidence/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        top_k: 6,
        industry_tag: effectiveIndustryTag(),
      }),
    });

    section.evidenceHits = res.hits || [];
    this.renderEvidencePane(section.evidenceHits);

    const log = [
      `章节：${section.section_key}`,
      `检索语句：${shortText(query, 120)}`,
      `命中数：${section.evidenceHits.length}`,
    ].join("\n");
    $("#sectionTaskLog").textContent = log;
    this.updateGenerationPreview(section);

    setTaskStatus(`专家库检索完成：${section.section_key}`);
    Toast.success(`检索到 ${section.evidenceHits.length} 条专家资料`);
  },

  async generateSection(sectionKey = state.selectedSectionKey, options = {}) {
    const { silent = false, showRealtime = true } = options;
    const section = getSectionByKey(sectionKey);
    if (!section) {
      Toast.error("请先选择章节");
      return;
    }

    if (!state.outlineId || !state.outlineConfirmed) {
      Toast.error("请先完成目录确认，再进行逐章生成");
      return;
    }

    this.setStep("generate");
    this.syncEditorInputs();

    if (state.selectedSectionKey !== section.section_key) {
      state.selectedSectionKey = section.section_key;
      this.renderSectionList();
      this.renderSectionEditor();
    }

    return this.runSectionGeneration(section, { silent, showRealtime });
  },

  async runSectionGeneration(section, { silent = false, showRealtime = true } = {}) {
    const agentPreset = $("#generationAgentPreset")?.value || "content-v1";
    const requirementTexts = section.requirement_texts.length
      ? [...section.requirement_texts, ...(section.userInput.trim() ? [`用户交付补充：${section.userInput.trim()}`] : [])]
      : [`${section.section_title}（人工补充）${section.userInput.trim()}`];

    const payload = {
      outline_id: state.outlineId,
      project_id: ensureProjectId(),
      section_key: section.section_key,
      section_title: section.section_title,
      requirement_texts: [`生成智能体配置：${agentPreset}`, ...requirementTexts],
      industry_tag: effectiveIndustryTag(),
    };

    setTaskStatus(`逐章生成中：${section.section_key}`);
    if (showRealtime) {
      $("#sectionTaskLog").textContent = `准备启动章节任务...\n${JSON.stringify(payload, null, 2)}`;
    }

    const enqueue = await api("/v1/workflow/section", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const taskId = enqueue.task_ids?.SECTION_PIPELINE;
    if (!taskId) {
      throw new Error(`章节 ${section.section_key} 任务未返回 task_id`);
    }

    section.status = "PENDING";
    this.renderSectionList();
    if (state.selectedSectionKey === section.section_key) {
      this.renderSectionEditor();
    }

    await pollTask(taskId, {
      onTick: (taskRes) => {
        if (showRealtime && state.selectedSectionKey === section.section_key) {
          $("#sectionTaskLog").textContent = `task_id=${taskId}\nstatus=${taskRes.status}\n${JSON.stringify(taskRes.result || {}, null, 2)}`;
        }
        setTaskStatus(`章节任务 ${section.section_key}: ${taskRes.status}`);
      },
      onDone: (taskRes) => {
        if (taskRes.status === "SUCCESS") {
          const payloadRes = taskRes.result || {};
          const generated = payloadRes.stages?.generate || {};
          section.aiDraft = generated.generated_text || "";
          section.status = payloadRes.status || generated.status || "NEED_HUMAN_INPUT";

          if (!section.evidenceHits.length) {
            const retrievalIds = generated.evidence_ids || [];
            section.evidenceHits = retrievalIds.map((id) => ({ chunk_id: id, score: 0, text: `证据片段 ID: ${id}` }));
          }

          if (!section.finalDraft.trim()) {
            section.finalDraft = this.buildComposedDraft(section);
          }

          this.renderSectionList();
          if (state.selectedSectionKey === section.section_key) {
            this.renderSectionEditor();
          }
          ReviewWorkbench.refreshSectionSelect();
          if (!silent) {
            Toast.success(`章节 ${section.section_key} 生成完成`);
          }
        } else {
          section.status = "FAILURE";
          this.renderSectionList();
          if (state.selectedSectionKey === section.section_key) {
            this.renderSectionEditor();
          }
          if (!silent) {
            Toast.error(`章节 ${section.section_key} 生成失败`);
          }
        }
      },
      onError: (err) => {
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes("超时")) {
          section.status = "PENDING";
          if (!silent) {
            Toast.info(`章节 ${section.section_key} 仍在后台执行，可稍后重试查询`);
          }
        } else {
          section.status = "FAILURE";
        }
        this.renderSectionList();
        if (state.selectedSectionKey === section.section_key) {
          this.renderSectionEditor();
        }
        if (showRealtime) {
          $("#sectionTaskLog").textContent = `任务异常: ${msg}`;
        }
      },
    });
    return section.status;
  },

  async generateAllSections() {
    if (!state.outlineId || !state.outlineConfirmed) {
      Toast.error("请先确认目录，再执行批量生成");
      return;
    }
    if (!state.sections.length) {
      Toast.error("暂无章节可生成");
      return;
    }

    this.syncEditorInputs();
    this.setStep("generate");

    const concurrency = Math.max(1, Math.min(8, Number.parseInt($("#generationConcurrency").value || "1", 10) || 1));
    const queue = state.sections.filter((section) => section.status !== "SECTION_CONFIRMED");
    if (!queue.length) {
      Toast.info("所有章节均已确认，无需批量生成");
      return;
    }

    let pointer = 0;
    let done = 0;
    let failed = 0;
    const logs = [`批量生成开始：章节=${queue.length}，并发=${concurrency}`];
    $("#sectionTaskLog").textContent = logs.join("\n");

    const worker = async () => {
      while (pointer < queue.length) {
        const index = pointer;
        pointer += 1;
        const section = queue[index];
        logs.push(`[${index + 1}/${queue.length}] 启动 ${section.section_key}`);
        $("#sectionTaskLog").textContent = logs.slice(-18).join("\n");
        try {
          await this.runSectionGeneration(section, { silent: true, showRealtime: false });
          logs.push(`✓ ${section.section_key} 完成 (${sectionStatusLabel(section.status)})`);
        } catch (error) {
          failed += 1;
          section.status = "FAILURE";
          const msg = error instanceof Error ? error.message : String(error);
          logs.push(`✗ ${section.section_key} 失败: ${msg}`);
        }
        done += 1;
        setTaskStatus(`批量生成进度 ${done}/${queue.length}`);
        this.renderSectionList();
      }
    };

    await Promise.all(Array.from({ length: Math.min(concurrency, queue.length) }, () => worker()));
    this.renderSectionEditor();
    ReviewWorkbench.refreshSectionSelect();
    $("#sectionTaskLog").textContent = logs.slice(-40).join("\n");

    if (failed > 0) {
      Toast.error(`批量生成完成：成功 ${queue.length - failed}，失败 ${failed}`);
    } else {
      Toast.success(`批量生成完成：共 ${queue.length} 章`);
    }
    setTaskStatus("批量生成完成");
  },

  exportGenerationResult() {
    if (!state.sections.length) {
      Toast.error("暂无可导出的章节内容");
      return;
    }
    state.sections.forEach((section) => {
      if (!section.finalDraft.trim() && (section.aiDraft.trim() || section.userInput.trim())) {
        section.finalDraft = this.buildComposedDraft(section);
      }
    });
    this.renderSectionEditor();
    const ok = ReviewWorkbench.buildFinalDraft();
    if (!ok) return;
    this.setStep("export");
    focusPanel("panel-publish-hub");
  },

  buildComposedDraft(section) {
    const blocks = [];

    if (section.userInput.trim()) {
      blocks.push(`【用户交付内容】\n${section.userInput.trim()}`);
    }

    if (section.aiDraft.trim()) {
      blocks.push(`【AI 生成内容】\n${section.aiDraft.trim()}`);
    }

    if (section.evidenceHits.length) {
      const evidenceText = section.evidenceHits
        .slice(0, 4)
        .map((item, idx) => `${idx + 1}. ${item.text}`)
        .join("\n");
      blocks.push(`【专家库参考】\n${evidenceText}`);
    }

    if (!blocks.length) {
      return `${section.section_title}\n\n请补充本章内容。`;
    }

    return blocks.join("\n\n");
  },

  composeSectionDraft() {
    const section = getSectionByKey(state.selectedSectionKey);
    if (!section) {
      Toast.error("请先选择章节");
      return;
    }

    this.syncEditorInputs();
    section.finalDraft = this.buildComposedDraft(section);
    $("#sectionFinalDraft").value = section.finalDraft;
    this.updateGenerationPreview(section);
    Toast.success("章节工作稿已合成，可继续人工调整");
  },

  async confirmSection() {
    const section = getSectionByKey(state.selectedSectionKey);
    if (!section) {
      Toast.error("请先选择章节");
      return;
    }

    this.syncEditorInputs();
    if (!section.finalDraft.trim()) {
      Toast.error("章节最终稿为空，无法确认");
      return;
    }

    if (!state.outlineId) {
      Toast.error("缺少 outline_id，请先重新生成目录");
      return;
    }

    setTaskStatus(`章节确认中：${section.section_key}`);
    const res = await api("/v1/workflow/section/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        outline_id: state.outlineId,
        section_key: section.section_key,
        approved: true,
      }),
    });

    section.status = res.status || "SECTION_CONFIRMED";
    this.renderSectionList();
    this.renderSectionEditor();
    ReviewWorkbench.refreshSectionSelect();

    $("#feedbackOutlineId").value = state.outlineId;
    $("#feedbackSectionKey").value = section.section_key;
    $("#feedbackSectionTitle").value = section.section_title;
    $("#feedbackContent").value = section.finalDraft;
    this.updateGenerationPreview(section);

    setTaskStatus(`章节确认完成：${section.section_key}`);
    Toast.success(`章节 ${section.section_key} 已确认`);
  },
};
