# Cloudflare Builds Setup Checklist

Follow these steps to connect your `zoom-broker` Worker to GitHub for automatic CI/CD.

## Prerequisites

- [ ] Cloudflare account created
- [ ] `zoom-broker` Worker already deployed (or will be deployed as part of setup)
- [ ] GitHub repository access
- [ ] Zoom OAuth app created with redirect URL configured

## Step-by-Step Setup

### 1. Verify Worker Name Match

**Why:** Cloudflare Builds require the Worker name in the dashboard to match `wrangler.jsonc`

- [ ] Open `zoom-broker/wrangler.jsonc`
- [ ] Verify `"name": "zoom-broker"` (line 7)
- [ ] This name must match exactly in the Cloudflare Dashboard

### 2. Navigate to Cloudflare Dashboard

- [ ] Go to https://dash.cloudflare.com
- [ ] Click **Workers & Pages** in the left sidebar
- [ ] Find or create the `zoom-broker` Worker

### 3. Connect to Git Repository

- [ ] Click on the `zoom-broker` Worker
- [ ] Go to **Settings** → **Builds**
- [ ] Click **Connect** (or **Connect Git** button)
- [ ] Choose **GitHub** or **GitLab**
- [ ] Authorize Cloudflare to access your GitHub account (if first time)
- [ ] Select your repository from the list
- [ ] Configure build settings:

```
Production branch: main
Root directory: /zoom-broker
Build command: npm ci && npm test && npx wrangler deploy
```

- [ ] Click **Save and Deploy**

### 4. Configure Environment Variables

**Important:** Secrets must be set in the Cloudflare Dashboard, not in `wrangler.jsonc`

- [ ] Go to **Settings** → **Variables and Secrets**
- [ ] Add the following secrets (click **Add variable** → **Encrypt**):

| Name | Value | Description |
|------|-------|-------------|
| `ZOOM_CLIENT_ID` | Your OAuth Client ID | From Zoom Marketplace app |
| `ZOOM_CLIENT_SECRET` | Your OAuth Client Secret | From Zoom Marketplace app |
| `ALLOWED_ORIGIN` | `http://localhost` | CORS restriction (⚠️ REQUIRED for security) |

- [ ] Click **Save** after adding each secret

**Security Note:** Without `ALLOWED_ORIGIN` set to a specific origin, your broker will accept requests from any website, creating a security vulnerability.

### 5. Verify KV Namespace

- [ ] Go to **Settings** → **Bindings**
- [ ] Verify **KV Namespace** binding exists:
  - Variable name: `AUTH`
  - KV namespace: Should show your KV namespace ID

If missing, create it:
```bash
cd zoom-broker
npx wrangler kv namespace create AUTH
```

Then add the binding in the dashboard or update `wrangler.jsonc` and push to trigger a new build.

### 6. Test the Setup

- [ ] Push a small change to a feature branch
- [ ] Create a Pull Request to `main`
- [ ] Verify build starts automatically in **Deployments** tab
- [ ] Check build logs for any errors
- [ ] Verify preview URL is generated
- [ ] Test health endpoint: `curl https://<preview-url>/health`

### 7. Merge and Deploy

- [ ] Merge PR to `main` branch
- [ ] Verify production deployment starts automatically
- [ ] Check **Deployments** tab for success
- [ ] Test production URL: `curl https://zoom-broker.<user>.workers.dev/health`

### 8. Configure Zoom OAuth Redirect URLs

Now that you have both production and preview URLs, update your Zoom OAuth app:

- [ ] Go to https://marketplace.zoom.us/develop
- [ ] Select your OAuth app
- [ ] Add redirect URLs (you can have multiple):
  - Production: `https://zoom-broker.<user>.workers.dev/callback`
  - Optional: Add preview pattern if you want to test with PRs: `https://*.zoom-broker.<user>.workers.dev/callback`
- [ ] Click **Save**

### 9. Test OAuth Flow

- [ ] Run: `dlzoom login --auth-url https://zoom-broker.<user>.workers.dev`
- [ ] Verify browser opens to Zoom authorization page
- [ ] Authorize the app
- [ ] Verify CLI receives tokens successfully
- [ ] Run: `dlzoom whoami` to confirm authentication works

## Troubleshooting

### Build fails with "Worker name mismatch"

**Problem:** Dashboard Worker name doesn't match `wrangler.jsonc`

**Solution:** Either:
1. Rename Worker in dashboard to `zoom-broker`, or
2. Update `"name"` in `wrangler.jsonc` (requires commit/push)

### Build succeeds but Worker returns 500

**Possible causes:**
- Environment variables/secrets not set correctly
- KV namespace not bound
- CORS issues (check `ALLOWED_ORIGIN`)

**Debug:**
1. Check **Logs** tab in Cloudflare Dashboard
2. Look for error messages about missing bindings or environment variables
3. Verify secrets are set under **Settings** → **Variables and Secrets**

### Preview URL returns 404

**Possible causes:**
- Build is still in progress (wait a minute and retry)
- Build failed (check build logs in **Deployments** tab)

**Solution:** Check the **Deployments** tab for build status

### OAuth fails on preview URL

**Problem:** Zoom redirect URL not configured for preview domain

**Solution:** Add `https://*.zoom-broker.<user>.workers.dev/callback` to Zoom OAuth app redirect URLs

## Maintenance

### Viewing Deployments
- Go to **Workers & Pages** → `zoom-broker` → **Deployments**
- See all builds, their status, and preview URLs

### Viewing Logs
- Go to **Workers & Pages** → `zoom-broker` → **Logs**
- Real-time logs from your Worker
- Use for debugging production issues

### Rolling Back
- Go to **Deployments** tab
- Find a previous working version
- Click **Rollback to this deployment**

### Updating Secrets
- Go to **Settings** → **Variables and Secrets**
- Click **Edit** on the secret you want to update
- Enter new value and **Save**
- Redeploy or wait for next automatic deployment

## Next Steps

- [ ] Set up monitoring/alerting (optional)
- [ ] Review Cloudflare Analytics for Worker (optional)
- [ ] Document your specific Worker URL for your team
- [ ] Consider setting up branch previews for `develop` branch (optional)

## Resources

- [Cloudflare Builds Documentation](https://developers.cloudflare.com/workers/ci-cd/builds/)
- [Workers Secrets Documentation](https://developers.cloudflare.com/workers/configuration/secrets/)
- [KV Documentation](https://developers.cloudflare.com/kv/)
- Project-specific: See `DEPLOYMENT.md` for deployment procedures
