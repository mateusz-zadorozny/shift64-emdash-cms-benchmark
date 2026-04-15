# emdash-cms-pl — EmDash benchmark subject site

Astro 6 + [EmDash CMS](https://github.com/emdash-cms/emdash) + Cloudflare Workers + D1. This is the **EmDash side** of the *EmDash vs WordPress* benchmark published on SHIFT64.

- **Article:** [I Bought the Domain Before I Ran the Test. EmDash Still Lost to WordPress.](https://shift64.com/blog/emdash-cms-vs-wordpress-honest-benchmark)
- **Live site:** [emdashcms.pl](https://emdashcms.pl)
- **WordPress control site repo:** [shift64-wp-theme-emdash-flavor](https://github.com/shift64/shift64-wp-theme-emdash-flavor) — the hand-coded WordPress theme used as the comparison site, covering the same content set
- **Full benchmark write-up in this repo:** [`benchmark/`](./benchmark/) — 4,732 measurements over ~3.5 days, `bench.sh` cron collector, `analyze.py`, raw `results.csv`, and the full `report-v2.md`

---

## Branches

There are two branches and **which branch you check out matters**:

| Branch | What it is |
|---|---|
| `main` | The bare official [`emdash-blog`](https://github.com/emdash-cms/emdash-blog) starter template with content imported, deployed as-is. This is the **"before" baseline** — the version that scored 543 ms mean server processing in the benchmark. |
| **`perf/server-defer-widgets`** | **The "faster" version.** Three optimization commits on top of `main`, described below. This is the version that scored 322 ms mean (−41% on server time, −66% on max spike). Still 4.1× slower than WordPress, but the best EmDash can do without edge caching. |

Commits on the `perf/server-defer-widgets` branch (newest first):

```
ff3d075  perf: add edge caching via Cloudflare Cache API
86e7d61  perf: replace N+1 tag queries with batched getTermsForEntries
af1ae9b  perf: defer sidebar and footer widgets with server:defer
```

Every commit is a self-contained optimization — you can cherry-pick individually to see their isolated effect, or diff `main...perf/server-defer-widgets` to see the full set.

## Stack

| Layer | Choice |
|---|---|
| Framework | Astro 6 with `@astrojs/cloudflare` adapter |
| CMS | EmDash (`emdash-blog` starter template) |
| Runtime | Cloudflare Workers (v8 isolates / workerd) |
| Database | Cloudflare D1 (SQLite at edge) |
| Media storage | Cloudflare R2 |
| Plugins | `emdash/plugin-forms`, `emdash/plugin-webhook-notifier` |
| Language | TypeScript |
| Package manager | pnpm |

## What we learned the hard way

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

### 5. The D1 latency floor is architectural

Every D1 round-trip over the edge costs ~40 ms. A post page needs at least 3 sequential round-trips (entry → tags + related → related tags — the inner two can be parallelized, but the chain has depth 3). At 40 ms each, that is ~120 ms *before* HTML rendering even starts. Plus widgets. Plus post lists. Plus whatever the admin panel layer touches.

**This is not fixable at the application layer.** It is the cost of asking a database that lives at the edge to answer a question that requires follow-up questions. D1 read replicas (announced, not yet shipped at time of writing) would cut this 5–10×. Until then, a ~320 ms floor is the best you can do without full-page edge caching.

## Running locally

```bash
pnpm install
pnpm dev
```

Loads the D1 local emulator + R2 local emulator + Astro dev server. The dev UI is at `http://localhost:4321/_emdash`.

## Deploying to Cloudflare

```bash
pnpm deploy
```

Requires Wrangler auth and an existing D1 database + R2 bucket configured in `wrangler.jsonc`.

## Benchmark folder

See [`benchmark/README.md`](./benchmark/README.md) for what is in there — short version: everything you need to reproduce the 4,732-measurement report from scratch on your own VPS, including the bash collector, the Python analyzer, the raw CSV, and the full written report.

## License

Theme and content code: MIT. Seed content in the database is original material by [Mateusz Zadorożny](https://shift64.com).

---

*Published alongside [shift64.com/blog/emdash-cms-vs-wordpress-honest-benchmark](https://shift64.com/blog/emdash-cms-vs-wordpress-honest-benchmark).*
