/**
 * Data Comments.astro renders: the collection's comment settings and the
 * entry's comments.
 *
 * Astro sends a page's response only after the async components in its body
 * have rendered, and Comments.astro only runs once the page's frontmatter is
 * done. The post page calls preloadComments() as soon as it knows the entry
 * id instead: the queries run together with the page's own, and
 * Comments.astro awaits the same promise.
 */

import { getCollectionInfo, getComments } from "emdash";
import { timed } from "./timing";

interface CommentsQuery {
	collection: string;
	contentId: string;
	threaded: boolean;
}

async function loadComments({ collection, contentId, threaded }: CommentsQuery) {
	// If comments turn out to be disabled, Comments.astro doesn't render them
	const [collectionInfo, comments] = await Promise.all([
		getCollectionInfo(collection),
		getComments({ collection, contentId, threaded }),
	]);
	return { collectionInfo, comments };
}

type CommentsData = Awaited<ReturnType<typeof loadComments>>;

/** One promise per entry and request, shared by the page and Comments.astro. */
export function getCommentsData(locals: App.Locals, query: CommentsQuery): Promise<CommentsData> {
	const store = locals as { __comments?: Map<string, Promise<CommentsData>> };
	store.__comments ??= new Map();
	const key = `${query.collection}/${query.contentId}/${query.threaded}`;
	let data = store.__comments.get(key);
	if (!data) {
		data = timed(locals, "D1:comments", () => loadComments(query));
		store.__comments.set(key, data);
	}
	return data;
}

/**
 * Start loading the comments without waiting for them. Mark the rejection as
 * handled here; Comments.astro still sees it when it awaits.
 */
export function preloadComments(locals: App.Locals, query: CommentsQuery): void {
	getCommentsData(locals, query).catch(() => {});
}
