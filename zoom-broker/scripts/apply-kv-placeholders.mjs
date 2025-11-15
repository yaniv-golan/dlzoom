#!/usr/bin/env node
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, "..");
const templatePath = path.join(projectRoot, "wrangler.jsonc");
const localConfigPath = path.join(projectRoot, ".wrangler.local.jsonc");
const prodPlaceholder = "__REPLACE_WITH_PRODUCTION_KV_ID__";
const previewPlaceholder = "__REPLACE_WITH_PREVIEW_KV_ID__";

const prodId =
	process.env.WRANGLER_KV_PROD_ID?.trim() ||
	process.env.WRANGLER_KV_ID?.trim() ||
	"";
const previewId =
	process.env.WRANGLER_KV_PREVIEW_ID?.trim() ||
	process.env.WRANGLER_KV_PREVIEW?.trim() ||
	"";

if (!prodId || !previewId) {
	console.log(
		"[apply-kv-placeholders] Skipping .wrangler.local.jsonc generation because WRANGLER_KV_PROD_ID and/or WRANGLER_KV_PREVIEW_ID are not set."
	);
	process.exit(0);
}

let template;
try {
	template = readFileSync(templatePath, "utf8");
} catch (err) {
	console.error(`[apply-kv-placeholders] Failed to read ${templatePath}:`, err);
	process.exit(1);
}

if (!template.includes(prodPlaceholder) || !template.includes(previewPlaceholder)) {
	console.log(
		"[apply-kv-placeholders] Placeholders not found in wrangler.jsonc; nothing to write."
	);
	process.exit(0);
}

const localConfig = template
	.replace(prodPlaceholder, prodId)
	.replace(previewPlaceholder, previewId);

try {
	writeFileSync(localConfigPath, localConfig);
	console.log(
		`[apply-kv-placeholders] Wrote .wrangler.local.jsonc using WRANGLER_KV_PROD_ID/WRANGLER_KV_PREVIEW_ID.`
	);
} catch (err) {
	console.error(`[apply-kv-placeholders] Failed to write ${localConfigPath}:`, err);
	process.exit(1);
}
