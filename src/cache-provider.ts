/**
 * Astro cache provider that turns EmDash's cache invalidations into a purge
 * of the HTML cache in src/worker.ts (see src/utils/html-cache.ts).
 *
 * EmDash calls invalidate() after it changes published content, menus,
 * taxonomies, widgets, bylines or settings, and after scheduled publishing,
 * but only when a cache provider is configured. This one caches nothing
 * itself and sets no headers.
 */

import type { CacheProviderFactory } from "astro";
import { purgeHtmlCache } from "./utils/html-cache";

const factory: CacheProviderFactory = () => ({
	name: "html-cache",
	setHeaders: () => new Headers(),
	invalidate: purgeHtmlCache,
});

export default factory;
