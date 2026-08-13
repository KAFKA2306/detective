import fs from "node:fs";

const sitemap = JSON.parse(fs.readFileSync("reports/note_sitemap_status.json", "utf8"));
const pages = JSON.parse(fs.readFileSync("reports/note_public_page_status.json", "utf8"));

if (sitemap.status !== "compatible") throw new Error("note sitemap source is not compatible");
if (pages.status !== "compatible") throw new Error("note public-page probe is not compatible");
if (pages.forbidden_paths_used !== false) throw new Error("note public-page probe reports a forbidden collection path");
if (!Array.isArray(pages.collection_paths) || !pages.collection_paths.includes("/sitemaps/*") || !pages.collection_paths.includes("/*/n/*")) {
  throw new Error("note public-page collection paths are outside the declared sitemap/article contract");
}
if (typeof sitemap.collector_policy !== "string" || !sitemap.collector_policy.includes("robots+sitemap only")) {
  throw new Error("note sitemap collector policy is missing");
}

console.log("note collection contract evidence: PASS");
