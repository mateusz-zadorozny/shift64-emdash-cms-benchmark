/**
 * Purging the HTML cache in src/worker.ts.
 *
 * The Cache API can't delete by tag, and cache.delete() only reaches one data
 * centre. So every cache key carries a generation: a purge stores a new one in
 * KV, and the old entries are never looked up again (they expire on their
 * own). The Worker version is in the key too, so a deploy never serves HTML
 * that points at the previous build's assets.
 *
 * Purges come from src/cache-provider.ts (EmDash's invalidations: content,
 * menus, taxonomies, widgets, bylines, settings, scheduled publishing) and
 * from src/worker.ts (comment and media writes, which EmDash doesn't report).
 */

import { env } from "cloudflare:workers";

/** Public pages: browsers always revalidate, the edge keeps them a day. */
export const HTML_CACHE_CONTROL = "public, max-age=0, s-maxage=86400";

const GENERATION_KEY = "html-cache:generation";
// An isolate reuses the generation it last read for this long, then refreshes
// it in the background
const REFRESH_MS = 10_000;
// Workers KV allows one write per second to the same key
const KV_WRITE_INTERVAL_MS = 1_100;

let known: { value: string; readAt: number } | undefined;

async function readGeneration(): Promise<string> {
	const value = (await env.SESSION.get(GENERATION_KEY)) ?? "0";
	known = { value, readAt: Date.now() };
	return value;
}

/** Part of every cache key. Null when it can't be read: skip the cache. */
export async function getCacheVersion(ctx: {
	waitUntil(promise: Promise<unknown>): void;
}): Promise<string | null> {
	let generation = known?.value;
	if (!known) {
		try {
			generation = await readGeneration();
		} catch {
			return null;
		}
	} else if (Date.now() - known.readAt > REFRESH_MS) {
		ctx.waitUntil(readGeneration().catch(() => {}));
	}
	return `${env.CF_VERSION_METADATA?.id ?? "dev"}.${generation}`;
}

/** Make every cached page unreachable. Never throws: a failed purge must not fail the edit that caused it. */
export async function purgeHtmlCache(): Promise<void> {
	for (let attempt = 0; attempt < 2; attempt++) {
		const value = Date.now().toString(36);
		try {
			await env.SESSION.put(GENERATION_KEY, value);
			known = { value, readAt: Date.now() };
			return;
		} catch (error) {
			if (attempt === 1) console.error("[html-cache] purge failed:", error);
			else await new Promise((resolve) => setTimeout(resolve, KV_WRITE_INTERVAL_MS));
		}
	}
}
