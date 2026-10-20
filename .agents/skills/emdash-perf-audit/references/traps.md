# Known EmDash-on-D1 performance traps

The costs below were measured on emdashcms.pl in October 2026: EmDash 1.1.0, Astro 7.3.5, the Workers Free plan, and about 25 ms per D1 query. They are reference values only. Measure the cost on the audited site whenever you can.

Each trap below lists:

- **Detect:** how to find it.
- **Cost:** what it costs.
- **Fix:** how to fix it.
- **Notes:** caveats, where there are any.

Go through them in this order. It roughly follows how much each trap tends to cost.

## 1. D1 sessions turn every request into a queue

- **Detect:**
  - `d1({ ..., session: ... })` is set in `astro.config.mjs`. The EmDash templates turn it on.
  - In the waterfall, queries that a page starts together still run one after another. The longest chain equals the query count.
  - In production, `db.total` ≈ `render`.
- **Cost:** about 25 ms for every query in the queue. On emdashcms.pl, pages took 296–356 ms of render before the fix and 50–67 ms after it.
- **Fix:** remove `session` when the database has no read replicas. Replicas add little anyway for a database in Vienna and readers in Poland. Then start independent queries together with `Promise.all`.
- **Upstream:** emdash#3915, fix in review as #3937.

## 2. Sequential awaits in pages and components

- **Detect:** waterfall chains where query B doesn't need A's result but still starts after A ends. Look for `await` in a row in `src/pages/**` and in components.
- **Cost:** about 25 ms for each link in the chain.
- **Fix:** use `Promise.all` for independent lookups, or move the work to a batch API:
  - `getTermsForEntries` instead of per-post `getEntryTerms`;
  - one query for comments instead of a count followed by a list. #3905 is fixed upstream by #3907.

## 3. Posts without an explicit byline credit

- **Detect:** SQL `posts-without-byline` in `sql.md`. In the waterfall, two extra queries on every list that contains such a post (an `author_id` fallback).
- **Cost:** 2 queries on every list page that shows such a post. Fixing it took another 30–50 ms off each listing on emdashcms.pl, where 5 of 18 posts were affected.
- **Fix:** credit a byline. Use the post editor sidebar, or `PUT /_emdash/api/content/posts/{id}` with only `bylines` and `_rev`. This is a content change, so recommend it and let the user decide.

## 4. Custom byline fields, even empty ones

- **Detect:** SQL `byline-fields` returns more than 0 rows. Queries against `_emdash_byline_field_values` or `_emdash_byline_field_group_values` show up in the waterfall.
- **Cost:** 4–7 queries per page on emdashcms.pl, pushing server time back to 130–200 ms. Once any field exists, EmDash reads the field values every time it loads bylines.
- **Fix:** delete fields nobody uses. Check `/_emdash/api/admin/byline-fields/{slug}/usage` first, and take a D1 time-travel bookmark before deleting.

## 5. Byline-fields version check on every request

- **Detect:** an `options` read of `byline_fields_version` on every request, even with no fields defined.
- **Cost:** 1 query per request.
- **Fix:** none on the site side. It is upstream emdash#3903, still open. Report it as a known core cost.

## 6. Entries with no terms in a taxonomy are queried again

- **Detect:** SQL `posts-without-tags` returns rows, and list pages show one extra taxonomy query after the content query.
- **Cost:** 1 query on the home page and the post list. Locally, 5 → 4 queries and 75 → 52 ms.
- **Fix:** upstream emdash#3904, fixed by PR #4088 (pending review when this was written). Check its state, and drop this trap once the site runs a release that contains it.

## 7. Astro 7 holds the first byte for async components

- **Detect:** Astro ≥ 7, and components that load their own data (comments, related posts). In the waterfall, these queries run before the headers and stretch the time to the first byte. Queries that run during streaming show as `body` and never reach Server-Timing.
- **Cost:** about 40 ms of TTFB on post pages (110 ms against 88 ms on Astro 6). Starting the comment queries earlier won back about half of it.
- **Fix:** start component data loading in the page frontmatter and pass the promise down. Accept the rest as a trade-off for Astro 7's 3× faster builds.

## 8. Free plan CPU limit

- **Detect:** empty 503s under sustained uncached load. In production, `render` is fine but a share of requests fails. The plan is Free.
- **Cost:** up to 60% of uncached requests failed for 5 minutes during an aggressive benchmark.
- **Fix:** the Workers Paid plan ($5 a month), or a page cache so that most requests never render.
- **Notes:** this is also why the audit itself must stay gentle.

## 9. No page cache, or a short one

- **Detect:**
  - The response has no `x-cache: HIT` on a second plain request.
  - The `s-maxage` is short.
  - Workers on a custom domain skip the CDN cache unless the handler uses the Cache API itself.
- **Cost:** the difference between a full render (median 170 ms of server time from Warsaw) and a cache hit (28 ms).
- **Fix:** an edge cache keyed by Worker version plus a purge generation, purged by EmDash content, comment and media hooks. On emdashcms.pl it is `src/utils/html-cache.ts`, with `s-maxage=604800` (7 days) since 10 October 2026.

## 10. KV object cache: missing, misconfigured or redundant

- **Detect:** the `objectCache` option in `emdash()`.
- **Cost / gain:** with `kvCache`, a warm render took 12 ms and 67 ms of server time, with 1 D1 query instead of 9–10. A cold KV read took 102 ms render and 155 ms server time. KV keeps a value hot per location for about a minute.
- **Notes:**
  - On the Free plan KV allows 1,000 writes a day, so `defaultTtl` should be 86400 or more. The default hour rewrites every cached query hourly.
  - When a page cache is configured, EmDash skips the object cache while it renders pages, so configuring both buys nothing. Recommend one or the other.

## 11. Cron and cold starts

- **Detect:** `crons` in `wrangler.jsonc`, and a high `rt.*` in Server-Timing on the first request after a quiet period.
- **Cost:** the every-minute cron had no measurable effect (174 ms with it, 170 ms without). The first request after 15 quiet minutes cost +54 ms, about the same as WordPress's +64 ms.
- **Fix:** usually nothing. Report it only if `rt` dominates.

## 12. Astro 7 whitespace

- **Detect:** Astro ≥ 7 without `compressHTML: true`. Words glued together, such as "18artykułów".
- **Cost:** correctness, not speed.
- **Fix:** `compressHTML: true`.
