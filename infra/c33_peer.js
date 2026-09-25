const http = require("http");
const fs = require("fs");
const crypto = require("crypto");

const STORE = "/app/data/c33-peer.json";
const MAX = 2_000_000;

let state = { messages: {} };
try {
  state = JSON.parse(fs.readFileSync(STORE, "utf8"));
  if (!state || typeof state !== "object" || !state.messages || typeof state.messages !== "object") {
    throw new Error("invalid store");
  }
} catch (_) {
  state = { messages: {} };
}

function persist() {
  const tmp = STORE + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(state));
  fs.renameSync(tmp, STORE);
}

function json(res, status, body) {
  res.writeHead(status, {"content-type": "application/json", "cache-control": "no-store"});
  res.end(JSON.stringify(body));
}

function idDigest() {
  const ids = Object.keys(state.messages).sort();
  return crypto.createHash("sha256").update(ids.join("\n")).digest("hex");
}

function bodyOf(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", chunk => {
      size += chunk.length;
      if (size > MAX) {
        reject(new Error("too_large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function authorized(req, raw) {
  const secret = String(process.env.PEER_REPLICATION_SECRET || "");
  const supplied = String(req.headers["x-c33-replication-signature"] || "");
  if (!secret || !supplied) return false;
  const expected = crypto.createHmac("sha256", secret).update(raw).digest("hex");
  const a = Buffer.from(supplied);
  const b = Buffer.from(expected);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    return json(res, 200, {
      status: "alive",
      service: "C-33",
      deployment_sha: process.env.RAILWAY_GIT_COMMIT_SHA || "peer",
      role: "secondary"
    });
  }

  if (req.method === "GET" && req.url === "/ready") {
    return json(res, 200, {
      status: "ready",
      service: "C-33",
      deployment_sha: process.env.RAILWAY_GIT_COMMIT_SHA || "peer",
      database: "file",
      peer_configured: false,
      provider_count: 0
    });
  }

  if (req.method === "GET" && req.url === "/v1/replication/status") {
    const count = Object.keys(state.messages).length;
    return json(res, 200, {
      status: "ok",
      deployment_sha: process.env.RAILWAY_GIT_COMMIT_SHA || "peer",
      backend_role: "secondary",
      peer_url_configured: false,
      peer_status: "NOT_CONFIGURED",
      replication_pending: 0,
      total_messages: count,
      unique_message_ids: count,
      message_id_digest: idDigest(),
      quiesced: false
    });
  }

  if (req.method === "POST" && req.url === "/internal/replicate") {
    if (String(req.headers["x-c33-replication-version"] || "") !== "1") {
      return json(res, 400, {detail: "unsupported_replication_version"});
    }

    let raw;
    try {
      raw = await bodyOf(req);
    } catch (err) {
      return json(res, err.message === "too_large" ? 413 : 400, {detail: "invalid_replication_body"});
    }

    if (!authorized(req, raw)) {
      return json(res, 401, {detail: "invalid_replication_signature"});
    }

    let body;
    try {
      body = JSON.parse(raw.toString("utf8"));
    } catch (_) {
      return json(res, 400, {detail: "invalid_replication_payload"});
    }

    if (!body || !Array.isArray(body.messages)) {
      return json(res, 400, {detail: "invalid_replication_payload"});
    }
    if (body.messages.length > 100) {
      return json(res, 413, {detail: "replication_batch_too_large"});
    }

    const next = {...state.messages};
    const acceptedIds = [];

    for (const msg of body.messages) {
      if (!msg || typeof msg !== "object" || !msg.id) {
        return json(res, 400, {detail: "invalid_replication_message"});
      }
      const id = String(msg.id);
      if (Object.prototype.hasOwnProperty.call(next, id)) {
        if (JSON.stringify(next[id]) !== JSON.stringify(msg)) {
          return json(res, 409, {detail: "message_id_conflict:" + id});
        }
      } else {
        next[id] = msg;
      }
      acceptedIds.push(id);
    }

    state = {messages: next};
    persist();

    return json(res, 200, {
      status: "ok",
      accepted: acceptedIds.length,
      received: body.messages.length,
      accepted_ids: acceptedIds,
      receipt_sha256: crypto.createHash("sha256").update(raw).digest("hex")
    });
  }

  return json(res, 404, {detail: "not_found"});
});

server.listen(Number(process.env.PORT || 8080), "0.0.0.0");
