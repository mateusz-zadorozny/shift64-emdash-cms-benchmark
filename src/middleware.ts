import { defineMiddleware } from "astro:middleware";
import { HTML_CACHE_CONTROL } from "./utils/html-cache";
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
		// s-maxage: src/worker.ts keeps the page for a day; content changes
		// purge it sooner (src/utils/html-cache.ts)
		// max-age=0: browser always revalidates, so a purge reaches it at once
		response.headers.set("Cache-Control", HTML_CACHE_CONTROL);
	}

	return response;
});
