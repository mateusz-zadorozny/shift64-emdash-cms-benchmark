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

	return response;
});
