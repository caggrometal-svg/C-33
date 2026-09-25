const C = window.C33_CONFIG || {};
const DEFAULT_BACKEND_URLS = ["https://iac33-backup-production.up.railway.app"];
const configuredBackendUrls = Array.isArray(C.BACKEND_URLS)
  ? C.BACKEND_URLS.map((url) => String(url || "").trim().replace(/\/$/, "")).filter(Boolean)
  : [];
const USING_BUNDLED_BACKEND_FALLBACK = configuredBackendUrls.length === 0;
const BACKEND_URLS = Array.from(new Set(
  configuredBackendUrls.length ? configuredBackendUrls : DEFAULT_BACKEND_URLS
));
const API_PATH = C.CHAT_PATH || "/v1/chat";
const HEALTH_PATH = C.HEALTH_PATH || "/health";
const READY_PATH = C.READY_PATH || "/ready";
const AI_READY_PATH = C.AI_READY_PATH || "/v1/ai-ready";
const CLIENT_TIMEOUT_MS = Number(C.CLIENT_TIMEOUT_MS || 22000);
const PROBE_TIMEOUT_MS = Number(C.PROBE_TIMEOUT_MS || 2500);
const CIRCUIT_KEY = "C33_BACKEND_CIRCUITS_V4";
const USER_ID_KEY = "C33_USER_ID";
const CONVERSATION_KEY = "C33_CONVERSATION_ID";
const DIAGNOSTIC_KEY = "C33_REMOTE_DIAGNOSTICS_V1";
const MAX_DIAGNOSTICS = 40;
const CONFIG_VERSION = String(C.CONFIG_VERSION || "bundled-fallback");

function truncateDiagnostic(value, max = 4000) {
  const text = value == null ? "" : String(value);
  return text.length > max ? text.slice(0, max) + "…[truncated]" : text;
}

function readDiagnostics() {
  try {
    const parsed = JSON.parse(localStorage.getItem(DIAGNOSTIC_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function recordDiagnostic(stage, details = {}) {
  const entry = { ts: new Date().toISOString(), stage, ...details };
  const entries = [entry, ...readDiagnostics()].slice(0, MAX_DIAGNOSTICS);
  try { localStorage.setItem(DIAGNOSTIC_KEY, JSON.stringify(entries)); } catch {}
  try { console.info("[C33][DIAG]", entry); } catch {}
  window.C33_LAST_DIAGNOSTIC = entry;
  return entry;
}

if (USING_BUNDLED_BACKEND_FALLBACK) {
  recordDiagnostic("config-fallback", {
    reason: "runtime_config_missing_or_empty",
    config_version: CONFIG_VERSION,
    backend_count: BACKEND_URLS.length,
    backend: BACKEND_URLS[0] || "",
  });
}

function responseDiagnostic(response, startedAt) {
  return {
    url: response?.url || "",
    status: response?.status ?? null,
    statusText: response?.statusText || "",
    contentType: response?.headers?.get("content-type") || "",
    elapsed_ms: Math.round(performance.now() - startedAt),
  };
}

function diagnosticReport() {
  const entries = readDiagnostics().slice(0, 12);
  if (!entries.length) return "C33 diagnóstico: no hay registros todavía.";
  return entries.map((entry, index) => {
    const body = entry.body ? "\nbody=" + truncateDiagnostic(entry.body, 1800) : "";
    const reason = entry.reason ? " reason=" + truncateDiagnostic(entry.reason, 500) : "";
    const statusCode = entry.status == null ? "" : " HTTP=" + entry.status;
    const provider = entry.provider ? " provider=" + truncateDiagnostic(entry.provider, 300) : "";
    return "[" + index + "] " + entry.ts + " | " + entry.stage + statusCode + reason + provider + body;
  }).join("\n\n");
}

window.C33_DIAGNOSTICS = Object.freeze({
  getAll: () => readDiagnostics(),
  report: () => diagnosticReport(),
  clear: () => { try { localStorage.removeItem(DIAGNOSTIC_KEY); } catch {} },
});


const form = document.getElementById("chat-form");
const input = document.getElementById("message");
const chat = document.getElementById("chat");
const send = document.getElementById("send");
const audio = document.getElementById("audio");
const status = document.getElementById("status");
const statusDot = document.getElementById("status-dot");
const welcome = document.getElementById("welcome");
const settings = document.getElementById("settings");
const settingsOpen = document.getElementById("settings-open");
const settingsClose = document.getElementById("settings-close");
const voiceTone = document.getElementById("voice-tone");
const colorVariety = document.getElementById("color-variety");
const fontSize = document.getElementById("font-size");
const personalityOptions = [...document.querySelectorAll("[data-personality]")];

function createId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return "c33-" + Date.now() + "-" + Math.random().toString(36).slice(2);
}

const userId = localStorage.getItem(USER_ID_KEY) || createId();
localStorage.setItem(USER_ID_KEY, userId);
const conversationId = localStorage.getItem(CONVERSATION_KEY) || createId();
localStorage.setItem(CONVERSATION_KEY, conversationId);

const SETTINGS_KEY = "C33_NEXO_SETTINGS";
const defaultSettings = { voiceTone: "neutral", colorVariety: false, fontSize: "medium", personality: "aggressive" };
function loadSettings() {
  try { return { ...defaultSettings, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") }; }
  catch { return { ...defaultSettings }; }
}
const nexoSettings = loadSettings();
function saveSettings() { localStorage.setItem(SETTINGS_KEY, JSON.stringify(nexoSettings)); }
function applySettings() {
  document.body.classList.remove("font-small", "font-medium", "font-large", "font-xl");
  document.body.classList.add("font-" + nexoSettings.fontSize);
  document.body.classList.toggle("color-variety", nexoSettings.colorVariety);
  if (voiceTone) voiceTone.value = nexoSettings.voiceTone;
  if (colorVariety) colorVariety.checked = nexoSettings.colorVariety;
  if (fontSize) fontSize.value = nexoSettings.fontSize;
  personalityOptions.forEach((button) => {
    const selected = button.dataset.personality === nexoSettings.personality;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}
function setSettingsOpen(open) {
  settings?.classList.toggle("open", open);
  settings?.setAttribute("aria-hidden", String(!open));
  (open ? settingsClose : settingsOpen)?.focus();
}
if (settings && settingsOpen && settingsClose) {
  settingsOpen.addEventListener("click", () => setSettingsOpen(true));
  settingsClose.addEventListener("click", () => setSettingsOpen(false));
  settings.querySelector("[data-settings-close]")?.addEventListener("click", () => setSettingsOpen(false));
  voiceTone?.addEventListener("change", () => { nexoSettings.voiceTone = voiceTone.value; saveSettings(); });
  colorVariety?.addEventListener("change", () => { nexoSettings.colorVariety = colorVariety.checked; applySettings(); saveSettings(); });
  fontSize?.addEventListener("change", () => { nexoSettings.fontSize = fontSize.value; applySettings(); saveSettings(); });
  personalityOptions.forEach((button) => button.addEventListener("click", () => { nexoSettings.personality = button.dataset.personality; applySettings(); saveSettings(); }));
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && settings.classList.contains("open")) setSettingsOpen(false); });
  applySettings();
}

function localFallbackMessage(message) {
  return "NEXO está operando en respaldo local. La IA remota no está disponible. Consulta recibida: " + message.slice(0, 200);
}

function addMessage(text, role) {
  welcome?.remove();
  const node = document.createElement("div");
  node.className = "message " + role;
  node.textContent = text;
  chat.appendChild(node);
  node.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return node;
}

const CONNECTION_STATES = Object.freeze(["OFFLINE", "ONLINE", "READY", "STREAMING", "AI_READY", "DEGRADED"]);
const CONNECTED_STATE = "AI_READY";
const VALID_TRANSITIONS = Object.freeze({
  OFFLINE: new Set(["OFFLINE", "ONLINE", "READY", "AI_READY", "DEGRADED"]),
  ONLINE: new Set(["ONLINE", "READY", "AI_READY", "DEGRADED", "OFFLINE"]),
  READY: new Set(["READY", "STREAMING", "AI_READY", "DEGRADED", "OFFLINE", "ONLINE"]),
  STREAMING: new Set(["STREAMING", "AI_READY", "DEGRADED", "READY", "OFFLINE"]),
  AI_READY: new Set(["AI_READY", "DEGRADED", "READY", "STREAMING", "ONLINE", "OFFLINE"]),
  DEGRADED: new Set(["DEGRADED", "AI_READY", "READY", "ONLINE", "OFFLINE"]),
});
let connectionState = "OFFLINE";
let lastBackendIndex = 0;
let lastMeta = null;
let circuits = loadCircuits();
const activeControllers = new Set();

window.addEventListener("pagehide", () => {
  for (const controller of activeControllers) controller.abort();
  activeControllers.clear();
});

function loadCircuits() {
  try {
    const raw = JSON.parse(localStorage.getItem(CIRCUIT_KEY) || "{}");
    return BACKEND_URLS.reduce((acc, _, index) => {
      acc[index] = {
        failures: Number(raw[index]?.failures || 0),
        openUntil: Number(raw[index]?.openUntil || 0),
        lastReason: raw[index]?.lastReason || "",
      };
      return acc;
    }, {});
  } catch {
    return BACKEND_URLS.reduce((acc, _, index) => {
      acc[index] = { failures: 0, openUntil: 0, lastReason: "" };
      return acc;
    }, {});
  }
}
function saveCircuits() { localStorage.setItem(CIRCUIT_KEY, JSON.stringify(circuits)); }
function backendRole(index) { return index === 0 ? "principal" : "respaldo"; }
function circuitOpen(index) { return Number(circuits[index]?.openUntil || 0) > Date.now(); }
function recordBackendSuccess(index) {
  circuits[index] = { failures: 0, openUntil: 0, lastReason: "success" };
  lastBackendIndex = index;
  saveCircuits();
}
function recordBackendFailure(index, reason) {
  const item = circuits[index] || { failures: 0, openUntil: 0, lastReason: "" };
  item.failures += 1;
  item.lastReason = reason;
  if (item.failures >= Number(C.CIRCUIT_FAILURE_THRESHOLD || 2)) item.openUntil = Date.now() + Number(C.CIRCUIT_COOLDOWN_MS || 60000);
  circuits[index] = item;
  saveCircuits();
}
function transition(next, detail = "") {
  if (!CONNECTION_STATES.includes(next)) throw new Error("invalid_connection_state");
  if (!VALID_TRANSITIONS[connectionState]?.has(next)) throw new Error("invalid_connection_transition");
  connectionState = next;
  status.textContent = detail || next;
  statusDot.className = "status-dot " + next.toLowerCase().replace("_", "-");
}
function stateRank(value) {
  return { OFFLINE: 0, ONLINE: 1, READY: 2, DEGRADED: 4, AI_READY: 5 }[value] ?? 0;
}
function connectedState() { return connectionState === CONNECTED_STATE; }

function normalizeError(error) {
  if (error?.name === "AbortError") return "timeout";
  if (error instanceof TypeError) return "network_error";
  return error instanceof Error ? error.message : "connection_error";
}

async function fetchBounded(url, options = {}, timeoutMs = CLIENT_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), Math.max(250, timeoutMs));
  try { return await fetch(url, { ...options, signal: controller.signal, cache: "no-store" }); }
  finally { clearTimeout(timer); }
}

async function probeBackend(index, { ignoreCircuit = false } = {}) {
  const base = BACKEND_URLS[index];
  if (!base) return { backend: index, state: "OFFLINE", reason: "not_configured" };
  if (circuitOpen(index) && !ignoreCircuit) {
    recordDiagnostic("circuit_open", { backend: index, role: backendRole(index), url: base, reason: "circuit_open" });
    return { backend: index, state: "OFFLINE", reason: "circuit_open" };
  }
  if (circuitOpen(index) && ignoreCircuit) {
    recordDiagnostic("circuit_half_open_probe", { backend: index, role: backendRole(index), url: base, reason: "live_probe_overrides_circuit" });
  }

  const deadlineAt = Date.now() + Math.max(PROBE_TIMEOUT_MS + 3000, 5500);

  try {
    let remaining = Math.max(500, deadlineAt - Date.now());

    let startedAt = performance.now();
    const health = await fetchBounded(base + HEALTH_PATH, {}, remaining);
    const healthBody = await health.clone().text().catch(() => "");
    recordDiagnostic("health", {
      backend: index,
      role: backendRole(index),
      ...responseDiagnostic(health, startedAt),
      body: truncateDiagnostic(healthBody),
    });
    if (!health.ok) return {
      backend: index,
      state: "OFFLINE",
      reason: "health_http_" + health.status,
      diagnostic: truncateDiagnostic(healthBody, 500),
    };

    remaining = Math.max(500, deadlineAt - Date.now());
    startedAt = performance.now();
    const ready = await fetchBounded(base + READY_PATH, {}, remaining);
    const readyBody = await ready.clone().text().catch(() => "");
    recordDiagnostic("ready", {
      backend: index,
      role: backendRole(index),
      ...responseDiagnostic(ready, startedAt),
      body: truncateDiagnostic(readyBody),
    });
    if (!ready.ok) return {
      backend: index,
      state: "ONLINE",
      reason: "ready_http_" + ready.status,
      diagnostic: truncateDiagnostic(readyBody, 500),
    };

    remaining = Math.max(500, deadlineAt - Date.now());
    startedAt = performance.now();
    const ai = await fetchBounded(base + AI_READY_PATH, {}, remaining);
    const aiBody = await ai.text().catch(() => "");
    let aiData = null;
    try { aiData = JSON.parse(aiBody); } catch {}

    recordDiagnostic("ai-ready", {
      backend: index,
      role: backendRole(index),
      ...responseDiagnostic(ai, startedAt),
      body: truncateDiagnostic(aiBody),
      parsed_status: aiData?.status ?? null,
      provider_used: aiData?.provider_used ?? null,
      failover_triggered: aiData?.failover_triggered ?? null,
    });

    if (ai.ok && aiData?.status === "ai_ready" && Boolean(aiData?.provider_used)) {
      recordBackendSuccess(index);
      return {
        backend: index,
        state: aiData.failover_triggered ? "DEGRADED" : "AI_READY",
        reason: aiData.failover_triggered ? "remote_success_failover" : "remote_success",
        provider: aiData.provider_used || "",
        diagnostic: aiBody,
      };
    }

    const reason = aiData?.detail?.reason
      || aiData?.reason
      || ("ai_ready_http_" + ai.status);

    recordBackendFailure(index, reason);
    return {
      backend: index,
      state: "READY",
      reason,
      diagnostic: aiBody,
      status: ai.status,
    };
  } catch (error) {
    const reason = normalizeError(error);
    recordDiagnostic("probe_error", {
      backend: index,
      role: backendRole(index),
      url: base + AI_READY_PATH,
      reason,
      error_name: error?.name || "",
      error_message: error?.message || "",
    });
    recordBackendFailure(index, reason);
    return { backend: index, state: "OFFLINE", reason };
  }
}

let refreshInFlight = null;
async function refreshConnection() {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    if (activeControllers.size > 0) return [];
    const results = await Promise.all(BACKEND_URLS.map((_, i) => probeBackend(i, { ignoreCircuit: true })));
    const best = results.reduce((a, b) => stateRank(b.state) > stateRank(a.state) ? b : a, results[0] || { state: "OFFLINE", backend: 0 });
    if (best?.state === "AI_READY") transition(best.backend === 0 ? "AI_READY" : "DEGRADED", "NEXO · " + (best.backend === 0 ? "Conectado · IA lista" : "Degradado · respaldo activo") + " · " + backendRole(best.backend));
    else if (best?.state === "DEGRADED") transition("DEGRADED", "NEXO · Degradado · respaldo activo");
    else if (best?.state === "READY") transition("READY", "NEXO · Backend listo · " + (best.reason || "IA pendiente"));
    else if (best?.state === "ONLINE") transition("ONLINE", "NEXO · Internet disponible · backend no listo");
    else transition("OFFLINE", "NEXO · Sin conexión · " + (best?.reason || "sin diagnóstico"));
    return results;
  })().finally(() => { refreshInFlight = null; });
  return refreshInFlight;
}

function orderedBackends() {
  const available = BACKEND_URLS
    .map((_, index) => index)
    .filter((index) => !circuitOpen(index));
  if (available.length) return available;

  const halfOpen = BACKEND_URLS
    .map((_, index) => ({
      index,
      openUntil: Number(circuits[index]?.openUntil || 0),
    }))
    .sort((a, b) => a.openUntil - b.openUntil);

  return halfOpen.length ? [halfOpen[0].index] : [];
}

async function streamChatWithFailover(options = {}) {
  const started = performance.now();
  const deadlineAt = Date.now() + CLIENT_TIMEOUT_MS;
  const failures = [];

  for (const index of orderedBackends()) {
    const remaining = Math.max(750, deadlineAt - Date.now());
    if (remaining <= 750) break;
    const base = BACKEND_URLS[index];
    if (!base) continue;

    transition("STREAMING", "NEXO · IA remota " + backendRole(index) + "…");
    const controller = new AbortController();
    activeControllers.add(controller);
    const timer = setTimeout(() => controller.abort(), remaining);
    let receivedToken = false;
    let fallbackReceived = false;
    let streamError = null;

    try {
      const response = await fetch(base + "/v1/ai/stream", {
        ...options,
        headers: {
          ...(options.headers || {}),
          "Accept": "text/event-stream",
          "Cache-Control": "no-cache",
          "X-C33-Deadline-Epoch-Ms": String(deadlineAt),
          "X-C33-Client-Timeout-Ms": String(CLIENT_TIMEOUT_MS),
          "X-C33-Allow-Local-Fallback": "true",
        },
        signal: controller.signal,
        cache: "no-store",
      });

      recordDiagnostic("stream-response", {
        backend: index,
        role: backendRole(index),
        ...responseDiagnostic(response, started),
        endpoint: "/v1/ai/stream",
      });

      if (!response.ok) {
        let detail = "HTTP " + response.status;
        let errorBody = "";
        try {
          errorBody = await response.text();
          const body = JSON.parse(errorBody);
          detail = body?.detail?.reason || body?.detail || detail;
        } catch {}
        recordDiagnostic("stream-http-error", {
          backend: index,
          role: backendRole(index),
          status: response.status,
          endpoint: "/v1/ai/stream",
          reason: String(detail),
          body: truncateDiagnostic(errorBody),
        });
        failures.push(backendRole(index) + ": " + detail);
        recordBackendFailure(index, String(detail));
        continue;
      }

      if (!response.body) throw new Error("stream_body_unavailable");

      const decoder = new TextDecoder("utf-8");
      const reader = response.body.getReader();
      let buffer = "";
      let finalMeta = null;
      const assistantNode = addMessage("", "assistant");

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n?/g, "\n");
        const frames = buffer.split("\n\n");
        buffer = frames.pop() || "";

        for (const frame of frames) {
          const lines = frame.split("\n");
          let eventName = "";
          let dataLine = "";
          for (const line of lines) {
            if (line.startsWith("event:")) eventName = line.slice(6).trim();
            else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
          }
          if (!dataLine) continue;

          let data;
          try { data = JSON.parse(dataLine); }
          catch {
            recordDiagnostic("sse-parse-error", {
              backend: index,
              role: backendRole(index),
              event: eventName || "message",
              raw: truncateDiagnostic(dataLine, 1200),
            });
            continue;
          }

          if (eventName === "fallback" || eventName === "error" || eventName === "done") {
            const diagnosticData = { ...data };
            delete diagnosticData.text;
            recordDiagnostic("sse-" + (eventName || "message"), {
              backend: index,
              role: backendRole(index),
              data: diagnosticData,
            });
          }

          if (eventName === "token" && data.text) {
            receivedToken = true;
            assistantNode.textContent += data.text;
            assistantNode.scrollIntoView({ behavior: "smooth", block: "nearest" });
          }
          if (eventName === "fallback" && data.text) {
            fallbackReceived = true;
            assistantNode.textContent += data.text;
            finalMeta = data._meta || finalMeta;
          }
          if (eventName === "error") {
            streamError = data?.reason || "stream_error";
            finalMeta = data?._meta || finalMeta;
          }
          if (eventName === "done") finalMeta = data._meta || null;
        }
      }

      if (streamError) throw new Error(streamError);
      if (finalMeta?.used_local_fallback || fallbackReceived) {
        const reason = finalMeta?.final_reason || "remote_generation_failed";
        recordBackendFailure(index, reason);
        if (Date.now() < deadlineAt && index < BACKEND_URLS.length - 1) {
          assistantNode.remove();
          continue;
        }
        lastMeta = finalMeta;
        assistantNode.classList.add("fallback");
        transition("DEGRADED", "NEXO · respaldo local · IA remota no disponible");
        return { meta: finalMeta, fallback: true, client_latency_ms: Math.round(performance.now() - started) };
      }
      if (!receivedToken) {
        recordDiagnostic("stream-empty", {
          backend: index,
          role: backendRole(index),
          endpoint: "/v1/ai/stream",
          elapsed_ms: Math.round(performance.now() - started),
          fallback_received: fallbackReceived,
          stream_error: streamError || "",
        });
        throw new Error("empty_stream");
      }
      recordBackendSuccess(index);
      lastMeta = finalMeta;
      const degraded = index !== 0 || Boolean(finalMeta?.failover_triggered) || finalMeta?.system_status === "DEGRADED";
      transition(degraded ? "DEGRADED" : "AI_READY", "NEXO · " + (degraded ? "respaldo activo" : "Conectado · IA lista") + " · " + backendRole(index));
      return { meta: finalMeta, client_latency_ms: Math.round(performance.now() - started) };
    } catch (error) {
      const reason = normalizeError(error);
      recordDiagnostic("stream-error", {
        backend: index,
        role: backendRole(index),
        endpoint: "/v1/ai/stream",
        reason,
        error_name: error?.name || "",
        error_message: error?.message || "",
        received_token: receivedToken,
        fallback_received: fallbackReceived,
        elapsed_ms: Math.round(performance.now() - started),
      });
      failures.push(backendRole(index) + ": " + reason);
      recordBackendFailure(index, reason);
      if (receivedToken) {
        throw new Error("NEXO stream interrumpido: " + reason);
      }
    } finally {
      clearTimeout(timer);
      activeControllers.delete(controller);
    }
  }

  transition("OFFLINE", "NEXO · backends no disponibles");
  const error = new Error("NEXO no pudo iniciar streaming. " + failures.join(" "));
  error.code = "REMOTE_EXHAUSTED";
  throw error;
}

async function requestWithFailover(path, options = {}) {
  if (path === API_PATH && options.method === "POST") {
    return requestWithFailoverHttp(path, options);
  }
  return requestWithFailoverHttp(path, options);
}

async function requestWithFailoverHttp(path, options = {}) {
  const started = performance.now();
  const deadlineAt = Date.now() + CLIENT_TIMEOUT_MS;
  const failures = [];
  for (const index of orderedBackends()) {
    const remaining = Math.max(500, deadlineAt - Date.now());
    if (remaining <= 500) break;
    const base = BACKEND_URLS[index];
    if (!base) continue;
    transition("ONLINE", "NEXO · " + backendRole(index) + "…");
    try {
      const response = await fetchBounded(
        base + path,
        {
          ...options,
          headers: {
            ...(options.headers || {}),
            "X-C33-Deadline-Epoch-Ms": String(deadlineAt),
            "X-C33-Client-Timeout-Ms": String(CLIENT_TIMEOUT_MS),
          },
        },
        remaining,
      );
      let data = null;
      try { data = await response.json(); } catch { data = null; }
      if (!response.ok) {
        const reason = data?.detail?.reason || data?.detail || "HTTP " + response.status;
        failures.push(backendRole(index) + ": " + reason);
        recordBackendFailure(index, String(reason));
        if ([400, 401, 403].includes(response.status)) throw new Error(String(reason));
        continue;
      }
      if (data?._meta?.used_local_fallback) {
        failures.push(backendRole(index) + ": " + (data._meta.final_reason || "remote_generation_failed"));
        lastMeta = data._meta;
        continue;
      }
      recordBackendSuccess(index);
      lastMeta = data?._meta || null;
      lastBackendIndex = index;
      const degraded = index !== 0 || Boolean(lastMeta?.failover_triggered) || lastMeta?.system_status === "DEGRADED" || lastMeta?.memory_sync === "PENDING";
      transition(degraded ? "DEGRADED" : "AI_READY", "NEXO · " + (degraded ? "DEGRADED" : "AI_READY") + " · " + backendRole(index));
      lastMeta = { ...(lastMeta || {}), client_latency_ms: Math.round(performance.now() - started), backend_role: backendRole(index) };
      return { response, data };
    } catch (error) {
      const reason = normalizeError(error);
      failures.push(backendRole(index) + ": " + reason);
      recordBackendFailure(index, reason);
      if (Date.now() >= deadlineAt) break;
    }
  }
  throw new Error("NEXO no pudo completar la operación. " + failures.join(" "));
}

function resizeInput() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 150) + "px";
}
input.addEventListener("input", resizeInput);
input.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); } });

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message || send.disabled) return;
  addMessage(message, "user");

  if (/^\/?diagn[oó]stico$/i.test(message)) {
    addMessage(diagnosticReport(), "assistant");
    input.value = "";
    resizeInput();
    transition(connectionState, "NEXO · diagnóstico remoto");
    input.focus();
    return;
  }

  input.value = "";
  resizeInput();
  send.disabled = true;
  transition("READY", "NEXO · procesando…");
  const requestId = createId();
  const requestPayload = {
    message,
    user_id: userId,
    conversation_id: conversationId,
    request_id: requestId,
    stream: true,
    personality: nexoSettings.personality,
    voice_tone: nexoSettings.voiceTone,
  };
  try {
    await streamChatWithFailover({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload),
    });
  } catch (error) {
    if (error?.code === "REMOTE_EXHAUSTED") {
      recordDiagnostic("stream-exhausted", {
        reason: error.message || "REMOTE_EXHAUSTED",
        request_id: requestId,
      });
      try {
        const httpResult = await requestWithFailover(API_PATH, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...requestPayload, stream: false }),
        });
        const data = httpResult?.data;
        if (data?.synthesis) {
          addMessage(data.synthesis, "assistant");
          transition("AI_READY", "NEXO · IA lista · recuperación HTTP");
          recordDiagnostic("stream-http-recovery", {
            request_id: requestId,
            provider: data?._meta?.provider_used || "",
            status: httpResult?.response?.status ?? null,
          });
        } else {
          throw new Error("http_recovery_empty_response");
        }
      } catch (recoveryError) {
        recordDiagnostic("stream-http-recovery-failed", {
          request_id: requestId,
          reason: normalizeError(recoveryError),
          error_name: recoveryError?.name || "",
          error_message: recoveryError?.message || "",
        });
        addMessage("NEXO no pudo conectarse a la IA remota. Diagnóstico: " + (error.message || "REMOTE_EXHAUSTED") + " | recuperación HTTP: " + (recoveryError.message || "failed"), "error");
        transition("OFFLINE", "NEXO · IA remota no disponible");
      }
    } else {
      addMessage(error.message || "Error de conexión.", "error");
      transition("DEGRADED", "NEXO · servicio no disponible");
    }
  } finally {
    send.disabled = false;
    input.focus();
  }
});

let recognition = null;
let recording = false;
if ("SpeechRecognition" in window || "webkitSpeechRecognition" in window) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRecognition();
  recognition.lang = "es-CL";
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.onstart = () => { recording = true; audio.classList.add("recording"); audio.setAttribute("aria-label", "Detener grabación"); audio.title = "Detener"; };
  recognition.onresult = (event) => { let transcript = ""; for (let i = event.resultIndex; i < event.results.length; i += 1) transcript += event.results[i][0].transcript; input.value = transcript; resizeInput(); };
  recognition.onerror = () => {};
  recognition.onend = () => { recording = false; audio.classList.remove("recording"); audio.setAttribute("aria-label", "Hablar con NEXO"); audio.title = "Hablar"; input.focus(); };
  audio.addEventListener("click", () => recording ? recognition.stop() : recognition.start());
} else {
  audio.addEventListener("click", () => addMessage("El reconocimiento de voz no está disponible en este dispositivo.", "error"));
}

refreshConnection();
setInterval(() => { if (document.visibilityState === "visible" && activeControllers.size === 0) refreshConnection(); }, 60000);
resizeInput();
