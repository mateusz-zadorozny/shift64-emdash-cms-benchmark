/**
 * Simple query timing utility.
 * Stores timings in Astro.locals for output in the Server-Timing header.
 */

export interface Timing {
	label: string;
	dur: number;
}

/**
 * EmDash's middleware runs around ours and replaces the Server-Timing header
 * with its own metrics (db.*, cache.*), so src/middleware.ts sends our
 * timings in this header and src/worker.ts appends them to Server-Timing.
 */
export const APP_TIMING_HEADER = "X-App-Server-Timing";

// A Server-Timing metric name must be an HTTP token (no ":" or spaces)
const NON_TOKEN_CHARS = /[^!#$%&'*+\-.^_`|~0-9A-Za-z]/g;

export function getTimings(locals: App.Locals): Timing[] {
	return (locals as any).__timings ?? [];
}

export async function timed<T>(
	locals: App.Locals,
	label: string,
	fn: () => T | Promise<T>,
): Promise<T> {
	const start = performance.now();
	const result = await fn();
	const dur = performance.now() - start;
	const timings = ((locals as any).__timings ??= []) as Timing[];
	timings.push({ label, dur });
	return result;
}

/** Server-Timing entries: `D1_posts;dur=12.3;desc="D1:posts"`. */
export function formatServerTiming(timings: Timing[]): string {
	return timings
		.map((t) => `${t.label.replace(NON_TOKEN_CHARS, "_")};dur=${t.dur.toFixed(1)};desc="${t.label}"`)
		.join(", ");
}
