// Tiny Zoom OAuth broker: Authorization Code (no PKCE needed because the broker is confidential)
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    // CORS for CLI (optionally restrict via ALLOWED_ORIGIN)
    const allowedOrigin = env.ALLOWED_ORIGIN || "*";
    const cors = {
      "Access-Control-Allow-Origin": allowedOrigin,
      "Access-Control-Allow-Headers": "content-type",
      "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
      "Vary": "Origin",
    };
    if (request.method === "OPTIONS") return new Response("", { headers: cors });

    // 1) Start auth: returns { auth_url, session_id }
    if (url.pathname === "/zoom/auth/start" && request.method === "POST") {
      const sessionId = crypto.randomUUID();

      // Store session skeleton (expires in 10 minutes)
      await env.AUTH.put(`sess:${sessionId}`, JSON.stringify({ status: "pending", created_at: Date.now() }), { expirationTtl: 600 });

      const params = new URLSearchParams({
        response_type: "code",
        client_id: env.ZOOM_CLIENT_ID,
        redirect_uri: callbackUrl(url),
        state: sessionId,                   // CSRF + session correlation
      });
      const authUrl = `https://zoom.us/oauth/authorize?${params.toString()}`;
      return json({ auth_url: authUrl, session_id: sessionId }, 200, cors);
    }

    // 2) OAuth callback from Zoom: exchange code -> tokens, store in KV, show "done" page
    if (url.pathname === "/callback" && request.method === "GET") {
      const code = url.searchParams.get("code");
      const state = url.searchParams.get("state");
      if (!code || !state) return html("Missing code/state", 400);

      // Validate session exists and is pending
      const sess = await env.AUTH.get(`sess:${state}`, { type: "json" });
      if (!sess || sess.status !== "pending") {
        return html("Invalid or expired session", 400);
      }

      // Basic auth header
      const basic = "Basic " + btoa(`${env.ZOOM_CLIENT_ID}:${env.ZOOM_CLIENT_SECRET}`);

      const tokenBody = new URLSearchParams({
        grant_type: "authorization_code",
        code,
        redirect_uri: callbackUrl(url),
      });
      const resp = await fetch("https://zoom.us/oauth/token", {
        method: "POST",
        headers: {
          "Authorization": basic,
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: tokenBody,
      });

      const txt = await resp.text();
      const contentType = resp.headers.get("content-type") || "";
      if (resp.ok && contentType.includes("application/json")) {
        // Persist raw JSON token response; short TTL.
        await env.AUTH.put(`tok:${state}`, txt, { expirationTtl: 600 });
        await env.AUTH.put(`sess:${state}`, JSON.stringify({ status: "done" }), { expirationTtl: 600 });
        return html(`<p>Zoom authorization complete. You can close this window.</p>`, 200);
      } else {
        // Persist error for polling clients
        const err = JSON.stringify({ status: "error", http_status: resp.status, body: txt });
        await env.AUTH.put(`tok:${state}`, err, { expirationTtl: 600 });
        await env.AUTH.put(`sess:${state}`, JSON.stringify({ status: "error" }), { expirationTtl: 600 });
        return html(`<p>Zoom authorization failed. Please retry from the CLI.</p>`, 500);
      }
    }

    // 3) CLI polls for status/tokens
    if (url.pathname === "/zoom/auth/poll" && request.method === "GET") {
      const id = url.searchParams.get("id");
      if (!id) return json({ error: "missing id" }, 400, cors);

      const status = await env.AUTH.get(`sess:${id}`, { type: "json" });
      if (!status) return json({ status: "expired" }, 410, cors);

      if (status.status === "error") {
        const errPayload = await env.AUTH.get(`tok:${id}`);
        return new Response(errPayload || JSON.stringify({ status: "error" }), { status: 500, headers: { "content-type": "application/json", ...cors } });
      }
      if (status.status !== "done") return json({ status: "pending" }, 200, cors);

      const tok = await env.AUTH.get(`tok:${id}`);
      if (!tok) return json({ status: "pending" }, 200, cors);

      // One-time read: delete after serving
      await env.AUTH.delete(`tok:${id}`);
      return new Response(tok, { status: 200, headers: { "content-type": "application/json", ...cors } });
    }

    // 4) Refresh
    if (url.pathname === "/zoom/token/refresh" && request.method === "POST") {
      const { refresh_token } = await safeJson(request) || {};
      if (!refresh_token) return json({ error: "missing refresh_token" }, 400, cors);
      if (typeof refresh_token !== "string" || refresh_token.length < 10 || refresh_token.length > 4096) {
        return json({ error: "invalid refresh_token" }, 400, cors);
      }

      const basic = "Basic " + btoa(`${env.ZOOM_CLIENT_ID}:${env.ZOOM_CLIENT_SECRET}`);
      const body = new URLSearchParams({ grant_type: "refresh_token", refresh_token });
      const r = await fetch("https://zoom.us/oauth/token", {
        method: "POST",
        headers: { "Authorization": basic, "Content-Type": "application/x-www-form-urlencoded" },
        body
      });
      const t = await r.text();
      return new Response(t, { status: r.status, headers: { "content-type": "application/json", ...cors } });
    }

    return new Response("Not found", { status: 404, headers: cors });
  }
};

function callbackUrl(u) {
  // Build the exact callback URL of this worker regardless of hostname
  return `${u.protocol}//${u.host}/callback`;
}
async function safeJson(req) { try { return await req.json(); } catch { return null; } }
function json(obj, status = 200, headers = {}) { return new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json", ...headers } }); }
function html(s, status = 200) { return new Response(`<!doctype html><meta charset="utf-8"><body>${s}</body>`, { status, headers: { "content-type": "text/html; charset=utf-8" } }); }
