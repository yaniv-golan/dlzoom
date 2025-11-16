#!/usr/bin/env bash
# Helper script to provision KV namespaces and update wrangler.jsonc placeholders.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_TEMPLATE="$PROJECT_ROOT/wrangler.jsonc"
LOCAL_CONFIG="$PROJECT_ROOT/.wrangler.local.jsonc"
PROD_PLACEHOLDER="__REPLACE_WITH_PRODUCTION_KV_ID__"
PREVIEW_PLACEHOLDER="__REPLACE_WITH_PREVIEW_KV_ID__"

echo "⚙️  Zoom Broker KV Namespace Helper"
echo "=================================="
echo ""

if [[ ! -f "$CONFIG_TEMPLATE" ]]; then
    echo "❌ Could not find wrangler.jsonc at $CONFIG_TEMPLATE"
    exit 1
fi

if ! grep -q "$PROD_PLACEHOLDER" "$CONFIG_TEMPLATE"; then
    echo "❌ Production placeholder ($PROD_PLACEHOLDER) not found in wrangler.jsonc."
    echo "   Make sure you are running this script on a fresh clone or reset the placeholder manually."
    exit 1
fi

if ! grep -q "$PREVIEW_PLACEHOLDER" "$CONFIG_TEMPLATE"; then
    echo "❌ Preview placeholder ($PREVIEW_PLACEHOLDER) not found in wrangler.jsonc."
    echo "   Make sure you are running this script on a fresh clone or reset the placeholder manually."
    exit 1
fi

if ! command -v npx >/dev/null 2>&1; then
    echo "❌ npx (Node.js) is required. Install Node.js to continue."
    exit 1
fi

if ! command -v wrangler >/dev/null 2>&1 && ! npx wrangler --version >/dev/null 2>&1; then
    echo "❌ wrangler CLI is required. Install with: npm install -g wrangler"
    exit 1
fi

create_namespace() {
    local mode="$1" # production or preview
    local cmd=("npx" "wrangler" "kv" "namespace" "create" "AUTH")
    if [[ "$mode" == "preview" ]]; then
        cmd+=("--preview")
    fi

    echo ""
    echo "Creating $mode KV namespace..."
output="$("${cmd[@]}")" || {
        echo "❌ Failed to create $mode namespace."
        exit 1
    }
    printf "%s\n" "$output" >&2
    echo ""
    # Extract first quoted value after `id =`
    local id
    id="$(echo "$output" | sed -n 's/.*id = "\([^"]*\)".*/\1/p' | head -n 1)"
    if [[ -z "$id" ]]; then
        read -rp "Could not automatically parse the namespace id. Enter the $mode namespace id: " id
    fi
    echo "$id"
}

read -rp "Create Cloudflare production namespace now? (y/n) " prod_choice
if [[ "$prod_choice" =~ ^[Yy]$ ]]; then
prod_id="$(create_namespace "production")"
else
    read -rp "Enter existing production namespace id: " prod_id
fi

read -rp "Create Cloudflare preview namespace now? (y/n) " preview_choice
if [[ "$preview_choice" =~ ^[Yy]$ ]]; then
preview_id="$(create_namespace "preview")"
else
    read -rp "Enter existing preview namespace id: " preview_id
fi

if [[ -z "$prod_id" || -z "$preview_id" ]]; then
    echo "❌ Namespace ids cannot be empty."
    exit 1
fi

export CONFIG_TEMPLATE
export LOCAL_CONFIG
export PROD_ID="$prod_id"
export PREVIEW_ID="$preview_id"
export PROD_PLACEHOLDER
export PREVIEW_PLACEHOLDER

python - <<'PY'
from pathlib import Path
import os

config_template = Path(os.environ["CONFIG_TEMPLATE"])
local_config = Path(os.environ["LOCAL_CONFIG"])
prod_id = os.environ["PROD_ID"].strip()
preview_id = os.environ["PREVIEW_ID"].strip()
prod_placeholder = os.environ["PROD_PLACEHOLDER"]
preview_placeholder = os.environ["PREVIEW_PLACEHOLDER"]

text = config_template.read_text()
if prod_placeholder not in text or preview_placeholder not in text:
    raise SystemExit("Placeholders not found in wrangler.jsonc")

text = text.replace(prod_placeholder, prod_id, 1)
text = text.replace(preview_placeholder, preview_id, 1)
local_config.write_text(text)
PY

echo ""
echo "✅ Wrote local Wrangler config: $LOCAL_CONFIG"
echo "   Production ID: $prod_id"
echo "   Preview ID:    $preview_id"
echo ""
echo "Use this config via the helper:"
echo "  ./scripts/wrangler-local.sh deploy"
echo "or set WRANGLER_CONFIG=.wrangler.local.jsonc before running npx wrangler."
echo ""
echo "The tracked wrangler.jsonc remains unchanged, so there's nothing to reset before committing."
