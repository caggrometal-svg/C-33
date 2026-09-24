const API_URL = (window.C33_CONFIG?.API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const API_PATH = window.C33_CONFIG?.CHAT_PATH || "/v1/chat";
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

async function checkHealth() {
  try {
    const response = await fetch(`${API_URL}/health`);
    if (!response.ok) throw new Error("healthcheck failed");
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
  setStatus("C-33 pensando...");

  try {
    const response = await fetch(`${API_URL}${API_PATH}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        user_id: userId,
        stream: false,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "La API rechazó la solicitud.");
    }

    addMessage(data.synthesis || "C-33 no devolvió una síntesis.", "assistant");
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
