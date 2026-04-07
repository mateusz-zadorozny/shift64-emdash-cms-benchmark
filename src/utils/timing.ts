/**
 * Simple query timing utility.
 * Stores timings in Astro.locals.timings for output in Server-Timing header.
 */

export interface Timing {
	label: string;
	dur: number;
}

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
