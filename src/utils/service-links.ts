/**
 * Links from this blog to the commercial site (emdash.pl). Every link carries
 * UTM tags so analytics on emdash.pl can tell which placement brought the
 * visit (hero, footer, post sidebar, end of post, ...).
 */
const SERVICE_ORIGIN = "https://emdash.pl";

export type ServicePlacement =
	| "hero"
	| "footer"
	| "footer-bottom"
	| "post-sidebar"
	| "post-end"
	| "post-list"
	| "404";

export function serviceUrl(placement: ServicePlacement, hash = ""): string {
	const params = new URLSearchParams({
		utm_source: "emdashcms.pl",
		utm_medium: placement,
		utm_campaign: "blog",
	});
	return `${SERVICE_ORIGIN}/?${params}${hash}`;
}
