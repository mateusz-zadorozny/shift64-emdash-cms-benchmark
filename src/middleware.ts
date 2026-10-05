import { defineMiddleware } from "astro:middleware";
import { APP_TIMING_HEADER, formatServerTiming, getTimings } from "./utils/timing";

export const onRequest = defineMiddleware(async (context, next) => {
	const start = performance.now();
	const response = await next();
	const total = performance.now() - start;

	// Our query timings. EmDash would overwrite a Server-Timing header set
	// here, so src/worker.ts moves this one into Server-Timing.
	const timings = [...getTimings(context.locals), { label: "total", dur: total }];
	response.headers.set(APP_TIMING_HEADER, formatServerTiming(timings));

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
