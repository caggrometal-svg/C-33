const BACKEND_URLS = Array.from(
  new Set((window.C33_CONFIG?.BACKEND_URLS || ["http://localhost:8000"]).map((url) => url.replace(/\/$/, ""))),
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

const userId = localStorage.getItem(USER_ID_KEY) || crypto.randomUUID();
localStorage.setItem(USER_ID_KEY, userId);

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
  for (const baseUrl of BACKEND_URLS) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 12000);
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
      lastError = error instanceof Error ? error : new Error("Error de conexión.");
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
