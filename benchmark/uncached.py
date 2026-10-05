#!/usr/bin/env python3
"""Uncached-hit timing for emdashcms.pl (issue #11).

Fetches each page with a unique `?nc=` value so the edge cache in
src/worker.ts never answers, and records curl timings plus the
Server-Timing fields EmDash and src/middleware.ts emit.

    python3 benchmark/uncached.py --label before --rounds 30
    python3 benchmark/uncached.py --summary benchmark/uncached-before.csv

Each round requests every page once, in shuffled order, each with a fresh
curl process (new TCP + TLS connection), like bench.sh.

--accept browser sends a browser navigation Accept header. EmDash only
prefetches layout data (menus, widgets, taxonomies) when Accept starts with
text/html, so curl's default `*/*` measures a different code path than a
real visitor.
"""
import argparse, csv, os, random, re, statistics, subprocess, sys, time, uuid
from datetime import datetime, timezone

BASE = "https://emdashcms.pl"
PAGES = ["/", "/posts/", "/posts/architektura-emdash-typescript-astro", "/category/technologia"]
ACCEPT = {
    "curl": "*/*",
    "browser": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
CURL_FMT = "%{time_appconnect}\t%{time_starttransfer}\t%{time_total}\t%{http_code}\t%{size_download}"
FIELDS = ["time", "label", "accept", "page", "status", "x_cache", "placement", "colo",
          "appconnect_ms", "ttfb_ms", "total_ms", "server_ms", "bytes",
          "db_count", "db_total", "db_first", "db_last", "render", "cache_hit", "cache_miss",
          "server_timing"]


def server_timing(values):
    """Parse every Server-Timing header into {name: dur}."""
    out = {}
    for value in values:
        for part in value.split(","):
            m = re.match(r"\s*([^;\s]+)(?:;dur=([\d.]+))?", part)
            if m and m.group(2) is not None:
                out[m.group(1)] = float(m.group(2))
    return out


def fetch(base, page, accept):
    sep = "&" if "?" in page else "?"
    url = f"{base}{page}{sep}nc={uuid.uuid4().hex}"
    proc = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-D", "-", "--max-time", "20",
         "-H", f"Accept: {ACCEPT[accept]}", "-H", "User-Agent: emdash-bench/uncached",
         "-w", "\n__TIMING__" + CURL_FMT, url],
        capture_output=True, text=True,
    )
    head, _, timing = proc.stdout.partition("\n__TIMING__")
    headers = {}
    timings = []
    for line in head.splitlines():
        name, sep_, value = line.partition(":")
        if not sep_:
            continue
        name = name.strip().lower()
        value = value.strip()
        if name == "server-timing":
            timings.append(value)
        headers[name] = value
    appconnect, ttfb, total, status, size = (timing.split("\t") + ["0"] * 5)[:5]
    st = server_timing(timings)
    ms = lambda s: round(float(s or 0) * 1000, 1)
    return {
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "page": page,
        "status": status,
        "x_cache": headers.get("x-cache", ""),
        "placement": headers.get("cf-placement", ""),
        "colo": headers.get("cf-ray", "-").split("-")[-1],
        "appconnect_ms": ms(appconnect),
        "ttfb_ms": ms(ttfb),
        "total_ms": ms(total),
        "server_ms": round(ms(ttfb) - ms(appconnect), 1),
        "bytes": size,
        "db_count": st.get("db.count", ""),
        "db_total": st.get("db.total", ""),
        "db_first": st.get("db.first", ""),
        "db_last": st.get("db.last", ""),
        "render": st.get("render", ""),
        "cache_hit": st.get("cache.hit", ""),
        "cache_miss": st.get("cache.miss", ""),
        "server_timing": " | ".join(timings),
    }


def pct(values, p):
    values = sorted(values)
    if not values:
        return float("nan")
    k = (len(values) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def summarize(rows):
    groups = {}
    for r in rows:
        if r["status"] != "200" or r["x_cache"] == "HIT":
            continue
        groups.setdefault((r["label"], r["accept"], r["page"]), []).append(r)
    # db.total sums every query's duration, so it only equals wall time while
    # queries run one after another. db.last (when the last query before the
    # response headers finished) and render are wall-clock.
    print(f"{'label':<10} {'accept':<8} {'page':<45} {'n':>3} {'db.count':>10} "
          f"{'db.total p50/p95':>17} {'db.last p50/p95':>16} {'render p50/p95':>15} "
          f"{'TTFB p50/p95':>13} {'total p50/p95':>14}")
    for (label, accept, page), rs in sorted(groups.items()):
        num = lambda k: [float(r[k]) for r in rs if r[k] not in ("", None)]
        counts = num("db_count")
        cnt = f"{statistics.median(counts):.0f} ({min(counts):.0f}-{max(counts):.0f})" if counts else "-"
        cols = [num(k) for k in ("db_total", "db_last", "render", "ttfb_ms", "total_ms")]
        stats = "".join(f"{pct(c, 50):>9.0f} / {pct(c, 95):>4.0f}" for c in cols)
        print(f"{label:<10} {accept:<8} {page:<45} {len(rs):>3} {cnt:>10}{stats}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="run")
    ap.add_argument("--rounds", type=int, default=30)
    ap.add_argument("--accept", choices=[*ACCEPT, "both"], default="both")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--pages", default=",".join(PAGES))
    ap.add_argument("--out", help="CSV to append to (default benchmark/uncached-<label>.csv)")
    ap.add_argument("--pause", type=float, default=0.2, help="seconds between requests")
    ap.add_argument("--summary", nargs="*", help="only summarize these CSV files")
    a = ap.parse_args()

    if a.summary is not None:
        rows = []
        for path in a.summary:
            with open(path) as f:
                rows += list(csv.DictReader(f))
        summarize(rows)
        return

    out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), f"uncached-{a.label}.csv")
    new = not os.path.exists(out)
    accepts = list(ACCEPT) if a.accept == "both" else [a.accept]
    pages = a.pages.split(",")
    rows = []
    with open(out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for n in range(a.rounds):
            jobs = [(p, acc) for p in pages for acc in accepts]
            random.shuffle(jobs)
            for page, accept in jobs:
                row = fetch(a.base, page, accept)
                row.update(label=a.label, accept=accept)
                w.writerow(row)
                rows.append(row)
                time.sleep(a.pause)
            f.flush()
            print(f"round {n + 1}/{a.rounds}", file=sys.stderr)
    summarize(rows)
    print(f"\nrows appended to {out}")


if __name__ == "__main__":
    main()
