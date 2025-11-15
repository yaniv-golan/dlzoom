#!/usr/bin/env node
/**
 * Replaces the placeholder KV namespace IDs in wrangler.jsonc when
 * CF_AUTH_KV_ID and CF_AUTH_KV_PREVIEW_ID environment variables are set.
 *
 * This is intended for CI environments (e.g., Cloudflare Builds) so that
 * deployments can supply real namespace IDs without committing them.
 */
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, "..");
const configPath = path.join(projectRoot, "wrangler.jsonc");
const prodPlaceholder = "__REPLACE_WITH_PRODUCTION_KV_ID__";
const previewPlaceholder = "__REPLACE_WITH_PREVIEW_KV_ID__";

const prodId =
	process.env.CF_AUTH_KV_ID?.trim() ||
	process.env.AUTH_KV_ID?.trim() ||
	"";
const previewId =
	process.env.CF_AUTH_KV_PREVIEW_ID?.trim() ||
	process.env.AUTH_KV_PREVIEW_ID?.trim() ||
	"";

if (!prodId && !previewId) {
	// No env vars set -> nothing to do (local development)
	process.exit(0);
}

if (!prodId || !previewId) {
	console.warn(
		"[apply-kv-placeholders] Both CF_AUTH_KV_ID and CF_AUTH_KV_PREVIEW_ID are required."
	);
	process.exit(0);
}

let configText;
try {
	configText = readFileSync(configPath, "utf8");
} catch (err) {
	console.error(`[apply-kv-placeholders] Failed to read ${configPath}:`, err);
	process.exit(1);
}

if (!configText.includes(prodPlaceholder) && !configText.includes(previewPlaceholder)) {
	console.log("[apply-kv-placeholders] Placeholder IDs already replaced; skipping.");
	process.exit(0);
}

const updated = configText
	.replace(prodPlaceholder, prodId)
	.replace(previewPlaceholder, previewId);

writeFileSync(configPath, updated);
console.log("[apply-kv-placeholders] Injected KV namespace IDs into wrangler.jsonc.");
