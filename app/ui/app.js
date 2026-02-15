const API_BASE = "";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function isValidUuid(value) {
  return UUID_PATTERN.test(String(value || "").trim());
}

function normalizeStoredProjectId(value) {
  const candidate = String(value || "").trim();
  return isValidUuid(candidate) ? candidate : "";
}

function parseStoredArray(raw, fallback = []) {
  if (!raw) return [...fallback];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [...fallback];
  } catch {
    return [...fallback];
  }
}

const state = {
  projectId: normalizeStoredProjectId(localStorage.getItem("be_project_id")),
  industryTag: String(localStorage.getItem("be_industry_tag") || "").trim(),
  industryTagHistory: parseStoredArray(localStorage.getItem("be_industry_tag_history")),
  completedBids: [],
  outlineId: "",
  outlineConfirmed: false,
  sections: [],
  selectedSectionKey: "",
  analysisRunId: "",
  analysisDetail: null,
  finalBidDraft: "",
  finalCheck: null,
  finalLocked: false,
  coverTemplate: "none",
  byokProfiles: [],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);

const Toast = {
  container: null,
  init() {
    this.container = $("#toastContainer");
  },
  show(message, type = "info", duration = 3200) {
    if (!this.container) return;
    const icon = type === "success" ? "check-line" : type === "error" ? "close-circle-line" : "information-line";
    const node = document.createElement("div");
    node.className = `toast ${type}`;
    node.innerHTML = `<i class="ri-${icon}"></i><span>${escapeHtml(message)}</span>`;
    this.container.appendChild(node);
    setTimeout(() => {
      node.style.opacity = "0";
      node.style.transform = "translateX(10px)";
      node.addEventListener("transitionend", () => node.remove(), { once: true });
    }, duration);
  },
  success(msg) {
    this.show(msg, "success");
  },
  error(msg) {
    this.show(msg, "error", 4600);
  },
  info(msg) {
    this.show(msg, "info");
  },
};

async function api(path, options = {}) {
  const config = { ...options };
  try {
    const response = await fetch(API_BASE + path, config);
    if (!response.ok) {
      const text = await response.text();
      let message = response.statusText || `HTTP ${response.status}`;
      try {
        const parsed = JSON.parse(text);
        if (typeof parsed.detail === "string") {
          message = parsed.detail;
        } else if (parsed.detail) {
          message = JSON.stringify(parsed.detail);
        } else {
          message = JSON.stringify(parsed);
        }
      } catch {
        if (text) message = text;
      }
      throw new Error(message);
    }
    return await response.json();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (error && typeof error === "object") {
      error.__toastShown = true;
    }
    Toast.error(message);
    throw error;
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function splitLines(text) {
  return text
    .split(/\n+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function normalizeOutputName(name) {
  const cleaned = (name || "").trim() || `投标文件_${new Date().toISOString().slice(0, 10)}.docx`;
  return cleaned.toLowerCase().endsWith(".docx") ? cleaned : `${cleaned}.docx`;
}

function ensureProjectId() {
  const projectId = state.projectId.trim();
  if (!isValidUuid(projectId)) {
    throw new Error("请先手动输入项目 ID（UUID）");
  }
  return projectId;
}

function effectiveIndustryTag() {
  const inner = $("#expertIndustryTag").value.trim();
  return inner || state.industryTag || "";
}

function renderIndustryTagHistory() {
  const datalist = $("#engineeringCategoryHistory");
  if (!datalist) return;
  const options = [...new Set(state.industryTagHistory.map((item) => String(item || "").trim()).filter(Boolean))].slice(0, 20);
  datalist.innerHTML = options.map((item) => `<option value="${escapeHtml(item)}"></option>`).join("");
}

function rememberIndustryTag(raw) {
  const value = String(raw || "").trim();
  if (!value) return;
  state.industryTagHistory = [value, ...state.industryTagHistory.filter((item) => item !== value)].slice(0, 20);
  localStorage.setItem("be_industry_tag_history", JSON.stringify(state.industryTagHistory));
  renderIndustryTagHistory();
}

function applyIndustryTag(value, source = "") {
  const normalized = String(value || "").trim();
  state.industryTag = normalized;
  if (source !== "top" && $("#industryTagInput")) {
    $("#industryTagInput").value = normalized;
  }
  if (source !== "expert" && $("#expertIndustryTag")) {
    $("#expertIndustryTag").value = normalized;
  }
  if (normalized) {
    localStorage.setItem("be_industry_tag", normalized);
    rememberIndustryTag(normalized);
  } else {
    localStorage.removeItem("be_industry_tag");
  }
}

function setTaskStatus(text) {
  $("#taskStatusText").textContent = text;
}

function guarded(action) {
  return (...args) => {
    Promise.resolve(action(...args)).catch((error) => {
      console.error(error);
      const message = error instanceof Error ? error.message : String(error);
      if (!error || !error.__toastShown) Toast.error(message);
      setTaskStatus("操作失败，请检查输入后重试");
    });
  };
}

function updateOutlineBadge(text, level = "") {
  const badge = $("#outlineStatusBadge");
  badge.textContent = text;
  badge.classList.remove("ok", "warn", "error");
  if (level) badge.classList.add(level);
}

function focusPanel(panelId) {
  $$(".flow-item").forEach((node) => {
    node.classList.toggle("active", node.dataset.target === panelId);
  });
  $$(".view-panel").forEach((node) => {
    node.classList.toggle("active", node.id === panelId);
  });
}

function getSectionByKey(sectionKey) {
  return state.sections.find((item) => item.section_key === sectionKey) || null;
}

function sectionStatusLabel(status) {
  const mapping = {
    NEW: "待编写",
    PENDING: "生成中",
    SUPPORTED: "可确认",
    NEED_HUMAN_INPUT: "需人工补充",
    SECTION_CONFIRMED: "已确认",
    SECTION_REJECTED: "已退回",
    NEED_REWRITE: "需重写",
    FAILURE: "失败",
  };
  return mapping[status] || status || "待编写";
}

function shortText(text, limit = 88) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  if (value.length <= limit) return value;
  return `${value.slice(0, limit)}...`;
}

async function pollTask(taskId, { onTick, onDone, onError, timeoutMs = 180000, intervalMs = 2000 } = {}) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await api(`/v1/tasks/${taskId}`);
      onTick?.(res);
      if (["SUCCESS", "FAILURE", "REVOKED"].includes(res.status)) {
        onDone?.(res);
        return res;
      }
    } catch (err) {
      onError?.(err);
      throw err;
    }
    await sleep(intervalMs);
  }
  const timeoutError = new Error("任务轮询超时，请稍后在任务中心查看状态");
  onError?.(timeoutError);
  throw timeoutError;
}

const Navigation = {
  init() {
    $$(".flow-item").forEach((item) => {
      item.addEventListener("click", () => {
        const target = item.dataset.target;
        if (target) focusPanel(target);
      });
    });

    $("#btnUsePointsForOutline").addEventListener("click", () => {
      BidWorkbench.loadTenderPointsToOutline();
      focusPanel("panel-bid-hub");
    });

    $("#btnJumpToFeedback").addEventListener("click", () => {
      focusPanel("panel-expert-hub");
      Toast.info("请在“投标文件回灌专家库”中执行回灌操作");
    });
  },
};

const GlobalBar = {
  init() {
    Toast.init();
    $("#projectIdInput").value = state.projectId;
    $("#industryTagInput").value = state.industryTag;
    $("#expertIndustryTag").value = state.industryTag;
    if (state.industryTag) {
      rememberIndustryTag(state.industryTag);
    } else {
      renderIndustryTagHistory();
    }

    $("#projectIdInput").addEventListener("change", () => {
      const raw = $("#projectIdInput").value.trim();
      if (!raw) {
        state.projectId = "";
        localStorage.removeItem("be_project_id");
        if ($("#byokProjectId")) $("#byokProjectId").value = "";
        CompletedBidHub.syncProjectIdInput();
        guarded(() => CompletedBidHub.loadRecords())();
        Toast.info("项目 ID 已清空");
        guarded(() => ExpertHub.loadDocList())();
        guarded(() => TenderHub.loadRuns())();
        return;
      }
      if (!isValidUuid(raw)) {
        Toast.error("项目 ID 必须是 UUID 格式");
        return;
      }
      state.projectId = raw;
      localStorage.setItem("be_project_id", raw);
      if ($("#byokProjectId")) $("#byokProjectId").value = raw;
      CompletedBidHub.syncProjectIdInput();
      guarded(() => CompletedBidHub.loadRecords())();
      Toast.success("项目 ID 已更新");
      guarded(() => ExpertHub.loadDocList())();
      guarded(() => TenderHub.loadRuns())();
    });

    $("#industryTagInput").addEventListener("change", () => {
      applyIndustryTag($("#industryTagInput").value, "top");
      Toast.success(state.industryTag ? "工程类别已更新" : "工程类别已清空");
      guarded(() => ExpertHub.loadDocList())();
    });

    $("#expertIndustryTag").addEventListener("change", () => {
      applyIndustryTag($("#expertIndustryTag").value, "expert");
      Toast.success(state.industryTag ? "工程类别已更新" : "工程类别已清空");
    });

    $("#btnHealth").addEventListener(
      "click",
      guarded(async () => {
        try {
          await api("/health");
          $("#healthBadge").textContent = "在线";
          $("#healthBadge").style.color = "var(--success)";
        } catch {
          $("#healthBadge").textContent = "离线";
          $("#healthBadge").style.color = "var(--danger)";
        }
      }),
    );

    setInterval(() => {
      $("#clock").textContent = new Date().toLocaleTimeString("zh-CN");
    }, 1000);

    $("#btnHealth").click();
  },
};

const ExpertHub = {
  init() {
    $("#btnExpertIngest").addEventListener("click", guarded(() => this.ingestPdfFiles()));
    $("#btnStructuredIngest").addEventListener("click", guarded(() => this.ingestStructured()));
    $("#btnLibraryDocs").addEventListener("click", guarded(() => this.loadDocList()));
    $("#btnLibraryChunks").addEventListener("click", guarded(() => this.loadChunks()));
    $("#btnFeedbackPdfIngest").addEventListener("click", guarded(() => this.feedbackPdfIngest()));
    $("#btnFeedbackSectionUpsert").addEventListener("click", guarded(() => this.feedbackSectionUpsert()));
    this.loadDocList();
  },

  async ingestPdfFiles() {
    const files = Array.from($("#expertPdfFiles").files || []);
    if (!files.length) {
      Toast.error("请至少选择一个 PDF 文件");
      return;
    }

    const industryTag = effectiveIndustryTag();
    const docType = $("#expertDocType").value;
    const projectId = state.projectId.trim();
    const resultView = $("#expertIngestResult");
    const logs = [];

    setTaskStatus(`资料入库中（0/${files.length}）`);

    for (let idx = 0; idx < files.length; idx += 1) {
      const file = files[idx];
      const formData = new FormData();
      formData.append("file", file);
      formData.append("doc_type", docType);
      formData.append("industry_tag", industryTag);
      if (projectId) formData.append("project_id", projectId);

      try {
        const res = await api("/v1/expert-library/ingest-upload", {
          method: "POST",
          body: formData,
        });
        logs.push(`[${idx + 1}/${files.length}] ${file.name} -> SUCCEEDED | chunks=${res.chunk_count} | qdrant=${res.qdrant_upserted}`);
        setTaskStatus(`资料入库中（${idx + 1}/${files.length}）`);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        logs.push(`[${idx + 1}/${files.length}] ${file.name} -> FAILED | ${message}`);
      }
      resultView.textContent = logs.join("\n");
    }

    setTaskStatus("资料入库完成");
    Toast.success("PDF 入库流程完成");
    this.loadDocList();
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
        const text = `${item.title || item.expert_doc_id.slice(0, 8)} | ${item.doc_type} | 切片 ${item.chunk_count}`;
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
      view.innerHTML = `<p class="hint">该文档暂无切片。</p>`;
      setTaskStatus("切片加载完成");
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

    setTaskStatus(`切片加载完成（${res.items.length} 条）`);
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

const BidWorkbench = {
  init() {
    $("#btnLoadTenderPoints").addEventListener("click", guarded(() => this.loadTenderPointsToOutline()));
    $("#btnCreateOutline").addEventListener("click", guarded(() => this.createOutline()));
    $("#btnConfirmOutline").addEventListener("click", guarded(() => this.confirmOutline()));

    $("#btnRetrieveEvidence").addEventListener("click", guarded(() => this.retrieveEvidence()));
    $("#btnGenerateSection").addEventListener("click", guarded(() => this.generateSection()));
    $("#btnGenerateSelected").addEventListener("click", guarded(() => this.generateSection()));
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

const ReviewWorkbench = {
  init() {
    $("#btnRunSectionReview").addEventListener("click", guarded(() => this.runSectionReview()));
    $("#btnApplyReviewNote").addEventListener("click", guarded(() => this.applyReviewInteraction()));
    $("#btnBuildFinalDraft").addEventListener("click", guarded(() => this.buildFinalDraft()));
    $("#reviewSectionSelect").addEventListener("change", () => this.onSectionSwitch());
  },

  refreshSectionSelect() {
    const select = $("#reviewSectionSelect");
    const current = select.value;
    select.innerHTML = "";

    if (!state.sections.length) {
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "暂无章节";
      select.appendChild(empty);
      this.renderOverallMetrics();
      return;
    }

    state.sections.forEach((section) => {
      const option = document.createElement("option");
      option.value = section.section_key;
      option.textContent = `${section.section_key} ${section.section_title} | ${sectionStatusLabel(section.status)}`;
      select.appendChild(option);
    });

    if (current && getSectionByKey(current)) {
      select.value = current;
    }

    this.onSectionSwitch();
    this.renderOverallMetrics();
  },

  onSectionSwitch() {
    const section = getSectionByKey($("#reviewSectionSelect").value);
    if (!section) {
      $("#reviewUserNote").value = "";
      $("#reviewReport").innerHTML = `<p class="hint">审核后会显示本章合规与得分情况。</p>`;
      return;
    }

    $("#reviewUserNote").value = section.review?.userNote || "";
    $("#reviewDecision").value = section.reviewDecision || "PASS";
    this.renderReviewReport(section);
  },

  async runSectionReview() {
    const section = getSectionByKey($("#reviewSectionSelect").value);
    if (!section) {
      Toast.error("请先选择章节");
      return;
    }

    const draftText = section.finalDraft.trim();
    if (!draftText) {
      Toast.error("该章节暂无最终稿，无法审核");
      return;
    }

    const evidence = (section.evidenceHits || []).map((item) => ({
      evidence_id: item.chunk_id,
      text: item.text,
    }));

    const evidenceIds = evidence.map((item) => item.evidence_id);

    setTaskStatus(`章节审核中：${section.section_key}`);

    const validateRes = await api("/v1/generation/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        requirement_id: section.section_key,
        generated_text: draftText,
        evidence_ids: evidenceIds,
        evidence,
      }),
    });

    const pricingRes = await api("/v1/policy/pricing-fuse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: draftText }),
    });

    const coverage = Number(validateRes.coverage || 0);
    const baseScore = coverage * 70;
    const gateBonus = validateRes.status === "SUPPORTED" ? 20 : 8;
    const pricingBonus = pricingRes.blocked ? 0 : 10;
    const penalty = (validateRes.missing_sentences || []).length * 4;
    const score = Math.max(0, Math.min(100, Math.round(baseScore + gateBonus + pricingBonus - penalty)));

    section.review = {
      validate: validateRes,
      pricing: pricingRes,
      score,
      reviewedAt: new Date().toISOString(),
      userNote: section.review?.userNote || "",
    };

    this.renderReviewReport(section);
    this.renderOverallMetrics();

    setTaskStatus(`章节审核完成：${section.section_key}`);
    Toast.success(`章节审核完成，得分 ${score}`);
  },

  renderReviewReport(section) {
    const report = $("#reviewReport");
    const review = section.review;
    if (!review) {
      report.innerHTML = `<p class="hint">尚未执行审核。请点击“执行章节审核评分”。</p>`;
      return;
    }

    const missing = review.validate.missing_sentences || [];
    report.innerHTML = `
      <div class="review-line"><span>章节</span><strong>${escapeHtml(section.section_key)} ${escapeHtml(section.section_title)}</strong></div>
      <div class="review-line"><span>合规状态</span><strong>${escapeHtml(review.validate.status)}</strong></div>
      <div class="review-line"><span>覆盖率</span><strong>${(Number(review.validate.coverage || 0) * 100).toFixed(1)}%</strong></div>
      <div class="review-line"><span>价格内容熔断</span><strong>${review.pricing.blocked ? "触发（需处理）" : "未触发"}</strong></div>
      <div class="review-line"><span>本章评分</span><strong>${review.score}</strong></div>
      <div class="review-line"><span>缺失提示</span><strong>${escapeHtml(missing.length ? missing.join("；") : "无")}</strong></div>
    `;
  },

  applyReviewInteraction() {
    const section = getSectionByKey($("#reviewSectionSelect").value);
    if (!section) {
      Toast.error("请先选择章节");
      return;
    }

    const decision = $("#reviewDecision").value;
    const note = $("#reviewUserNote").value.trim();

    section.reviewDecision = decision;
    section.review = section.review || { score: 0, validate: { coverage: 0, status: "NEED_HUMAN_INPUT", missing_sentences: [] }, pricing: { blocked: false, reasons: [] } };
    section.review.userNote = note;

    if (note) {
      const block = `\n\n【审核交互记录】\n结论：${decision}\n说明：${note}`;
      if (!section.finalDraft.includes("【审核交互记录】")) {
        section.finalDraft = `${section.finalDraft.trim()}${block}`.trim();
      }
    }

    if (decision === "REWRITE") {
      section.status = "NEED_REWRITE";
    } else if (decision === "ADJUST_PASS") {
      section.status = section.status === "SECTION_CONFIRMED" ? "SECTION_CONFIRMED" : "SUPPORTED";
    } else if (section.status === "NEW" || section.status === "NEED_REWRITE") {
      section.status = "SUPPORTED";
    }

    BidWorkbench.renderSectionList();
    BidWorkbench.renderSectionEditor();
    this.renderReviewReport(section);
    this.renderOverallMetrics();

    Toast.success("审核交互结果已应用到章节最终稿");
  },

  buildFinalDraft() {
    const completedSections = state.sections
      .filter((section) => section.finalDraft && section.finalDraft.trim())
      .sort((a, b) => a.section_key.localeCompare(b.section_key, "zh-CN"));

    if (!completedSections.length) {
      Toast.error("尚无可汇总章节");
      return false;
    }

    const header = [
      `项目ID：${state.projectId || "未设置"}`,
      `编制时间：${new Date().toLocaleString("zh-CN")}`,
      state.analysisDetail?.run?.filename ? `对应招标文件：${state.analysisDetail.run.filename}` : "",
    ]
      .filter(Boolean)
      .join("\n");

    const body = completedSections
      .map((section) => `# ${section.section_key} ${section.section_title}\n\n${section.finalDraft.trim()}`)
      .join("\n\n");

    state.finalBidDraft = `${header}\n\n${body}`;
    $("#finalDraftPreview").value = state.finalBidDraft;
    $("#publishFinalDraft").value = state.finalBidDraft;

    this.renderOverallMetrics();
    Toast.success("最终投标文件已形成，可进入排版与终审");
    return true;
  },

  renderOverallMetrics() {
    const total = state.sections.length;
    const confirmed = state.sections.filter((section) => section.status === "SECTION_CONFIRMED").length;
    const reviewed = state.sections.filter((section) => section.review).length;
    const scores = state.sections.map((section) => section.review?.score).filter((score) => typeof score === "number");
    const avgScore = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;

    const ready = total > 0 && confirmed === total && reviewed === total && avgScore >= 75;

    $("#reviewOverallMetrics").innerHTML = [
      { k: "章节总数", v: total },
      { k: "已确认章节", v: confirmed },
      { k: "已审核章节", v: reviewed },
      { k: "平均得分", v: avgScore },
      { k: "可终审状态", v: ready ? "是" : "否" },
    ]
      .map(
        (item) => `
          <div class="summary-card">
            <div class="k">${escapeHtml(String(item.k))}</div>
            <div class="v">${escapeHtml(String(item.v))}</div>
          </div>
        `,
      )
      .join("");
  },
};

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

    return { page, styles };
  },

  buildTypesetSummary(config) {
    const page = config.page;
    const pageLine = `封面=${page.coverTemplate} | 页眉="${page.headerText}"(${page.headerOffset}cm) | 页脚="${page.footerText}"(${page.footerOffset}cm) | 页边距 上${page.marginTop}/下${page.marginBottom}/左${page.marginLeft}/右${page.marginRight} cm`;
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

    setTaskStatus("WPS 排版导出中");
    $("#renderResult").textContent = "正在生成 docx，请稍候...";

    const res = await api("/v1/render/word", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        output_path: filename,
        placeholders: {
          project_name: state.projectId || "未命名项目",
          technical_plan: technicalPlan,
          implementation_plan: implementationPlan,
        },
      }),
    });

    $("#renderResult").textContent = `导出完成：${res.output_path}`;
    setTaskStatus("WPS 排版导出完成");
    Toast.success("WPS 排版稿已生成");
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
      <div class="review-line"><span>终审建议</span><strong>${
        !check.pricingBlocked && check.mustRatio >= 0.85 && check.sectionReady >= 1 && check.typesetReady ? "可锁定交付" : "请先按提示调整"
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

const ByokSettings = {
  init() {
    $("#btnOpenByokSettings").addEventListener("click", guarded(() => this.open()));
    $("#btnCloseByokSettings").addEventListener("click", () => this.close());
    $("#drawerByok").addEventListener("click", (event) => {
      if (event.target === $("#drawerByok")) this.close();
    });

    $("#btnByokLoadProfiles").addEventListener("click", guarded(() => this.loadProfiles()));
    $("#btnByokLoadPolicy").addEventListener("click", guarded(() => this.loadPolicy()));
    $("#btnByokCreateProfile").addEventListener("click", guarded(() => this.createProfile()));
    $("#btnByokSavePolicy").addEventListener("click", guarded(() => this.savePolicy()));
    $("#btnByokPresetQwen3").addEventListener("click", () => this.applyQwen3Preset());
    $("#byokProvider").addEventListener("change", () => this.onProviderChange());
    $("#byokProfileList").addEventListener("click", guarded((event) => this.onProfileAction(event)));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !$("#drawerByok").classList.contains("hidden")) this.close();
    });

    this.applyQwen3Preset();
    this.renderProfileOptions();
  },

  async open() {
    const projectId = ensureProjectId();
    $("#byokProjectId").value = projectId;
    $("#drawerByok").classList.remove("hidden");
    await this.loadProfiles();
    await this.loadPolicy();
  },

  close() {
    $("#drawerByok").classList.add("hidden");
  },

  projectId() {
    const raw = ($("#byokProjectId").value || "").trim();
    if (!isValidUuid(raw)) {
      throw new Error("模型设置项目 ID 必须是 UUID");
    }
    if (state.projectId !== raw) {
      state.projectId = raw;
      $("#projectIdInput").value = raw;
      localStorage.setItem("be_project_id", raw);
      CompletedBidHub.syncProjectIdInput();
    }
    return raw;
  },

  applyQwen3Preset() {
    $("#byokProvider").value = "qwen";
    $("#byokModelName").value = "qwen3";
    if (!$("#byokBaseUrl").value.trim()) {
      $("#byokBaseUrl").value = "https://dashscope.aliyuncs.com/compatible-mode/v1";
    }
    $("#byokResult").textContent = "已预置默认模型：百炼 qwen3";
  },

  onProviderChange() {
    const provider = $("#byokProvider").value;
    if (provider === "qwen") {
      if (!$("#byokModelName").value.trim()) $("#byokModelName").value = "qwen3";
      if (!$("#byokBaseUrl").value.trim()) {
        $("#byokBaseUrl").value = "https://dashscope.aliyuncs.com/compatible-mode/v1";
      }
    }
  },

  roleSelectIds() {
    return [
      "#byokWorkflowExpert",
      "#byokWorkflowEmbed",
      "#byokWorkflowTender",
      "#byokWorkflowBid",
      "#byokWorkflowReview",
      "#byokWorkflowPublish",
    ];
  },

  isEmbeddingProfile(profile) {
    const provider = String(profile?.provider || "").toLowerCase();
    const model = String(profile?.default_model || "").toLowerCase();
    const tasks = Array.isArray(profile?.allowed_tasks)
      ? profile.allowed_tasks.map((item) => String(item || "").toUpperCase())
      : [];
    if (tasks.includes("EMBED") || tasks.includes("EMBEDDING")) return true;
    if (provider === "voyage") return true;
    return /(embedding|embed|text-embedding|bge|gte|m3e|e5|jina|vector)/.test(model);
  },

  profilesForRole(selectId, profiles) {
    if (selectId !== "#byokWorkflowEmbed") return profiles;
    return profiles.filter((item) => this.isEmbeddingProfile(item));
  },

  renderProfileOptions(selected = {}) {
    const defaultLabelByRole = {
      "#byokWorkflowEmbed": "系统默认（Embedding 默认链路）",
    };
    const defaultLabel = "系统默认（百炼 qwen3）";
    const profiles = state.byokProfiles || [];

    this.roleSelectIds().forEach((id) => {
      const select = $(id);
      if (!select) return;
      const previous = selected[id] ?? select.value ?? "";
      const roleProfiles = this.profilesForRole(id, profiles);
      select.innerHTML = "";

      const defaultOption = document.createElement("option");
      defaultOption.value = "";
      defaultOption.textContent = defaultLabelByRole[id] || defaultLabel;
      select.appendChild(defaultOption);

      roleProfiles.forEach((profile) => {
        const option = document.createElement("option");
        option.value = profile.id;
        option.textContent = `${profile.provider}:${profile.default_model}`;
        select.appendChild(option);
      });

      if (roleProfiles.some((item) => item.id === previous)) {
        select.value = previous;
      } else {
        select.value = "";
      }
    });

    const list = $("#byokProfileList");
    if (!profiles.length) {
      list.innerHTML = `<p class="hint" style="padding:0.65rem">暂无 profile，请先创建。</p>`;
      return;
    }

    list.innerHTML = profiles
      .map(
        (profile) => `
          <div class="byok-profile-item">
            <div class="byok-profile-meta">
              <div><strong>${escapeHtml(profile.provider)}:${escapeHtml(profile.default_model)}</strong></div>
              <div>ID: ${escapeHtml(profile.id)}</div>
              <div>Base URL: ${escapeHtml(profile.base_url || "-")}</div>
              <div>Tasks: ${escapeHtml((profile.allowed_tasks || ["*"]).join(","))}</div>
            </div>
            <div class="byok-profile-actions">
              <button class="btn btn-outline btn-sm" data-action="test" data-id="${escapeHtml(profile.id)}" type="button">测试</button>
              <button class="btn btn-outline btn-sm" data-action="delete" data-id="${escapeHtml(profile.id)}" type="button">删除</button>
            </div>
          </div>
        `,
      )
      .join("");
  },

  async loadProfiles() {
    const projectId = this.projectId();
    const res = await api(`/api/provider-profiles?project_id=${encodeURIComponent(projectId)}`);
    state.byokProfiles = res.items || [];
    this.renderProfileOptions();
    $("#byokResult").textContent = `已加载 ${state.byokProfiles.length} 个 profiles`;
  },

  async onProfileAction(event) {
    const target = event.target.closest("button[data-action]");
    if (!target) return;
    const action = target.dataset.action;
    const profileId = target.dataset.id;
    if (!profileId) return;

    if (action === "test") {
      const res = await api(`/api/provider-profiles/${profileId}/test`, { method: "POST" });
      $("#byokResult").textContent = JSON.stringify(res, null, 2);
      Toast.info(`测试完成: ${res.ok ? "OK" : "FAIL"}`);
      return;
    }

    if (action === "delete") {
      await api(`/api/provider-profiles/${profileId}`, { method: "DELETE" });
      Toast.success("Profile 已删除");
      await this.loadProfiles();
      await this.loadPolicy();
    }
  },

  async createProfile() {
    const projectId = this.projectId();
    const provider = $("#byokProvider").value;
    const defaultModel = ($("#byokModelName").value || "").trim();
    const apiKey = ($("#byokApiKey").value || "").trim();
    const baseUrl = ($("#byokBaseUrl").value || "").trim();
    const keyStorage = $("#byokKeyStorage").value;

    if (!defaultModel) throw new Error("请填写模型名称");
    if (!apiKey) throw new Error("请填写 API Key");

    const payload = {
      project_id: projectId,
      provider,
      base_url: baseUrl || null,
      default_model: defaultModel,
      api_key: apiKey,
      key_storage: keyStorage,
      allowed_tasks: ["*"],
    };

    const res = await api("/api/provider-profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    $("#byokApiKey").value = "";
    $("#byokResult").textContent = JSON.stringify(res, null, 2);
    Toast.success("Profile 创建成功");
    await this.loadProfiles();
  },

  async loadPolicy() {
    const projectId = this.projectId();
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/model-policy`);
    if (response.status === 404) {
      this.renderProfileOptions({
        "#byokWorkflowExpert": "",
        "#byokWorkflowEmbed": "",
        "#byokWorkflowTender": "",
        "#byokWorkflowBid": "",
        "#byokWorkflowReview": "",
        "#byokWorkflowPublish": "",
      });
      $("#byokResult").textContent = "当前项目尚未绑定流程模型策略，使用默认（通用：百炼 qwen3；Embedding：系统默认链路）";
      return;
    }
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `加载策略失败: ${response.status}`);
    }
    const policy = await response.json();
    this.renderProfileOptions({
      "#byokWorkflowExpert": policy.extract_profile_id || "",
      "#byokWorkflowEmbed": policy.embed_profile_id || "",
      "#byokWorkflowTender": policy.query_rewrite_profile_id || "",
      "#byokWorkflowBid": policy.generate_profile_id || "",
      "#byokWorkflowReview": policy.review_profile_id || "",
      "#byokWorkflowPublish": policy.program_support_profile_id || "",
    });
    $("#byokResult").textContent = JSON.stringify(policy, null, 2);
  },

  async savePolicy() {
    const projectId = this.projectId();
    const profileExpert = $("#byokWorkflowExpert").value || null;
    const profileEmbed = $("#byokWorkflowEmbed").value || null;
    const profileTender = $("#byokWorkflowTender").value || null;
    const profileBid = $("#byokWorkflowBid").value || null;
    const profileReview = $("#byokWorkflowReview").value || null;
    const profilePublish = $("#byokWorkflowPublish").value || null;

    const payload = {
      extract_profile_id: profileExpert,
      embed_profile_id: profileEmbed,
      query_rewrite_profile_id: profileTender,
      generate_profile_id: profileBid,
      review_profile_id: profileReview,
      program_support_profile_id: profilePublish,
      enable_review: true,
    };

    const res = await api(`/api/projects/${encodeURIComponent(projectId)}/model-policy`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    $("#byokResult").textContent = JSON.stringify(res, null, 2);
    Toast.success("流程模型策略已保存");
  },
};

document.addEventListener("DOMContentLoaded", () => {
  GlobalBar.init();
  Navigation.init();
  ExpertHub.init();
  TenderHub.init();
  BidWorkbench.init();
  ReviewWorkbench.init();
  PublishHub.init();
  CompletedBidHub.init();
  ByokSettings.init();

  updateOutlineBadge("未生成");
  setTaskStatus("工作台已就绪");
  console.log("AI辅助投标系统 Loaded");
});
