---
layout: default
title: Privacy Policy – dlzoom
permalink: /zoom-app/privacy/
---

Privacy Policy – dlzoom

Effective date: 2025‑01‑01

dlzoom helps you download your own Zoom Cloud Recordings. This policy explains what information we handle and why, in simple terms.

What we access
- Basic details needed to sign you in to your Zoom account.
- Information about your recordings (like titles and dates) when you ask the tool to list or download them.
- The recording files you choose to download, which go straight to your computer.

How we use it
- To sign you in to Zoom and show/download your recordings.
- We don't use your data for ads or user-tracking analytics.
- Note: When hosted sign‑in is enabled, it uses Cloudflare Workers, which collects infrastructure-level metrics (request counts, errors, performance) for operational monitoring. This is standard infrastructure observability and does not track individual users or their data.

Where it's stored and for how long
- Sign‑in tokens are stored locally on your device in the standard OS config directory (`~/Library/Application Support/dlzoom/tokens.json` on macOS, `~/.config/dlzoom/tokens.json` on Linux, `%APPDATA%\\dlzoom\\tokens.json` on Windows) until you log out or they expire. You can override this path with `DLZOOM_TOKENS_PATH`.
- To finish sign‑in, the OAuth broker temporarily stores the full token response from Zoom (access token, refresh token, expiry data) in Cloudflare Workers KV. This copy lives for at most 10 minutes—and is usually deleted sooner once the CLI fetches it—so the CLI can download it exactly once and then remove it.
- Downloaded recordings are saved only on your device and are under your control.

OAuth broker (authentication service)
- **Default**: dlzoom uses a hosted OAuth broker at `https://zoom-broker.dlzoom.workers.dev` to handle the sign-in flow.
- **What it does**: Temporarily stores session data and the OAuth token payload (max 10 minutes) so the CLI can pick up the tokens once. It does not log, persist, or have access to your Zoom recordings or account data beyond what's needed for authentication, and the tokens are deleted immediately after retrieval or when the TTL expires.
- **Open source**: All broker code is available in the `zoom-broker/` directory of the repository and can be audited.
- **Generic**: The broker works with any Zoom OAuth app. You create your own app in Zoom Marketplace with your own credentials.
- **Infrastructure monitoring**: The broker runs on Cloudflare Workers, which collects standard infrastructure metrics (request counts, errors, performance) for operational monitoring. This does not track individual users or their data.
- **Self‑hosting option**: If you prefer, you can deploy your own instance of the broker and configure dlzoom to use it with `--auth-url` or the `DLZOOM_AUTH_URL` environment variable. See `zoom-broker/README.md` for instructions.

Sharing
- We don’t sell your information or share it with advertisers. No selling of any data, ever.

Security
- The CLI does not include any Zoom secret. Short‑lived tokens and one‑time codes reduce risk.
- You are responsible for keeping your own computer (and, if self‑hosting, your service) secure.

Your choices
- You can remove access at any time in Zoom: App Marketplace → Manage → Added Apps → Remove (or Profile → Apps → Manage → Remove).
- You can delete any downloaded files from your computer whenever you like.

Optional permissions (advanced)
- If enabled by you, the app may request additional Zoom permissions to improve the experience (granular scopes):
  - `meeting:read:meeting`: allows identifying whether a meeting is recurring when browsing recordings. No changes to what is downloaded; only metadata lookup to determine recurrence.
  - `user:read:user`: allows displaying your Zoom profile info (name/email) in `dlzoom whoami` when using user tokens.
- These are optional. Without them, the CLI still works; recurrence is inferred only within your selected date range, and `whoami` confirms token validity without showing profile details.

Contact
- Questions or requests: open a GitHub issue or email yaniv+dlzoom@golan.name.

Changes to this policy
- If we change this policy, we’ll update the date above and the repository history.
