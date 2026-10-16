/**
 * view-transition-name for a post's featured image. The same name on a card
 * (home, lists, "Czytaj dalej") and on the post's hero lets the browser morph
 * the image between the two pages. A name must be a valid CSS identifier and
 * unique on the page, otherwise the browser skips the whole transition.
 */
export function postImageTransitionName(slug: string): string {
	return `post-image-${slug.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}
