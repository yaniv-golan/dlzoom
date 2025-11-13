# Zoom Broker

[![JS CI](https://github.com/yaniv-golan/dlzoom/actions/workflows/js.yml/badge.svg?branch=main)](https://github.com/yaniv-golan/dlzoom/actions/workflows/js.yml)
![Node Version](https://img.shields.io/badge/node-%3E%3D20%20%3C21-339933?logo=node.js&logoColor=white)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](../LICENSE)

**Zoom Broker** is a minimal Cloudflare Worker that handles the OAuth 2.0 Authorization Code flow for Zoom on behalf of the CLI.
It securely stores your Zoom OAuth credentials and issues short-lived access tokens for per-user access to the Zoom API (e.g., listing and downloading cloud recordings).

Note on availability
- The CLI’s hosted sign‑in will be enabled after the Zoom app is published. Until then, this broker is the supported way to use User OAuth with dlzoom. Deploy it and pass `--auth-url` to `dlzoom login`.

---

## 🚀 Overview

Because an open-source CLI cannot safely embed a Zoom client secret, the broker acts as a lightweight backend:

1. **`POST /zoom/auth/start`**
   Creates a short-lived session in Cloudflare KV and returns
   `{ auth_url, session_id }`.

2. **User authorizes in browser**
   Zoom redirects to `https://<your-worker>/callback?code=...&state=...`.

3. **`/callback`**
   Exchanges the authorization `code` for tokens using your client secret, stores them temporarily in KV, and displays a confirmation page.

4. **`GET /zoom/auth/poll?id=<session_id>`**
   The CLI polls this endpoint to retrieve the tokens once authorization completes.

5. **`POST /zoom/token/refresh`**
   Exchanges a refresh token for a new access token.

---

## 🛠 Setup

### 1. Create a User-Managed OAuth App in Zoom

* App Type: **User-managed OAuth**
* Redirect URL:
  `https://<your-worker>.workers.dev/callback`
* Scopes (required):

  * `cloud_recording:read:list_user_recordings`
  * `cloud_recording:read:list_recording_files`
* Optional scopes (for enhanced features):
  * `meeting:read:meeting` — granular scope to read meeting details; lets the CLI mark recurring meetings definitively when browsing recordings (otherwise recurrence is inferred within the selected date range only).
  * `user:read:user` — granular scope to read the signed-in user's profile; lets the CLI show user name/email in `dlzoom whoami` when using user tokens.
* Save and install the app (via **Local Test → Install**).

### 2. Secrets

> **⚠️ CRITICAL SECURITY REQUIREMENT**: You **MUST** set the `ALLOWED_ORIGIN` environment variable in production to restrict which domains can access token endpoints. Without this, your broker is vulnerable to token theft from malicious websites.

```bash
npx wrangler secret put ZOOM_CLIENT_ID
npx wrangler secret put ZOOM_CLIENT_SECRET

# REQUIRED for production - restrict CORS to your CLI domain
# For CLI usage from localhost, use: http://localhost
# For public deployments, use your specific domain
npx wrangler secret put ALLOWED_ORIGIN
# When prompted, enter: http://localhost
# (or your specific domain for production deployments)
```

**Without `ALLOWED_ORIGIN` set**, the broker defaults to `Access-Control-Allow-Origin: *`, which allows **any website** to make requests to your token endpoints. This is **ONLY acceptable for development/testing**.

### 3. Key-Value Namespace

```bash
npx wrangler kv namespace create AUTH
# confirm wrangler.jsonc contains:
# "kv_namespaces": [{ "binding": "AUTH", "id": "<your-id>", "remote": true }]
```

### 4. Deploy

```bash
npx wrangler deploy
```

Output example:

```
Deployed zoom-broker
https://zoom-broker.<user>.workers.dev

Environment tips:
- To restrict CORS for token endpoints, set `ALLOWED_ORIGIN` in your Worker environment (e.g., your CLI’s origin) to replace the default `*`.
```

---

## 💻 CLI Integration

1. **Start authorization**

   ```bash
   curl -s -X POST -H 'content-type: application/json' \
     https://zoom-broker.<user>.workers.dev/zoom/auth/start | jq
   ```
2. **Open the `auth_url`**, approve the app.
3. **Poll for tokens**

   ```bash
   curl -s "https://zoom-broker.<user>.workers.dev/zoom/auth/poll?id=<session_id>" | jq
   ```
4. **Use token**

   ```bash
   curl -H "Authorization: Bearer <access_token>" \
     https://api.zoom.us/v2/users/me/recordings
   ```
5. **Refresh when needed**

   ```bash
   curl -s -X POST -H 'content-type: application/json' \
     https://zoom-broker.<user>.workers.dev/zoom/token/refresh \
     -d '{"refresh_token":"<old_refresh_token>"}' | jq
   ```

---

## ⚙️ Endpoints Summary

| Method | Path                  | Purpose                                   |
| :----- | :-------------------- | :---------------------------------------- |
| `POST` | `/zoom/auth/start`    | Begin auth; returns auth URL + session ID |
| `GET`  | `/callback`           | Zoom redirect; exchanges code for tokens  |
| `GET`  | `/zoom/auth/poll`     | CLI polls for token status                |
| `POST` | `/zoom/token/refresh` | Refresh access token                      |

---

## 🧩 Architecture

* **Platform:** Cloudflare Workers + KV Store
* **Auth flow:** OAuth 2.0 Authorization Code
* **Security:**

  * Secrets stored via `wrangler secret`
  * Tokens cached temporarily (≤10 min)
  * CORS limited to `*` for CLI use
* **No database**—fully serverless.

---

## 🧪 Local Test

```bash
npx wrangler dev
curl -X POST http://127.0.0.1:8787/zoom/auth/start
```

Open the returned URL; after authorization, check the KV entries with
`npx wrangler kv key list --namespace AUTH`.

---

## 📄 License

Same license as the parent CLI project.
