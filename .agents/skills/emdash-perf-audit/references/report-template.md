# Report template

Save as `perf-audits/perf-audit-YYYY-MM-DD.md` (`benchmark/audits/` in the benchmark repo). Write in the user's language. Lead with the answer, keep every number labelled with its source, and link to the technical deep-dive (https://github.com/mateusz-zadorozny/shift64-emdash-cms-benchmark/blob/main/benchmark/report-v3.md) instead of re-explaining background.

```markdown
# Performance audit: <site>, <date>

<One or two sentences: the slowest page, its query chain and time, and the single fix that would save the most.>

Setup: EmDash <x>, Astro <y>, adapter <z>, live version <id> (main at <sha>). Page cache: <yes/no, TTL>. Object cache: <none / KV, defaultTtl>.

## Pages

| Page | render (prod, ms) | queries pre / body | longest chain | db.last (ms) |
| --- | --- | --- | --- | --- |

Source: production Server-Timing, <n> rounds, Accept: text/html, <date>. Queries and chain: local waterfall, mirrored production data, latency 20 ms.

## Traps

| # | Trap | Status | Cost on this site |
| --- | --- | --- | --- |

## Fixes, ranked

1. **<fix>** — saves ~<ms> on <pages>; effort <S/M/L>; <code / content / config / upstream>.

## Not measured

<Anything skipped and why, e.g. no production mirror, a page that needs a login.>
```

Statuses: OK, Present, Not applicable. A recommendation that changes content, settings or deploys a new version is listed, never done.
