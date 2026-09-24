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
const status = document.getElementById("status");

const userId = localStorage.getItem(USER_ID_KEY) || crypto.randomUUID();
localStorage.setItem(USER_ID_KEY, userId);

function addMessage(text, role) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = text;
  chat.appendChild(node);
  node.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return node;
}

function setStatus(text) {
  status.textContent = text;
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
    setStatus("Conectado");
  } catch {
    setStatus("Desconectado");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;

  addMessage(message, "user");
  input.value = "";
  send.disabled = true;
  setStatus("NEXO pensando...");

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
    addMessage(data.synthesis || "NEXO no devolvió una síntesis.", "assistant");
    setStatus("Conectado");
  } catch (error) {
    addMessage(error.message || "Error de conexión.", "error");
    setStatus("Error");
  } finally {
    send.disabled = false;
    input.focus();
  }
});

checkHealth();
input.focus();
