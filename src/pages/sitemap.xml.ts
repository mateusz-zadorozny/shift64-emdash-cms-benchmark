import type { APIRoute } from "astro";
import { getEmDashCollection, getTaxonomyTerms } from "emdash";

export const GET: APIRoute = async ({ url }) => {
	const siteUrl = url.origin;

	const [{ entries: posts }, { entries: pages }, categoryTerms, tagTerms] =
		await Promise.all([
			getEmDashCollection("posts", {
				orderBy: { published_at: "desc" },
			}),
			getEmDashCollection("pages"),
			getTaxonomyTerms("category"),
			getTaxonomyTerms("tag"),
		]);

	const urls: { loc: string; lastmod?: string; priority?: string }[] = [];

	// Homepage
	urls.push({ loc: siteUrl, priority: "1.0" });

	// Posts index
	urls.push({ loc: `${siteUrl}/posts`, priority: "0.8" });

	// Individual posts
	for (const post of posts) {
		urls.push({
			loc: `${siteUrl}/posts/${post.id}`,
			lastmod: post.data.updatedAt instanceof Date ? post.data.updatedAt.toISOString() : undefined,
			priority: "0.7",
		});
	}

	// Static pages
	for (const page of pages) {
		urls.push({
			loc: `${siteUrl}/pages/${page.id}`,
			lastmod: page.data.updatedAt instanceof Date ? page.data.updatedAt.toISOString() : undefined,
			priority: "0.5",
		});
	}

	// Category pages
	for (const term of categoryTerms) {
		urls.push({
			loc: `${siteUrl}/category/${term.slug}`,
			priority: "0.6",
		});
	}

	// Tag pages
	for (const term of tagTerms) {
		urls.push({
			loc: `${siteUrl}/tag/${term.slug}`,
			priority: "0.5",
		});
	}

	const urlEntries = urls
		.map((u) => {
			let entry = `  <url>\n    <loc>${escapeXml(u.loc)}</loc>`;
			if (u.lastmod) entry += `\n    <lastmod>${u.lastmod}</lastmod>`;
			if (u.priority) entry += `\n    <priority>${u.priority}</priority>`;
			entry += `\n  </url>`;
			return entry;
		})
		.join("\n");

	const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urlEntries}
</urlset>`;

	return new Response(sitemap, {
		headers: {
			"Content-Type": "application/xml; charset=utf-8",
			"Cache-Control": "public, max-age=3600",
		},
	});
};

function escapeXml(str: string): string {
	return str
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;");
}
