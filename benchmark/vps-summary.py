#!/usr/bin/env python3
"""Summarize vps-bench.py's results.csv: per site and arm, the request
count, errors, server time (TTFB minus DNS/TCP/TLS, April's metric), TTFB,
EmDash render time, query count, and what answered (cache status, colo).

    python3 vps-summary.py [results.csv] [--since 2026-10-06T12:00:00Z]
"""
import collections
import csv
import statistics
import sys


def pct(values, p):
    values = sorted(values)
    if not values:
        return float("nan")
    k = (len(values) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def main():
    args = sys.argv[1:]
    since = ""
    if "--since" in args:
        i = args.index("--since")
        since = args[i + 1]
        del args[i:i + 2]
    path = args[0] if args else "results.csv"
    rows = [r for r in csv.DictReader(open(path)) if r["time"] >= since]
    runs = sorted({r["run"] for r in rows})
    print(f"{len(rows)} requests in {len(runs)} runs, {runs[0] if runs else '-'} .. {runs[-1] if runs else '-'}")
    print(f"{'site':4} {'arm':8} {'n':>5} {'err':>4} {'server p50':>10} {'p95':>6} {'TTFB p50':>9} {'p95':>6}"
          f" {'render p50':>10} {'db p50':>6}  answered by")
    for site in ("cf", "kv", "wp"):
        for arm in ("uncached", "served"):
            sel = [r for r in rows if r["site"] == site and r["arm"] == arm]
            ok = [r for r in sel if r["status"] == "200"]
            if not sel:
                continue
            server = [float(r["server_ms"]) for r in ok]
            ttfb = [float(r["ttfb_ms"]) for r in ok]
            render = [float(r["render"]) for r in ok if r["render"]]
            db = [float(r["db_count"]) for r in ok if r["db_count"]]
            answered = collections.Counter(r["x_cache"] or r["cf_cache_status"] or "-" for r in ok)
            print(f"{site:4} {arm:8} {len(sel):5} {len(sel) - len(ok):4} {pct(server, .5):10.1f} {pct(server, .95):6.0f}"
                  f" {pct(ttfb, .5):9.1f} {pct(ttfb, .95):6.0f} {pct(render, .5):10.1f} {pct(db, .5):6.0f}"
                  f"  {dict(answered.most_common(3))}")
    colos = collections.Counter(r["colo"] for r in rows if r["colo"])
    print("colos:", dict(colos.most_common(5)))


if __name__ == "__main__":
    main()
