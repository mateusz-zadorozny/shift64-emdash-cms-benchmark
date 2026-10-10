# EmDash on Cloudflare: the technical deep-dive

The full story behind the round-two article: every fix, trap and number, for anyone running EmDash 1.1 on Cloudflare Workers and D1. Measured in October 2026 on EmDash 1.1.0, Astro 7.3.5 and the free Workers plan.

## The fix: EmDash asked the database one question at a time

A page on emdashcms.pl made 12–16 database queries, and EmDash ran them strictly one after another. On Cloudflare D1 each query is a round trip of about 25 ms, so a post page spent over 300 ms just waiting.

Median server time until the response headers, uncached browser visits (EmDash Server-Timing `render`, emdashcms.pl production):

| Page | Before the fixes (5 Oct) | After the fixes, Astro 6 (5 Oct) | Now, Astro 7 (6 Oct) |
| --- | --- | --- | --- |
| Home | 296 ms | 67 ms | 76 ms |
| All posts | 300 ms | 66 ms | 80 ms |
| A post | 320 ms | 63 ms | 110 ms |
| Category | 356 ms | 50 ms | 68 ms |

The cause sat between EmDash and D1. With D1 sessions on, EmDash's database layer runs a request's queries one at a time, even when a page starts several of them together. For browser visits it also prefetches menus and widgets ahead of the page's own queries. The site has no D1 read replicas, so sessions bought it nothing. I turned them off and made every page start its independent queries together: one config line and a handful of `Promise.all` calls, with the rendered HTML unchanged.

## The minefield: bylines

Two of the biggest costs weren't in my code. They were in content settings that look harmless in the admin.

- **Posts without a byline credit.** A post with an author but no explicit byline makes EmDash run a fallback: two extra queries on every page that lists it. Five of my 18 posts had been created that way. Crediting them cut another 30–50 ms from every listing page. The byline picker sits in the post editor's sidebar, and it is easy to miss.
- **Empty custom byline fields.** While hunting for that picker, I added two byline fields, "Job title" and "X link", and left them empty. That alone added 4–7 queries to every page and pushed server time back up to 130–200 ms. Once any field exists, EmDash reads field values every time it loads bylines, even when there are none. Deleting the fields brought the numbers back.
- **The version check.** Even with no fields at all, EmDash checks a byline-fields version number on every request: one more query, every time.

Nothing in the admin warns you about any of this. The only way I found them was by counting queries per page.

## Upstream reports

I reported four issues to EmDash on 5 October. One was fixed and merged four days later, and I sent my own fix for another.

| Issue | What it costs | Status on 10 October |
| --- | --- | --- |
| [#3905](https://github.com/emdash-cms/emdash/issues/3905) | Comments are counted and listed in two sequential queries | Fixed by [#3907](https://github.com/emdash-cms/emdash/pull/3907), opened by EmDash's bot 46 minutes after the report and merged on 10 October. Ships after 1.2.0. |
| [#3915](https://github.com/emdash-cms/emdash/issues/3915) | A D1 session runs one query at a time, and the layout prefetch queues first | Open; fix in review ([#3937](https://github.com/emdash-cms/emdash/pull/3937)) |
| [#3903](https://github.com/emdash-cms/emdash/issues/3903) | The byline-fields version is read from D1 on every request | Open |
| [#3904](https://github.com/emdash-cms/emdash/issues/3904) | Entries with no terms in a taxonomy aren't primed, so terms are queried again | My fix: [#4088](https://github.com/emdash-cms/emdash/pull/4088), opened 10 October and awaiting maintainer review. On this site it takes the home page and post list from 5 to 4 queries. |

## Astro 7 and the free plan: two more surprises

EmDash itself is built and tested on Astro 7, so I upgraded. The build went from 40 to 14 seconds. The one visible breakage was whitespace: Astro 7's new default glued "18 artykułów" into "18artykułów" until I set `compressHTML: true`.

The less visible change: Astro 7 sends nothing until every async component on the page has rendered. My comments section loads its own data, so the post page's first byte arrived about 40 ms later. Starting the comment queries earlier won back half of that. The post page now takes 110 ms of server time, against 88 ms on Astro 6 in the same test.

Then the site started failing. For five minutes, until I rolled back, up to 60% of uncached requests returned an empty 503. Cloudflare's free Workers plan allows 10 ms of CPU per request, and a rendered EmDash page needs 10–24 ms. Cloudflare tolerates the occasional overrun, but my own benchmark, about 1,000 uncached page loads in under an hour, crossed the line. The fix is the $5-a-month paid plan, or much gentler benchmarking.

## What I skipped: Workers Cache

Astro 7 can hand page caching to Cloudflare's new [Workers Cache](https://developers.cloudflare.com/workers/cache/), which answers from the edge before the Worker even runs. EmDash already purges the right pages when you publish. I tested it and kept my own cache instead, but made it smarter. It keeps pages for a day now, and EmDash's own publish hooks purge it, along with comment and media changes and every deploy.

For readers in Poland it would save about 40 ms per cached page. In exchange, signed-in editors would get the cached anonymous page, and every request, static files included, would be billed. Purges are also capped at five a minute. On a small blog, that trade isn't worth it yet.

## Would a bigger site blow up the same way?

Not the way bylines did, and the reason is where each query goes. WordPress talks to MySQL on the same server, so a query costs well under a millisecond. EmDash on Workers talks to D1 over the network, about 25 ms per round trip. WordPress adds rows to queries it already runs; EmDash adds round trips.

| What you add | WordPress (MySQL on the same server) | EmDash on D1 |
| --- | --- | --- |
| Custom fields | Stored as post meta. All fields of all listed posts load in one query, so more fields means more rows, not more queries. | Stored as columns of the content table, so they come with the post row at no extra cost. |
| Custom taxonomies | All terms of all listed posts load in one primed query. | Batched per lookup (`getTermsForEntries`), but each kind of lookup is another round trip. |
| Several authors per post | Core has one author; plugins such as Co-Authors Plus keep authors as terms, which load with the term cache. | Built in. Credits and profiles load in two batched queries. The traps are a post with no credit (a 2-query fallback) and custom byline fields (2 more queries). |
| Related or referenced posts | Usually a few extra queries at under 1 ms each. | One round trip per kind of relation, in sequence when it depends on the previous result. |
| Full-page cache | Common (server or plugin); a cached hit never runs PHP. | Our own edge cache: a day per page, purged on every publish or edit. |

A rough estimate, not measured: a richer EmDash site with three taxonomies, bylines with fields, related entries and comments would run 12–18 queries a page. With independent queries started together, that is a chain of maybe 5–7 round trips, or 120–170 ms of server time on an uncached page. The WordPress equivalent might run 50–100 queries, but at well under a millisecond each they add maybe 20–40 ms. There, PHP rendering is the bigger cost. WordPress forgives a one-query-per-post plugin; EmDash makes you pay for every new kind of data, on every uncached request.

## The rematch: results

Server time from the OVH VPS in Warsaw (method below), 317 runs, 4,121 requests per site and arm:

| Server time (ms) | April p50 | October p50 | October p95 | October p99 |
| --- | --- | --- | --- | --- |
| EmDash, full render | 547 | **170** | 348 | 938 |
| EmDash, page cache hit | — | **28** | 51 | 510 |
| EmDash, KV object cache | — | **136** | 218 | 922 |
| WordPress (object cache, no page cache) | 68 | **78** | 160 | 249 |

- **The cron wasn't it.** I wondered whether the every-minute cron, which wasn't there in April, flattered EmDash by keeping D1 warm. It didn't: the full render took 174 ms with it and 170 ms without.
- **Cold starts hit everyone alike.** The first request to a site after 15 quiet minutes cost +54 ms on EmDash and +64 ms on WordPress.
- **EmDash slows down during the European day.** Its median goes from 146 ms at night to 183 ms in the afternoon (UTC). WordPress stays flat at 77–79 ms, so this is probably load on D1.
- **The tails barely moved.** EmDash's p99 is 938 ms (1,095 ms in April), with a worst case of 2.7 s. WordPress's p99 is 249 ms. The median is a different story; the rare D1 stalls are the same.

## Using the KV object cache: three things to know

```js
// astro.config.mjs, plus a KV namespace bound as CACHE in wrangler.jsonc
emdash({ objectCache: kvCache({ binding: "CACHE", defaultTtl: 86400 }) })
```

| KV object cache, uncached page | Render | Server time | D1 queries |
| --- | --- | --- | --- |
| First request for a page in a run (KV cold) | 102 ms | 155 ms | 1 |
| Second request within a minute (KV warm) | **12 ms** | **67 ms** | 1 |
| For comparison: full render, no object cache | 103 ms | 170 ms | 9–10 |

- **Raise `defaultTtl` on the free plan.** It caps KV at 1,000 writes a day, and the default one-hour TTL rewrites every cached query hourly.
- **Pick it or a page cache, not both.** With a page cache configured, EmDash skips the object cache when it renders a page, so it never refills a purged page from data that may be a minute old.
- **It's still a render on every request.** The free plan's 10 ms CPU limit still applies; a page cache hit doesn't even run the Worker.

## Method

The same OVH VPS in Warsaw as in April, the same 13 pages and the same metric: server time is time to first byte minus DNS, TCP and TLS. It ran every 15 minutes from 6 October, 09:37 UTC, to 9 October, 18:00 UTC, on three sites:

- emdashcms.pl, with the page cache
- kv.emdashcms.pl, the same code with EmDash's KV object cache instead
- emdash.pl, the WordPress site

Each run covered two arms, uncached (`?nc=`) and as served, with 1.5 s between requests. There were no deploys or content edits until it ended. The site's every-minute cron (EmDash's scheduler) was off, as it was in April. I removed it at 09:52 UTC, but Cloudflare kept firing it until 10:38, about 46 minutes against the documented 15, so the analysed data starts with the 10:52 run: 317 runs, 24,726 requests, no errors.

Raw data: [`vps-results-2026-10.csv`](./vps-results-2026-10.csv), collected by [`vps-bench.py`](./vps-bench.py) and summarised by [`vps-summary.py`](./vps-summary.py) (`python3 vps-summary.py --since 2026-10-06T10:52:00Z`).
