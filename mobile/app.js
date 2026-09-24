const DEFAULT_API_URL = "http://localhost:8000";
const API_URL = (localStorage.getItem("C33_API_URL") || DEFAULT_API_URL).replace(/\/$/, "");
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

async function checkHealth() {
  try {
    const response = await fetch(`${API_URL}/health`);
    if (!response.ok) throw new Error("healthcheck failed");
    status.textContent = "Conectado";
  } catch {
    status.textContent = "Desconectado";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;

  addMessage(message, "user");
  input.value = "";
  send.disabled = true;
  status.textContent = "Procesando…";

  try {
    const response = await fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, user_id: userId }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "La API rechazó la solicitud.");
    }

    addMessage(data.synthesis || "C-33 no devolvió una síntesis.", "assistant");
    status.textContent = "Conectado";
  } catch (error) {
    addMessage(error.message || "Error de conexión.", "error");
    status.textContent = "Error";
  } finally {
    send.disabled = false;
    input.focus();
  }
});

checkHealth();
input.focus();
