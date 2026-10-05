# benchmark/waterfall/ — local D1 query waterfall

`Server-Timing` on production shows how many D1 queries ran and their summed
time, but not which ones, in what order, or whether they overlapped. It also
only covers queries that finished before the response headers were sent;
anything a component queries while the body streams (e.g. comments) is
invisible to it.

This tool runs the production build locally under `wrangler dev` with
`bench-entry.mjs` in front of it. The wrapper adds a fixed latency to every
D1 call (production pays about 25 ms per query) and records each call's start
and end, so a local request reproduces production's waterfall.

```bash
npm run build
python3 benchmark/waterfall/waterfall.py snapshot after              # copies dist/ to .bench/builds/after
python3 benchmark/waterfall/waterfall.py prepare-db --build after --mirror-prod
python3 benchmark/waterfall/waterfall.py run after --latency 20
python3 benchmark/waterfall/waterfall.py report .bench/results/after-prod-L20.json --waterfall --accept browser
```

To compare two versions, `snapshot` each build under its own name, `run` both
and check the rendered HTML with
`waterfall.py diff .bench/results/before-prod-L20.json .bench/results/after-prod-L20.json`.

- **`--latency 20`** matches production: local SQLite adds about 5 ms per
  query, so `run before --latency 20` reproduces production's `render` time
  within a few percent.
- **`--mirror-prod`** copies production's public content tables into the local
  database with read-only `SELECT`s (`wrangler d1 execute --remote`). Query
  counts depend on data, so the seed alone undercounts. Secrets in `options`
  are not read; comment authors are anonymized. Without the flag the database
  holds `seed/seed.json` only.
- **`accept`**: `browser` sends `Accept: text/html`, `curl` sends `*/*`.
  EmDash prefetches layout data only for the former.
- **`pre` / `body`**: whether a query finished before the response headers
  (what `Server-Timing` reports) or while the body streamed.

Everything is written to `.bench/` (gitignored). Requests run one at a time,
because the wrapper attributes each D1 call to the request in flight.
