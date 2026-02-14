const ui = {
  healthBadge: document.getElementById("healthBadge"),
  ingestResult: document.getElementById("ingestResult"),
  taskResult: document.getElementById("taskResult"),
  expertResult: document.getElementById("expertResult"),
  searchResult: document.getElementById("searchResult"),
  generateResult: document.getElementById("generateResult"),
  byokResult: document.getElementById("byokResult"),
  reviewRiskBanner: document.getElementById("reviewRiskBanner"),
  libraryResult: document.getElementById("libraryResult"),
  tenderAnalysisResult: document.getElementById("tenderAnalysisResult"),
  tenderInsightView: document.getElementById("tenderInsightView"),
};

let currentEventSource = null;
let currentProfiles = [];
let currentLibraryDocs = [];
let currentAnalysisRuns = [];

const CATEGORY_LABELS = {
  BIDDING_POINTS: "投标要点",
  SCORING_POINTS: "评分要点",
  COMPLIANCE_REQUIREMENTS: "符合性要求",
  BONUS_POINTS: "加分项",
  RISK_ALERTS: "风险提示",
};
const CATEGORY_ORDER = [
  "BIDDING_POINTS",
  "SCORING_POINTS",
  "COMPLIANCE_REQUIREMENTS",
  "BONUS_POINTS",
  "RISK_ALERTS",
];

function setResult(el, data) {
  el.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const text = await res.text();
  const body = text ? JSON.parse(text) : {};
  if (!res.ok) throw new Error(JSON.stringify(body));
  return body;
}

function bindTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((x) => x.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(tab.dataset.tab).classList.add("active");
    });
  });
}

function bindClock() {
  const el = document.getElementById("clock");
  setInterval(() => {
    el.textContent = new Date().toLocaleString();
  }, 1000);
}

function getByokProjectId() {
  const value = document.getElementById("byokProjectId").value.trim();
  if (!value) throw new Error("请先输入项目 ID");
  return value;
}

function updateProfileSelects() {
  const ids = ["generateProfileId", "reviewProfileId", "embedProfileId"];
  ids.forEach((id) => {
    const select = document.getElementById(id);
    select.innerHTML = "";
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "(未绑定)";
    select.appendChild(empty);
    currentProfiles.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = `${item.provider} / ${item.default_model} / ${item.id.slice(0, 8)}`;
      select.appendChild(option);
    });
  });
}

function showReviewRisk(warnings = []) {
  const riskWarning = warnings.find((w) =>
    ["review_fallback_local_validator", "review_fallback_provider_used"].includes(w),
  );
  if (!riskWarning) {
    ui.reviewRiskBanner.textContent = "";
    ui.reviewRiskBanner.classList.add("hidden");
    return;
  }
  if (riskWarning === "review_fallback_provider_used") {
    ui.reviewRiskBanner.textContent = "注意：主审查模型不可用，已启用备用审查模型。";
  } else {
    ui.reviewRiskBanner.textContent = "风险：审查模型不可用，本次仅执行本地验证器，未进行强推理审查。";
  }
  ui.reviewRiskBanner.classList.remove("hidden");
}

function bindHealth() {
  document.getElementById("btnHealth").addEventListener("click", async () => {
    try {
      await api("/health");
      ui.healthBadge.textContent = "连接正常";
      ui.healthBadge.className = "badge badge-ok";
    } catch (e) {
      ui.healthBadge.textContent = "连接失败";
      ui.healthBadge.className = "badge badge-warn";
      console.error(e);
    }
  });
}

function getPdf() {
  const file = document.getElementById("pdfFile").files[0];
  if (!file) throw new Error("请先选择 PDF 文件");
  return file;
}

async function uploadPdf(path) {
  const fd = new FormData();
  fd.append("file", getPdf());
  return api(path, { method: "POST", body: fd });
}

function bindIngest() {
  document.getElementById("btnIngestSync").addEventListener("click", async () => {
    try {
      setResult(ui.ingestResult, "处理中...");
      const data = await uploadPdf("/v1/tender/ingest-upload");
      setResult(ui.ingestResult, data);
    } catch (e) {
      setResult(ui.ingestResult, String(e));
    }
  });

  document.getElementById("btnIngestAsync").addEventListener("click", async () => {
    try {
      setResult(ui.ingestResult, "提交后台任务...");
      const data = await uploadPdf("/v1/tasks/ingest-upload");
      setResult(ui.ingestResult, data);
      document.getElementById("taskId").value = data.task_id;
    } catch (e) {
      setResult(ui.ingestResult, String(e));
    }
  });
}

function bindTask() {
  document.getElementById("btnTaskQuery").addEventListener("click", async () => {
    const taskId = document.getElementById("taskId").value.trim();
    if (!taskId) return setResult(ui.taskResult, "请输入任务 ID");
    try {
      const data = await api(`/v1/tasks/${taskId}`);
      setResult(ui.taskResult, data);
    } catch (e) {
      setResult(ui.taskResult, String(e));
    }
  });

  document.getElementById("btnTaskStream").addEventListener("click", () => {
    const taskId = document.getElementById("taskId").value.trim();
    if (!taskId) return setResult(ui.taskResult, "请输入任务 ID");

    if (currentEventSource) currentEventSource.close();
    currentEventSource = new EventSource(`/v1/tasks/${taskId}/stream`);
    currentEventSource.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      setResult(ui.taskResult, data);
      if (["SUCCESS", "FAILURE", "REVOKED"].includes(data.status)) {
        currentEventSource.close();
      }
    };
    currentEventSource.onerror = () => {
      currentEventSource.close();
    };
  });
}

function bindExpert() {
  document.getElementById("btnUpsert").addEventListener("click", async () => {
    const expertDocId = document.getElementById("expertDocId").value.trim();
    const industryTag = document.getElementById("industryTag").value.trim();
    const lines = document
      .getElementById("expertLines")
      .value.split("\n")
      .map((x) => x.trim())
      .filter(Boolean);

    const chunks = lines.map((text, idx) => ({
      chunk_id: `chunk-${String(idx + 1).padStart(3, "0")}`,
      text,
      doc_type: "CASE",
      section_type: "实施计划",
      industry_tag: industryTag || null,
      sensitivity_level: "PUBLIC_OK",
      valid_to: null,
      forbidden_tags: [],
      quality_score: 85,
      source_locator: { from: "ui_manual_input", line: idx + 1 },
    }));

    try {
      const data = await api("/v1/evidence/upsert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expert_doc_id: expertDocId || "doc-ui-001", chunks }),
      });
      setResult(ui.expertResult, data);
      document.getElementById("taskId").value = data.task_id;
    } catch (e) {
      setResult(ui.expertResult, String(e));
    }
  });
}

function bindSearchAndGenerate() {
  document.getElementById("btnSearch").addEventListener("click", async () => {
    try {
      const query = document.getElementById("searchQuery").value.trim();
      const industryTag = document.getElementById("industryTag").value.trim();
      const data = await api("/v1/evidence/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: 6, industry_tag: industryTag || null }),
      });
      setResult(ui.searchResult, data);
    } catch (e) {
      setResult(ui.searchResult, String(e));
    }
  });

  document.getElementById("btnGenerate").addEventListener("click", async () => {
    try {
      const query = document.getElementById("searchQuery").value.trim();
      const industryTag = document.getElementById("industryTag").value.trim();
      const projectId = document.getElementById("projectId").value.trim() || null;
      const data = await api("/v1/generation/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          requirement_id: "REQ-UI-001",
          requirement_text: query,
          top_k: 6,
          project_id: projectId,
          industry_tag: industryTag || null,
          tender_template_id: "tmpl-ui",
        }),
      });
      const view = {
        llm_provider: data.llm_provider,
        llm_model: data.llm_model,
        status: data.status,
        coverage: data.coverage,
        cache_hit: data.cache_hit,
        budget_remaining: data.budget_remaining,
        warnings: data.warnings,
        evidence_ids: data.evidence_ids,
        generated_text: data.generated_text,
      };
      setResult(ui.generateResult, view);
      showReviewRisk(data.warnings || []);
    } catch (e) {
      setResult(ui.generateResult, String(e));
      showReviewRisk([]);
    }
  });

  document.getElementById("btnSanitize").addEventListener("click", async () => {
    try {
      const data = await api("/v1/policy/sanitize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: document.getElementById("searchQuery").value,
          strategy: "mask",
          allowlist: [],
        }),
      });
      setResult(ui.generateResult, data);
    } catch (e) {
      setResult(ui.generateResult, String(e));
    }
  });
}

async function loadProfiles(projectId) {
  const data = await api(`/api/provider-profiles?project_id=${encodeURIComponent(projectId)}`);
  currentProfiles = data.items || [];
  updateProfileSelects();
  return data;
}

function bindByok() {
  document.getElementById("btnLoadProfiles").addEventListener("click", async () => {
    try {
      const projectId = getByokProjectId();
      const data = await loadProfiles(projectId);
      setResult(ui.byokResult, data);
    } catch (e) {
      setResult(ui.byokResult, String(e));
    }
  });

  document.getElementById("btnCreateProfile").addEventListener("click", async () => {
    try {
      const projectId = getByokProjectId();
      const payload = {
        project_id: projectId,
        provider: document.getElementById("providerName").value,
        base_url: document.getElementById("providerBaseUrl").value.trim() || null,
        default_model: document.getElementById("providerModel").value.trim(),
        api_key: document.getElementById("providerApiKey").value.trim(),
        key_storage: document.getElementById("providerStorage").value,
        allowed_tasks: ["*"],
      };
      const created = await api("/api/provider-profiles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const listed = await loadProfiles(projectId);
      setResult(ui.byokResult, { created, listed });
    } catch (e) {
      setResult(ui.byokResult, String(e));
    }
  });

  document.getElementById("btnTestProfile").addEventListener("click", async () => {
    try {
      const profileId = document.getElementById("generateProfileId").value;
      if (!profileId) throw new Error("请先在下拉中选择一个 Profile");
      const data = await api(`/api/provider-profiles/${profileId}/test`, { method: "POST" });
      setResult(ui.byokResult, data);
    } catch (e) {
      setResult(ui.byokResult, String(e));
    }
  });

  document.getElementById("btnBindPolicy").addEventListener("click", async () => {
    try {
      const projectId = getByokProjectId();
      const payload = {
        generate_profile_id: document.getElementById("generateProfileId").value || null,
        review_profile_id: document.getElementById("reviewProfileId").value || null,
        embed_profile_id: document.getElementById("embedProfileId").value || null,
        enable_review: document.getElementById("enableReview").value === "true",
      };
      const data = await api(`/api/projects/${projectId}/model-policy`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setResult(ui.byokResult, data);
    } catch (e) {
      setResult(ui.byokResult, String(e));
    }
  });

  document.getElementById("btnLoadPolicy").addEventListener("click", async () => {
    try {
      const projectId = getByokProjectId();
      const data = await api(`/api/projects/${projectId}/model-policy`);
      ["generateProfileId", "reviewProfileId", "embedProfileId"].forEach((id) => {
        document.getElementById(id).value = data[`${id.replace("ProfileId", "_profile_id")}`] || "";
      });
      document.getElementById("enableReview").value = data.enable_review ? "true" : "false";
      setResult(ui.byokResult, data);
    } catch (e) {
      setResult(ui.byokResult, String(e));
    }
  });

  document.getElementById("btnSyncProjectId").addEventListener("click", () => {
    document.getElementById("projectId").value = document.getElementById("byokProjectId").value.trim();
  });
}

function _setLibraryDocOptions() {
  const select = document.getElementById("libraryDocSelect");
  select.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "请选择专家文档";
  select.appendChild(empty);
  currentLibraryDocs.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.expert_doc_id;
    option.textContent = `${item.title || "untitled"} / chunks:${item.chunk_count}`;
    select.appendChild(option);
  });
}

function _splitTextareaLines(id) {
  return document
    .getElementById(id)
    .value.split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function _syncLibraryModelInput() {
  const preset = document.getElementById("libraryModelPreset").value;
  const customInput = document.getElementById("libraryModelCustom");
  const isCustom = preset === "custom";
  customInput.disabled = !isCustom;
  if (!isCustom) customInput.value = "";
}

function _resolveLibraryModelId() {
  const preset = document.getElementById("libraryModelPreset").value.trim();
  const custom = document.getElementById("libraryModelCustom").value.trim();
  if (preset === "custom") return custom;
  return preset;
}

function bindLibrary() {
  document.getElementById("libraryModelPreset").addEventListener("change", _syncLibraryModelInput);
  _syncLibraryModelInput();

  document.getElementById("btnLibraryIngest").addEventListener("click", async () => {
    try {
      const file = document.getElementById("libraryPdfFile").files[0];
      if (!file) throw new Error("请先选择历史标书 PDF");
      const fd = new FormData();
      fd.append("file", file);
      const projectId = document.getElementById("libraryProjectId").value.trim();
      const industryTag = document.getElementById("libraryIndustryTag").value.trim();
      const title = document.getElementById("libraryTitle").value.trim();
      const modelId = _resolveLibraryModelId();
      if (document.getElementById("libraryModelPreset").value === "custom" && !modelId) {
        throw new Error("请选择预设模型，或填写自定义模型 ID");
      }
      if (projectId) fd.append("project_id", projectId);
      if (industryTag) fd.append("industry_tag", industryTag);
      if (title) fd.append("title", title);
      if (modelId) fd.append("model_id", modelId);

      setResult(ui.libraryResult, "入库处理中...");
      const data = await api("/v1/expert-library/ingest-upload", { method: "POST", body: fd });
      setResult(ui.libraryResult, data);
    } catch (e) {
      setResult(ui.libraryResult, String(e));
    }
  });

  document.getElementById("btnLibraryDocs").addEventListener("click", async () => {
    try {
      const params = new URLSearchParams();
      const projectId = document.getElementById("libraryProjectId").value.trim();
      const industryTag = document.getElementById("libraryIndustryTag").value.trim();
      if (projectId) params.set("project_id", projectId);
      if (industryTag) params.set("industry_tag", industryTag);
      const data = await api(`/v1/expert-library/docs?${params.toString()}`);
      currentLibraryDocs = data.items || [];
      _setLibraryDocOptions();
      setResult(ui.libraryResult, data);
    } catch (e) {
      setResult(ui.libraryResult, String(e));
    }
  });

  document.getElementById("btnLibraryStructuredIngest").addEventListener("click", async () => {
    try {
      const payload = {
        project_id: document.getElementById("libraryProjectId").value.trim() || null,
        industry_tag: document.getElementById("libraryIndustryTag").value.trim() || null,
        created_by: "ui_user",
        standard_items: _splitTextareaLines("structuredStandard"),
        company_performance_items: _splitTextareaLines("structuredCompanyPerformance"),
        company_qualification_items: _splitTextareaLines("structuredCompanyQualification"),
        pm_qualification_performance_items: _splitTextareaLines("structuredPmQualificationPerformance"),
      };
      setResult(ui.libraryResult, "结构化资料入库处理中...");
      const data = await api("/v1/expert-library/ingest-structured", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setResult(ui.libraryResult, data);
      const projectId = document.getElementById("libraryProjectId").value.trim();
      const params = new URLSearchParams();
      if (projectId) params.set("project_id", projectId);
      const industryTag = document.getElementById("libraryIndustryTag").value.trim();
      if (industryTag) params.set("industry_tag", industryTag);
      const docs = await api(`/v1/expert-library/docs?${params.toString()}`);
      currentLibraryDocs = docs.items || [];
      _setLibraryDocOptions();
    } catch (e) {
      setResult(ui.libraryResult, String(e));
    }
  });

  document.getElementById("btnLibraryChunks").addEventListener("click", async () => {
    try {
      const expertDocId = document.getElementById("libraryDocSelect").value;
      if (!expertDocId) throw new Error("请先选择专家文档");
      const data = await api(`/v1/expert-library/docs/${expertDocId}/chunks`);
      setResult(ui.libraryResult, data);
    } catch (e) {
      setResult(ui.libraryResult, String(e));
    }
  });

  document.getElementById("btnLibrarySyncSearch").addEventListener("click", () => {
    document.getElementById("industryTag").value = document.getElementById("libraryIndustryTag").value.trim();
  });
}

function _setAnalysisRunOptions() {
  const select = document.getElementById("analysisRunSelect");
  select.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "请选择分析记录";
  select.appendChild(empty);
  currentAnalysisRuns.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.run_id;
    option.textContent = `${item.filename} / ${item.status} / ${item.created_at.slice(0, 19)}`;
    select.appendChild(option);
  });
}

function renderTenderInsights(detail) {
  if (!detail || !Array.isArray(detail.key_infos)) {
    ui.tenderInsightView.classList.add("hidden");
    ui.tenderInsightView.innerHTML = "";
    return;
  }
  const summary = detail.summary || {};
  const categoryCounts = summary.category_counts || {};
  const byCategory = {};
  detail.key_infos.forEach((item) => {
    const key = item.category || "BIDDING_POINTS";
    if (!byCategory[key]) byCategory[key] = [];
    byCategory[key].push(item);
  });

  let html = `<div class="insight-summary"><strong>总条目：</strong>${escapeHtml(summary.total_items || 0)}</div>`;
  CATEGORY_ORDER.forEach((key) => {
    const items = byCategory[key] || [];
    const label = CATEGORY_LABELS[key] || key;
    html += `<section class="insight-card"><h4>${escapeHtml(label)} (${escapeHtml(categoryCounts[key] || items.length)})</h4>`;
    if (!items.length) {
      html += '<p class="hint">未识别到该类信息。</p></section>';
      return;
    }
    html += "<ul>";
    items.slice(0, 20).forEach((item) => {
      const meta = [
        item.page_no ? `第${item.page_no}页` : null,
        item.section_anchor ? item.section_anchor : null,
        item.score_weight != null ? `分值:${item.score_weight}` : null,
        item.is_must ? "必须项" : null,
      ]
        .filter(Boolean)
        .join(" | ");
      html += `<li><div class="insight-text">${escapeHtml(item.content)}</div><div class="insight-meta">${escapeHtml(meta)}</div></li>`;
    });
    html += "</ul></section>";
  });

  ui.tenderInsightView.innerHTML = html;
  ui.tenderInsightView.classList.remove("hidden");
}

async function loadTenderRuns(projectId) {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  const data = await api(`/v1/tender/analysis-runs?${params.toString()}`);
  currentAnalysisRuns = data.items || [];
  _setAnalysisRunOptions();
  return data;
}

function bindTenderAnalysis() {
  document.getElementById("btnTenderAnalyze").addEventListener("click", async () => {
    try {
      const file = document.getElementById("analysisPdfFile").files[0];
      if (!file) throw new Error("请先选择招标 PDF");
      const projectId = document.getElementById("analysisProjectId").value.trim();
      const fd = new FormData();
      fd.append("file", file);
      if (projectId) fd.append("project_id", projectId);
      fd.append("created_by", "ui_user");
      setResult(ui.tenderAnalysisResult, "分析处理中...");
      const data = await api("/v1/tender/analyze-upload", { method: "POST", body: fd });
      setResult(ui.tenderAnalysisResult, data);
      await loadTenderRuns(projectId);
      document.getElementById("analysisRunSelect").value = data.run_id;
      const detail = await api(`/v1/tender/analysis-runs/${data.run_id}`);
      renderTenderInsights(detail);
    } catch (e) {
      setResult(ui.tenderAnalysisResult, String(e));
      renderTenderInsights(null);
    }
  });

  document.getElementById("btnTenderRuns").addEventListener("click", async () => {
    try {
      const projectId = document.getElementById("analysisProjectId").value.trim();
      const data = await loadTenderRuns(projectId);
      setResult(ui.tenderAnalysisResult, data);
    } catch (e) {
      setResult(ui.tenderAnalysisResult, String(e));
    }
  });

  document.getElementById("btnTenderDetail").addEventListener("click", async () => {
    try {
      const runId = document.getElementById("analysisRunSelect").value;
      if (!runId) throw new Error("请先选择分析记录");
      const detail = await api(`/v1/tender/analysis-runs/${runId}`);
      setResult(ui.tenderAnalysisResult, detail);
      renderTenderInsights(detail);
    } catch (e) {
      setResult(ui.tenderAnalysisResult, String(e));
      renderTenderInsights(null);
    }
  });

  document.getElementById("btnTenderSyncProject").addEventListener("click", () => {
    const projectId = document.getElementById("analysisProjectId").value.trim();
    document.getElementById("projectId").value = projectId;
    document.getElementById("libraryProjectId").value = projectId;
  });
}

bindTabs();
bindClock();
bindHealth();
bindByok();
bindIngest();
bindTenderAnalysis();
bindTask();
bindExpert();
bindSearchAndGenerate();
bindLibrary();
