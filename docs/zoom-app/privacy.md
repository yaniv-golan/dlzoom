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
- Note: Our hosted authentication service uses Cloudflare Workers, which collects infrastructure-level metrics (request counts, errors, performance) for operational monitoring. This is standard infrastructure observability and does not track individual users or their data.

Where it's stored and for how long
- Sign‑in tokens are stored locally on your device (in `~/.config/dlzoom/tokens.json`) until you log out or they expire.
- To finish sign‑in, a small authorization code is stored briefly in the authentication service and expires automatically after 10 minutes.
- Downloaded recordings are saved only on your device and are under your control.

Hosted vs self‑hosted sign‑in
- Default: If you use our hosted sign‑in, the short‑lived code is handled by our service only to complete sign‑in, then it expires.
- Self‑hosted: If you host your own sign‑in, that short‑lived code is handled by your service instead.

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
