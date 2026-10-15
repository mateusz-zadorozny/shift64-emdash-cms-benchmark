import cloudflare from "@astrojs/cloudflare";
import react from "@astrojs/react";
import { d1, r2 } from "@emdash-cms/cloudflare";
import { formsPlugin } from "@emdash-cms/plugin-forms";
import webhookNotifier from "@emdash-cms/plugin-webhook-notifier";
import { defineConfig } from "astro/config";
import emdash from "emdash/astro";

export default defineConfig({
	output: "server",
	// Astro 7 defaults to JSX whitespace rules ("jsx"), which drop the newline
	// between `{count}` and its label ("18artykułów") and between inline links.
	// true keeps Astro 6 output.
	compressHTML: true,
	adapter: cloudflare(),
	// Turns EmDash's cache invalidations (publishing, edits, scheduled posts)
	// into a purge of the HTML cache in src/worker.ts. Not Workers Cache: the
	// adapter only enables that for its own "cloudflare" provider.
	cache: { provider: { name: "html-cache", entrypoint: "./src/cache-provider.ts" } },
	// Content language for EmDash: new entries, terms and menus get "pl".
	// With a single locale EmDash keeps i18n off, so queries don't filter by
	// locale and URLs get no /pl/ prefix.
	i18n: {
		defaultLocale: "pl",
		locales: ["pl"],
	},
	image: {
		layout: "constrained",
		responsiveStyles: true,
	},
	integrations: [
		react(),
		emdash({
			// No D1 sessions: the database has no read replicas, and on a session
			// EmDash runs a request's queries one at a time (and, for browser
			// navigations, prefetches widget and taxonomy data ahead of the page's
			// own queries). Without one, queries a page starts together overlap.
			// If read replication is enabled, use session: "auto" with
			// coalesce: true, which batches those queries instead.
			database: d1({ binding: "DB" }),
			storage: r2({ binding: "MEDIA" }),
			plugins: [formsPlugin(), webhookNotifier],
		}),
	],
	// Inline the site's stylesheets (each under 32 KB, ~3 KB gzipped) into the
	// HTML so they don't block the first render with extra requests. The HTML
	// is edge-cached anyway. The admin's ~270 KB stylesheet stays external.
	// Returning undefined keeps Vite's default for every other asset.
	vite: {
		build: {
			assetsInlineLimit: (file, content) =>
				file.endsWith(".css") ? content.length < 32 * 1024 : undefined,
		},
	},
	devToolbar: { enabled: false },
});
