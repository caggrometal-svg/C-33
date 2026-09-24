const BACKEND_URLS = Array.from(
  new Set(
    (
      window.C33_CONFIG?.BACKEND_URLS || [
        "https://iac33-backup-production.up.railway.app",
        "https://c33-backend.onrender.com",
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

settingsOpen.addEventListener("click", () => setSettingsOpen(true));
settingsClose.addEventListener("click", () => setSettingsOpen(false));
settings.querySelector("[data-settings-close]").addEventListener("click", () => setSettingsOpen(false));

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

async function requestWithFailover(path, options = {}) {
  let lastError = new Error("Todos los servidores están desconectados.");
  const isChat = path === API_PATH;
  const timeoutMs = isChat ? 90000 : 10000;

  for (const baseUrl of BACKEND_URLS) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetch(`${baseUrl}${path}`, {
          ...options,
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response;
      } finally {
        clearTimeout(timeout);
      }
    } catch (error) {
      if (error?.name === "AbortError") {
        lastError = new Error(
          isChat
            ? "NEXO tardó demasiado en responder. El servidor sigue procesando la solicitud."
            : "Tiempo de conexión agotado.",
        );
      } else {
        lastError = error instanceof Error ? error : new Error("Error de conexión.");
      }
    }
  }
  throw lastError;
}

async function checkHealth() {
  try {
    await requestWithFailover(HEALTH_PATH);
    setStatus("Conectado", "online");
  } catch {
    setStatus("Desconectado");
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
