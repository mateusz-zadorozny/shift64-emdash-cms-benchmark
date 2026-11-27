/**
 * Astro cache provider for the HTML cache in src/worker.ts
 * (see src/utils/html-cache.ts).
 *
 * setHeaders: Astro calls it after all middleware has run, and only when the
 * route set a cache hint (Astro.cache.set(cacheHint)) that nothing disabled
 * later. EmDash disables the route cache with cache.set(false) for logged-in
 * users and for renders whose redirect or settings data turned out stale, so
 * those responses get no s-maxage and the Worker doesn't store them. Pages
 * that should be cached must call Astro.cache.set(cacheHint).
 *
 * invalidate: EmDash calls it after it changes published content, menus,
 * taxonomies, widgets, bylines or settings, after scheduled publishing, and
 * (since 1.5) when an approved comment is published, moderated or deleted,
 * but only when a cache provider is configured. It purges the HTML cache.
 */

import type { CacheProviderFactory } from "astro";
import { HTML_CACHE_CONTROL, purgeHtmlCache } from "./utils/html-cache";

const factory: CacheProviderFactory = () => ({
	name: "html-cache",
	// s-maxage: src/worker.ts keeps the page for 7 days; content changes
	// purge it sooner. max-age=0: the browser always revalidates, so a purge
	// reaches it at once.
	setHeaders: () => new Headers({ "Cache-Control": HTML_CACHE_CONTROL }),
	invalidate: purgeHtmlCache,
});

export default factory;
