window.C33_CONFIG = Object.freeze({
  CONFIG_VERSION: "2026-09-26.1",
  BACKEND_URLS: [
    "https://iac33-fastapi-edge-main-production.up.railway.app",
    "https://iac33-backup-production.up.railway.app",
  ],
  CHAT_PATH: "/v1/chat",
  HEALTH_PATH: "/health",
  READY_PATH: "/ready",
  AI_READY_PATH: "/v1/ai-ready",
  CLIENT_TIMEOUT_MS: 22000,
  PROBE_TIMEOUT_MS: 4000,
  CIRCUIT_COOLDOWN_MS: 10000,
  CIRCUIT_FAILURE_THRESHOLD: 2,
  FAILOVER_ATTEMPT_TIMEOUT_MS: 10000,
});
