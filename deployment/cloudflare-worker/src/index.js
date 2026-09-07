const STATE_NAMES = new Set(["seen_jobs.json", "last_successful_run.json"]);
const MAX_TELEGRAM_BYTES = 45 * 1024 * 1024;

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

function sanitizeFilename(value) {
  const name = (value || "").trim().replace(/[^A-Za-z0-9._-]/g, "_");
  if (!name || name === "." || name === ".." || name.length > 180) return null;
  return name;
}

function validDate(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value || "");
}

async function sha256Bytes(value) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
}

async function secureEqual(a, b) {
  if (!a || !b) return false;
  const [aa, bb] = await Promise.all([sha256Bytes(a), sha256Bytes(b)]);
  let diff = aa.length ^ bb.length;
  const n = Math.max(aa.length, bb.length);
  for (let i = 0; i < n; i++) diff |= (aa[i % aa.length] || 0) ^ (bb[i % bb.length] || 0);
  return diff === 0;
}

async function authorized(request, env) {
  const header = request.headers.get("authorization") || "";
  if (!header.startsWith("Bearer ")) return false;
  return secureEqual(header.slice(7), env.INGEST_TOKEN);
}

async function handleState(request, env, pathname) {
  const name = pathname.slice("/v1/state/".length);
  if (!STATE_NAMES.has(name)) return jsonResponse({ error: "invalid state name" }, 404);
  const key = `state/${name}`;

  if (request.method === "GET") {
    const object = await env.PRIVATE_BUCKET.get(key);
    if (!object) return jsonResponse({ found: false }, 404);
    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("etag", object.httpEtag);
    headers.set("cache-control", "no-store");
    if (!headers.has("content-type")) headers.set("content-type", "application/json; charset=utf-8");
    return new Response(object.body, { headers });
  }

  if (request.method === "PUT") {
    const body = await request.arrayBuffer();
    if (body.byteLength > 10 * 1024 * 1024) return jsonResponse({ error: "state payload too large" }, 413);
    await env.PRIVATE_BUCKET.put(key, body, {
      httpMetadata: { contentType: request.headers.get("content-type") || "application/json" },
      customMetadata: { updatedAt: new Date().toISOString() },
    });
    return jsonResponse({ ok: true, key });
  }

  return jsonResponse({ error: "method not allowed" }, 405);
}

async function handleArchive(request, env, pathname) {
  if (request.method !== "PUT") return jsonResponse({ error: "method not allowed" }, 405);
  const rest = pathname.slice("/v1/archive/".length);
  const slash = rest.indexOf("/");
  if (slash < 0) return jsonResponse({ error: "expected /v1/archive/YYYY-MM-DD/filename" }, 400);
  const day = rest.slice(0, slash);
  const filename = sanitizeFilename(rest.slice(slash + 1));
  if (!validDate(day) || !filename) return jsonResponse({ error: "invalid archive path" }, 400);

  const body = await request.arrayBuffer();
  if (body.byteLength > 50 * 1024 * 1024) return jsonResponse({ error: "archive payload too large" }, 413);
  const key = `archive/${day}/${filename}`;
  await env.PRIVATE_BUCKET.put(key, body, {
    httpMetadata: { contentType: request.headers.get("content-type") || "application/octet-stream" },
    customMetadata: { uploadedAt: new Date().toISOString() },
  });
  return jsonResponse({ ok: true, key, bytes: body.byteLength });
}

async function handleTelegram(request, env) {
  if (request.method !== "POST") return jsonResponse({ error: "method not allowed" }, 405);
  const filename = sanitizeFilename(request.headers.get("x-filename"));
  if (!filename) return jsonResponse({ error: "missing or invalid x-filename" }, 400);

  const caption = (request.headers.get("x-caption") || "").slice(0, 900);
  const contentType = request.headers.get("content-type") || "application/octet-stream";
  const body = await request.arrayBuffer();
  if (body.byteLength === 0) return jsonResponse({ error: "empty file" }, 400);
  if (body.byteLength > MAX_TELEGRAM_BYTES) return jsonResponse({ error: "file too large for configured Telegram safety limit" }, 413);

  const form = new FormData();
  form.set("chat_id", env.TELEGRAM_CHAT_ID);
  if (caption) form.set("caption", caption);
  form.set("document", new Blob([body], { type: contentType }), filename);

  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendDocument`, {
    method: "POST",
    body: form,
  });
  const payload = await response.json().catch(() => ({ ok: false, description: "Telegram returned non-JSON" }));
  if (!response.ok || !payload.ok) {
    return jsonResponse({ error: "telegram delivery failed", status: response.status, description: payload.description || "unknown" }, 502);
  }
  return jsonResponse({ ok: true, telegram_message_id: payload.result?.message_id ?? null, bytes: body.byteLength });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health" && request.method === "GET") {
      return jsonResponse({ ok: true, service: "job-market-monitor-private-gateway" });
    }

    if (!(await authorized(request, env))) {
      return jsonResponse({ error: "unauthorized" }, 401);
    }

    try {
      if (url.pathname.startsWith("/v1/state/")) return await handleState(request, env, url.pathname);
      if (url.pathname.startsWith("/v1/archive/")) return await handleArchive(request, env, url.pathname);
      if (url.pathname === "/v1/telegram/document") return await handleTelegram(request, env);
      return jsonResponse({ error: "not found" }, 404);
    } catch (error) {
      console.error("private gateway error", error);
      return jsonResponse({ error: "internal error" }, 500);
    }
  },
};
