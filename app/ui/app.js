const ui = {
  healthBadge: document.getElementById("healthBadge"),
  ingestResult: document.getElementById("ingestResult"),
  taskResult: document.getElementById("taskResult"),
  expertResult: document.getElementById("expertResult"),
  searchResult: document.getElementById("searchResult"),
  generateResult: document.getElementById("generateResult"),
};

let currentEventSource = null;

function setResult(el, data) {
  el.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
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
      const llmProvider = document.getElementById("llmProvider").value;
      const llmModel = document.getElementById("llmModel").value.trim();
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
          llm_provider: llmProvider,
          llm_model: llmModel,
        }),
      });
      const view = {
        llm_provider: data.llm_provider || llmProvider,
        llm_model: data.llm_model || llmModel,
        status: data.status,
        coverage: data.coverage,
        cache_hit: data.cache_hit,
        budget_remaining: data.budget_remaining,
        warnings: data.warnings,
        evidence_ids: data.evidence_ids,
        generated_text: data.generated_text,
      };
      setResult(ui.generateResult, view);
    } catch (e) {
      setResult(ui.generateResult, String(e));
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

bindTabs();
bindClock();
bindHealth();
bindIngest();
bindTask();
bindExpert();
bindSearchAndGenerate();
