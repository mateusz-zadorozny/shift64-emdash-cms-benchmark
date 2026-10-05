import { defineMiddleware } from "astro:middleware";
import { getTimings } from "./utils/timing";

export const onRequest = defineMiddleware(async (context, next) => {
	const start = performance.now();
	const response = await next();
	const total = performance.now() - start;

	// Build Server-Timing header from collected query timings
	const timings = getTimings(context.locals);
	const parts = timings.map(
		(t, i) => `${t.label.replace(/\s/g, "_")};dur=${t.dur.toFixed(1)};desc="${t.label}"`,
	);
	parts.push(`total;dur=${total.toFixed(1)};desc="Total"`);

	response.headers.set("Server-Timing", parts.join(", "));

	// CDN caching for public HTML pages
	// Skip: admin routes, API routes, non-200, non-HTML, logged-in users
	const path = context.url.pathname;
	const isPublicPage =
		response.status === 200 &&
		response.headers.get("content-type")?.includes("text/html") &&
		!path.startsWith("/_emdash") &&
		!path.startsWith("/api") &&
		!context.locals.user;

	if (isPublicPage && !response.headers.has("Cache-Control")) {
		// s-maxage: CDN caches for 60s (origin not hit)
		// stale-while-revalidate: serve stale for 5min while refreshing in background
		// max-age=0: browser always revalidates with CDN (so CDN purge is instant for users)
		response.headers.set(
			"Cache-Control",
			"public, max-age=0, s-maxage=60, stale-while-revalidate=300",
		);
	}

	return response;
});
