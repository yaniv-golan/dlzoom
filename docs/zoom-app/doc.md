dlzoom – Download your Zoom Cloud Recordings

dlzoom is a simple command‑line tool that helps you list and download your Zoom Cloud Recordings to your computer.

Most people can use dlzoom without any setup. When you sign in, we open a Zoom page in your browser so you can approve access. Advanced users can host their own sign‑in service if they prefer.

dlzoom is open‑source and free, and it will stay that way. We never sell any data.

Disclaimer
- dlzoom is provided “as is.” Use at your own risk. See Terms in docs/zoom-app/terms.md.

What you can do
- See a list of your Zoom Cloud Recordings.
- Download the recordings you choose to your computer.
- Keep everything local — we don’t upload your files anywhere.

How sign‑in works
- Default (no setup): dlzoom uses our hosted sign‑in service at `https://zoom-broker.yaniv-b91.workers.dev` to connect your Zoom account securely.
- Advanced (optional): You can host your own sign‑in service and point dlzoom to it. See developer docs at `zoom-broker/README.md`.

Permissions requested (read‑only)
- View your list of cloud recordings and their files. dlzoom does not request permission to change meetings or recordings.

Signing in
1. Run the dlzoom login command.
2. A browser window opens to Zoom. Approve access.
3. Return to the terminal and continue.

Where your data goes
- Tokens: dlzoom keeps sign‑in tokens in memory while you use the tool.
- Short‑term cache: the sign‑in service briefly stores a code to finish login, then it expires automatically.
- Recordings: downloads go straight from Zoom to your computer.
- Analytics: none.

Uninstall / revoke access
- Zoom web: App Marketplace → Manage → Added Apps → Remove.
- Or Zoom Profile → Apps → Manage → Remove.
- You can delete any downloaded files from your computer at any time.

Need help?
- See Support at docs/zoom-app/support.md or open an issue on GitHub.
- Email: yaniv+dlzoom@golan.name

Open source
- Code and issues: https://github.com/yaniv-golan/dlzoom

**Support**
- Open a GitHub issue in the project repository or email the maintainer at <your‑support‑email>.

For details on the broker endpoints and set‑up, see `zoom-broker/README.md` in the repository.

**Optional permissions (advanced)**
- To improve fidelity (not required):
  - `meeting:read` — lets the CLI mark recurring meetings definitively when browsing recordings.
  - `user:read` — lets `dlzoom whoami` show your name/email when using user tokens.
  - Without these, the CLI still works: recurrence is inferred within the chosen date range; `whoami` confirms token validity without profile details.
