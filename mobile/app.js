const BACKEND_URLS = Array.from(
  new Set(
    (
      window.C33_CONFIG?.BACKEND_URLS || [
        "https://c33-backend.onrender.com",
        "https://iac33-backup-production.up.railway.app",
      ]
    ).map((url) => url.replace(/\/$/, "")),
  ),
);
const API_PATH = window.C33_CONFIG?.CHAT_PATH || "/v1/chat";
const HEALTH_PATH = window.C33_CONFIG?.HEALTH_PATH || "/health";
const USER_ID_KEY = "C33_USER_ID";

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

function createUserId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  if (window.crypto?.getRandomValues) {
    const bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0"));
    return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10, 16).join("")}`;
  }
  return `c33-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

const userId = localStorage.getItem(USER_ID_KEY) || createUserId();
localStorage.setItem(USER_ID_KEY, userId);

const SETTINGS_KEY = "C33_NEXO_SETTINGS";
const defaultSettings = {
  voiceTone: "neutral",
  colorVariety: false,
  fontSize: "medium",
  personality: "aggressive",
};

function loadSettings() {
  try {
    return { ...defaultSettings, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") };
  } catch {
    return { ...defaultSettings };
  }
}

const nexoSettings = loadSettings();

function saveSettings() {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(nexoSettings));
}

function applySettings() {
  document.body.classList.remove("font-small", "font-medium", "font-large", "font-xl");
  document.body.classList.add(`font-${nexoSettings.fontSize}`);
  document.body.classList.toggle("color-variety", nexoSettings.colorVariety);

  voiceTone.value = nexoSettings.voiceTone;
  colorVariety.checked = nexoSettings.colorVariety;
  fontSize.value = nexoSettings.fontSize;

  personalityOptions.forEach((button) => {
    const selected = button.dataset.personality === nexoSettings.personality;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}

function setSettingsOpen(open) {
  settings.classList.toggle("open", open);
  settings.setAttribute("aria-hidden", String(!open));
  if (open) settingsClose.focus();
  else settingsOpen.focus();
}

if (settings && settingsOpen && settingsClose && voiceTone && colorVariety && fontSize) {
  settingsOpen.addEventListener("click", () => setSettingsOpen(true));
  settingsClose.addEventListener("click", () => setSettingsOpen(false));
  settings.querySelector("[data-settings-close]")?.addEventListener("click", () => setSettingsOpen(false));

  voiceTone.addEventListener("change", () => {
    nexoSettings.voiceTone = voiceTone.value;
    saveSettings();
  });

  colorVariety.addEventListener("change", () => {
    nexoSettings.colorVariety = colorVariety.checked;
    applySettings();
    saveSettings();
  });

  fontSize.addEventListener("change", () => {
    nexoSettings.fontSize = fontSize.value;
    applySettings();
    saveSettings();
  });

  personalityOptions.forEach((button) => {
    button.addEventListener("click", () => {
      nexoSettings.personality = button.dataset.personality;
      applySettings();
      saveSettings();
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && settings.classList.contains("open")) {
      setSettingsOpen(false);
    }
  });

  applySettings();
}

function addMessage(text, role) {
  if (welcome) welcome.remove();
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = text;
  chat.appendChild(node);
  node.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return node;
}

function setStatus(text, mode = "") {
  status.textContent = text;
  statusDot.className = `status-dot ${mode}`;
}

const PRIMARY_BACKEND_INDEX = 0;
const BACKUP_BACKEND_INDEX = 1;
let activeBackendIndex = PRIMARY_BACKEND_INDEX;
let primaryCooldownUntil = 0;

function backendRole(index) {
  return index === PRIMARY_BACKEND_INDEX ? "principal" : "respaldo";
}

function normalizeNetworkError(error, backend) {
  if (error?.name === "AbortError") {
    return new Error(`${backendRole(backend)} agotó su tiempo de conexión.`);
  }

  if (error instanceof TypeError && /failed to fetch|networkerror|load failed/i.test(error.message || "")) {
    return new Error(`${backendRole(backend)} no está accesible desde este dispositivo.`);
  }

  return error instanceof Error ? error : new Error("Error de conexión.");
}

async function requestWithFailover(path, options = {}) {
  const isChat = path === API_PATH;
  const primaryCoolingDown = Date.now() < primaryCooldownUntil;
  const order = primaryCoolingDown
    ? [BACKUP_BACKEND_INDEX, PRIMARY_BACKEND_INDEX]
    : [PRIMARY_BACKEND_INDEX, BACKUP_BACKEND_INDEX];

  const failures = [];

  for (const index of order) {
    const baseUrl = BACKEND_URLS[index];
    if (!baseUrl) continue;

    const isPrimary = index === PRIMARY_BACKEND_INDEX;
    const attemptMs = isChat
      ? (isPrimary ? 6000 : 45000)
      : (isPrimary ? 2500 : 7000);

    setStatus(
      isChat
        ? `NEXO conectando · ${backendRole(index)}…`
        : `Comprobando ${backendRole(index)}…`,
      "busy",
    );

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), attemptMs);

    try {
      const response = await fetch(`${baseUrl}${path}`, {
        ...options,
        signal: controller.signal,
        cache: "no-store",
      });

      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const body = await response.json();
          detail = body?.detail || body?.message || detail;
        } catch {
          // Conserva el estado HTTP cuando la respuesta no es JSON.
        }
        throw new Error(detail);
      }

      activeBackendIndex = index;
      if (isPrimary) primaryCooldownUntil = 0;
      return response;
    } catch (error) {
      const normalized = normalizeNetworkError(error, index);
      failures.push(`${backendRole(index)}: ${normalized.message}`);

      if (isPrimary && (error?.name === "AbortError" || error instanceof TypeError)) {
        primaryCooldownUntil = Date.now() + 30000;
      }
    } finally {
      clearTimeout(timeoutId);
    }
  }

  const detail = failures.length
    ? failures.join(" ")
    : "No hubo servidores configurados.";

  throw new Error(`NEXO no pudo conectarse. ${detail} Revisa tu conexión y vuelve a enviar el mensaje.`);
}

async function checkHealth() {
  try {
    await requestWithFailover(HEALTH_PATH);
    const role = BACKEND_URLS[activeBackendIndex].includes("render.com")
      ? "principal"
      : "respaldo";
    setStatus(`Conectado · ${role}`, "online");
  } catch {
    setStatus("Sin conexión");
  }
}

function resizeInput() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
}

input.addEventListener("input", resizeInput);

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message || send.disabled) return;

  addMessage(message, "user");
  input.value = "";
  resizeInput();
  send.disabled = true;
  setStatus("NEXO pensando…", "busy");

  try {
    const response = await requestWithFailover(API_PATH, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        user_id: userId,
        stream: false,
        personality: nexoSettings.personality,
        voice_tone: nexoSettings.voiceTone,
      }),
    });

    const data = await response.json();
    addMessage(data.synthesis || "NEXO no devolvió una respuesta utilizable.", "assistant");
    setStatus("Conectado", "online");
  } catch (error) {
    addMessage(error.message || "Error de conexión.", "error");
    setStatus("Error", "busy");
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

  recognition.onstart = () => {
    recording = true;
    audio.classList.add("recording");
    audio.setAttribute("aria-label", "Detener grabación");
    audio.title = "Detener";
    setStatus("Escuchando…", "busy");
  };

  recognition.onresult = (event) => {
    let transcript = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      transcript += event.results[i][0].transcript;
    }
    input.value = transcript;
    resizeInput();
  };

  recognition.onerror = () => {
    setStatus("Conectado", "online");
  };

  recognition.onend = () => {
    recording = false;
    audio.classList.remove("recording");
    audio.setAttribute("aria-label", "Hablar con NEXO");
    audio.title = "Hablar";
    if (status.textContent === "Escuchando…") setStatus("Conectado", "online");
    input.focus();
  };

  audio.addEventListener("click", () => {
    if (recording) {
      recognition.stop();
    } else {
      recognition.start();
    }
  });
} else {
  audio.addEventListener("click", () => {
    addMessage("El reconocimiento de voz no está disponible en este dispositivo.", "error");
  });
}

checkHealth();
resizeInput();
input.focus();
