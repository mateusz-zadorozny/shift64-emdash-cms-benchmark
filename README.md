# emdash-cms-pl — EmDash benchmark subject site

Astro 7 + [EmDash CMS](https://github.com/emdash-cms/emdash) + Cloudflare Workers + D1. This is the **EmDash side** of the *EmDash vs WordPress* benchmark published on SHIFT64.

- **Article:** [I Bought the Domain Before I Ran the Test. EmDash Still Lost to WordPress.](https://shift64.com/blog/emdash-cms-vs-wordpress-honest-benchmark)
- **Live site:** [emdashcms.pl](https://emdashcms.pl)
- **WordPress control site repo:** [shift64-wp-theme-emdash-flavor](https://github.com/mateusz-zadorozny/shift64-wp-theme-emdash-flavor) — the hand-coded WordPress theme used as the comparison site, covering the same content set
- **Round two (October 2026), technical deep-dive:** [`benchmark/report-v3.md`](./benchmark/report-v3.md) — what made EmDash 3× faster (D1 sessions, bylines, Astro 7), the KV object cache, and 24,726 fresh measurements against WordPress
- **Full benchmark write-up in this repo:** [`benchmark/`](./benchmark/) — 4,732 measurements over ~3.5 days, `bench.sh` cron collector, `analyze.py`, raw `results.csv`, and the full `report-v2.md`

---

## Branches

`main` is the site as it runs today on [emdashcms.pl](https://emdashcms.pl). The April versions are kept for reference.

| Branch or commit | What it is |
|---|---|
| **`main`** | **The round-two site (October 2026).** EmDash 1.1, Astro 7, D1 sessions off with independent queries started together, the byline traps removed, comments preloaded, and a page cache that keeps pages for a day and is purged on every publish, comment or media change. Uncached server time: **170 ms** median, against WordPress's 78 ms; a page cache hit takes **28 ms**. See [`benchmark/report-v3.md`](./benchmark/report-v3.md). |
| `exp/kv-object-cache` | `main` without the page cache, plus EmDash's KV object cache (`kvCache`), deployed as [kv.emdashcms.pl](https://kv.emdashcms.pl) for the round-two comparison: **136 ms** median, **12 ms** warm render. |
| [`0e1a24e`](https://github.com/mateusz-zadorozny/shift64-emdash-cms-benchmark/tree/0e1a24e) | **The April baseline:** the bare official [`emdash-blog`](https://github.com/emdash-cms/emdash-blog) starter with content imported. It scored 543 ms mean server time in the [April article](https://shift64.com/blog/emdash-cms-vs-wordpress-honest-benchmark). |
| `perf/server-defer-widgets` | **The April "faster" version:** `server:defer` widgets, batched tag queries and a Cache API edge cache on top of the baseline. It scored 322 ms mean, still 4.1× slower than WordPress. Merged into `main` in October. |

The round-two changes came in through PRs [#8](https://github.com/mateusz-zadorozny/shift64-emdash-cms-benchmark/pull/8)–[#18](https://github.com/mateusz-zadorozny/shift64-emdash-cms-benchmark/pull/18); their branches are kept on the remote.

## Stack

| Layer | Choice |
|---|---|
| Framework | Astro 7 with `@astrojs/cloudflare` adapter (v14) |
| CMS | EmDash (`emdash-blog` starter template) |
| Runtime | Cloudflare Workers (v8 isolates / workerd) |
| Database | Cloudflare D1 (SQLite at edge) |
| Media storage | Cloudflare R2 |
| Plugins | `emdash/plugin-forms`, `emdash/plugin-webhook-notifier` |
| Language | TypeScript |
| Package manager | npm |

## What we learned the hard way

> **April 2026 findings.** Point 5 turned out to be wrong: the "floor" was D1 sessions running every query one at a time. With sessions off, uncached server time fell to 170 ms in October. See [`benchmark/report-v3.md`](./benchmark/report-v3.md).

The article covers the headline numbers. This section is the longer list of things I wish the EmDash docs had flagged up front. Every one of these was a real rabbit hole during the benchmark.

### 1. `cacheHint` is emitted into a void unless you configure `experimental.cache`

Every page in the official `emdash-blog` starter does this:

```ts
const { entries: posts, cacheHint } = await getEmDashCollection("posts");
Astro.cache.set(cacheHint);
```

It looks like page caching. It is not. `Astro.cache.set()` only does anything if `experimental.cache` is configured in `astro.config.mjs` to consume the hints. The starter does **not** configure one. The hints are being emitted into nothing.

**Impact:** every HTML request — human, curl, or Googlebot — runs the full D1 query chain and renders fresh. No caching is actually in play.

### 2. `server:defer` does not apply to `node_modules` components

EmDash's `WidgetArea` component (sidebar + footer widgets) fires 7 D1 queries on the critical path of every post page. The obvious fix is `<WidgetArea name="sidebar" server:defer>` — but that does not work, because `server:defer` is a compile-time directive that requires the component to be part of your project, not imported from `node_modules`.

**Workaround (on the `perf/server-defer-widgets` branch):** write thin wrapper components inside `src/components/` that import the EmDash component and re-export it, then attach `server:defer` to the wrapper. Add skeleton fallbacks so the page doesn't pop when the deferred micro-request completes.

```astro
<!-- src/components/DeferredSidebar.astro -->
---
import { WidgetArea } from "emdash/ui";
---
<WidgetArea name="sidebar" />
```

```astro
<DeferredSidebar server:defer>
  <div slot="fallback" class="sidebar-skeleton">
    <div class="skeleton-block"></div>
    <div class="skeleton-block"></div>
  </div>
</DeferredSidebar>
```

### 3. `getTermsForEntries` exists but is not documented

Every page that lists posts ran an N+1 loop (`getEntryTerms()` per post). EmDash exposes `getTermsForEntries()` — a batch API that fetches all tags in a single `WHERE entry_id IN (...)` query. It is not in the docs. I found it by reading source. Applied to the 5 listing pages (`/`, `/posts`, `/posts/[slug]`, `/category/[slug]`, `/tag/[slug]`). Full diff in the `perf: replace N+1 tag queries with batched getTermsForEntries` commit.

### 4. Workers on a custom domain bypass Cloudflare's CDN cache

You add `Cache-Control: public, s-maxage=60, stale-while-revalidate=300` via middleware. You deploy. You curl. `X-Cache: MISS`. Always.

This is because Workers on a custom domain hit the Worker first, and the Worker returns the response directly to the client — Cloudflare's CDN cache layer is not in the path. The `Cache-Control` header works for *downstream* caches, but it does not make the edge cache the response on your behalf.

**Workaround:** wrap the Worker entrypoint with explicit Cache API calls (`caches.open("html-pages")` → `match` → `put`). `caches.default` does not work on custom domains; named caches do. See the `perf: add edge caching via Cloudflare Cache API` commit for the full implementation in `src/worker.ts`.

*Update, October 2026:* Cloudflare now offers [Workers Cache](https://developers.cloudflare.com/workers/cache/), an opt-in cache in front of the Worker, and Astro 7's `cacheCloudflare()` provider uses it. We evaluated it in [#7](https://github.com/mateusz-zadorozny/shift64-emdash-cms-benchmark/issues/7) and kept the Cache API wrapper; the issue explains why.

### 5. The D1 latency floor is architectural

Every D1 round-trip over the edge costs ~40 ms. A post page needs at least 3 sequential round-trips (entry → tags + related → related tags — the inner two can be parallelized, but the chain has depth 3). At 40 ms each, that is ~120 ms *before* HTML rendering even starts. Plus widgets. Plus post lists. Plus whatever the admin panel layer touches.

**This is not fixable at the application layer.** It is the cost of asking a database that lives at the edge to answer a question that requires follow-up questions. D1 read replicas (announced, not yet shipped at time of writing) would cut this 5–10×. Until then, a ~320 ms floor is the best you can do without full-page edge caching.

## Running locally

```bash
npm install
npm run dev
```

Loads the D1 local emulator + R2 local emulator + Astro dev server. The dev UI is at `http://localhost:4321/_emdash`.

## Deploying to Cloudflare

```bash
npm run deploy
```

Requires Wrangler auth and an existing D1 database + R2 bucket configured in `wrangler.jsonc`.

## Benchmark folder

See [`benchmark/README.md`](./benchmark/README.md) for what is in there — short version: everything you need to reproduce the 4,732-measurement report from scratch on your own VPS, including the bash collector, the Python analyzer, the raw CSV, and the full written report.

## License

Theme and content code: MIT. Seed content in the database is original material by [Mateusz Zadorożny](https://shift64.com).

---

*Published alongside [shift64.com/blog/emdash-cms-vs-wordpress-honest-benchmark](https://shift64.com/blog/emdash-cms-vs-wordpress-honest-benchmark).*
