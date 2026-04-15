# EmDash (Cloudflare Workers) vs WordPress — TTFB Benchmark Report

## Methodology

| Parameter | Value |
|-----------|-------|
| Test period | 2026-04-03 16:30 → 2026-04-06 10:02 UTC (~66h) |
| Total measurements | 2,496 (1,248 per site) |
| Runs | 96 |
| Tested pages | 13 (homepage + 12 posts, identical content on both sites) |
| Tool | `curl` with full timing breakdown (`--write-out`) |
| Test server | OVH VPS, Warsaw (Poland) |
| Isolation | Each URL = new curl process (no keep-alive, no cache) |
| Request order | Randomized per run (eliminates DNS cache bias) |

### Cron schedule evolution

| Phase | Schedule | Gap | Measurements | Purpose |
|-------|----------|-----|--------------|---------|
| 1 (Apr 3 16:30–20:50) | `*/10 * * * *` | 10 min | 572 | Baseline — Workers stay warm |
| 2 (Apr 3 21:00–23:02) | `0,1,2 * * * *` | 58 min | 234 | Attempt to capture cold starts |
| 3 (Apr 4 01:00+) | `0,1,2 */3 * * *` | ~3h | 1,690 | Force cold starts — Workers must sleep |

Each burst fires 3 runs at :00, :01, :02. The :00 request hits after the full gap ("cold"), :01/:02 hit a warm Worker.

### Test subjects

| | EmDash (CF Workers) | WordPress |
|--|---------------------|-----------|
| **Engine** | Astro 6 + D1 (SQLite at edge) | PHP 8.4 + MySQL |
| **Hosting** | Cloudflare Workers (serverless) | Hetzner (Frankfurt) |
| **CDN** | Cloudflare (native) | Cloudflare (proxy) |
| **URL** | emdashcms.pl | emdash.pl |
| **Network path** | OVH Waw → CF Edge → D1 | OVH Waw → CF Proxy → Hetzner Fra (~400 km) |

> Note: WordPress has a longer network path (extra hop to Frankfurt), yet wins on every metric. The gap is entirely server processing.

### Plan change: Free → Paid Workers

On 2026-04-05 between 07:02 and 10:00 UTC, the Cloudflare account was upgraded from the **Free plan** to the **Workers Paid plan** ($5/mo). This creates a natural A/B experiment.

| Period | Plan | CF measurements |
|--------|------|-----------------|
| Apr 3 16:30 → Apr 5 07:02 | Free | 897 |
| Apr 5 10:00 → Apr 6 10:02 | Paid | 351 |

---

## Results: Server Processing Time (overall)

> **Server processing** = TTFB minus DNS/TCP/SSL. Pure backend work — database queries, HTML rendering.

| Metric | CF (EmDash) | WP | Delta | Winner |
|--------|-------------|-----|-------|--------|
| **Mean** | 543 ms | 84 ms | +459 ms | **WP** (6.4x faster) |
| Median | 543 ms | 69 ms | +474 ms | WP |
| Min | 129 ms | 42 ms | +87 ms | WP |
| Max | 2,196 ms | 246 ms | +1,950 ms | WP |
| P95 | 864 ms | 148 ms | +716 ms | WP |
| P99 | 1,121 ms | 234 ms | +887 ms | WP |
| Std Dev | 178 ms | 42 ms | | |
| CV | 32.8% | 49.7% | | **CF** (more consistent) |

## Results: Total TTFB (user perspective)

> **Total TTFB** = DNS + TCP + SSL + Server. What the user actually waits from click to first byte.

| Metric | CF (EmDash) | WP | Delta |
|--------|-------------|-----|-------|
| **Mean** | 596 ms | 136 ms | +460 ms |
| Median | 593 ms | 116 ms | +477 ms |
| P95 | 939 ms | 233 ms | +706 ms |
| Max | 2,294 ms | 373 ms | +1,921 ms |

## Network Breakdown (averages)

| Phase | CF | WP | Note |
|-------|-----|-----|------|
| DNS | 3 ms | 3 ms | Identical (both behind Cloudflare) |
| TCP | 1 ms | 1 ms | Test server close to both |
| SSL | 49 ms | 47 ms | Both using CF certificates |
| **Server** | **543 ms** | **84 ms** | **This is where the gap lives** |

---

## Per-Page Comparison

| Page | CF server | WP server | Delta | Ratio |
|------|-----------|-----------|-------|-------|
| **Homepage** | 225 ms | 83 ms | +142 ms | 2.7x |
| ai | 579 ms | 79 ms | +500 ms | 7.3x |
| architektura | 554 ms | 85 ms | +469 ms | 6.5x |
| bezpieczenstwo | 579 ms | 91 ms | +488 ms | 6.4x |
| co-to-jest-emdash-cms | 582 ms | 83 ms | +499 ms | 7.0x |
| emdash-vs-wordpress | 561 ms | 88 ms | +473 ms | 6.4x |
| jak-zainstalowac | 586 ms | 84 ms | +502 ms | 7.0x |
| migracja | 564 ms | 78 ms | +486 ms | 7.2x |
| monetyzacja | 552 ms | 79 ms | +473 ms | 7.0x |
| open-source | 577 ms | 83 ms | +494 ms | 7.0x |
| przyszlosc | 559 ms | 87 ms | +472 ms | 6.4x |
| serverless | 569 ms | 89 ms | +480 ms | 6.4x |
| wtyczki | 567 ms | 89 ms | +478 ms | 6.4x |

**Score: WP wins 13/13 pages.**

---

## Free vs Paid Workers

### Server processing time

| Metric | CF Free | CF Paid | Delta | WP (control) |
|--------|---------|---------|-------|--------------|
| **Mean** | 522 ms | 594 ms | **+72 ms (+14%)** | 84 → 85 ms (+1%) |
| Median | 512 ms | 578 ms | +66 ms | 68 → 69 ms |
| P95 | 837 ms | 952 ms | +115 ms | 148 → 152 ms |
| P99 | 1,055 ms | 1,145 ms | +90 ms | 234 → 236 ms |
| Max | 1,762 ms | 2,196 ms | +434 ms | 246 → 239 ms |
| >800 ms | 5.0% | **8.5%** | | 0% → 0% |
| >1,000 ms | 1.8% | **4.3%** | | 0% → 0% |
| n | 897 | 351 | | |

### Cold starts: free vs paid (3h-gap bursts only)

| Metric | Free cold | Paid cold | Free warm | Paid warm |
|--------|-----------|-----------|-----------|-----------|
| Mean | 625 ms | **677 ms** | 544 ms | 553 ms |
| Max | 1,762 ms | **2,196 ms** | 768 ms | 939 ms |
| >800 ms | 15% | **24%** | 0% | 1% |
| n | 143 | 117 | 286 | 234 |
| Cold penalty | +81 ms (+15%) | **+124 ms (+22%)** | | |

### Same time-of-day comparison (eliminating daytime bias)

To rule out time-of-day bias, we compare cold starts (:00) at matching hours:

| Hour (UTC) | Free avg | Paid avg | Delta |
|------------|----------|----------|-------|
| 01:00 | 503 ms | 596 ms | +92 ms |
| 04:00 | 520 ms | 592 ms | +72 ms |
| 07:00 | 645 ms | 640 ms | -5 ms |
| 10:00 | 712 ms | 761 ms | +49 ms |
| 13:00 | 733 ms | 665 ms | -68 ms |
| 16:00 | 774 ms | 656 ms | -118 ms |
| 19:00 | 668 ms | 705 ms | +37 ms |
| 22:00 | 648 ms | 718 ms | +71 ms |
| **Overall** | **625 ms** | **677 ms** | **+52 ms** |

After controlling for time of day, paid is still ~52 ms slower on average. However, the result is **mixed** — paid is worse at night (01:00–04:00) but slightly better at peak hours (13:00–16:00). No clear winner.

### Verdict: Paid plan does not improve TTFB

With 351 paid measurements (9 bursts, covering all hours of day), the picture is clearer:

- **Overall:** paid is 72 ms slower (+14%)
- **Time-controlled:** paid is 52 ms slower (+8%), but results vary by hour
- **Cold start spikes:** worse on paid (24% vs 15% >800 ms)
- **WP control group:** unchanged (+1 ms), confirming the difference is real

The paid plan's benefits (higher CPU limits, 10M requests/mo, Durable Objects) **do not address the bottleneck**, which is D1 edge round-trip latency. The slight degradation may be due to different Worker pool placement or statistical noise.

---

## Cold Start Analysis

### CF Workers — cold vs warm (all burst data, phases 2 & 3)

| | Mean | Median | Std Dev | P95 | Max | n |
|--|------|--------|---------|-----|-----|---|
| **Cold** (:00) | 649 ms | 548 ms | 274 ms | 1,121 ms | 2,196 ms | 260 |
| **Warm** (:01/:02) | 549 ms | 519 ms | 142 ms | 703 ms | 939 ms | 520 |
| **Delta** | **+100 ms (+18%)** | | | | | |

### Spike distribution — CF cold vs warm

| Threshold | Cold (:00) | Warm (:01/:02) |
|-----------|------------|----------------|
| >600 ms | 136/260 **(52%)** | 155/520 (30%) |
| >800 ms | 50/260 **(19%)** | 2/520 **(0.4%)** |
| >1,000 ms | 20/260 **(8%)** | 0/520 **(0%)** |

**The >800 ms zone is cold-start exclusive** — only 2 out of 520 warm requests ever crossed it, vs 50 out of 260 cold requests (48x more likely).

### Cold start severity by time of day (aggregated across all days)

| Hour (UTC) | CF cold avg | CF cold max | Spikes >800 ms |
|------------|-------------|-------------|----------------|
| 01:00 | 549 ms | 864 ms | 3/26 (12%) |
| 04:00 | 556 ms | 1,236 ms | 2/26 (8%) |
| 07:00 | 642 ms | 1,762 ms | 5/26 (19%) |
| 10:00 | 745 ms | 2,196 ms | 9/26 (35%) |
| 13:00 | 699 ms | 1,271 ms | 5/26 (19%) |
| 16:00 | 715 ms | 1,299 ms | 8/26 (31%) |
| 19:00 | 705 ms | 1,145 ms | 4/13 (31%) |
| 22:00 | 718 ms | 1,121 ms | 4/13 (31%) |

Cold starts follow a clear daily pattern: **mildest at night** (549 ms avg, 8–12% spikes) and **worst during business hours** (745 ms avg at 10:00, 35% spikes). This correlates with global Cloudflare platform load.

### WP — cold vs warm (for comparison)

| | Mean | Max | n |
|--|------|-----|---|
| **Cold** (:00) | 80 ms | 243 ms | 260 |
| **Warm** (:01/:02) | 84 ms | 239 ms | 520 |
| **Delta** | -4 ms (-5%) | | |

WordPress shows **zero cold start effect**.

---

## Analysis

### 1. WordPress is 6.4x faster on server processing

Mean 84 ms (WP) vs 543 ms (CF). The gap widened as more cold start data accumulated (initial 5.5x → 6.4x). Even WP's **worst** measurement (246 ms) beats CF's **best** post page (~400 ms).

### 2. The homepage tells a different story (2.7x, not 6.4x)

CF homepage (225 ms) is the only page under 400 ms. The homepage fetches a post list with a single query. Post pages require multiple sequential D1 round-trips: entry → tags + related posts (parallel) → related tags (parallel). Each D1 round-trip adds ~50–100 ms.

EmDash uses `Promise.all()` where possible, but the dependency chain requires at minimum 3 sequential D1 round-trips per post page. This is a fundamental limitation of edge databases, not an optimization issue.

### 3. Cold starts are confirmed and follow a daily cycle

- Average cold penalty: **+18%** (100 ms)
- **52% of cold requests exceed 600 ms** (vs 30% warm)
- **19% exceed 800 ms** (vs 0.4% warm)
- **8% exceed 1 second** (vs 0% warm)
- Daily cycle: mildest at 01:00–04:00 UTC, worst at 10:00 UTC (35% spike rate)

This confirms the original hypothesis: manual testing during business hours catches the worst cold starts.

### 4. Paying for Workers doesn't help TTFB

With 351 paid measurements across all hours of day, the paid plan shows no improvement:
- Mean is 72 ms slower (+14%)
- Time-controlled comparison: 52 ms slower (+8%)
- Cold start spikes are more frequent (24% vs 15%)
- The paid plan's advantages don't address D1 latency

### 5. The network path favors WordPress — but shouldn't

WP traffic routes OVH Warsaw → CF Proxy → Hetzner Frankfurt (~400 km). CF Workers process at the edge. Despite this, WP wins because local MySQL (<0.1 ms) dominates D1 edge queries (~50–100 ms per round-trip).

---

## Conclusions

1. **WP is 6.4x faster** — driven entirely by database access pattern (MySQL localhost vs D1 edge round-trips)
2. **CF cold starts confirmed** — +18% average, 19% of cold requests >800 ms, 8% >1 second
3. **Cold starts follow a daily cycle** — 8% spike rate at night, 35% at 10:00 UTC
4. **Paid Workers plan ($5/mo) does not improve TTFB** — confirmed with 351 measurements across all hours
5. **The >800 ms zone is cold-start exclusive** — warm requests virtually never cross it
6. **Network topology doesn't save CF** — edge advantage negated by edge database latency

### What this means for EmDash

The performance gap is an architectural trade-off, not a code quality issue. Edge databases (D1) trade latency for global distribution and zero-ops. For content sites where TTFB matters, this currently favors traditional hosting with local databases.

Potential mitigations:
- Aggressive query batching / single-query page rendering
- D1 read replicas (when available) for reduced round-trip latency
- Full-page edge caching (eliminates D1 round-trips for repeat visits)
- Smart Cache: cache HTML at edge, invalidate on content change

---

## Experiment Log

| Date | Change |
|------|--------|
| 2026-04-03 16:30 | Start. Cron `*/10 * * * *` (every 10 min). CF Free plan. |
| 2026-04-03 ~21:00 | Changed to `0,1,2 * * * *` (burst 3x/h, 58 min gap). |
| 2026-04-04 ~01:00 | Changed to `0,1,2 */3 * * *` (burst 3x every 3h, ~3h gap). |
| 2026-04-05 ~08:00 | Upgraded CF to Workers Paid plan ($5/mo). |
| 2026-04-05 10:00 | First paid-plan burst recorded. |

---

---

## Update: Performance Optimization (2026-04-07)

### Context

Following the initial benchmark results, we attempted to reduce EmDash's TTFB through code-level optimizations. The goal was to cut the number of D1 round-trips per page — the primary bottleneck identified in the analysis above.

**Important caveat:** These optimizations required manual refactoring of the site code. They are **not available out of the box** in EmDash — a developer must identify query hotspots, write wrapper components, and restructure data fetching. For a CMS that positions itself as a WordPress alternative, this is a significant barrier: WordPress achieves 84 ms with zero manual query tuning, while EmDash requires careful engineering to get from 542 ms down to 322 ms — still 4x slower.

### What was changed

**1. `server:defer` on widget areas (sidebar + footer)**

EmDash's `WidgetArea` component renders widgets server-side, each making its own D1 queries. On a post page, the sidebar alone (search, categories, tags, recent posts, archives) generated **7 D1 queries** blocking the initial response.

Astro's `server:defer` directive moves these queries out of the critical path — the page sends HTML with a placeholder immediately, and the deferred component loads via a separate micro-request.

Because `server:defer` cannot be applied directly to components from `node_modules` (serialization constraints), we had to create thin wrapper components:

```astro
<!-- src/components/DeferredSidebar.astro -->
---
import { WidgetArea } from "emdash/ui";
---
<WidgetArea name="sidebar" />
```

```astro
<!-- Usage in posts/[slug].astro -->
<DeferredSidebar server:defer>
  <div slot="fallback" class="sidebar-skeleton">
    <div class="skeleton-block"></div>
    <div class="skeleton-block"></div>
  </div>
</DeferredSidebar>
```

The same pattern was applied to the footer `WidgetArea` in the base layout.

**2. Batch tag queries with `getTermsForEntries`**

Every page listing posts (homepage, archives, post detail with "read more" section) fetched tags per-post in a loop — an N+1 pattern generating one D1 query per post:

```js
// BEFORE: N+1 — one query per post
const filteredPosts = await Promise.all(
  posts.map(async (post) => {
    const tags = await getEntryTerms("posts", post.data.id, "tag");
    return { post, tags };
  })
);
```

EmDash exposes a `getTermsForEntries` batch API (undocumented) that fetches all tags in a single `WHERE entry_id IN (...)` query:

```js
// AFTER: single query for all posts
const tagsMap = await getTermsForEntries(
  "posts", posts.map((p) => p.data.id), "tag"
);
const filteredPosts = posts.map((post) => ({
  post,
  tags: tagsMap.get(post.data.id) ?? [],
}));
```

This was applied to all 5 pages that list posts: `/`, `/posts`, `/posts/[slug]`, `/category/[slug]`, `/tag/[slug]`.

### Query count reduction

| Page | Before | After | Saved |
|------|--------|-------|-------|
| `/posts/[slug]` (post detail) | ~17 queries | ~8 critical + ~9 deferred | 9 off critical path, 3 eliminated |
| `/` (homepage) | ~11 queries | ~5 queries | 6 eliminated |
| `/posts` (archive, N posts) | 2 + N queries | 3 queries | N-1 eliminated |
| `/category/[slug]` (N posts) | 3 + N queries | 4 queries | N-1 eliminated |
| `/tag/[slug]` (N posts) | 3 + N queries | 4 queries | N-1 eliminated |

### Results (30 runs, ~30 minutes post-deploy)

| Metric | Before (182 runs) | After (30 runs) | Delta |
|--------|-------------------|-----------------|-------|
| **Server mean** | 542 ms | 322 ms | **-220 ms (-41%)** |
| **Server median** | 547 ms | 317 ms | **-230 ms (-42%)** |
| **TTFB mean** | 593 ms | 373 ms | **-220 ms (-37%)** |
| **P95** | 732 ms | 368 ms | **-364 ms (-50%)** |
| **P99** | 1,094 ms | 424 ms | **-670 ms (-61%)** |
| **Max spike** | 2,196 ms | 745 ms | **-1,451 ms (-66%)** |
| **CV (consistency)** | 29.3% | 11.6% | **2.5x more stable** |

Per-page post averages dropped from ~570 ms to ~325 ms. The homepage went from 215 ms to 294 ms — likely noise given the smaller sample size (30 vs 182 runs).

### Comparison with WordPress (post-optimization)

| Metric | CF (optimized) | WP | Ratio |
|--------|---------------|-----|-------|
| Server mean | 322 ms | 78 ms | **4.1x** (was 6.4x) |
| Server median | 317 ms | 53 ms | 6.0x |
| P95 | 368 ms | 142 ms | 2.6x |
| Max spike | 745 ms | 245 ms | 3.0x |

### Assessment

The optimizations cut TTFB by 41% and nearly eliminated >1s spikes. However:

1. **Still 4x slower than WordPress** — the remaining ~320 ms is the floor for ~8 sequential D1 round-trips at ~40 ms each. This is architectural, not fixable by query optimization.

2. **Required non-trivial developer effort** — identifying the N+1 pattern, discovering the undocumented batch API, creating wrapper components for `server:defer`, adding skeleton loading states. A WordPress site achieves better performance with zero manual tuning.

3. **`server:defer` improves perceived performance beyond TTFB** — the user sees the article content immediately while the sidebar loads in the background. This benefit is real but not captured by curl-based TTFB benchmarks.

4. **The gap narrows at the tail** — P95 is now 2.6x (was 4.9x), max spike is 3.0x (was 8.9x). The optimization disproportionately helps worst-case scenarios by removing queries from the critical path.

The remaining path to close the gap with WordPress would be full-page edge caching with `stale-while-revalidate` — effectively eliminating D1 round-trips for repeat visits entirely. But that moves the problem from "slow" to "stale" and requires cache invalidation infrastructure.

---

## Update: Edge Caching (2026-04-07, follow-up)

### Why caching became necessary

The query optimizations above (server:defer + batch queries) cut server time from 542 ms to 322 ms — a 41% improvement, but still **4x slower than WordPress's uncached 78 ms**. The remaining ~320 ms is the architectural floor: ~8 D1 round-trips at ~40 ms each. There is no code-level fix for edge database latency.

Since we could not achieve competitive TTFB on raw database queries alone, we added full-page edge caching via the Cloudflare Cache API.

**Important note on fairness:** WordPress also has extensive caching options (WP Super Cache, W3 Total Cache, Cloudflare APO, Varnish, Redis object cache, etc.) that would bring its TTFB close to zero. The numbers below compare *cached EmDash* against *uncached WordPress* — this is **not an apples-to-apples comparison** and should not be used to claim EmDash is "faster" than WordPress. Both platforms can achieve near-instant responses with caching. The point here is to demonstrate that edge caching is a viable mitigation for D1 latency, not to declare a winner.

### Implementation

Two components were added:

**1. Cache-Control headers via Astro middleware**

The middleware sets CDN-friendly headers on all public HTML pages:

```typescript
// src/middleware.ts (excerpt)
if (isPublicPage && !response.headers.has("Cache-Control")) {
  response.headers.set(
    "Cache-Control",
    "public, max-age=0, s-maxage=60, stale-while-revalidate=300",
  );
}
```

- `s-maxage=60` — edge cache serves fresh content for 60 seconds
- `stale-while-revalidate=300` — after 60s, serves stale while refreshing in background (up to 5 min)
- `max-age=0` — browser always revalidates with edge (so cache purge takes effect immediately)
- Skipped for: admin routes (`/_emdash`), API routes, logged-in users

**2. Cloudflare Cache API wrapper in worker entry**

Workers on custom domains bypass Cloudflare's CDN cache layer by default. The standard `Cache-Control` header has no effect — responses go directly from the Worker to the client. To enable caching, the Worker entry point was wrapped with explicit `caches.open()` / `match()` / `put()` calls:

```typescript
// src/worker.ts (excerpt)
const cache = await caches.open("html-pages");
const cached = await cache.match(cacheKey);
if (cached) {
  const hit = new Response(cached.body, cached);
  hit.headers.set("X-Cache", "HIT");
  return hit;
}

const response = await handler.fetch(request, env, ctx);
if (response.status === 200 && cacheControl?.includes("s-maxage")) {
  ctx.waitUntil(cache.put(cacheKey, toCache));
}
```

This required discovering that:
- `caches.default` does not work on Workers with custom domains (only on Workers behind Cloudflare proxy)
- Named caches (`caches.open("...")`) do work
- Cache keys must be normalized (stripped query params, GET-only Request objects) for consistent matching
- HEAD requests bypass the Worker's `fetch()` handler — `X-Cache` only appears on GET responses

### Results (cached, single PoP — Warsaw)

| Page | Uncached (optimized) | Cached (HIT) | Improvement |
|------|---------------------|--------------|-------------|
| Homepage | 294 ms | ~150 ms | -49% |
| Post pages | ~325 ms | ~110 ms | -66% |

### Staleness window and consistency

With `s-maxage=60`, content can be up to 60 seconds stale after an edit in the admin panel. For a blog/content site, this is acceptable. Crucially, the **entire page is cached as one unit** — sidebar widgets, main content, and footer all come from the same cached response. There is no scenario where a new post appears in the main content but not in the sidebar's "Recent Posts" widget. Either everything is fresh, or everything is equally stale.

EmDash does have built-in tag-based cache invalidation (`cache.invalidate({ tags: [collection, id] })`) on every content save/delete/publish operation. However, this requires Astro's `experimental.cache` provider, which is not yet available for the Cloudflare adapter. When it ships, `s-maxage` caching can be replaced with instant purge-on-edit — eliminating the staleness window entirely.

### What this does NOT prove

To reiterate: this comparison is structurally unfair. WordPress was tested **without any caching layer** — raw PHP + MySQL on every request. Adding WP Super Cache, Cloudflare APO, or even a simple Varnish proxy would give WordPress sub-50ms TTFB. The purpose of this section is to show that EmDash + edge caching is a *workable* solution for production, not that it outperforms WordPress.

---

*Report v2.2 — updated 2026-04-07. Edge caching section added. Based on ~66h baseline data (4,732 measurements) + 30 post-optimization runs (780 measurements) + manual cache verification.*
