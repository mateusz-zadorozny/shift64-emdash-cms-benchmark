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
	return response;
});
