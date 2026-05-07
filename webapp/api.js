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
 * @typedef {Object} MessageDetail
 * @property {string} id
 * @property {string} subject
 * @property {string} sender
 * @property {string} recipient
 * @property {string} date
 * @property {string} body
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
 * @property {boolean} dummyMode
 * @property {string} imapHost
 * @property {number} imapPort
 * @property {boolean} imapUseSSL
 * @property {string} imapPassword
 * @property {string} smtpHost
 * @property {number} smtpPort
 * @property {boolean} smtpUseSSL
 * @property {string} smtpPassword
 * @property {string} username
 * @property {string} recipientEmail
 * @property {string} summarisedTag
 * @property {string} llmProvider
 * @property {string} openaiApiKey
 * @property {string} anthropicApiKey
 * @property {string} ollamaHost
 * @property {boolean} ollamaAutoStart
 * @property {boolean} ollamaStartOnStartup
 * @property {boolean} ollamaStopOnExit
 * @property {string} ollamaSystemMessage
 * @property {string} openaiSystemMessage
 * @property {string} anthropicSystemMessage
 * @property {string} modelName
 * @property {string} backendBaseURL
 */

/**
 * @typedef {Object} SystemMessageDefaultsResponse
 * @property {string} ollamaSystemMessage
 * @property {string} openaiSystemMessage
 * @property {string} anthropicSystemMessage
 */

/**
 * @typedef {Object} BackendRuntimeStatus
 * @property {boolean} running
 * @property {boolean} canShutdown
 */

/**
 * @typedef {Object} OllamaRuntimeStatus
 * @property {boolean} installed
 * @property {boolean} running
 * @property {boolean} startedByApp
 * @property {string} host
 * @property {string} modelName
 * @property {string} startupAction
 * @property {string} message
 * @property {string} installUrl
 */

/**
 * @typedef {Object} RuntimeStatusResponse
 * @property {BackendRuntimeStatus} backend
 * @property {OllamaRuntimeStatus} ollama
 */

/**
 * @typedef {Object} RuntimeActionResponse
 * @property {string} status
 * @property {string} message
 * @property {RuntimeStatusResponse} runtime
 */

/**
 * @typedef {Object} DatabaseResetCounts
 * @property {number} settings
 * @property {number} logs
 * @property {number} jobs
 * @property {number} undo
 */

/**
 * @typedef {Object} DatabaseResetResponse
 * @property {string} status
 * @property {string} message
 * @property {DatabaseResetCounts} removed
 * @property {AppSettings} settings
 */

/**
 * @typedef {Object} FakeMailStatusResponse
 * @property {boolean} enabled
 * @property {boolean} running
 * @property {string} message
 * @property {string} imapHost
 * @property {number} imapPort
 * @property {string} smtpHost
 * @property {number} smtpPort
 * @property {string} username
 * @property {string} password
 * @property {string} recipientEmail
 * @property {AppSettings | null} suggestedSettings
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
   * @param {string} rawBaseUrl
   * @returns {string}
   */
  function normalizeBaseUrl(rawBaseUrl) {
    const trimmed = String(rawBaseUrl || "").trim();
    const withScheme = /^[a-zA-Z][a-zA-Z\d+.-]*:\/\//.test(trimmed)
      ? trimmed
      : `http://${trimmed}`;
    const parsed = new URL(withScheme);
    return parsed.toString().replace(/\/$/, "");
  }

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

    const rawBaseUrl = context.getBaseUrl();
    let normalizedBaseUrl = "";
    let requestUrl = "";

    try {
      normalizedBaseUrl = normalizeBaseUrl(rawBaseUrl);
      requestUrl = new URL(path, `${normalizedBaseUrl}/`).toString();
    } catch (_error) {
      throw new Error(`Invalid backend URL: ${String(rawBaseUrl || "").trim() || "(empty)"}`);
    }

    let response;
    try {
      response = await fetch(requestUrl, {
        ...options,
        headers,
      });
    } catch (error) {
      throw new Error(
        `Could not reach backend at ${normalizedBaseUrl}. ` +
          "Check that the backend is running and the backend URL is correct."
      );
    }

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
    /** @returns {Promise<SystemMessageDefaultsResponse>} */
    getSystemMessageDefaults() {
      return request("/settings/system-message-defaults");
    },
    /** @returns {Promise<RuntimeStatusResponse>} */
    getRuntimeStatus() {
      return request("/runtime/status");
    },
    /** @returns {Promise<RuntimeActionResponse>} */
    startOllamaRuntime() {
      return request("/runtime/ollama/start", {
        method: "POST",
        body: JSON.stringify({}),
      });
    },
    /** @returns {Promise<RuntimeActionResponse>} */
    installOllamaRuntime() {
      return request("/runtime/ollama/install", {
        method: "POST",
        body: JSON.stringify({}),
      });
    },
    /** @returns {Promise<RuntimeActionResponse>} */
    stopOllamaRuntime() {
      return request("/runtime/ollama/stop", {
        method: "POST",
        body: JSON.stringify({}),
      });
    },
    /** @returns {Promise<{status: string, message?: string}>} */
    shutdownRuntime() {
      return request("/runtime/shutdown", {
        method: "POST",
        body: JSON.stringify({}),
      });
    },
    /** @param {string} confirmation @returns {Promise<DatabaseResetResponse>} */
    resetDatabase(confirmation) {
      return request("/admin/database/reset", {
        method: "POST",
        body: JSON.stringify({ confirmation }),
      });
    },
    /** @returns {Promise<FakeMailStatusResponse>} */
    getFakeMailStatus() {
      return request("/dev/fake-mail/status");
    },
    /** @returns {Promise<FakeMailStatusResponse>} */
    startFakeMailServer() {
      return request("/dev/fake-mail/start", {
        method: "POST",
        body: JSON.stringify({}),
      });
    },
    /** @returns {Promise<FakeMailStatusResponse>} */
    stopFakeMailServer() {
      return request("/dev/fake-mail/stop", {
        method: "POST",
        body: JSON.stringify({}),
      });
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
    /** @param {string} name */
    serveModel(name) {
      return request("/models/serve", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
    },
    /** @param {string} name */
    deleteLocalModel(name) {
      return request(`/models/local?name=${encodeURIComponent(name)}`, {
        method: "DELETE",
      });
    },
    /** @param {AppSettings} settings */
    saveSettings(settings) {
      return request("/settings", {
        method: "POST",
        body: JSON.stringify(settings),
      });
    },
    /** @param {AppSettings} settings */
    testConnection(settings) {
      return request("/settings/test-connection", {
        method: "POST",
        body: JSON.stringify(settings),
      });
    },
    /** @param {boolean} dummyMode */
    setDummyMode(dummyMode) {
      return request("/settings/dummy-mode", {
        method: "POST",
        body: JSON.stringify({ dummyMode }),
      });
    },
    /** @param {SummaryRequest} payload @returns {Promise<SummaryResponse>} */
    createSummary(payload) {
      return request("/summaries", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    /** @param {string} jobId @param {string} messageId @returns {Promise<MessageDetail>} */
    getMessageDetail(jobId, messageId) {
      return request(`/jobs/${encodeURIComponent(jobId)}/messages/${encodeURIComponent(messageId)}`);
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
