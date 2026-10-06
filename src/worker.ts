import handler from "@astrojs/cloudflare/entrypoints/server";
import { createScheduledHandler } from "@emdash-cms/cloudflare/worker";
import { APP_TIMING_HEADER } from "./utils/timing";
export { PluginBridge } from "@emdash-cms/cloudflare/sandbox";

/**
 * Experiment (kv.emdashcms.pl): no page cache here. Every request renders,
 * and EmDash's object cache in KV (astro.config.mjs) stands in for D1 where it
 * can. Compare with main, which caches whole pages in this file.
 */
export default {
	async fetch(request: Request, env: unknown, ctx: ExecutionContext): Promise<Response> {
		const response = await handler.fetch(request, env, ctx);
		// Append src/middleware.ts's query timings to EmDash's Server-Timing
		const appTiming = response.headers.get(APP_TIMING_HEADER);
		if (appTiming) {
			response.headers.delete(APP_TIMING_HEADER);
			response.headers.append("Server-Timing", appTiming);
		}
		// A copy of emdashcms.pl for measurements only: keep it out of search
		response.headers.set("X-Robots-Tag", "noindex, nofollow");
		return response;
	},

	// Unused while wrangler.jsonc has no cron trigger (emdashcms.pl runs it)
	scheduled: createScheduledHandler({ generalCron: "* * * * *" }),
} satisfies ExportedHandler;
