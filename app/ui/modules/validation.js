import { isValidUuid } from "./state.js";

function normalizeFiles(files) {
  if (!files) return [];
  if (Array.isArray(files)) return files;
  return Array.from(files);
}

export function clearFieldError(inputId, errorId) {
  const input = inputId ? document.getElementById(inputId) : null;
  const error = errorId ? document.getElementById(errorId) : null;
  if (input) input.classList.remove("is-invalid");
  if (error) error.textContent = "";
}

export function setFieldError(inputId, errorId, message) {
  const input = inputId ? document.getElementById(inputId) : null;
  const error = errorId ? document.getElementById(errorId) : null;
  if (input) input.classList.add("is-invalid");
  if (error) error.textContent = String(message || "").trim();
}

export function clearAllFieldErrors(pairs) {
  (pairs || []).forEach((pair) => clearFieldError(pair.inputId, pair.errorId));
}

export function validateExpertUploadForm({ files, projectId }) {
  const errors = {};
  const normalizedFiles = normalizeFiles(files);
  if (!normalizedFiles.length) {
    errors.expertPdfFiles = "请至少选择一个文件";
  }
  const normalizedProjectId = String(projectId || "").trim();
  if (normalizedProjectId && !isValidUuid(normalizedProjectId)) {
    errors.projectId = "项目 ID 必须是 UUID 格式";
  }
  return {
    ok: Object.keys(errors).length === 0,
    errors,
  };
}

export function validateStructuredIngestForm(payload) {
  const errors = {};
  const entries = [
    ...(payload.standard_items || []),
    ...(payload.company_performance_items || []),
    ...(payload.company_qualification_items || []),
    ...(payload.pm_qualification_performance_items || []),
    ...(payload.safety_production_items || []),
    ...(payload.quality_management_items || []),
    ...(payload.equipment_capability_items || []),
    ...(payload.financial_credit_items || []),
    ...(payload.award_honors_items || []),
    ...(payload.service_commitment_items || []),
  ];
  if (!entries.length) {
    errors.structuredForm = "请至少填写一条结构化数据";
  }
  const projectId = String(payload.project_id || "").trim();
  if (projectId && !isValidUuid(projectId)) {
    errors.structuredForm = "项目 ID 必须是 UUID 格式";
  }
  if (entries.some((item) => String(item || "").length > 500)) {
    errors.structuredForm = "单条结构化文本不能超过 500 字";
  }
  return {
    ok: Object.keys(errors).length === 0,
    errors,
  };
}

export function validateOcrSettings({ provider, apiKey, baseUrl, model, requireApiKey = true }) {
  const errors = {};
  const normalizedProvider = String(provider || "").trim().toLowerCase();
  const normalizedApiKey = String(apiKey || "").trim();
  const normalizedBaseUrl = String(baseUrl || "").trim();
  const normalizedModel = String(model || "").trim();

  if (requireApiKey && !normalizedApiKey) {
    errors.ocrApiKey = "请填写 OCR API Key";
  }

  if (normalizedProvider === "textin" && (!normalizedModel || normalizedModel === "your-textin-app-id")) {
    errors.ocrModel = "textin 模式下 OCR Model 必须填写 App ID";
  }

  if (normalizedBaseUrl && !/^https?:\/\//i.test(normalizedBaseUrl)) {
    errors.ocrBaseUrl = "Base URL 需以 http:// 或 https:// 开头";
  }

  return {
    ok: Object.keys(errors).length === 0,
    errors,
  };
}
