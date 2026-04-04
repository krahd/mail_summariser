import { createApiClient } from "/web/api.js";

const storageKeys = {
  baseUrl: "mail-summariser-base-url",
  apiKey: "mail-summariser-api-key",
};

let currentJobId = null;

const statusLine = document.getElementById("status-line");
const testConnectionBtn = document.getElementById("test-connection");
const connectionTestStatusLine = document.getElementById("connection-test-status");
const dummyModeToggleBtn = document.getElementById("dummy-mode-toggle");
const dummyModeField = document.getElementById("dummy-mode-field");
const dummyModeDescription = document.getElementById("dummy-mode-description");

const searchForm = document.getElementById("search-form");
const summaryText = document.getElementById("summary-text");
const jobIdLabel = document.getElementById("job-id");
const messagesBody = document.getElementById("messages-body");

const markReadBtn = document.getElementById("mark-read");
const tagSummaryBtn = document.getElementById("tag-summary");
const emailSummaryBtn = document.getElementById("email-summary");
const undoActionBtn = document.getElementById("undo-action");

const logsBody = document.getElementById("logs-body");
const refreshLogsBtn = document.getElementById("refresh-logs");

const settingsForm = document.getElementById("settings-form");
const providerSelect = document.getElementById("llm-provider");
const refreshModelsBtn = document.getElementById("refresh-models");
const ollamaStatusLine = document.getElementById("ollama-status");
const downloadableModelSelect = document.getElementById("downloadable-model");
const refreshCatalogBtn = document.getElementById("refresh-catalog");
const downloadModelBtn = document.getElementById("download-model");
const catalogStatusLine = document.getElementById("catalog-status");
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
  statusLine.style.color = isError ? "#b5312e" : "#245f58";
}

function setConnectionTestStatus(message, isError = false) {
  if (!connectionTestStatusLine) {
    return;
  }
  connectionTestStatusLine.textContent = message;
  connectionTestStatusLine.style.color = isError ? "#b5312e" : "#245f58";
}

function setActionButtons(enabled) {
  markReadBtn.disabled = !enabled;
  tagSummaryBtn.disabled = !enabled;
  emailSummaryBtn.disabled = !enabled;
}

function renderMessages(messages) {
  if (!Array.isArray(messages) || messages.length === 0) {
    messagesBody.innerHTML = "<tr><td colspan='4'>No messages returned.</td></tr>";
    return;
  }

  messagesBody.innerHTML = messages
    .map(
      (m) =>
        `<tr><td>${escapeHtml(m.id)}</td><td>${escapeHtml(m.subject)}</td><td>${escapeHtml(
          m.sender
        )}</td><td>${escapeHtml(m.date)}</td></tr>`
    )
    .join("");
}

function renderLogs(logs) {
  if (!Array.isArray(logs) || logs.length === 0) {
    logsBody.innerHTML = "<tr><td colspan='6'>No logs available.</td></tr>";
    return;
  }

  logsBody.innerHTML = logs
    .map(
      (item) => {
        let undoCell = '<span class="log-badge log-badge-final">Final</span>';
        if (item.undoable) {
          undoCell = `<button type="button" class="log-undo-btn" data-log-id="${escapeHtml(
            item.id || ""
          )}">Undo</button>`;
        }

        return (
        `<tr><td>${escapeHtml(item.timestamp || "")}</td><td>${escapeHtml(
          item.action || ""
        )}</td><td>${escapeHtml(item.status || "")}</td><td>${escapeHtml(
          item.details || ""
        )}</td><td>${escapeHtml(item.job_id || "")}</td><td>${undoCell}</td></tr>`
        );
      }
    )
    .join("");
}

function fillSettings(settings) {
  const keyFieldNames = ["openaiApiKey", "anthropicApiKey", "imapPassword", "smtpPassword"];
  Object.entries(settings).forEach(([name, value]) => {
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
  syncDummyModeUI(Boolean(settings.dummyMode));
  refreshProviderKeyWarning();
  refreshProviderKeyFieldVisibility();
}

function syncDummyModeUI(enabled) {
  if (dummyModeField) {
    dummyModeField.checked = enabled;
  }
  if (dummyModeToggleBtn) {
    dummyModeToggleBtn.textContent = enabled ? "Dummy Mode: On" : "Dummy Mode: Off";
    dummyModeToggleBtn.classList.toggle("is-live", !enabled);
  }
  if (dummyModeDescription) {
    dummyModeDescription.textContent = enabled
      ? "Dummy mode is on. Searches and actions use the built-in test mailbox."
      : "Dummy mode is off. Searches and actions use the configured IMAP and SMTP servers.";
  }
}

function setOllamaStatus(message, isError = false) {
  if (!ollamaStatusLine) {
    return;
  }
  ollamaStatusLine.textContent = message;
  ollamaStatusLine.style.color = isError ? "#b5312e" : "#245f58";
}

function setCatalogStatus(message, isError = false) {
  if (!catalogStatusLine) {
    return;
  }
  catalogStatusLine.textContent = message;
  catalogStatusLine.style.color = isError ? "#b5312e" : "#245f58";
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
  const provider = providerSelect?.value || "ollama";

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
  const provider = providerSelect?.value || "ollama";
  openaiKeyGroup?.classList.toggle("is-hidden", provider !== "openai");
  anthropicKeyGroup?.classList.toggle("is-hidden", provider !== "anthropic");
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
  const provider = providerSelect?.value || "ollama";
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
    summaryLength: Number(form.get("summaryLength") || 5),
  };
}

function collectSettings() {
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
  if (helpButton) {
    helpButton.textContent = isHelpActive ? "×" : "?";
    helpButton.setAttribute("aria-label", isHelpActive ? "Close help" : "Open help");
  }
}

async function loadInitialData() {
  try {
    const [logs, settings] = await Promise.all([api.getLogs(), api.getSettings()]);
    renderLogs(logs);
    fillSettings(settings);
    await refreshModelOptions();
    await refreshDownloadCatalog();
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
  } catch (error) {
    setStatus(`Action failed: ${error.message}`, true);
  }
}

function wireEvents() {
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
      jobIdLabel.textContent = `Current Job: ${result.jobId}`;
      summaryText.textContent = result.summary;
      renderMessages(result.messages || []);
      setActionButtons(true);
      setStatus(`Summary created for ${result.messages.length} messages.`);
      renderLogs(await api.getLogs());
    } catch (error) {
      setStatus(`Summary request failed: ${error.message}`, true);
    }
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
  providerSelect.addEventListener("change", () => {
    refreshModelOptions();
    refreshProviderKeyWarning();
    refreshProviderKeyFieldVisibility();
  });
  openaiApiKeyInput?.addEventListener("input", refreshProviderKeyWarning);
  anthropicApiKeyInput?.addEventListener("input", refreshProviderKeyWarning);
  toggleOpenAiKeyBtn?.addEventListener("click", () => toggleSecretField(openaiApiKeyInput, toggleOpenAiKeyBtn));
  toggleAnthropicKeyBtn?.addEventListener("click", () => toggleSecretField(anthropicApiKeyInput, toggleAnthropicKeyBtn));
  toggleBackendKeyBtn?.addEventListener("click", () => toggleSecretField(backendApiKeyInput, toggleBackendKeyBtn));
  toggleImapPasswordBtn?.addEventListener("click", () => toggleSecretField(imapPasswordInput, toggleImapPasswordBtn));
  toggleSmtpPasswordBtn?.addEventListener("click", () => toggleSecretField(smtpPasswordInput, toggleSmtpPasswordBtn));
  refreshCatalogBtn.addEventListener("click", refreshDownloadCatalog);
  downloadModelBtn.addEventListener("click", downloadSelectedModel);
  dummyModeToggleBtn?.addEventListener("click", async () => {
    const nextMode = !(dummyModeField?.checked);
    try {
      await api.setDummyMode(nextMode);
      syncDummyModeUI(nextMode);
      setStatus(nextMode ? "Dummy mode enabled." : "Dummy mode disabled.");
      renderLogs(await api.getLogs());
    } catch (error) {
      setStatus(`Dummy mode update failed: ${error.message}`, true);
    }
  });

  settingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const previousBaseUrl = localStorage.getItem(storageKeys.baseUrl) || "";
      const nextBaseUrl = getBaseUrl();
      const payload = collectSettings();
      localStorage.setItem(storageKeys.baseUrl, getBaseUrl());
      localStorage.setItem(storageKeys.apiKey, backendApiKeyInput?.value || "");
      await api.saveSettings(payload);
      syncDummyModeUI(Boolean(payload.dummyMode));
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
  bindTabs();
  wireEvents();
  refreshProviderKeyWarning();
  refreshProviderKeyFieldVisibility();
  loadInitialData();
}

init();
