# benchmark/ — EmDash vs WordPress TTFB benchmark

Full measurement artifacts from the benchmark published on SHIFT64:

- **Article:** [I Bought the Domain Before I Ran the Test. EmDash Still Lost to WordPress.](https://shift64.com/blog/emdash-cms-vs-wordpress-honest-benchmark)
- **WordPress comparison theme repo:** [shift64-wp-theme-emdash-flavor](https://github.com/shift64/shift64-wp-theme-emdash-flavor)
- **Parent repo README:** [`../README.md`](../README.md) — describes what was learned from the EmDash side (cache hints, `server:defer` gotcha, undocumented batch API, custom-domain CDN cache bypass, D1 latency floor)

## What is in here

| File | What it is |
|---|---|
| **[`report-v2.md`](./report-v2.md)** | **The full written report.** 4,732 measurements, methodology across all three cron phases, per-page breakdowns, hourly cold-start distribution, Free vs Paid Workers A/B, and the post-optimization / post-caching follow-ups. This is what the article's data tables are drawn from. |
| [`raport-v1.md`](./raport-v1.md) | Early Polish-language version covering just the first 3.5 hours of data (Phase 1 only). Kept as a historical artifact — superseded by `report-v2.md`. |
| [`bench.sh`](./bench.sh) | The cron-scheduled bash collector that produced `results.csv`. Uses `curl --write-out` for full phase-by-phase timing breakdown (DNS / TCP / SSL / server / total TTFB), randomizes URL order per run, spawns a fresh `curl` process per URL to eliminate keep-alive and client-cache effects. |
| [`analyze.py`](./analyze.py) | Python analyzer that consumes `results.csv` and produces the percentile / distribution / per-page / cold-vs-warm / Free-vs-Paid summaries in `report-v2.md`. Re-run after any new collection pass. |
| [`results.csv`](./results.csv) | Raw curl timings. One row per URL hit per run. 4,732 rows from the baseline collection, plus additional rows for the post-optimization runs. |

## Reproducing the numbers from scratch

On any Linux VPS with `curl`, `bash`, and cron:

```bash
# 1. Clone this repo
git clone https://github.com/shift64/shift64-emdash-cms-benchmark.git
cd shift64-emdash-cms-benchmark/benchmark

# 2. Edit bench.sh to point at your two test URLs
#    (CF_BASE and WP_BASE variables near the top)

# 3. Install the cron entry manually, phased:
#    Phase 1 — Workers stay warm:        */10 * * * * bash /path/to/bench.sh
#    Phase 2 — catch cold starts:        0,1,2 * * * * bash /path/to/bench.sh
#    Phase 3 — force cold starts:        0,1,2 */3 * * * bash /path/to/bench.sh

# 4. Let it run for ~3.5 days (results.csv grows one row per URL per cron fire)

# 5. Analyze
python3 analyze.py results.csv
```

`analyze.py` prints the same headline numbers that feed the report: mean / median / P95 / P99 / max / std-dev for each site, per-page breakdowns, Cold-vs-Warm distribution, and the Free vs Paid A/B if the CSV is labelled accordingly.

## Measurement isolation — what the benchmark deliberately controls for

- **DNS cache bias:** URL order is randomized per run, so the first URL in the sequence isn't systematically the one that eats the DNS lookup cost.
- **Keep-alive bias:** every URL hit spawns a fresh `curl` process with no connection reuse. This eliminates the scenario where the second URL in a run benefits from a still-open TCP/TLS connection from the first.
- **Client cache bias:** `curl` runs without a cookie jar, without `If-None-Match`, without `If-Modified-Since`. Every hit is a cold client.
- **Cloudflare warmup bias (Phase 3):** 3-hour gaps between runs force the Worker to actually sleep. Within a run, the `:00` / `:01` / `:02` burst separates the first-after-sleep request (cold) from the next two (warm).
- **Time-of-day bias:** Phase 3 runs are spread across 8 distinct UTC hours (01:00, 04:00, 07:00, 10:00, 13:00, 16:00, 19:00, 22:00) so daily load patterns on Cloudflare's global edge are captured rather than concentrated in one window.

## What the benchmark does **not** control for

- **Network path from the test VPS.** The test VPS is OVH Warsaw. WordPress traffic hits Cloudflare → Hetzner Frankfurt (~400 km round-trip). EmDash traffic hits Cloudflare edge (presumably Warsaw). Geography favors EmDash in the network layer by ~20–40 ms — and EmDash still loses by 459 ms on server processing. This is a net-negative control-for-me situation: the comparison's geography handicap is on WordPress, and WordPress still wins.
- **Hetzner vs Cloudflare uptime / reliability.** Both sides stayed up for the whole 3.5-day collection. One Hetzner hiccup or one Cloudflare incident would change the max-spike column. Take the max rows with appropriate salt.
- **What happens after a deploy-triggered Worker restart on the EmDash side.** The 3-hour gap in Phase 3 creates cold starts, but a deploy is a cleaner reset. Not tested here.

## See also

- [`../src/`](../src/) — the Astro + EmDash application code, including the `perf/server-defer-widgets` optimization branch
- [Cloudflare's EmDash launch post](https://blog.cloudflare.com/emdash-wordpress/) — source for the "serverless, but you can run it on your own hardware or any platform you choose" and "You can run EmDash anywhere, on any Node.js server" quotes cited in the article's Node.js caveat
