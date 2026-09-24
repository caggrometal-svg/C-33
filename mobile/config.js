window.C33_CONFIG = Object.freeze({
  BACKEND_URLS: [
    "https://c33-backend.onrender.com",
    "https://iac33-backup-production.up.railway.app",
  ],
  CHAT_PATH: "/v1/chat",
  HEALTH_PATH: "/health",
  READY_PATH: "/ready",
  AI_READY_PATH: "/v1/ai-ready",
  CLIENT_TIMEOUT_MS: 28000,
  PROBE_TIMEOUT_MS: 2500,
  CIRCUIT_COOLDOWN_MS: 60000,
  CIRCUIT_FAILURE_THRESHOLD: 2,
});
