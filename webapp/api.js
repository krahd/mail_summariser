/**
 * @typedef {Object} SearchCriteria
 * @property {string} keyword
 * @property {string} rawSearch
 * @property {string} sender
 * @property {string} recipient
 * @property {boolean} unreadOnly
 * @property {boolean} readOnly
 * @property {boolean|null} replied
 * @property {string} tag
 * @property {boolean} useAnd
 */

/**
 * @typedef {Object} SummaryRequest
 * @property {SearchCriteria} criteria
 * @property {number} summaryLength
 */

/**
 * @typedef {Object} MessageItem
 * @property {string} id
 * @property {string} subject
 * @property {string} sender
 * @property {string} date
 */

/**
 * @typedef {Object} SummaryResponse
 * @property {string} jobId
 * @property {MessageItem[]} messages
 * @property {string} summary
 */

/**
 * @typedef {Object} ActionLogItem
 * @property {string} id
 * @property {string} timestamp
 * @property {string} action
 * @property {string} status
 * @property {string} details
 * @property {string|null} job_id
 * @property {boolean} [undoable]
 * @property {string} [undo_status]
 */

/**
 * @typedef {Object} AppSettings
 * @property {string} imapHost
 * @property {number} imapPort
 * @property {string} smtpHost
 * @property {number} smtpPort
 * @property {string} username
 * @property {string} recipientEmail
 * @property {string} summarisedTag
 * @property {string} llmProvider
 * @property {string} openaiApiKey
 * @property {string} anthropicApiKey
 * @property {string} ollamaHost
 * @property {boolean} ollamaAutoStart
 * @property {string} modelName
 * @property {string} backendBaseURL
 */

/**
 * @typedef {Object} ModelOptionsResponse
 * @property {string} provider
 * @property {string[]} models
 * @property {{running: boolean, host: string, message: string} | null} ollama
 */

/**
 * @typedef {Object} ModelCatalogResponse
 * @property {string} provider
 * @property {string[]} models
 * @property {number} count
 */

/**
 * @typedef {Object} DownloadStatusResponse
 * @property {string} name
 * @property {string} status - "completed" | "downloading" | "not_found" | "error"
 * @property {string} [message]
 */

/**
 * @typedef {Object} ClientContext
 * @property {() => string} getBaseUrl
 * @property {() => string} getApiKey
 * @property {string} [apiKeyHeader]
 */

/**
 * @param {ClientContext} context
 */
export function createApiClient(context) {
  const apiKeyHeader = context.apiKeyHeader || "X-API-Key";

  /**
   * @template T
   * @param {string} path
   * @param {RequestInit} [options]
   * @returns {Promise<T>}
   */
  async function request(path, options = {}) {
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };
    const key = context.getApiKey().trim();
    if (key) {
      headers[apiKeyHeader] = key;
    }

    const response = await fetch(`${context.getBaseUrl()}${path}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return /** @type {Promise<T>} */ (response.json());
    }
    return /** @type {Promise<T>} */ (response.text());
  }

  return {
    /** @returns {Promise<{status: string}>} */
    health() {
      return request("/health");
    },
    /** @returns {Promise<ActionLogItem[]>} */
    getLogs() {
      return request("/logs");
    },
    /** @returns {Promise<AppSettings>} */
    getSettings() {
      return request("/settings");
    },
    /** @param {string} provider @returns {Promise<ModelOptionsResponse>} */
    getModelOptions(provider) {
      const value = encodeURIComponent(provider || "");
      return request(`/models/options?provider=${value}`);
    },
    /** @param {string} query @param {number} [limit] @returns {Promise<ModelCatalogResponse>} */
    getModelCatalog(query, limit = 60) {
      const q = encodeURIComponent(query || "");
      return request(`/models/catalog?query=${q}&limit=${limit}`);
    },
    /** @param {string} name @returns {Promise<DownloadStatusResponse>} */
    getDownloadStatus(name) {
      return request(`/models/download/status?name=${encodeURIComponent(name)}`);
    },
    /** @param {string} name */
    downloadModel(name) {
      return request("/models/download", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
    },
    /** @param {AppSettings} settings */
    saveSettings(settings) {
      return request("/settings", {
        method: "POST",
        body: JSON.stringify(settings),
      });
    },
    /** @param {SummaryRequest} payload @returns {Promise<SummaryResponse>} */
    createSummary(payload) {
      return request("/summaries", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    /** @param {string} jobId */
    markRead(jobId) {
      return request("/actions/mark-read", {
        method: "POST",
        body: JSON.stringify({ jobId }),
      });
    },
    /** @param {string} jobId */
    tagSummarised(jobId) {
      return request("/actions/tag-summarised", {
        method: "POST",
        body: JSON.stringify({ jobId }),
      });
    },
    /** @param {string} jobId */
    emailSummary(jobId) {
      return request("/actions/email-summary", {
        method: "POST",
        body: JSON.stringify({ jobId }),
      });
    },
    undo() {
      return request("/actions/undo", { method: "POST" });
    },
    /** @param {string} logId */
    undoLog(logId) {
      return request(`/actions/undo/logs/${encodeURIComponent(logId)}`, { method: "POST" });
    },
  };
}