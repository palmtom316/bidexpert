const ExpertHub = {
  init() {
    $("#btnExpertIngest").addEventListener("click", guarded(() => this.ingestPdfFiles()));
    $("#btnStructuredConvert").addEventListener("click", guarded(() => this.convertStructuredDocument()));
    $("#btnStructuredConvertAndIngest").addEventListener("click", guarded(() => this.convertAndIngestStructuredDocument()));
    $("#btnStructuredConfirm").addEventListener("click", guarded(() => this.confirmStructuredConversion()));
    $("#convertSessionHistory").addEventListener("change", () => this.applyConversionHistorySelection());
    $("#btnStructuredIngest").addEventListener("click", guarded(() => this.ingestStructured()));
    $("#btnLibraryDocs").addEventListener("click", guarded(() => this.loadDocList()));
    $("#btnLibraryChunks").addEventListener("click", guarded(() => this.loadChunks()));
    $("#btnFeedbackPdfIngest").addEventListener("click", guarded(() => this.feedbackPdfIngest()));
    $("#btnFeedbackSectionUpsert").addEventListener("click", guarded(() => this.feedbackSectionUpsert()));
    this.renderConversionHistoryOptions();
    this.loadDocList();
  },

  normalizedConversionHistory() {
    const source = Array.isArray(state.conversionHistory) ? state.conversionHistory : [];
    return source
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const conversionId = String(item.conversion_id || item.id || "").trim();
        if (!conversionId) return null;
        return {
          conversion_id: conversionId,
          filename: String(item.filename || "").trim(),
          title: String(item.title || "").trim(),
          doc_type: String(item.doc_type || "").trim(),
          created_at: String(item.created_at || "").trim(),
        };
      })
      .filter(Boolean)
      .slice(0, 20);
  },

  saveConversionHistory(history) {
    state.conversionHistory = Array.isArray(history) ? history : [];
    localStorage.setItem(CONVERSION_HISTORY_STORAGE_KEY, JSON.stringify(state.conversionHistory));
  },

  rememberConversionSession({ conversionId, filename = "", title = "", docType = "" }) {
    const normalizedId = String(conversionId || "").trim();
    if (!normalizedId) return;
    const normalizedHistory = this.normalizedConversionHistory();
    const next = [
      {
        conversion_id: normalizedId,
        filename: String(filename || "").trim(),
        title: String(title || "").trim(),
        doc_type: String(docType || "").trim(),
        created_at: new Date().toISOString(),
      },
      ...normalizedHistory.filter((item) => item.conversion_id !== normalizedId),
    ].slice(0, 20);
    this.saveConversionHistory(next);
    this.renderConversionHistoryOptions(normalizedId);
  },

  renderConversionHistoryOptions(selectedId = "") {
    const select = $("#convertSessionHistory");
    if (!select) return;
    const history = this.normalizedConversionHistory();
    this.saveConversionHistory(history);
    select.innerHTML = "";

    const defaultOption = document.createElement("option");
    defaultOption.value = "";
    defaultOption.textContent = history.length ? "选择历史会话（可直接确认入库）" : "无历史会话";
    select.appendChild(defaultOption);

    history.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.conversion_id;
      const timestamp = item.created_at
        ? new Date(item.created_at).toLocaleString("zh-CN", { hour12: false })
        : "--";
      const fileName = item.filename || item.title || item.conversion_id.slice(0, 12);
      option.textContent = `${timestamp} | ${fileName} | ${item.doc_type || "EXPERT_HISTORY"}`;
      select.appendChild(option);
    });

    const preferred = String(selectedId || $("#convertSessionId")?.value || "").trim();
    if (preferred) {
      select.value = preferred;
    }
  },

  applyConversionHistorySelection() {
    const conversionId = ($("#convertSessionHistory")?.value || "").trim();
    if (!conversionId) return;
    $("#convertSessionId").value = conversionId;
    const selected = this.normalizedConversionHistory().find((item) => item.conversion_id === conversionId);
    if (selected?.title && !$("#convertTitle").value.trim()) {
      $("#convertTitle").value = selected.title;
    }
    if (selected?.doc_type) {
      $("#convertDocType").value = selected.doc_type;
    }
    Toast.info("已回填 conversion_id，可直接点击“确认入库”");
  },

  async ingestPdfFiles() {
    const files = Array.from($("#expertPdfFiles").files || []);
    if (!files.length) {
      Toast.error("请至少选择一个文件");
      return;
    }

    const industryTag = effectiveIndustryTag();
    const docType = $("#expertDocType").value;
    const ocrProvider = normalizeConfiguredOcrProvider(state.ocrProvider);
    const projectId = state.projectId.trim();
    const resultView = $("#expertIngestResult");
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    formData.append("doc_type", docType);
    formData.append("industry_tag", industryTag);
    formData.append("ocr_provider", ocrProvider);
    appendOcrRuntimeConfig(formData, ocrProvider);
    if (projectId) formData.append("project_id", projectId);

    setTaskStatus(`资料入库提交中（${files.length} 个文件）`);
    const res = await api("/v1/expert-library/ingest-uploads", {
      method: "POST",
      body: formData,
    });

    const logs = (res.items || []).map((item, idx) => {
      if (item.status === "SUCCEEDED") {
        const warnings = (item.warnings || []).length ? ` | warnings=${item.warnings.join(";")}` : "";
        return `[${idx + 1}/${res.total_files}] ${item.filename} -> SUCCEEDED | chunks=${item.chunk_count} | qdrant=${item.qdrant_upserted}${warnings}`;
      }
      return `[${idx + 1}/${res.total_files}] ${item.filename} -> FAILED | ${item.error || "unknown error"}`;
    });
    resultView.textContent = logs.join("\n");

    setTaskStatus(`资料入库完成（成功 ${res.success_count}/${res.total_files}）`);
    if (res.failure_count > 0) {
      Toast.info(`入库完成：成功 ${res.success_count}，失败 ${res.failure_count}`);
    } else {
      Toast.success("资料入库流程完成");
    }
    this.loadDocList();
  },

  async convertStructuredDocument({ suppressSuccessToast = false } = {}) {
    const file = $("#convertSourceFile").files[0];
    if (!file) {
      Toast.error("请选择待转换文件");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("doc_type", $("#convertDocType").value);
    formData.append("industry_tag", effectiveIndustryTag());
    const ocrProvider = normalizeConfiguredOcrProvider(state.ocrProvider);
    formData.append("ocr_provider", ocrProvider);
    appendOcrRuntimeConfig(formData, ocrProvider);
    const title = $("#convertTitle").value.trim();
    const docType = $("#convertDocType").value;
    if (title) formData.append("title", title);
    if (state.projectId.trim()) formData.append("project_id", state.projectId.trim());

    setTaskStatus("文档结构化转换中");
    $("#convertPreviewResult").textContent = "正在转换，请稍候...";
    const res = await api("/v1/expert-library/convert-upload", {
      method: "POST",
      body: formData,
    });

    const conversionId = String(res.conversion_id || "").trim();
    $("#convertSessionId").value = conversionId;
    this.rememberConversionSession({
      conversionId,
      filename: res.filename,
      title,
      docType,
    });
    const sectionPreview = (res.preview_sections || []).length
      ? `\n预览章节：\n- ${res.preview_sections.join("\n- ")}`
      : "";
    const warningText = (res.warnings || []).length ? `\n告警：\n- ${res.warnings.join("\n- ")}` : "";
    $("#convertPreviewResult").textContent =
      `转换成功\nconversion_id=${conversionId}\n文件=${res.filename}\npage=${res.page_count}\nblocks=${res.block_count}\nsections=${res.section_count}\nchunks=${res.chunk_count}${sectionPreview}${warningText}\n\n下一步：点击“确认入库”执行分块、向量化与 embedding。`;
    setTaskStatus("文档结构化转换完成，等待确认入库");
    if (!suppressSuccessToast) {
      Toast.success("结构化转换完成，请确认后入库");
    }
    return res;
  },

  async convertAndIngestStructuredDocument() {
    setTaskStatus("一键流程执行中：结构化转换 -> 入库");
    const converted = await this.convertStructuredDocument({ suppressSuccessToast: true });
    const conversionId = String(converted?.conversion_id || "").trim();
    if (!conversionId) {
      throw new Error("结构化转换成功但未返回 conversion_id");
    }
    const confirmed = await this.confirmStructuredConversion({ conversionId, suppressSuccessToast: true });
    setTaskStatus("一键流程完成：结构化转换 + 入库");
    Toast.success(`一键流程完成，已入库 chunk=${confirmed.chunk_count}`);
  },

  async confirmStructuredConversion({ conversionId = "", suppressSuccessToast = false } = {}) {
    const resolvedConversionId = String(conversionId || $("#convertSessionId").value || "").trim();
    $("#convertSessionId").value = resolvedConversionId;
    this.renderConversionHistoryOptions(resolvedConversionId);
    if (!resolvedConversionId) {
      Toast.error("请先执行转换或选择历史会话");
      return;
    }

    const docType = $("#convertDocType").value;
    const title = $("#convertTitle").value.trim() || null;
    const projectId = state.projectId.trim() || null;
    const industryTag = effectiveIndustryTag() || null;
    const payload = {
      conversion_id: resolvedConversionId,
      project_id: projectId,
      industry_tag: industryTag,
      title,
      created_by: "user",
      doc_type: docType,
    };

    this.rememberConversionSession({
      conversionId: resolvedConversionId,
      title: title || "",
      docType,
    });
    setTaskStatus("根据结构化结果入库中（分块/向量化/embedding）");
    const res = await api("/v1/expert-library/convert-confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    $("#convertPreviewResult").textContent = `${$("#convertPreviewResult").textContent}\n\n确认入库结果：\n${JSON.stringify(res, null, 2)}`;
    setTaskStatus("专家库文档生成完成（已完成向量化与 embedding）");
    if (!suppressSuccessToast) {
      Toast.success(`已确认入库，chunk=${res.chunk_count}`);
    }
    this.loadDocList();
    return res;
  },

  async ingestStructured() {
    const payload = {
      project_id: state.projectId || null,
      industry_tag: effectiveIndustryTag(),
      created_by: "user",
      standard_items: splitLines($("#structuredStandard").value),
      company_performance_items: splitLines($("#structuredCompanyPerformance").value),
      company_qualification_items: splitLines($("#structuredCompanyQualification").value),
      pm_qualification_performance_items: splitLines($("#structuredPmQualificationPerformance").value),
    };

    const totalItems =
      payload.standard_items.length +
      payload.company_performance_items.length +
      payload.company_qualification_items.length +
      payload.pm_qualification_performance_items.length;

    if (!totalItems) {
      Toast.error("请至少填写一条结构化数据");
      return;
    }

    setTaskStatus("结构化补录提交中");
    const result = await api("/v1/expert-library/ingest-structured", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    $("#structuredResult").textContent = JSON.stringify(result, null, 2);
    setTaskStatus("结构化补录完成");
    Toast.success(`已补录 ${result.total_chunks} 条知识`);
  },

  async loadDocList() {
    const project = state.projectId.trim();
    const industry = effectiveIndustryTag();
    const params = new URLSearchParams({ limit: "80" });
    if (project) params.set("project_id", project);
    if (industry) params.set("industry_tag", industry);

    try {
      const res = await api(`/v1/expert-library/docs?${params.toString()}`);
      const docSelect = $("#libraryDocSelect");
      const feedbackSelect = $("#feedbackTargetDoc");
      docSelect.innerHTML = "";
      feedbackSelect.innerHTML = "";

      if (!res.items.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "暂无文档";
        docSelect.appendChild(opt.cloneNode(true));
        feedbackSelect.appendChild(opt);
        return;
      }

      res.items.forEach((item) => {
        const text = `${item.title || item.expert_doc_id.slice(0, 8)} | ${item.doc_type} | 内容片段 ${item.chunk_count}`;
        const optionA = document.createElement("option");
        optionA.value = item.expert_doc_id;
        optionA.textContent = text;
        docSelect.appendChild(optionA);

        const optionB = document.createElement("option");
        optionB.value = item.expert_doc_id;
        optionB.textContent = text;
        feedbackSelect.appendChild(optionB);
      });

      Toast.info(`已加载 ${res.items.length} 个专家文档`);
    } catch {
      // error toast handled by api()
    }
  },

  async loadChunks() {
    const docId = $("#libraryDocSelect").value;
    if (!docId) {
      Toast.error("请先选择文档");
      return;
    }

    setTaskStatus("加载专家库切片中");
    const res = await api(`/v1/expert-library/docs/${docId}/chunks?limit=200`);
    const view = $("#libraryModulesView");

    if (!res.items.length) {
      view.innerHTML = `<p class="hint">该文档暂无内容片段。</p>`;
      setTaskStatus("内容片段加载完成");
      return;
    }

    view.innerHTML = res.items
      .map(
        (item, index) => `
          <div class="chunk">
            <div class="chunk-header">#${index + 1} | score=${Number(item.quality_score || 0).toFixed(1)} | ${escapeHtml(item.section_anchor || "未标记章节")}</div>
            <div>${escapeHtml(item.excerpt_text)}</div>
          </div>
        `,
      )
      .join("");

    setTaskStatus(`内容片段加载完成（${res.items.length} 条）`);
  },

  async feedbackPdfIngest() {
    const file = $("#feedbackPdfFile").files[0];
    if (!file) {
      Toast.error("请选择要回灌的 PDF 文件");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("doc_type", $("#feedbackDocType").value);
    formData.append("industry_tag", effectiveIndustryTag());
    const ocrProvider = normalizeConfiguredOcrProvider(state.ocrProvider);
    formData.append("ocr_provider", ocrProvider);
    appendOcrRuntimeConfig(formData, ocrProvider);
    const title = $("#feedbackTitle").value.trim();
    if (title) formData.append("title", title);
    if (state.projectId.trim()) formData.append("project_id", state.projectId.trim());

    setTaskStatus("投标文件 PDF 回灌中");
    const res = await api("/v1/expert-library/ingest-upload", {
      method: "POST",
      body: formData,
    });

    $("#feedbackResult").textContent = JSON.stringify(res, null, 2);
    setTaskStatus("投标文件 PDF 回灌完成");
    Toast.success("投标文件 PDF 回灌成功");
    this.loadDocList();
  },

  async feedbackSectionUpsert() {
    const expertDocId = $("#feedbackTargetDoc").value;
    const outlineId = $("#feedbackOutlineId").value.trim();
    const sectionKey = $("#feedbackSectionKey").value.trim();
    const sectionTitle = $("#feedbackSectionTitle").value.trim();
    const content = $("#feedbackContent").value.trim();

    if (!expertDocId || !outlineId || !sectionKey || !sectionTitle || !content) {
      Toast.error("请完整填写章节回灌参数");
      return;
    }

    setTaskStatus("章节内容回灌中");
    const enqueue = await api("/v1/evidence/feedback-upsert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        outline_id: outlineId,
        section_key: sectionKey,
        section_title: sectionTitle,
        expert_doc_id: expertDocId,
        content_md: content,
        industry_tag: effectiveIndustryTag(),
      }),
    });

    $("#feedbackResult").textContent = `任务已提交: ${enqueue.task_id}\n状态: ${enqueue.status}`;

    await pollTask(enqueue.task_id, {
      onTick: (taskRes) => {
        setTaskStatus(`章节回灌任务: ${taskRes.status}`);
        $("#feedbackResult").textContent = JSON.stringify(taskRes, null, 2);
      },
      onDone: (taskRes) => {
        if (taskRes.status === "SUCCESS") {
          Toast.success("章节回灌已完成");
        }
      },
    });

    this.loadDocList();
  },
};
