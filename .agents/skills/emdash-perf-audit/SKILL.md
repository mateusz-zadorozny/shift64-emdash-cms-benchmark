---
name: emdash-perf-audit
description: Audit the performance of an EmDash site on Cloudflare Workers + D1 (the site in the current repo, in development or in production). Count D1 queries per page, find sequential query chains, check the known EmDash traps (D1 sessions, byline fields and missing byline credits, Astro 7 streaming, Free plan CPU limit, KV object cache TTL, page cache), measure locally with the waterfall tool against a production mirror, and write a dated Markdown report in the repo. Also use it while building a new EmDash site, to check a page's query count before it ships. Use this whenever the user asks why an EmDash page is slow, wants a performance/speed/TTFB audit or health check, asks to count queries, check Server-Timing, compare before/after a change, or check whether a setting, upgrade (EmDash or Astro) or content change made the site slower, even if they don't say "audit".
---

# EmDash performance audit

An EmDash page on D1 is slow almost always for one reason: too many database round trips, run one after another. Each D1 query costs about 25 ms from a Worker, so a page is as fast as its longest chain of sequential queries. Every costly problem found on emdashcms.pl so far was a hidden extra query or a hidden queue, and none of them showed up as an error. The audit's job is to make those queries visible, tie each to its cause, and rank the fixes by milliseconds saved.

The tools ship with this skill in `scripts/`. Run them from the site root (the directory with `wrangler.jsonc`); they write everything to `.bench/`, which should be in `.gitignore`.

- `scripts/uncached.py` reads production Server-Timing.
- `scripts/waterfall.py`, with `scripts/bench-entry.mjs`, gives a per-query local waterfall.

The traps, with their measured costs, are in `references/traps.md`. Read it before Step 4. They were measured on emdashcms.pl, the site in the shift64-emdash-cms-benchmark repo, which is also the source of this skill.

## Ground rules (why they matter)

- **Be gentle with production.** The site runs on the Workers Free plan, which allows 10 ms of CPU per request, and an EmDash render takes 10–24 ms. About 1,000 uncached requests in under an hour once produced 503s on up to 60% of requests. Stay at about 10 rounds per page with a pause of at least 1.5 s, and do the heavy measuring locally.
- **Read only.** The audit doesn't deploy, edit content or change settings. `--mirror-prod` and the SQL in `references/sql.md` run SELECTs only. If a fix needs a production change, put it in the report as a recommendation and let the user decide.
- **A site that isn't live yet** has no production to measure. Skip Step 2 and measure only locally, on the seed or on content the user has added.
- **Never print tokens.** API tokens come from `~/.config/emdash/auth.json` and stay in shell variables. Mask any `ec_…` strings in output you show.
- **Say where every number comes from:** production Server-Timing, the local waterfall on mirrored production data, or the seed. A local result on seed data undercounts queries, because query counts depend on content (for example, a post without a byline credit costs 2 extra queries).
- **Know what is live.** Production may be deployed by hand with `wrangler deploy` and may not match `main`. Check `npx wrangler deployments list` and compare it with git before blaming or crediting code.

## Workflow

### 1. Context (5 minutes, no requests to the site)

Collect these facts, because every trap depends on one of them:

- `package.json`: the `emdash`, `astro` and `@astrojs/cloudflare` versions.
- `astro.config.mjs`: the `d1(...)` options (is `session` set?), `objectCache` (backend and `defaultTtl`), `compressHTML`, and any `experimental.cache` or route cache settings.
- `wrangler.jsonc`: `crons`, KV namespaces and the plan hints.
- `src/worker.ts`, `src/middleware.ts` and any cache helpers: whether a page cache exists, its `Cache-Control`/`s-maxage`, and how it is purged.
- The live version (`npx wrangler deployments list`) against `git log -1`.
- The upstream status of the known issues (`gh issue view <n> -R emdash-cms/emdash --json state`): #3903, #3904 (fix #4088), #3905 (fixed by #3907), #3915 (#3937). A merged fix changes what a trap costs on the next EmDash version.

### 2. Production snapshot (Server-Timing)

```bash
U=.claude/skills/emdash-perf-audit/scripts/uncached.py
python3 $U --base https://<site> --pages /,/<list>/,/<a-post> --label audit-$(date +%F) --rounds 10 --accept browser
python3 $U --summary .bench/uncached-audit-$(date +%F).csv
```

Pick one page of each type: home, a list, a single entry, a taxonomy page. Sending `Accept: text/html` matters: EmDash prefetches menus and widgets only for browser navigations, so curl's default `*/*` measures a different code path.

Fields per page, medians:

| Field | What it is |
| --- | --- |
| `render` | page render time |
| `db.count` | queries before the headers |
| `db.total` | summed query time |
| `db.last` | when the last pre-header query ended |
| `cache.hit` / `cache.miss` | the per-request cache |
| `rt.*` | runtime init phases on a cold start |

Two pitfalls:

- `db.total` divided by the page time shows overlap. A large `db.total` with a small render means parallel queries; `db.total` ≈ `render` means a queue.
- Judge by `render` and `db.last`, not `db.total`.

Server-Timing never sees queries made while the body streams, such as comments on Astro 7. Step 3 does.

Then spot-check the page cache with two plain requests per page (no `?nc=`) and look at `x-cache`, `cache-control` and `age`.

### 3. Local waterfall on mirrored production data

```bash
W=.claude/skills/emdash-perf-audit/scripts/waterfall.py
npm run build
python3 $W snapshot audit
python3 $W prepare-db --build audit --mirror-prod      # no production yet: leave out --mirror-prod
python3 $W run audit --latency 20 --accept browser --pages /,/<list>/,/<a-post>   # add --db seed without a mirror
python3 $W report .bench/results/audit-prod-L20.json --waterfall --accept browser
```

`--latency 20` plus about 5 ms of local SQLite reproduces production's roughly 25 ms per query. `--mirror-prod` copies the production D1 named in `wrangler.jsonc` with read-only SELECTs: every `ec_*` content table plus EmDash's bylines, taxonomies, menus, widgets, comments (anonymised) and the public options. Read off each page:

- **Query count**, split into `pre` (before the headers) and `body` (while the body streams).
- **The longest sequential chain.** Queries that start only after the previous one ended form one chain, so its length is the page's floor in round trips.
- **Repeats:** the same SQL repeated with different parameters (N+1), or the same SQL twice (a missed cache).
- **The SQL itself.** Match each query to a trap: `_emdash_byline_field*` tables, a fallback `author_id` lookup, `options` reads of `byline_fields_version`, a second taxonomy lookup, comment count followed by comment list.

To test a candidate fix:

1. Snapshot the new build under another name and run it the same way.
2. Run `waterfall.py diff before.json after.json` to prove the HTML did not change.
3. Restore any temporary patch in `node_modules` afterwards (keep a backup first).

### 4. Match against the traps

Go through `references/traps.md` in order and give each trap a status:

- **OK** — not present.
- **Present** — found, with its cost on this site.
- **Not applicable** — for example, no KV backend.

For the data-dependent traps (byline credits, byline fields, untagged posts), run the read-only queries from `references/sql.md`. Run them against the local mirror (the sqlite file under `.bench/state-prod`) or with `npx wrangler d1 execute <database_name from wrangler.jsonc> --remote --command "<SELECT>"`. Every cost in the report should be measured on this site where possible, with the October 2026 reference numbers as a fallback, labelled as such.

### 5. Write the report

Write `perf-audits/perf-audit-YYYY-MM-DD.md` at the repo root (`benchmark/audits/` in the benchmark repo) using the structure in `references/report-template.md`. The ranking matters more than the prose: fixes are ordered by milliseconds saved per uncached page × how many pages they touch, and each says what it costs to do. Keep it short; link to the [technical deep-dive](https://github.com/mateusz-zadorozny/shift64-emdash-cms-benchmark/blob/main/benchmark/report-v3.md) for background instead of restating it.

Commit only if the user asks, and confirm the branch first.

Finish in chat with three to five lines:

- the slowest page and its chain;
- the top fix and what it would save;
- where the report is.
