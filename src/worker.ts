import handler from "@astrojs/cloudflare/entrypoints/server";
export { PluginBridge } from "@emdash-cms/cloudflare/sandbox";

/**
 * Wrap the Astro handler with Cloudflare Cache API.
 * Workers on custom domains bypass Cloudflare CDN cache by default,
 * so we use caches.default to cache public HTML responses at the edge.
 *
 * Cache key uses a stripped URL (no query params except whitelisted ones)
 * to ensure consistent matching regardless of request headers.
 */
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

		// Use a clean URL as cache key (strip tracking params, normalize)
		const cacheUrl = new URL(url.pathname, url.origin);
		const cacheKey = new Request(cacheUrl.toString(), {
			method: "GET",
		});

		const cache = await caches.open("html-pages");
		const cached = await cache.match(cacheKey);
		if (cached) {
			// Add marker header so we know it was a cache hit
			const hit = new Response(cached.body, cached);
			hit.headers.set("X-Cache", "HIT");
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
