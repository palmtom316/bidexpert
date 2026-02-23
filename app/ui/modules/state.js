export const STORAGE_KEYS = {
  CONVERSION_HISTORY: "be_conversion_history",
  OCR_PROVIDER: "be_ocr_provider",
  OCR_API_KEY: "be_ocr_api_key",
  OCR_BASE_URL: "be_ocr_base_url",
  OCR_MODEL: "be_ocr_model",
  PROJECT_ID: "be_project_id",
  INDUSTRY_TAG: "be_industry_tag",
  INDUSTRY_TAG_HISTORY: "be_industry_tag_history",
  SIDEBAR_WIDTH: "be_sidebar_width",
  SIDEBAR_COLLAPSED: "be_sidebar_collapsed",
};

export const LEGACY_STORAGE_KEYS = {
  API_KEY: "be_api_key",
  GLM_OCR_API_KEY: "be_glm_ocr_api_key",
  GLM_OCR_BASE_URL: "be_glm_ocr_base_url",
  GLM_OCR_MODEL: "be_glm_ocr_model",
};

export const SESSION_STORAGE_KEYS = {
  API_KEY_SESSION: "be_api_key_session",
};

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isValidUuid(value) {
  return UUID_PATTERN.test(String(value || "").trim());
}

export function normalizeStoredProjectId(value) {
  const candidate = String(value || "").trim();
  return isValidUuid(candidate) ? candidate : "";
}

export function parseStoredArray(raw, fallback = []) {
  if (!raw) return [...fallback];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [...fallback];
  } catch {
    return [...fallback];
  }
}

function safeGet(storage, key) {
  try {
    return storage.getItem(key);
  } catch {
    return null;
  }
}

export function clearLegacyApiKeyStorage() {
  try {
    localStorage.removeItem(LEGACY_STORAGE_KEYS.API_KEY);
  } catch {
    // ignore storage access issues
  }
}

export function createUiState({
  normalizeConfiguredOcrProvider,
  resolveOcrBaseUrl,
  resolveOcrModel,
}) {
  const storedProvider = safeGet(localStorage, STORAGE_KEYS.OCR_PROVIDER) || "glm-ocr";
  return {
    projectId: normalizeStoredProjectId(safeGet(localStorage, STORAGE_KEYS.PROJECT_ID)),
    industryTag: String(safeGet(localStorage, STORAGE_KEYS.INDUSTRY_TAG) || "").trim(),
    industryTagHistory: parseStoredArray(safeGet(localStorage, STORAGE_KEYS.INDUSTRY_TAG_HISTORY)),
    apiKey: String(safeGet(sessionStorage, SESSION_STORAGE_KEYS.API_KEY_SESSION) || "").trim(),
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
    conversionHistory: parseStoredArray(safeGet(localStorage, STORAGE_KEYS.CONVERSION_HISTORY)),
    ocrProvider: normalizeConfiguredOcrProvider(storedProvider),
    ocrApiKey: String(
      safeGet(localStorage, STORAGE_KEYS.OCR_API_KEY) || safeGet(localStorage, LEGACY_STORAGE_KEYS.GLM_OCR_API_KEY) || "",
    ).trim(),
    ocrBaseUrl: resolveOcrBaseUrl(
      storedProvider,
      safeGet(localStorage, STORAGE_KEYS.OCR_BASE_URL) || safeGet(localStorage, LEGACY_STORAGE_KEYS.GLM_OCR_BASE_URL) || "",
    ).trim(),
    ocrModel: resolveOcrModel(
      storedProvider,
      safeGet(localStorage, STORAGE_KEYS.OCR_MODEL) || safeGet(localStorage, LEGACY_STORAGE_KEYS.GLM_OCR_MODEL) || "",
    ),
    sidebarWidth: parseInt(safeGet(localStorage, STORAGE_KEYS.SIDEBAR_WIDTH) || "280", 10),
    sidebarCollapsed: safeGet(localStorage, STORAGE_KEYS.SIDEBAR_COLLAPSED) === "true",
  };
}
