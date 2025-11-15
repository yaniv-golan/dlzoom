#!/usr/bin/env bash
# Setup script for Zoom Broker Cloudflare Worker secrets
set -euo pipefail

echo "🔐 Zoom Broker - Secret Setup Script"
echo "===================================="
echo ""
echo "This script will help you set up the required secrets for the Zoom Broker Worker."
echo "You'll need your Zoom OAuth app credentials from https://marketplace.zoom.us/develop/create"
echo ""

# Check if wrangler is installed
if ! command -v wrangler &> /dev/null; then
    echo "❌ Error: wrangler is not installed"
    echo "Install it with: npm install -g wrangler"
    echo "Or use npx: npx wrangler ..."
    exit 1
fi

echo "📋 Required secrets:"
echo "  1. ZOOM_CLIENT_ID - Your Zoom OAuth app Client ID"
echo "  2. ZOOM_CLIENT_SECRET - Your Zoom OAuth app Client Secret"
echo "  3. ALLOWED_ORIGIN - CORS origin restriction (e.g., http://localhost)"
echo ""

read -p "Do you want to set these secrets now? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Skipping secret setup. You can set them later with:"
    echo "  npx wrangler secret put ZOOM_CLIENT_ID"
    echo "  npx wrangler secret put ZOOM_CLIENT_SECRET"
    echo "  npx wrangler secret put ALLOWED_ORIGIN"
    exit 0
fi

echo ""
echo "Setting up secrets..."
echo ""

# Set ZOOM_CLIENT_ID
echo "1️⃣  ZOOM_CLIENT_ID"
npx wrangler secret put ZOOM_CLIENT_ID

echo ""

# Set ZOOM_CLIENT_SECRET
echo "2️⃣  ZOOM_CLIENT_SECRET"
npx wrangler secret put ZOOM_CLIENT_SECRET

echo ""

# Set ALLOWED_ORIGIN
echo "3️⃣  ALLOWED_ORIGIN"
echo "Examples:"
echo "  - Local development: http://localhost"
echo "  - Production: https://your-domain.com"
echo "  - Development only (⚠️  NOT recommended for production): * (allows any origin)"
npx wrangler secret put ALLOWED_ORIGIN

echo ""
echo "✅ All secrets have been set!"
echo ""
echo "Next steps:"
echo "  1. Verify KV namespace is configured in wrangler.jsonc"
echo "  2. Deploy: npx wrangler deploy"
echo "  3. Or connect to Cloudflare Builds in the dashboard for automatic deployments"
echo ""
echo "See DEPLOYMENT.md for more details."
