/**
 * Data Base.astro renders on every page: the primary menu and the footer's
 * list of pages.
 *
 * Astro runs a page's frontmatter to completion before the layout's, so if
 * Base.astro starts these queries itself they wait behind every query the page
 * makes. Pages call preloadLayoutData() first thing instead: the queries start
 * together with the page's own, and Base.astro awaits the same promise.
 */

import { getEmDashCollection, getMenu } from "emdash";
import { timed } from "./timing";

async function loadLayoutData() {
	const [menu, { entries: pages }] = await Promise.all([
		getMenu("primary"),
		getEmDashCollection("pages"),
	]);
	return { menu, pages };
}

type LayoutData = Awaited<ReturnType<typeof loadLayoutData>>;

/** One promise per request, shared by the page and Base.astro. */
export function getLayoutData(locals: App.Locals): Promise<LayoutData> {
	const store = locals as { __layoutData?: Promise<LayoutData> };
	store.__layoutData ??= timed(locals, "D1:layout", loadLayoutData);
	return store.__layoutData;
}

/**
 * Start loading the layout data without waiting for it. A page that bails out
 * early (redirect to /404) never renders Base.astro, so mark the rejection as
 * handled here; Base.astro still sees it when it awaits.
 */
export function preloadLayoutData(locals: App.Locals): void {
	getLayoutData(locals).catch(() => {});
}
