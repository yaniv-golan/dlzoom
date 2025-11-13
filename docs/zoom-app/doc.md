---
layout: default
title: dlzoom – Download your Zoom Cloud Recordings
permalink: /zoom-app/doc/
---

dlzoom – Download your Zoom Cloud Recordings

dlzoom is a simple command‑line tool that helps you list and download your Zoom Cloud Recordings to your computer.

Note on availability
- Hosted sign‑in will be available once Zoom publishes the app in the Marketplace. Until then, you can either self‑host the sign‑in broker or use Server‑to‑Server (S2S) OAuth.

dlzoom is open‑source and free, and it will stay that way. We never sell any data.

Disclaimer
- dlzoom is provided “as is.” Use at your own risk. See Terms at [Terms of Service]({{ '/zoom-app/terms/' | relative_url }}).

What you can do
- See a list of your Zoom Cloud Recordings.
- Download the recordings you choose to your computer.
- Keep everything local — we don’t upload your files anywhere.

How sign‑in works
- Hosted (coming soon): dlzoom will use a hosted sign‑in service to connect your Zoom account securely.
- Self‑hosted (available now): You can host your own sign‑in service and point dlzoom to it. See developer docs at `zoom-broker/README.md`.

Permissions requested (read‑only)
- View your list of cloud recordings and their files. dlzoom does not request permission to change meetings or recordings.

Signing in (user OAuth)
1. If using a self‑hosted broker, run: `dlzoom login --auth-url https://<your-worker>.workers.dev`
2. A browser window opens to Zoom. Approve access.
3. Return to the terminal and continue.

Where your data goes
- Tokens: dlzoom saves tokens locally to a tokens.json file under your user config directory (permissions restricted best‑effort). Tokens are refreshed automatically.
- Short‑term cache: the sign‑in service briefly stores a code to finish login, then it expires automatically.
- Recordings: downloads go straight from Zoom to your computer.
- Analytics: none.

Uninstall / revoke access
- Zoom web: App Marketplace → Manage → Added Apps → Remove.
- Or Zoom Profile → Apps → Manage → Remove.
- You can delete any downloaded files from your computer at any time.

Need help?
- See [Support]({{ '/zoom-app/support/' | relative_url }}) or open an issue on GitHub.
- Email: yaniv+dlzoom@golan.name

Open source
- Code and issues: https://github.com/yaniv-golan/dlzoom

**Support**
- Open a GitHub issue in the project repository or email the maintainer at yaniv+dlzoom@golan.name.

For details on the broker endpoints and set‑up, see `zoom-broker/README.md` in the repository.

**Optional permissions (advanced)**
- To improve fidelity (not required):
  - `meeting:read:meeting` — lets the CLI mark recurring meetings definitively when browsing recordings.
  - `user:read:user` — lets `dlzoom whoami` show your name/email when using user tokens.
  - Without these, the CLI still works: recurrence is inferred within the chosen date range; `whoami` confirms token validity without profile details.
