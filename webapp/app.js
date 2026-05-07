import { createApiClient } from "./api.js";

const storageKeys = {
  baseUrl: "mail_summariser-base-url",
  apiKey: "mail_summariser-api-key",
};

let currentJobId = null;
let currentMessages = [];
let selectedMessageId = null;
let currentMessageDetail = null;
let latestMessageDetailRequest = 0;
let currentRuntimeStatus = null;
let currentFakeMailStatus = null;
let currentSystemMessageDefaults = null;
let currentLogs = [];
let activeQuickFilter = "today-unread";
let backendStopping = false;
let activeDummyMode = true;

const statusLine = document.getElementById("status-line");
const runtimeStartupBanner = document.getElementById("runtime-startup-banner");
const runtimeStartupMessage = document.getElementById("runtime-startup-message");
const runtimeStartupActionBtn = document.getElementById("runtime-startup-action");
const testConnectionBtn = document.getElementById("test-connection");
const connectionTestStatusLine = document.getElementById("connection-test-status");
const dummyModeToggleBtn = document.getElementById("dummy-mode-toggle");
const dummyModeField = document.getElementById("dummy-mode-field");
const dummyModeDescription = document.getElementById("dummy-mode-description");

const searchForm = document.getElementById("search-form");
const summaryCard = document.getElementById("summary-card");
const summaryText = document.getElementById("summary-text");
const jobIdLabel = document.getElementById("job-id");
const messagesSummary = document.getElementById("messages-summary");
const messagesBody = document.getElementById("messages-body");
const messageDetailShell = document.getElementById("message-detail-shell");
const messageDetailSubject = document.getElementById("message-detail-subject");
const messageDetailDate = document.getElementById("message-detail-date");
const messageDetailSenderName = document.getElementById("message-detail-sender-name");
const messageDetailSenderAddress = document.getElementById("message-detail-sender-address");
const messageDetailRecipientName = document.getElementById("message-detail-recipient-name");
const messageDetailRecipientAddress = document.getElementById("message-detail-recipient-address");
const messageDetailBody = document.getElementById("message-detail-body");

const markReadBtn = document.getElementById("mark-read");
const tagSummaryBtn = document.getElementById("tag-summary");
const emailSummaryBtn = document.getElementById("email-summary");
const undoActionBtn = document.getElementById("undo-action");
const quickFilterButtons = Array.from(document.querySelectorAll(".quick-filter"));
const applyScopeActionsBtn = document.getElementById("apply-scope-actions");
const actionScopePreview = document.getElementById("action-scope-preview");
const scopeActionMarkRead = document.getElementById("scope-action-mark-read");
const scopeActionTag = document.getElementById("scope-action-tag");
const scopeActionEmail = document.getElementById("scope-action-email");
const healthMode = document.getElementById("health-mode");
const healthProvider = document.getElementById("health-provider");
const healthRuntime = document.getElementById("health-runtime");
const healthSync = document.getElementById("health-sync");
const digestMetricMessages = document.getElementById("digest-metric-messages");
const digestMetricSelected = document.getElementById("digest-metric-selected");
const digestMetricFilter = document.getElementById("digest-metric-filter");

const logsBody = document.getElementById("logs-body");
const refreshLogsBtn = document.getElementById("refresh-logs");
const logsCountLabel = document.getElementById("logs-count");
const logSearchInput = document.getElementById("log-search");
const logStatusFilter = document.getElementById("log-status-filter");
const logUndoOnlyToggle = document.getElementById("log-undo-only");

const settingsForm = document.getElementById("settings-form");
const settingsBasicScreen = document.getElementById("settings-basic-screen");
const settingsAdvancedScreen = document.getElementById("settings-advanced-screen");
const openAdvancedSettingsBtn = document.getElementById("open-advanced-settings");
const backToBasicSettingsBtn = document.getElementById("back-to-basic-settings");
const loadBasicSettingsBtn = document.getElementById("load-basic-settings");
const loadAdvancedSettingsBtn = document.getElementById("load-advanced-settings");
const providerSelect = document.getElementById("llm-provider");
const providerSystemMessageGroup = document.getElementById("provider-system-message-group");
const providerSystemMessageTitle = document.getElementById("provider-system-message-title");
const providerSystemMessageEditor = document.getElementById("provider-system-message");
const providerSystemMessageNote = document.getElementById("provider-system-message-note");
const resetSystemMessageBtn = document.getElementById("reset-system-message");
const refreshModelsBtn = document.getElementById("refresh-models");
const ollamaStatusLine = document.getElementById("ollama-status");
const ollamaRuntimeStatusLine = document.getElementById("ollama-runtime-status");
const runtimeOllamaInstallBtn = document.getElementById("runtime-ollama-install");
const runtimeOllamaActionBtn = document.getElementById("runtime-ollama-action");
const runtimeOllamaStopBtn = document.getElementById("runtime-ollama-stop");
const refreshRuntimeStatusBtn = document.getElementById("refresh-runtime-status");
const serveModelBtn = document.getElementById("serve-model");
const deleteModelBtn = document.getElementById("delete-model");
const downloadableModelSelect = document.getElementById("downloadable-model");
const refreshCatalogBtn = document.getElementById("refresh-catalog");
const downloadModelBtn = document.getElementById("download-model");
const catalogStatusLine = document.getElementById("catalog-status");
const stopMailSummariserBtn = document.getElementById("stop-mail_summariser");
const resetLocalDatabaseBtn = document.getElementById("reset-local-database");
const backendApiKeyInput = document.getElementById("backend-api-key");
const providerKeyWarningLine = document.getElementById("provider-key-warning");
const openaiApiKeyInput = document.getElementById("openai-api-key");
const anthropicApiKeyInput = document.getElementById("anthropic-api-key");
const imapPasswordInput = document.getElementById("imap-password");
const smtpPasswordInput = document.getElementById("smtp-password");
const toggleOpenAiKeyBtn = document.getElementById("toggle-openai-key");
const toggleAnthropicKeyBtn = document.getElementById("toggle-anthropic-key");
const toggleBackendKeyBtn = document.getElementById("toggle-backend-key");
const toggleImapPasswordBtn = document.getElementById("toggle-imap-password");
const toggleSmtpPasswordBtn = document.getElementById("toggle-smtp-password");
const openaiKeyGroup = document.getElementById("openai-key-group");
const anthropicKeyGroup = document.getElementById("anthropic-key-group");
const fakeMailCard = document.getElementById("fake-mail-card");
const fakeMailStatusLine = document.getElementById("fake-mail-status");
const fakeMailCredentialsLine = document.getElementById("fake-mail-credentials");
const startFakeMailBtn = document.getElementById("start-fake-mail");
const stopFakeMailBtn = document.getElementById("stop-fake-mail");
const useFakeMailSettingsBtn = document.getElementById("use-fake-mail-settings");
const diagnosticsProviderState = document.getElementById("diag-provider-state");
const diagnosticsRuntimeState = document.getElementById("diag-runtime-state");
const diagnosticsFakeMailState = document.getElementById("diag-fakemail-state");

const api = createApiClient({
  getBaseUrl,
  getApiKey: () => backendApiKeyInput?.value || "",
});

function getBaseUrl() {
  const backendUrlInput = settingsForm?.elements.namedItem("backendBaseURL");
  const stored = localStorage.getItem(storageKeys.baseUrl) || "";
  const raw = (backendUrlInput?.value || stored || "http://127.0.0.1:8766").toString();
  return raw.replace(/\/$/, "");
}

function setStatus(message, isError = false) {
  statusLine.textContent = message;
  statusLine.style.color = isError ? "var(--danger-ink)" : "var(--success-ink)";
}

function setConnectionTestStatus(message, isError = false) {
  if (!connectionTestStatusLine) {
    return;
  }
  connectionTestStatusLine.textContent = message;
  connectionTestStatusLine.style.color = isError ? "var(--danger-ink)" : "var(--success-ink)";
}

function setActionButtons(enabled) {
  markReadBtn.disabled = !enabled;
  tagSummaryBtn.disabled = !enabled;
  emailSummaryBtn.disabled = !enabled;
  if (applyScopeActionsBtn) {
    applyScopeActionsBtn.disabled = !enabled;
  }
}

function updateActionScopePreview() {
  if (!actionScopePreview) {
    return;
  }
  if (!currentJobId) {
    actionScopePreview.textContent = "No active job. Generate a digest first.";
    return;
  }
  if (currentMessages.length === 0) {
    actionScopePreview.textContent = "Current job has no messages. Change filters and generate another digest.";
    return;
  }

  const actionNames = [];
  if (scopeActionMarkRead?.checked) actionNames.push("mark read");
  if (scopeActionTag?.checked) actionNames.push("tag");
  if (scopeActionEmail?.checked) actionNames.push("email summary");

  if (actionNames.length === 0) {
    actionScopePreview.textContent = `Job ${currentJobId}: select at least one action.`;
    return;
  }

  const suffix = activeDummyMode ? " Sample mailbox actions stay in this local session." : "";
  actionScopePreview.textContent = `Job ${currentJobId}: ${actionNames.join(", ")}.${suffix}`;
}

function updateHealthStrip() {
  if (healthMode) {
    healthMode.textContent = `Mailbox: ${activeDummyMode ? "Sample" : "Live"}`;
  }
  if (healthProvider) {
    healthProvider.textContent = `Provider: ${providerDisplayName(selectedProvider())}`;
  }
  if (healthRuntime) {
    healthRuntime.textContent = currentRuntimeStatus?.ollama?.message
      ? `Runtime: ${currentRuntimeStatus.ollama.message}`
      : "Runtime: Status unavailable";
  }
  if (healthSync) {
    const stamp = new Date();
    healthSync.textContent = `Last sync: ${stamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  }
}

function updateDiagnosticsSummary() {
  if (diagnosticsProviderState) {
    const provider = providerDisplayName(selectedProvider());
    diagnosticsProviderState.textContent = `Provider: ${provider}`;
  }

  if (diagnosticsRuntimeState) {
    const runtimeMessage = currentRuntimeStatus?.ollama?.message || "not loaded";
    diagnosticsRuntimeState.textContent = `Runtime: ${runtimeMessage}`;
  }

  if (diagnosticsFakeMailState) {
    if (!currentFakeMailStatus || !currentFakeMailStatus.enabled) {
      diagnosticsFakeMailState.textContent = "Fake mail: unavailable";
    } else if (currentFakeMailStatus.running) {
      diagnosticsFakeMailState.textContent = "Fake mail: running";
    } else {
      diagnosticsFakeMailState.textContent = "Fake mail: available (stopped)";
    }
  }
}

function filteredLogs(logs) {
  const searchQuery = String(logSearchInput?.value || "").trim().toLowerCase();
  const statusFilterValue = String(logStatusFilter?.value || "").trim().toLowerCase();
  const undoOnly = Boolean(logUndoOnlyToggle?.checked);

  return (Array.isArray(logs) ? logs : []).filter((item) => {
    if (undoOnly && !item.undoable) {
      return false;
    }

    const itemStatus = String(item.status || "").toLowerCase();
    if (statusFilterValue && itemStatus !== statusFilterValue) {
      return false;
    }

    if (!searchQuery) {
      return true;
    }

    const haystack = [item.action, item.status, item.details, item.job_id, item.timestamp]
      .map((value) => String(value || "").toLowerCase())
      .join(" ");
    return haystack.includes(searchQuery);
  });
}

function renderLogsCount(visibleCount, totalCount) {
  if (!logsCountLabel) {
    return;
  }
  if (totalCount <= 0) {
    logsCountLabel.textContent = "0 items";
    return;
  }
  logsCountLabel.textContent = `${visibleCount} of ${totalCount} items`;
}

function refreshLogTimeline() {
  renderLogs(currentLogs);
}

function setQuickFilterState(activeFilter) {
  activeQuickFilter = activeFilter;
  quickFilterButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.filter === activeFilter);
  });
  updateDigestMetrics();
}

function formatQuickFilterLabel(filter) {
  const key = String(filter || "clear");
  const labels = {
    "today-unread": "Unread mail",
    "pending-replies": "Needs reply",
    finance: "Finance",
    clear: "All messages",
  };
  return labels[key] || "All messages";
}

function updateDigestMetrics() {
  if (digestMetricMessages) {
    digestMetricMessages.textContent = String(currentMessages.length || 0);
  }
  if (digestMetricSelected) {
    const selectedMessage = getMessageListItem(selectedMessageId);
    digestMetricSelected.textContent = selectedMessage?.subject || "None";
  }
  if (digestMetricFilter) {
    digestMetricFilter.textContent = formatQuickFilterLabel(activeQuickFilter);
  }
}

function applyQuickFilter(filter) {
  if (!searchForm) {
    return;
  }

  const keyword = searchForm.elements.namedItem("keyword");
  const sender = searchForm.elements.namedItem("sender");
  const tag = searchForm.elements.namedItem("tag");
  const unreadOnly = searchForm.elements.namedItem("unreadOnly");
  const readOnly = searchForm.elements.namedItem("readOnly");
  const replied = searchForm.elements.namedItem("replied");

  if (keyword) keyword.value = "";
  if (sender) sender.value = "";
  if (tag) tag.value = "";
  if (unreadOnly) unreadOnly.checked = true;
  if (readOnly) readOnly.checked = false;
  if (replied) replied.value = "";

  if (filter === "pending-replies") {
    if (replied) replied.value = "false";
  } else if (filter === "finance") {
    if (tag) tag.value = "finance";
    if (keyword) keyword.value = "invoice";
  } else if (filter === "clear") {
    if (keyword) keyword.value = "";
    if (sender) sender.value = "";
    if (tag) tag.value = "";
    if (unreadOnly) unreadOnly.checked = false;
    if (replied) replied.value = "";
  }

  setQuickFilterState(filter);
  setStatus(`Applied quick filter: ${formatQuickFilterLabel(filter)}.`);
}

function clearCurrentWorkspaceState() {
  currentJobId = null;
  currentMessages = [];
  selectedMessageId = null;
  currentMessageDetail = null;
  latestMessageDetailRequest += 1;
  jobIdLabel.textContent = "No job yet";
  if (summaryCard) {
    summaryCard.dataset.state = "idle";
  }
  summaryText.textContent = "Run a summary to see output here.";
  renderMessages([]);
  renderMessageDetail(null, {
    state: "empty",
    subject: "No mail selected",
    senderName: "",
    senderAddress: "",
    recipientName: "",
    recipientAddress: "",
    body: "",
  });
  setActionButtons(false);
  updateActionScopePreview();
  updateDigestMetrics();
}

function formatMessageDate(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) {
    return raw;
  }
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderMessages(messages) {
  currentMessages = Array.isArray(messages) ? messages : [];

  if (messagesSummary) {
    messagesSummary.textContent = currentMessages.length === 0
      ? ""
      : `${currentMessages.length} messages in the current job.`;
  }

  if (!Array.isArray(messages) || messages.length === 0) {
    messagesBody.innerHTML = "<tr><td colspan='3'>No messages returned.</td></tr>";
    updateDigestMetrics();
    return;
  }

  messagesBody.innerHTML = messages
    .map(
      (m) => {
        const isSelected = m.id === selectedMessageId;
        const displayDate = formatMessageDate(m.date);
        return `<tr class="message-row${isSelected ? " is-selected" : ""}" data-message-id="${escapeHtml(
          m.id
        )}" tabindex="0" aria-selected="${isSelected}"><td title="${escapeHtml(m.date)}">${escapeHtml(
          displayDate
        )}</td><td>${escapeHtml(m.sender)}</td><td>${escapeHtml(m.subject)}</td></tr>`;
      }
    )
    .join("");

  updateDigestMetrics();
}

function getMessageListItem(messageId) {
  return currentMessages.find((message) => message.id === messageId) || null;
}

function titleCaseWords(value) {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function fallbackMailboxName(address) {
  const localPart = String(address || "").split("@")[0] || String(address || "");
  const normalized = localPart.replace(/[._+-]+/g, " ").trim();
  return normalized ? titleCaseWords(normalized) : String(address || "");
}

function parseMailbox(value, fallbackName, fallbackAddress) {
  const raw = String(value || "").trim();
  if (!raw) {
    return {
      name: fallbackName,
      address: fallbackAddress,
    };
  }

  const namedMailboxMatch = raw.match(/^\s*"?([^"<]+?)"?\s*<([^>]+)>\s*$/);
  if (namedMailboxMatch) {
    const name = namedMailboxMatch[1].trim();
    const address = namedMailboxMatch[2].trim();
    return {
      name: name || fallbackMailboxName(address),
      address,
    };
  }

  if (raw.includes("@")) {
    return {
      name: fallbackMailboxName(raw),
      address: raw,
    };
  }

  return {
    name: raw,
    address: fallbackAddress || raw,
  };
}

function renderMessageDetail(detail, options = {}) {
  if (!messageDetailShell) {
    return;
  }

  const state = options.state || (detail ? "ready" : "empty");
  messageDetailShell.dataset.state = state;
  const isEmptyState = state === "empty";

  const subject = detail?.subject || options.subject || "No mail selected";
  const date = formatMessageDate(detail?.date || options.date || "");
  const body = isEmptyState ? "" : detail?.body || options.body || "";
  const senderMailbox = parseMailbox(
    detail?.sender,
    isEmptyState ? "" : options.senderName || "",
    isEmptyState ? "" : options.senderAddress || options.sender || ""
  );
  const recipientMailbox = parseMailbox(
    detail?.recipient,
    isEmptyState ? "" : options.recipientName || "",
    isEmptyState ? "" : options.recipientAddress || options.recipient || ""
  );

  messageDetailSubject.textContent = subject;
  messageDetailDate.textContent = date;
  messageDetailSenderName.textContent = senderMailbox.name;
  messageDetailSenderAddress.textContent = senderMailbox.address;
  messageDetailRecipientName.textContent = recipientMailbox.name;
  messageDetailRecipientAddress.textContent = recipientMailbox.address;
  messageDetailBody.textContent = body;
}

async function selectMessage(messageId) {
  if (!currentJobId || !messageId) {
    return;
  }

  selectedMessageId = messageId;
  currentMessageDetail = null;
  renderMessages(currentMessages);
  updateDigestMetrics();

  const listItem = getMessageListItem(messageId);
  renderMessageDetail(null, {
    state: "loading",
    subject: listItem?.subject || "Loading message",
    senderName: parseMailbox(listItem?.sender, "Loading sender", "Loading sender").name,
    senderAddress: parseMailbox(listItem?.sender, "Loading sender", "Loading sender").address,
    date: listItem?.date || "",
    recipientName: "Loading recipient",
    recipientAddress: "Loading recipient",
    body: "Loading message body...",
  });

  const requestId = ++latestMessageDetailRequest;

  try {
    const detail = await api.getMessageDetail(currentJobId, messageId);
    if (requestId !== latestMessageDetailRequest || selectedMessageId !== messageId) {
      return;
    }

    currentMessageDetail = detail;
    renderMessageDetail(detail);
    updateDigestMetrics();
  } catch (error) {
    if (requestId !== latestMessageDetailRequest || selectedMessageId !== messageId) {
      return;
    }

    currentMessageDetail = null;
    renderMessageDetail(null, {
      state: "error",
      subject: listItem?.subject || "Message unavailable",
      senderName: parseMailbox(listItem?.sender, "Message unavailable", "Could not load sender").name,
      senderAddress: parseMailbox(listItem?.sender, "Message unavailable", "Could not load sender").address,
      date: listItem?.date || "",
      recipientName: "Message unavailable",
      recipientAddress: "Could not load recipient",
      body: `Could not load this message: ${error.message}`,
    });
    setStatus(`Message load failed: ${error.message}`, true);
    updateDigestMetrics();
  }
}

function renderLogs(logs) {
  currentLogs = Array.isArray(logs) ? logs : [];
  const visibleLogs = filteredLogs(currentLogs);
  renderLogsCount(visibleLogs.length, currentLogs.length);

  if (!Array.isArray(visibleLogs) || visibleLogs.length === 0) {
    logsBody.innerHTML = "<article class='log-entry log-entry-empty'><p>No logs available.</p></article>";
    return;
  }

  logsBody.innerHTML = visibleLogs
    .map(
      (item) => {
        let undoCell = '<span class="log-badge log-badge-final">Final</span>';
        if (item.undoable) {
          undoCell = `<button type="button" class="log-undo-btn" data-log-id="${escapeHtml(
            item.id || ""
          )}">Undo</button>`;
        }

        return (
        `<article class="log-entry">` +
          `<div class="log-entry-head">` +
            `<span class="log-entry-time">${escapeHtml(item.timestamp || "")}</span>` +
            `<strong class="log-entry-action">${escapeHtml(item.action || "")}</strong>` +
            `<span class="log-badge log-badge-status">${escapeHtml(item.status || "")}</span>` +
          `</div>` +
          `<p class="log-entry-details">${escapeHtml(item.details || "")}</p>` +
          `<div class="log-entry-meta">` +
            `<span class="log-badge log-badge-muted">Job: ${escapeHtml(item.job_id || "-")}</span>` +
            `${undoCell}` +
          `</div>` +
        `</article>`
        );
      }
    )
    .join("");
}

function fillSettings(settings, options = {}) {
  const updateActiveMode = options.updateActiveMode !== false;
  const preserveBackendTarget = options.preserveBackendTarget !== false;
  const keyFieldNames = ["openaiApiKey", "anthropicApiKey", "imapPassword", "smtpPassword"];
  Object.entries(settings).forEach(([name, value]) => {
    if (preserveBackendTarget && name === "backendBaseURL") {
      return;
    }
    const input = settingsForm.elements.namedItem(name);
    if (input) {
      if (input.type === "checkbox") {
        input.checked = Boolean(value);
      } else if (keyFieldNames.includes(name) && value === "__MASKED__") {
        input.value = "";
        input.dataset.wasMasked = "1";
        input.placeholder = "Key stored — leave blank to keep, or enter new key to replace";
      } else {
        input.value = value;
        if (keyFieldNames.includes(name)) {
          delete input.dataset.wasMasked;
        }
      }
    }
  });
  if (updateActiveMode) {
    activeDummyMode = Boolean(settings.dummyMode);
  }
  if (dummyModeField) {
    dummyModeField.checked = Boolean(settings.dummyMode);
  }
  syncDummyModeUI(activeDummyMode);
  refreshProviderKeyWarning();
  refreshProviderKeyFieldVisibility();
  refreshProviderSystemMessageEditor();
  updateHealthStrip();
  updateDiagnosticsSummary();
}

function syncDummyModeUI(enabled) {
  if (dummyModeField) {
    dummyModeField.checked = enabled;
  }
  if (dummyModeToggleBtn) {
    dummyModeToggleBtn.textContent = enabled ? "Sample Mailbox: On" : "Sample Mailbox: Off";
    dummyModeToggleBtn.classList.toggle("is-live", !enabled);
  }
  if (dummyModeDescription) {
    dummyModeDescription.textContent = enabled
      ? "Sample mailbox is on. Searches and actions use resettable sample mail."
      : "Sample mailbox is off. Searches and actions use the configured IMAP and SMTP servers.";
  }
  updateHealthStrip();
}

function setOllamaStatus(message, isError = false) {
  if (!ollamaStatusLine) {
    return;
  }
  ollamaStatusLine.textContent = message;
  ollamaStatusLine.style.color = isError ? "var(--danger-ink)" : "var(--success-ink)";
}

function setOllamaRuntimeStatus(message, isError = false) {
  if (!ollamaRuntimeStatusLine) {
    return;
  }
  ollamaRuntimeStatusLine.textContent = message;
  ollamaRuntimeStatusLine.style.color = isError ? "var(--danger-ink)" : "var(--success-ink)";
}

function setCatalogStatus(message, isError = false) {
  if (!catalogStatusLine) {
    return;
  }
  catalogStatusLine.textContent = message;
  catalogStatusLine.style.color = isError ? "var(--danger-ink)" : "var(--success-ink)";
}

function selectedProvider() {
  return providerSelect?.value || "ollama";
}

function runtimeNeedsAttention(runtime) {
  const action = runtime?.ollama?.startupAction || "none";
  return action === "install" || action === "start";
}

function configureRuntimeActionButton(button, runtime) {
  if (!button) {
    return;
  }

  if (!runtime || selectedProvider() !== "ollama") {
    button.classList.add("is-hidden");
    return;
  }

  const action = runtime?.ollama?.startupAction || "none";
  if (action === "install") {
    button.textContent = "Install Ollama";
    button.classList.remove("is-hidden");
    return;
  }
  if (action === "start") {
    button.textContent = "Start Ollama";
    button.classList.remove("is-hidden");
    return;
  }
  button.classList.add("is-hidden");
}

function updateRuntimeStartupBanner(runtime) {
  if (!runtimeStartupBanner || !runtimeStartupMessage) {
    return;
  }

  if (!runtime || selectedProvider() !== "ollama" || !runtimeNeedsAttention(runtime) || backendStopping) {
    runtimeStartupBanner.classList.add("is-hidden");
    return;
  }

  runtimeStartupMessage.textContent = runtime.ollama.message || "Ollama needs attention.";
  runtimeStartupBanner.classList.remove("is-hidden");
  configureRuntimeActionButton(runtimeStartupActionBtn, runtime);
}

function renderRuntimeStatus(runtime) {
  currentRuntimeStatus = runtime;
  const needsAttention = runtimeNeedsAttention(runtime);
  const message = runtime?.ollama?.message || "Runtime status not available.";
  setOllamaRuntimeStatus(message, needsAttention);
  if (runtimeOllamaInstallBtn) {
    runtimeOllamaInstallBtn.disabled = Boolean(runtime?.ollama?.installed);
  }
  if (runtimeOllamaStopBtn) {
    runtimeOllamaStopBtn.disabled = !Boolean(runtime?.ollama?.running);
  }
  configureRuntimeActionButton(runtimeOllamaActionBtn, runtime);
  updateRuntimeStartupBanner(runtime);
  updateHealthStrip();
  updateDiagnosticsSummary();
}

async function refreshRuntimeStatus() {
  const runtime = await api.getRuntimeStatus();
  renderRuntimeStatus(runtime);
  return runtime;
}

function renderFakeMailStatus(status) {
  currentFakeMailStatus = status;

  if (!fakeMailCard || !fakeMailStatusLine || !fakeMailCredentialsLine) {
    updateDiagnosticsSummary();
    return;
  }

  if (!status?.enabled) {
    fakeMailCard.classList.add("is-hidden");
    updateDiagnosticsSummary();
    return;
  }

  fakeMailCard.classList.remove("is-hidden");
  fakeMailStatusLine.textContent = status.message || "Developer fake mail server is available.";
  fakeMailStatusLine.style.color = status.running ? "#245f58" : "#7a5f19";

  if (status.running) {
    fakeMailCredentialsLine.textContent =
      `IMAP ${status.imapHost}:${status.imapPort} | SMTP ${status.smtpHost}:${status.smtpPort} | ` +
      `Username ${status.username} | Password ${status.password} | Recipient ${status.recipientEmail}`;
  } else {
    fakeMailCredentialsLine.textContent =
      "Start the local fake IMAP/SMTP server to generate disposable test credentials.";
  }

  if (startFakeMailBtn) {
    startFakeMailBtn.disabled = Boolean(status.running);
  }
  if (stopFakeMailBtn) {
    stopFakeMailBtn.disabled = !status.running;
  }
  if (useFakeMailSettingsBtn) {
    useFakeMailSettingsBtn.disabled = !status.running || !status.suggestedSettings;
  }
  updateDiagnosticsSummary();
}

async function refreshFakeMailStatus() {
  const status = await api.getFakeMailStatus();
  renderFakeMailStatus(status);
  return status;
}

function openOllamaInstallPage() {
  const url = currentRuntimeStatus?.ollama?.installUrl || "https://ollama.com/download";
  window.open(url, "_blank", "noopener");
  setStatus("Opened the Ollama download page.");
}

function selectedModelName() {
  const input = settingsForm?.elements.namedItem("modelName");
  return String(input?.value || "").trim();
}

async function installOllamaRuntime() {
  try {
    const response = await api.installOllamaRuntime();
    setStatus(response.message || "Ollama installation completed.", response.status !== "ok");
    if (response.runtime) {
      renderRuntimeStatus(response.runtime);
    } else {
      await refreshRuntimeStatus();
    }
  } catch (error) {
    setStatus(`Ollama install failed: ${error.message}`, true);
    openOllamaInstallPage();
  }
}

async function stopOllamaRuntime() {
  try {
    const response = await api.stopOllamaRuntime();
    setStatus(response.message || "Ollama stop requested.", response.status !== "ok");
    if (response.runtime) {
      renderRuntimeStatus(response.runtime);
    } else {
      await refreshRuntimeStatus();
    }
  } catch (error) {
    setStatus(`Ollama stop failed: ${error.message}`, true);
  }
}

async function handleRuntimeAction() {
  const action = currentRuntimeStatus?.ollama?.startupAction || "none";

  if (action === "install") {
    await installOllamaRuntime();
    return;
  }

  if (action !== "start") {
    return;
  }

  try {
    const response = await api.startOllamaRuntime();
    setStatus(response.message || "Ollama start requested.", response.status === "warning");
    if (response.runtime) {
      renderRuntimeStatus(response.runtime);
    } else {
      await refreshRuntimeStatus();
    }
    await refreshModelOptions();
  } catch (error) {
    setStatus(`Ollama start failed: ${error.message}`, true);
  }
}

async function serveConfiguredModel() {
  const modelName = selectedModelName();
  if (!modelName) {
    setOllamaStatus("Choose a model name before serving.", true);
    return;
  }
  try {
    const response = await api.serveModel(modelName);
    setOllamaStatus(response.message || `Model ${modelName} is ready.`, response.status !== "ok");
    await refreshRuntimeStatus();
  } catch (error) {
    setOllamaStatus(`Serve model failed: ${error.message}`, true);
  }
}

async function deleteConfiguredModel() {
  const modelName = selectedModelName();
  if (!modelName) {
    setOllamaStatus("Choose a model name before deleting.", true);
    return;
  }
  if (!window.confirm(`Delete local model ${modelName}?`)) {
    return;
  }
  try {
    const response = await api.deleteLocalModel(modelName);
    setOllamaStatus(response.message || `Deleted ${modelName}.`, response.status !== "ok");
    await refreshModelOptions();
  } catch (error) {
    setOllamaStatus(`Delete model failed: ${error.message}`, true);
  }
}

function setBackendStoppedState(message) {
  backendStopping = true;
  setStatus(message, true);
  setConnectionTestStatus("Backend is stopped.", true);
  setOllamaRuntimeStatus("Backend is stopped.", true);
  setOllamaStatus("Backend is stopped.", true);
  setCatalogStatus("Backend is stopped.", true);
  updateRuntimeStartupBanner(null);
  document.querySelectorAll("button, input, select, textarea").forEach((element) => {
    if (element.id !== "help-button") {
      element.disabled = true;
    }
  });
}

function hasConfiguredKey(input) {
  if (!input) {
    return false;
  }
  return input.dataset.wasMasked === "1" || Boolean((input.value || "").trim());
}

function setProviderKeyWarning(message, isError = false) {
  if (!providerKeyWarningLine) {
    return;
  }
  providerKeyWarningLine.textContent = message;
  providerKeyWarningLine.style.color = isError ? "#b5312e" : "#245f58";
}

function refreshProviderKeyWarning() {
  const provider = selectedProvider();

  if (provider === "openai") {
    if (hasConfiguredKey(openaiApiKeyInput)) {
      setProviderKeyWarning("OpenAI selected. Key is configured.");
    } else {
      setProviderKeyWarning("OpenAI selected but no OpenAI key is configured. Summaries may fall back.", true);
    }
    return;
  }

  if (provider === "anthropic") {
    if (hasConfiguredKey(anthropicApiKeyInput)) {
      setProviderKeyWarning("Anthropic selected. Key is configured.");
    } else {
      setProviderKeyWarning("Anthropic selected but no Anthropic key is configured. Summaries may fall back.", true);
    }
    return;
  }

  setProviderKeyWarning("Ollama selected. Remote provider keys are not required.");
}

function refreshProviderKeyFieldVisibility() {
  const provider = selectedProvider();
  openaiKeyGroup?.classList.toggle("is-hidden", provider !== "openai");
  anthropicKeyGroup?.classList.toggle("is-hidden", provider !== "anthropic");
}

function providerSystemMessageFieldName(provider) {
  switch ((provider || "").trim().toLowerCase()) {
    case "openai":
      return "openaiSystemMessage";
    case "anthropic":
      return "anthropicSystemMessage";
    default:
      return "ollamaSystemMessage";
  }
}

function providerDisplayName(provider) {
  switch ((provider || "").trim().toLowerCase()) {
    case "openai":
      return "OpenAI";
    case "anthropic":
      return "Anthropic";
    default:
      return "Ollama";
  }
}

function saveVisibleProviderSystemMessage() {
  if (!providerSystemMessageEditor) {
    return;
  }
  const field = settingsForm?.elements.namedItem(providerSystemMessageFieldName(selectedProvider()));
  if (field) {
    field.value = providerSystemMessageEditor.value;
  }
}

function refreshProviderSystemMessageEditor() {
  if (!providerSystemMessageEditor || !providerSystemMessageGroup) {
    return;
  }
  const provider = selectedProvider();
  const displayName = providerDisplayName(provider);
  const field = settingsForm?.elements.namedItem(providerSystemMessageFieldName(provider));
  if (providerSystemMessageTitle) {
    providerSystemMessageTitle.textContent = `System Message for ${displayName}`;
  }
  providerSystemMessageEditor.value = field?.value || "";
  if (providerSystemMessageNote) {
    providerSystemMessageNote.textContent =
      `${displayName} uses its own saved system message. Switching providers swaps the text shown here.`;
  }
}

async function refreshSystemMessageDefaults() {
  currentSystemMessageDefaults = await api.getSystemMessageDefaults();
  return currentSystemMessageDefaults;
}

function showSettingsScreen(screen) {
  settingsBasicScreen?.classList.toggle("is-hidden", screen !== "basic");
  settingsAdvancedScreen?.classList.toggle("is-hidden", screen !== "advanced");
}

function toggleSecretField(input, button) {
  if (!input || !button) {
    return;
  }
  const reveal = input.type === "password";
  input.type = reveal ? "text" : "password";
  button.textContent = reveal ? "Hide" : "Show";
}

async function refreshDownloadCatalog() {
  try {
    const result = await api.getModelCatalog("", 80);
    const models = Array.isArray(result.models) ? result.models : [];

    if (downloadableModelSelect) {
      downloadableModelSelect.innerHTML = "";
      const first = document.createElement("option");
      first.value = "";
      first.textContent = "Select a model to download...";
      downloadableModelSelect.appendChild(first);

      models.forEach((name) => {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        downloadableModelSelect.appendChild(option);
      });
    }

    setCatalogStatus(`Loaded ${models.length} downloadable models from the Ollama catalogue.`);
  } catch (error) {
    setCatalogStatus(`Catalogue refresh failed: ${error.message}`, true);
  }
}

let _downloadPollTimer = null;

async function downloadSelectedModel() {
  const selected = downloadableModelSelect?.value || "";
  if (!selected) {
    setCatalogStatus("Select a model before downloading.", true);
    return;
  }

  try {
    downloadModelBtn.disabled = true;
    const response = await api.downloadModel(selected);
    setCatalogStatus(`${response.message || "Download started"} — checking progress…`);
    setStatus(`Model download started: ${selected}`);
    _startDownloadPoll(selected);
  } catch (error) {
    downloadModelBtn.disabled = false;
    setCatalogStatus(`Download failed: ${error.message}`, true);
  }
}

function _startDownloadPoll(modelName) {
  if (_downloadPollTimer) {
    clearInterval(_downloadPollTimer);
    _downloadPollTimer = null;
  }

  const intervalMs = 5000;
  const maxAttempts = 120; // 10 min
  let attempts = 0;

  _downloadPollTimer = setInterval(async () => {
    attempts++;
    if (attempts > maxAttempts) {
      clearInterval(_downloadPollTimer);
      _downloadPollTimer = null;
      setCatalogStatus("Download status unknown after 10 min — check Ollama is running.", true);
      downloadModelBtn.disabled = false;
      return;
    }

    try {
      const result = await api.getDownloadStatus(modelName);
      if (result.status === "completed") {
        clearInterval(_downloadPollTimer);
        _downloadPollTimer = null;
        setCatalogStatus(`✓ ${modelName} downloaded successfully!`);
        downloadModelBtn.disabled = false;
        setStatus(`Model ${modelName} is ready.`);
        await refreshModelOptions();
        await refreshDownloadCatalog();
      } else if (result.status === "downloading") {
        const elapsed = Math.round((attempts * intervalMs) / 1000);
        setCatalogStatus(`Downloading ${modelName}… ${elapsed}s elapsed (large models can take several minutes).`);
      } else if (attempts > 6) {
        // After 30 s with no sign of the download, report and stop polling
        clearInterval(_downloadPollTimer);
        _downloadPollTimer = null;
        setCatalogStatus(`Could not confirm download of ${modelName}. Check that Ollama is running.`, true);
        downloadModelBtn.disabled = false;
      }
    } catch (_err) {
      // Ignore transient network errors during polling
    }
  }, intervalMs);
}

async function refreshModelOptions() {
  const provider = selectedProvider();
  try {
    const result = await api.getModelOptions(provider);
    const modelInput = settingsForm.elements.namedItem("modelName");
    if (!modelInput) {
      return;
    }

    const options = Array.isArray(result.models) ? result.models : [];
    if (options.length > 0 && !options.includes(modelInput.value)) {
      modelInput.value = options[0];
    }

    if (result.ollama) {
      setOllamaStatus(result.ollama.message, !result.ollama.running);
    } else {
      setOllamaStatus(`Loaded ${options.length} suggested models for ${result.provider}.`);
    }
  } catch (error) {
    setOllamaStatus(`Model refresh failed: ${error.message}`, true);
  }
}

function collectSearchCriteria() {
  const form = new FormData(searchForm);
  const repliedRaw = form.get("replied");
  const replied = repliedRaw === "" ? null : repliedRaw === "true";

  return {
    criteria: {
      keyword: (form.get("keyword") || "").toString(),
      rawSearch: (form.get("rawSearch") || "").toString(),
      sender: (form.get("sender") || "").toString(),
      recipient: (form.get("recipient") || "").toString(),
      unreadOnly: form.get("unreadOnly") === "on",
      readOnly: form.get("readOnly") === "on",
      replied,
      tag: (form.get("tag") || "").toString(),
      useAnd: form.get("useAnd") === "on",
    },
    summaryLength: Math.max(1, Number(form.get("summaryLength") || 5)),
  };
}

function collectSettings() {
  saveVisibleProviderSystemMessage();
  const payload = {};
  [
    "dummyMode",
    "imapHost",
    "imapPort",
    "imapUseSSL",
    "imapPassword",
    "smtpHost",
    "smtpPort",
    "smtpUseSSL",
    "smtpPassword",
    "username",
    "recipientEmail",
    "summarisedTag",
    "llmProvider",
    "openaiApiKey",
    "anthropicApiKey",
    "ollamaHost",
    "ollamaAutoStart",
    "ollamaStartOnStartup",
    "ollamaStopOnExit",
    "ollamaSystemMessage",
    "openaiSystemMessage",
    "anthropicSystemMessage",
    "modelName",
    "backendBaseURL",
  ].forEach((key) => {
    const input = settingsForm.elements.namedItem(key);
    if (input.type === "checkbox") {
      payload[key] = Boolean(input.checked);
    } else if (["imapPort", "smtpPort"].includes(key)) {
      payload[key] = Number(input.value);
    } else if (["openaiApiKey", "anthropicApiKey", "imapPassword", "smtpPassword"].includes(key)) {
      // If user left the field blank and we know a key is already stored, send the sentinel
      payload[key] = input.dataset.wasMasked === "1" && input.value === "" ? "__MASKED__" : input.value;
    } else {
      payload[key] = input.value;
    }
  });
  return payload;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function bindTabs() {
  const tabButtons = document.querySelectorAll(".tab");
  const panels = {
    search: document.getElementById("tab-search"),
    logs: document.getElementById("tab-logs"),
    settings: document.getElementById("tab-settings"),
    help: document.getElementById("tab-help"),
  };

  let previousTab = "search";

  tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const newTab = button.dataset.tab;
      if (newTab !== "help") {
        previousTab = newTab;
      }
      
      tabButtons.forEach((btn) => btn.classList.remove("active"));
      Object.values(panels).forEach((panel) => panel.classList.remove("active"));

      button.classList.add("active");
      panels[newTab].classList.add("active");
      updateHelpButton(newTab === "help");
    });
  });

  // Help button in header - toggles help tab
  const helpButton = document.getElementById("help-button");
  if (helpButton) {
    helpButton.addEventListener("click", () => {
      const helpPanel = panels.help;
      const isHelpActive = helpPanel.classList.contains("active");

      if (isHelpActive) {
        // Go back to previous tab
        const previousTabBtn = document.querySelector(`.tab[data-tab='${previousTab}']`);
        if (previousTabBtn) {
          previousTabBtn.click();
        }
      } else {
        // Open help tab
        tabButtons.forEach((btn) => btn.classList.remove("active"));
        Object.values(panels).forEach((panel) => panel.classList.remove("active"));
        helpPanel.classList.add("active");
        updateHelpButton(true);
      }
    });

    // ESC key to close help
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        const helpPanel = panels.help;
        if (helpPanel.classList.contains("active")) {
          helpButton.click();
        }
      }
    });
  }
}

function updateHelpButton(isHelpActive) {
  const helpButton = document.getElementById("help-button");
  const helpGlyph = helpButton?.querySelector(".help-btn-glyph");
  if (helpButton && helpGlyph) {
    helpGlyph.textContent = isHelpActive ? "×" : "?";
    helpButton.setAttribute("aria-label", isHelpActive ? "Close help" : "Open help");
  }
}

async function loadInitialData() {
  try {
    const [logs, settings, defaults] = await Promise.all([
      api.getLogs(),
      api.getSettings(),
      api.getSystemMessageDefaults(),
    ]);
    renderLogs(logs);
    fillSettings(settings);
    currentSystemMessageDefaults = defaults;
    await refreshRuntimeStatus();
    await refreshModelOptions();
    await refreshDownloadCatalog();
    await refreshFakeMailStatus();
    setStatus("Connected and loaded initial data.");
  } catch (error) {
    setStatus(`Initial load failed: ${error.message}`, true);
  }
}

async function runJobAction(action) {
  if (!currentJobId) {
    setStatus("No active job selected.", true);
    return;
  }

  try {
    await action(currentJobId);
    setStatus("Action completed.");
    renderLogs(await api.getLogs());
    updateActionScopePreview();
  } catch (error) {
    setStatus(`Action failed: ${error.message}`, true);
  }
}

function wireEvents() {
  const loadSettings = async () => {
    try {
      const settings = await api.getSettings();
      fillSettings(settings);
      await refreshRuntimeStatus();
      await refreshModelOptions();
      await refreshDownloadCatalog();
      await refreshFakeMailStatus();
      await refreshSystemMessageDefaults();
      setConnectionTestStatus("Connection not tested yet.");
      setStatus("Settings loaded.");
    } catch (error) {
      setStatus(`Settings load failed: ${error.message}`, true);
    }
  };

  testConnectionBtn.addEventListener("click", async () => {
    try {
      const result = await api.testConnection(collectSettings());
      const imapMessage = result?.imap?.message || "IMAP test passed";
      const smtpMessage = result?.smtp?.message || "SMTP test passed";
      setConnectionTestStatus(`${imapMessage} | ${smtpMessage}`);
    } catch (error) {
      setConnectionTestStatus(`Connection test failed: ${error.message}`, true);
    }
  });

  searchForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setStatus("Creating summary...");
    try {
      const payload = collectSearchCriteria();
      const result = await api.createSummary(payload);

      currentJobId = result.jobId;
      selectedMessageId = null;
      currentMessageDetail = null;
      latestMessageDetailRequest += 1;
      jobIdLabel.textContent = `Current Job: ${result.jobId}`;
      summaryText.textContent = result.summary;
      const messages = result.messages || [];
      const hasMessages = messages.length > 0;
      if (summaryCard) {
        summaryCard.dataset.state = hasMessages ? "ready" : "empty-results";
      }
      renderMessages(messages);
      setActionButtons(hasMessages);
      updateActionScopePreview();
      setStatus(hasMessages ? `Summary created for ${messages.length} messages.` : "No messages matched the current filters.");
      if (hasMessages) {
        await selectMessage(messages[0].id);
      } else {
        renderMessageDetail(null, {
          state: "empty",
          subject: "No messages matched",
          senderName: "",
          senderAddress: "",
          recipientName: "",
          recipientAddress: "",
          body: "",
        });
      }
      renderLogs(await api.getLogs());
    } catch (error) {
      setStatus(`Summary request failed: ${error.message}`, true);
    }
  });

  quickFilterButtons.forEach((button) => {
    button.addEventListener("click", () => applyQuickFilter(button.dataset.filter || "clear"));
  });

  [scopeActionMarkRead, scopeActionTag, scopeActionEmail].forEach((field) => {
    field?.addEventListener("change", updateActionScopePreview);
  });

  applyScopeActionsBtn?.addEventListener("click", async () => {
    if (!currentJobId) {
      setStatus("No active job selected.", true);
      return;
    }

    const selectedActions = [];
    if (scopeActionMarkRead?.checked) selectedActions.push(api.markRead);
    if (scopeActionTag?.checked) selectedActions.push(api.tagSummarised);
    if (scopeActionEmail?.checked) selectedActions.push(api.emailSummary);

    if (selectedActions.length === 0) {
      setStatus("Select at least one action to apply.", true);
      return;
    }

    for (const action of selectedActions) {
      try {
        await action(currentJobId);
      } catch (error) {
        setStatus(`Scoped action failed: ${error.message}`, true);
        return;
      }
    }

    renderLogs(await api.getLogs());
    setStatus("Scoped actions applied.");
    updateActionScopePreview();
  });

  messagesBody.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const row = target.closest("tr[data-message-id]");
    if (!row) {
      return;
    }

    const messageId = row.getAttribute("data-message-id");
    if (!messageId || messageId === selectedMessageId) {
      return;
    }

    await selectMessage(messageId);
  });

  messagesBody.addEventListener("keydown", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }

    const row = target.closest("tr[data-message-id]");
    if (!row) {
      return;
    }

    const messageId = row.getAttribute("data-message-id");
    if (!messageId || messageId === selectedMessageId) {
      return;
    }

    event.preventDefault();
    await selectMessage(messageId);
  });

  markReadBtn.addEventListener("click", () => runJobAction(api.markRead));
  tagSummaryBtn.addEventListener("click", () => runJobAction(api.tagSummarised));
  emailSummaryBtn.addEventListener("click", () => runJobAction(api.emailSummary));

  undoActionBtn.addEventListener("click", async () => {
    try {
      await api.undo();
      setStatus("Undo requested.");
      renderLogs(await api.getLogs());
    } catch (error) {
      setStatus(`Undo failed: ${error.message}`, true);
    }
  });

  refreshLogsBtn.addEventListener("click", async () => {
    try {
      renderLogs(await api.getLogs());
      setStatus("Log refreshed.");
    } catch (error) {
      setStatus(`Log refresh failed: ${error.message}`, true);
    }
  });

  logSearchInput?.addEventListener("input", refreshLogTimeline);
  logStatusFilter?.addEventListener("change", refreshLogTimeline);
  logUndoOnlyToggle?.addEventListener("change", refreshLogTimeline);

  logsBody.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const undoButton = target.closest(".log-undo-btn");
    if (!undoButton) {
      return;
    }

    const logId = undoButton.getAttribute("data-log-id");
    if (!logId) {
      setStatus("Undo failed: missing log id.", true);
      return;
    }

    try {
      undoButton.setAttribute("disabled", "disabled");
      await api.undoLog(logId);
      setStatus("Undo requested for selected log entry.");
      renderLogs(await api.getLogs());
    } catch (error) {
      undoButton.removeAttribute("disabled");
      setStatus(`Undo failed: ${error.message}`, true);
    }
  });

  refreshModelsBtn.addEventListener("click", refreshModelOptions);
  refreshRuntimeStatusBtn?.addEventListener("click", async () => {
    try {
      await refreshRuntimeStatus();
      setStatus("Runtime status refreshed.");
    } catch (error) {
      setStatus(`Runtime status refresh failed: ${error.message}`, true);
    }
  });
  providerSelect.addEventListener("change", () => {
    refreshModelOptions();
    refreshRuntimeStatus().catch((error) => {
      setStatus(`Runtime status refresh failed: ${error.message}`, true);
    });
    refreshProviderKeyWarning();
    refreshProviderKeyFieldVisibility();
    refreshProviderSystemMessageEditor();
    updateHealthStrip();
    updateDiagnosticsSummary();
  });
  providerSystemMessageEditor?.addEventListener("input", saveVisibleProviderSystemMessage);
  resetSystemMessageBtn?.addEventListener("click", async () => {
    try {
      if (!currentSystemMessageDefaults) {
        await refreshSystemMessageDefaults();
      }
      const fieldName = providerSystemMessageFieldName(selectedProvider());
      const nextValue = currentSystemMessageDefaults?.[fieldName] || "";
      const field = settingsForm?.elements.namedItem(fieldName);
      if (field) {
        field.value = nextValue;
      }
      if (providerSystemMessageEditor) {
        providerSystemMessageEditor.value = nextValue;
      }
      setStatus(`${providerDisplayName(selectedProvider())} system message reset in the form. Save settings to keep it.`);
    } catch (error) {
      setStatus(`System message reset failed: ${error.message}`, true);
    }
  });
  runtimeStartupActionBtn?.addEventListener("click", handleRuntimeAction);
  runtimeOllamaActionBtn?.addEventListener("click", handleRuntimeAction);
  runtimeOllamaInstallBtn?.addEventListener("click", installOllamaRuntime);
  runtimeOllamaStopBtn?.addEventListener("click", stopOllamaRuntime);
  openaiApiKeyInput?.addEventListener("input", refreshProviderKeyWarning);
  anthropicApiKeyInput?.addEventListener("input", refreshProviderKeyWarning);
  serveModelBtn?.addEventListener("click", serveConfiguredModel);
  deleteModelBtn?.addEventListener("click", deleteConfiguredModel);
  toggleOpenAiKeyBtn?.addEventListener("click", () => toggleSecretField(openaiApiKeyInput, toggleOpenAiKeyBtn));
  toggleAnthropicKeyBtn?.addEventListener("click", () => toggleSecretField(anthropicApiKeyInput, toggleAnthropicKeyBtn));
  toggleBackendKeyBtn?.addEventListener("click", () => toggleSecretField(backendApiKeyInput, toggleBackendKeyBtn));
  toggleImapPasswordBtn?.addEventListener("click", () => toggleSecretField(imapPasswordInput, toggleImapPasswordBtn));
  toggleSmtpPasswordBtn?.addEventListener("click", () => toggleSecretField(smtpPasswordInput, toggleSmtpPasswordBtn));
  refreshCatalogBtn.addEventListener("click", refreshDownloadCatalog);
  downloadModelBtn.addEventListener("click", downloadSelectedModel);
  stopMailSummariserBtn?.addEventListener("click", async () => {
    const confirmed = window.confirm("Stop the connected mail_summariser backend now?");
    if (!confirmed) {
      return;
    }

    try {
      const response = await api.shutdownRuntime();
      setBackendStoppedState(response.message || "mail_summariser is shutting down.");
    } catch (error) {
      setStatus(`Shutdown failed: ${error.message}`, true);
    }
  });
  resetLocalDatabaseBtn?.addEventListener("click", async () => {
    const confirmation = window.prompt("Type RESET DATABASE to delete all stored backend data.");
    if (confirmation !== "RESET DATABASE") {
      setStatus("Database reset cancelled.");
      return;
    }

    try {
      const response = await api.resetDatabase("RESET DATABASE");
      clearCurrentWorkspaceState();
      fillSettings(response.settings);
      renderLogs(await api.getLogs());
      await refreshRuntimeStatus();
      await refreshModelOptions();
      await refreshDownloadCatalog();
      await refreshFakeMailStatus();
      await refreshSystemMessageDefaults();
      setConnectionTestStatus("Connection not tested yet.");
      setStatus(response.message || "Local database reset to defaults.");
    } catch (error) {
      setStatus(`Database reset failed: ${error.message}`, true);
    }
  });
  startFakeMailBtn?.addEventListener("click", async () => {
    try {
      const status = await api.startFakeMailServer();
      renderFakeMailStatus(status);
      setStatus(status.message || "Fake mail server started.");
    } catch (error) {
      setStatus(`Fake mail start failed: ${error.message}`, true);
    }
  });
  stopFakeMailBtn?.addEventListener("click", async () => {
    try {
      const status = await api.stopFakeMailServer();
      renderFakeMailStatus(status);
      setStatus(status.message || "Fake mail server stopped.");
    } catch (error) {
      setStatus(`Fake mail stop failed: ${error.message}`, true);
    }
  });
  useFakeMailSettingsBtn?.addEventListener("click", () => {
    const suggested = currentFakeMailStatus?.suggestedSettings;
    if (!suggested) {
      setStatus("Start the fake mail server before applying its settings.", true);
      return;
    }
    fillSettings(suggested, { updateActiveMode: false });
    setStatus("Fake mail settings loaded into the form. Save settings to use them.");
  });
  openAdvancedSettingsBtn?.addEventListener("click", () => showSettingsScreen("advanced"));
  backToBasicSettingsBtn?.addEventListener("click", () => showSettingsScreen("basic"));
  loadBasicSettingsBtn?.addEventListener("click", loadSettings);
  loadAdvancedSettingsBtn?.addEventListener("click", loadSettings);
  dummyModeToggleBtn?.addEventListener("click", async () => {
    const nextMode = !activeDummyMode;
    try {
      await api.setDummyMode(nextMode);
      activeDummyMode = nextMode;
      if (dummyModeField) {
        dummyModeField.checked = nextMode;
      }
      syncDummyModeUI(nextMode);
      clearCurrentWorkspaceState();
      setStatus(nextMode ? "Sample mailbox enabled." : "Live mailbox enabled.");
      renderLogs(await api.getLogs());
    } catch (error) {
      setStatus(`Mailbox mode update failed: ${error.message}`, true);
    }
  });

  settingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const previousDummyMode = activeDummyMode;
      const previousBaseUrl = localStorage.getItem(storageKeys.baseUrl) || "";
      const nextBaseUrl = getBaseUrl();
      const payload = collectSettings();
      localStorage.setItem(storageKeys.baseUrl, getBaseUrl());
      localStorage.setItem(storageKeys.apiKey, backendApiKeyInput?.value || "");
      await api.saveSettings(payload);
      const refreshedSettings = await api.getSettings();
      fillSettings(refreshedSettings);
      if (previousDummyMode !== Boolean(refreshedSettings.dummyMode)) {
        clearCurrentWorkspaceState();
      }
      await refreshRuntimeStatus();
      await refreshModelOptions();
      await refreshDownloadCatalog();
      await refreshFakeMailStatus();
      await refreshSystemMessageDefaults();
      if (previousBaseUrl && previousBaseUrl !== nextBaseUrl) {
        setStatus("Settings saved. Backend target updated; no backend restart was performed.");
      } else {
        setStatus("Settings saved.");
      }
      renderLogs(await api.getLogs());
    } catch (error) {
      setStatus(`Settings save failed: ${error.message}`, true);
    }
  });
}

function bootstrapConnectionFromStorage() {
  const savedUrl = localStorage.getItem(storageKeys.baseUrl);
  const savedApiKey = localStorage.getItem(storageKeys.apiKey);
  const backendUrlInput = settingsForm?.elements.namedItem("backendBaseURL");

  if (backendUrlInput && !backendUrlInput.value) {
    backendUrlInput.value = savedUrl || "http://127.0.0.1:8766";
  }
  if (backendApiKeyInput) {
    backendApiKeyInput.value = savedApiKey || "";
  }
}

function resetSearchFormOnLoad() {
  if (!searchForm) {
    return;
  }

  searchForm.reset();

  const summaryLengthInput = searchForm.elements.namedItem("summaryLength");
  if (summaryLengthInput) {
    summaryLengthInput.value = "5";
  }

  const unreadOnlyInput = searchForm.elements.namedItem("unreadOnly");
  const readOnlyInput = searchForm.elements.namedItem("readOnly");
  const useAndInput = searchForm.elements.namedItem("useAnd");
  const repliedSelect = searchForm.elements.namedItem("replied");

  if (unreadOnlyInput) unreadOnlyInput.checked = true;
  if (readOnlyInput) readOnlyInput.checked = false;
  if (useAndInput) useAndInput.checked = true;
  if (repliedSelect) repliedSelect.value = "";
}

function init() {
  bootstrapConnectionFromStorage();
  resetSearchFormOnLoad();
  showSettingsScreen("basic");
  bindTabs();
  wireEvents();
  refreshProviderKeyWarning();
  refreshProviderKeyFieldVisibility();
  updateActionScopePreview();
  updateHealthStrip();
  updateDiagnosticsSummary();
  setQuickFilterState("today-unread");
  applyQuickFilter("today-unread");
  updateDigestMetrics();
  loadInitialData();
}

init();
