#!/usr/bin/env node
// Fills the HTML cache right after a deploy, so the first uncached render of
// each page doesn't land on a reader.
//
// A deploy changes the Worker version, which is part of the cache key in
// src/worker.ts, so every page starts cold. The Worker runs at a placed
// location, and the cache it fills there serves every visitor, so one
// request per page is enough.
//
// The site is on the Workers Free plan (10 ms of CPU per request, and a
// render takes 10–24 ms). The pages are requested one at a time with a pause
// between them, and the script stops if the Worker starts answering with 5xx.
//
// Usage: node scripts/warm-cache.mjs [--base https://emdashcms.pl] [--pause 1500]

const args = process.argv.slice(2);
const option = (name, fallback) => {
	const index = args.indexOf(`--${name}`);
	return index === -1 ? fallback : args[index + 1];
};

const base = option("base", "https://emdashcms.pl").replace(/\/$/, "");
const pause = Number(option("pause", "1500"));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// A browser Accept header: EmDash prefetches layout data only for HTML
// navigations, so this renders the same way a reader's request does.
const headers = {
	Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
	"User-Agent": "emdashcms-cache-warmer",
};

const sitemap = await fetch(`${base}/sitemap.xml`, { headers });
if (!sitemap.ok) {
	console.error(`sitemap.xml answered ${sitemap.status}; nothing warmed`);
	process.exit(1);
}
const urls = [...(await sitemap.text()).matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
console.log(`warming ${urls.length} pages from ${base}/sitemap.xml, ${pause} ms apart`);

let failures = 0;
let misses = 0;
for (const url of urls) {
	const started = performance.now();
	const response = await fetch(url, { headers, redirect: "manual" });
	await response.arrayBuffer();
	const ms = Math.round(performance.now() - started);
	const cache = response.headers.get("x-cache") ?? "-";
	if (cache === "MISS") misses++;
	console.log(`${response.status} ${cache.padEnd(4)} ${String(ms).padStart(5)} ms  ${url}`);

	if (response.status >= 500) {
		failures++;
		if (failures >= 2) {
			console.error("two 5xx responses: stopping (check `wrangler tail` for exceededCpu)");
			process.exit(1);
		}
		await sleep(pause * 3);
	}
	await sleep(pause);
}
console.log(`done: ${misses} rendered and cached, ${urls.length - misses} already cached`);
