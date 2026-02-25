const API_BASE = "";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const CONVERSION_HISTORY_STORAGE_KEY = "be_conversion_history";
const OCR_PROVIDER_STORAGE_KEY = "be_ocr_provider";
const OCR_API_KEY_STORAGE_KEY = "be_ocr_api_key";
const OCR_BASE_URL_STORAGE_KEY = "be_ocr_base_url";
const OCR_MODEL_STORAGE_KEY = "be_ocr_model";
const LEGACY_GLM_OCR_API_KEY_STORAGE_KEY = "be_glm_ocr_api_key";
const LEGACY_GLM_OCR_BASE_URL_STORAGE_KEY = "be_glm_ocr_base_url";
const LEGACY_GLM_OCR_MODEL_STORAGE_KEY = "be_glm_ocr_model";
const TEXTIN_OCR_DEFAULT_BASE_URL = "https://api.textin.com/ai/service/v2/recognize/document";

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

function readSessionSecret(primaryKey, legacyLocalKeys = []) {
  const sessionValue = String(sessionStorage.getItem(primaryKey) || "").trim();
  if (sessionValue) return sessionValue;
  for (const localKey of legacyLocalKeys) {
    const legacyValue = String(localStorage.getItem(localKey) || "").trim();
    if (!legacyValue) continue;
    sessionStorage.setItem(primaryKey, legacyValue);
    localStorage.removeItem(localKey);
    return legacyValue;
  }
  return "";
}

const state = {
  projectId: normalizeStoredProjectId(localStorage.getItem("be_project_id")),
  industryTag: String(localStorage.getItem("be_industry_tag") || "").trim(),
  industryTagHistory: parseStoredArray(localStorage.getItem("be_industry_tag_history")),
  apiKey: readSessionSecret("be_api_key", ["be_api_key"]),
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
  conversionHistory: parseStoredArray(localStorage.getItem(CONVERSION_HISTORY_STORAGE_KEY)),
  ocrProvider: normalizeConfiguredOcrProvider(localStorage.getItem(OCR_PROVIDER_STORAGE_KEY) || "glm-ocr"),
  ocrApiKey: readSessionSecret(OCR_API_KEY_STORAGE_KEY, [OCR_API_KEY_STORAGE_KEY, LEGACY_GLM_OCR_API_KEY_STORAGE_KEY]),
  ocrBaseUrl: resolveOcrBaseUrl(
    localStorage.getItem(OCR_PROVIDER_STORAGE_KEY) || "glm-ocr",
    localStorage.getItem(OCR_BASE_URL_STORAGE_KEY) || localStorage.getItem(LEGACY_GLM_OCR_BASE_URL_STORAGE_KEY) || "",
  ).trim(),
  ocrModel: resolveOcrModel(
    localStorage.getItem(OCR_PROVIDER_STORAGE_KEY) || "glm-ocr",
    localStorage.getItem(OCR_MODEL_STORAGE_KEY) || localStorage.getItem(LEGACY_GLM_OCR_MODEL_STORAGE_KEY) || "",
  ),
  sidebarWidth: parseInt(localStorage.getItem("be_sidebar_width") || "280", 10),
  sidebarCollapsed: localStorage.getItem("be_sidebar_collapsed") === "true",
};
