import handler from "@astrojs/cloudflare/entrypoints/server";
export { PluginBridge } from "@emdash-cms/cloudflare/sandbox";

/**
 * Wrap the Astro handler with Cloudflare Cache API.
 * Workers on custom domains bypass Cloudflare CDN cache by default,
 * so we use caches.default to cache public HTML responses at the edge.
 *
 * Cache key is the URL without tracking params, with remaining query params
 * sorted. The query string must stay in the key: /search?q=foo and
 * /search?q=bar are different pages.
 */
const TRACKING_PARAMS = /^(utm_.+|fbclid|gclid|msclkid|mc_cid|mc_eid|ref)$/;

function cacheKeyUrl(url: URL): string {
	const params = [...url.searchParams]
		.filter(([key]) => !TRACKING_PARAMS.test(key))
		.sort(([a], [b]) => a.localeCompare(b));
	const keyUrl = new URL(url.pathname, url.origin);
	for (const [key, value] of params) keyUrl.searchParams.append(key, value);
	return keyUrl.toString();
}

export default {
	async fetch(request: Request, env: unknown, ctx: ExecutionContext): Promise<Response> {
		// Only cache GET requests
		if (request.method !== "GET") {
			return handler.fetch(request, env, ctx);
		}

		const url = new URL(request.url);

		// Skip cache for admin, API, and preview routes
		if (url.pathname.startsWith("/_emdash") || url.pathname.startsWith("/api")) {
			return handler.fetch(request, env, ctx);
		}

		const cacheKey = new Request(cacheKeyUrl(url), {
			method: "GET",
		});

		const cache = await caches.open("html-pages");
		const cached = await cache.match(cacheKey);
		if (cached) {
			// Add marker header so we know it was a cache hit
			const hit = new Response(cached.body, cached);
			hit.headers.set("X-Cache", "HIT");
			// The stored copy gets the zone's browser TTL (max-age=14400);
			// restore max-age=0 so browsers revalidate as the middleware intends
			hit.headers.set("Cache-Control", "public, max-age=0, s-maxage=60, stale-while-revalidate=300");
			return hit;
		}

		const response = await handler.fetch(request, env, ctx);

		// Only cache responses that have our s-maxage header (set by middleware)
		const cacheControl = response.headers.get("Cache-Control");
		if (response.status === 200 && cacheControl?.includes("s-maxage")) {
			const toCache = response.clone();
			ctx.waitUntil(cache.put(cacheKey, toCache));
		}

		response.headers.set("X-Cache", "MISS");
		return response;
	},
} satisfies ExportedHandler;
