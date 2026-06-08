/**
 * @typedef {Object} SearchCriteria
 * @property {string[]} accountIds
 * @property {string[]} mailboxes
 * @property {string} keyword
 * @property {string} rawSearch
 * @property {string} sender
 * @property {string} recipient
 * @property {boolean} unreadOnly
 * @property {boolean} readOnly
 * @property {boolean|null} flagged
 * @property {string} since
 * @property {string} before
 * @property {string} listId
 * @property {boolean|null} replied
 * @property {string} tag
 * @property {boolean} useAnd
 * @property {number} limit
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
 * @typedef {Object} MailIndexSyncRequest
 * @property {string} accountId
 * @property {string} mailbox
 * @property {number} limit
 */

/**
 * @typedef {Object} MailIndexSyncResponse
 * @property {string} accountId
 * @property {string} mailbox
 * @property {number} scanned
 * @property {number} indexed
 * @property {number} errors
 */

/**
 * @typedef {Object} MailIndexMessageSummary
 * @property {string} id
 * @property {string} accountId
 * @property {string} mailboxPath
 * @property {string} uid
 * @property {string} messageIdHeader
 * @property {string} subject
 * @property {string} sender
 * @property {string[]} recipients
 * @property {string} date
 * @property {string[]} flags
 * @property {string[]} keywords
 * @property {string} listId
 * @property {string} bodyPreview
 * @property {boolean} bodyCached
 * @property {string} lastSeenAt
 */

/**
 * @typedef {MailIndexMessageSummary & {bodyText: string}} MailIndexMessageDetail
 */

/**
 * @typedef {Object} SavedScopeQuery
 * @property {string[]} [accounts]
 * @property {string[]} [mailboxes]
 * @property {string[]} [excludeMailboxes]
 * @property {boolean} [unread]
 * @property {boolean} [flagged]
 * @property {string} [keyword]
 * @property {string|string[]} [tag]
 * @property {string|string[]} [keywords]
 * @property {string} [listIdContains]
 * @property {string} [senderContains]
 * @property {string} [subjectContains]
 * @property {string} [notMailboxKind]
 * @property {SavedScopeQuery[]} [any]
 * @property {SavedScopeQuery[]} [all]
 */

/**
 * @typedef {Object} SavedScope
 * @property {string} id
 * @property {string} name
 * @property {string} description
 * @property {SavedScopeQuery} query
 * @property {number} sortOrder
 */

/**
 * @typedef {Object} SavedScopeCreateRequest
 * @property {string | null} [id]
 * @property {string} name
 * @property {string} [description]
 * @property {SavedScopeQuery} query
 * @property {number} [sortOrder]
 */

/**
 * @typedef {Object} SavedScopeSummaryRequest
 * @property {number} [summaryLength]
 * @property {number} [limit]
 */

/**
 * @typedef {Object} MailIndexMessageQuery
 * @property {string} [accountId]
 * @property {string} [mailbox]
 * @property {boolean} [unread]
 * @property {boolean} [flagged]
 * @property {string} [tag]
 * @property {string} [keyword]
 * @property {string} [listId]
 * @property {string} [sender]
 * @property {number} [limit]
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
 * @property {MailAccountSettings[]} mailAccounts
 */

/**
 * @typedef {Object} MailAccountSettings
 * @property {string} id
 * @property {string} displayName
 * @property {boolean} enabled
 * @property {string} imapHost
 * @property {number} imapPort
 * @property {boolean} imapUseSSL
 * @property {string} username
 * @property {string} imapPassword
 * @property {string} smtpHost
 * @property {number} smtpPort
 * @property {boolean} smtpUseSSL
 * @property {string} smtpPassword
 * @property {string} recipientEmail
 */

/**
 * @typedef {Object} MailboxInfo
 * @property {string} accountId
 * @property {string} path
 * @property {string|null} delimiter
 * @property {boolean} selectable
 * @property {string[]} flags
 * @property {string} displayName
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
 * @property {number} [mail_accounts_index]
 * @property {number} [mailboxes_index]
 * @property {number} [messages_index]
 * @property {number} [sync_state]
 * @property {number} [saved_scopes]
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

  /**
   * @param {MailIndexMessageQuery} [filters]
   * @returns {string}
   */
  function buildQueryString(filters = {}) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value === undefined || value === null || value === "") {
        continue;
      }
      searchParams.set(key, String(value));
    }
    const query = searchParams.toString();
    return query ? `?${query}` : "";
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
    /** @param {string} accountId @returns {Promise<MailboxInfo[]>} */
    getAccountMailboxes(accountId) {
      return request(`/mail/accounts/${encodeURIComponent(accountId)}/mailboxes`);
    },
    /** @returns {Promise<MailboxInfo[]>} */
    getAllMailboxes() {
      return request("/mail/mailboxes");
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
    /** @param {MailIndexSyncRequest} payload @returns {Promise<MailIndexSyncResponse>} */
    syncMailIndex(payload) {
      return request("/mail/index/sync", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    /** @param {MailIndexMessageQuery} [filters] @returns {Promise<MailIndexMessageSummary[]>} */
    getMailIndexMessages(filters = {}) {
      return request(`/mail/index/messages${buildQueryString(filters)}`);
    },
    /** @param {string} messageId @returns {Promise<MailIndexMessageDetail>} */
    getMailIndexMessage(messageId) {
      return request(`/mail/index/messages/${encodeURIComponent(messageId)}`);
    },
    /** @returns {Promise<SavedScope[]>} */
    getSavedScopes() {
      return request("/mail/scopes");
    },
    /** @param {SavedScopeCreateRequest} payload @returns {Promise<SavedScope>} */
    createSavedScope(payload) {
      return request("/mail/scopes", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    /** @param {string} scopeId @param {SavedScopeCreateRequest} payload @returns {Promise<SavedScope>} */
    updateSavedScope(scopeId, payload) {
      return request(`/mail/scopes/${encodeURIComponent(scopeId)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    /** @param {string} scopeId @returns {Promise<{status: string}>} */
    deleteSavedScope(scopeId) {
      return request(`/mail/scopes/${encodeURIComponent(scopeId)}`, {
        method: "DELETE",
      });
    },
    /** @param {string} scopeId @param {number} [limit] @returns {Promise<MailIndexMessageSummary[]>} */
    getSavedScopeMessages(scopeId, limit = 200) {
      return request(`/mail/scopes/${encodeURIComponent(scopeId)}/messages?limit=${limit}`);
    },
    /** @param {string} scopeId @param {SavedScopeSummaryRequest} payload @returns {Promise<SummaryResponse>} */
    createSavedScopeSummary(scopeId, payload) {
      return request(`/mail/scopes/${encodeURIComponent(scopeId)}/summary`, {
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
