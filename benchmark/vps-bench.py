#!/usr/bin/env python3
"""EmDash vs WordPress, round two (October 2026), from the OVH VPS in Warsaw.

Same pages and curl method as April's bench.sh (homepage + 12 posts, a new
curl process per URL, no keepalive), with:

- three sites: cf = emdashcms.pl (page cache, PR #16), kv = kv.emdashcms.pl
  (EmDash's KV object cache, branch exp/kv-object-cache), wp = emdash.pl
- two arms: "uncached" adds a unique ?nc= so no cache layer can answer;
  "served" is the plain URL, as a visitor gets it
- the response headers that say what happened: Cloudflare colo and placement,
  X-Cache, cf-cache-status, and EmDash's Server-Timing (render, db.*)
- 1.5 s between requests and a one-hour pause after three errors from an
  EmDash site in one run: the Workers Free plan allows 10 ms of CPU per
  request, and sustained uncached load gets requests killed with 503s

One run = every site x page x arm in random order (78 requests, ~2.5 min).
Cron runs it every 15 minutes; it stops by itself at END.

    python3 vps-bench.py            # one run, appends to results.csv
    python3 vps-bench.py --dry-run  # print the plan, send nothing
"""
import csv
import os
import random
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results.csv")
PAUSE_FILE = os.path.join(HERE, "pause-until")
END = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)  # Friday 20:00 in Warsaw
GAP_S = 1.5
PAUSE_S = 3600
MAX_ERRORS = 3

SITES = {
    "cf": "https://emdashcms.pl",
    "kv": "https://kv.emdashcms.pl",
    "wp": "https://emdash.pl",
}
# April's pages: label -> (EmDash path, WordPress path)
PAGES = {
    "home": ("/", "/"),
    "co-to-jest-emdash-cms": ("/posts/co-to-jest-emdash-cms", "/co-to-jest-emdash-cms/"),
    "emdash-vs-wordpress": ("/posts/emdash-vs-wordpress", "/emdash-vs-wordpress/"),
    "jak-zainstalowac": ("/posts/jak-zainstalowac-emdash-cms", "/jak-zainstalowac-emdash-cms/"),
    "bezpieczenstwo": ("/posts/bezpieczenstwo-wtyczek-emdash", "/bezpieczenstwo-wtyczek-emdash/"),
    "serverless": ("/posts/emdash-serverless-cloudflare-workers", "/emdash-serverless-cloudflare-workers/"),
    "migracja": ("/posts/migracja-z-wordpress-do-emdash", "/migracja-z-wordpress-do-emdash/"),
    "open-source": ("/posts/emdash-open-source-licencja-mit", "/emdash-open-source-licencja-mit/"),
    "wtyczki": ("/posts/wtyczki-emdash-cms", "/wtyczki-emdash-cms/"),
    "ai": ("/posts/emdash-sztuczna-inteligencja-ai", "/emdash-sztuczna-inteligencja-ai/"),
    "monetyzacja": ("/posts/monetyzacja-tresci-x402-emdash", "/monetyzacja-tresci-x402-emdash/"),
    "architektura": ("/posts/architektura-emdash-typescript-astro", "/architektura-emdash-typescript-astro/"),
    "przyszlosc": ("/posts/przyszlosc-cms-emdash", "/przyszlosc-cms-emdash/"),
}
ARMS = ("uncached", "served")

FIELDS = [
    "run", "seq", "time", "arm", "site", "page", "url", "status", "size",
    "dns_ms", "tcp_ms", "ssl_ms", "server_ms", "ttfb_ms", "total_ms",
    "colo", "placement", "x_cache", "cf_cache_status", "age",
    "render", "db_count", "db_total", "db_last", "server_timing",
]
CURL_FMT = "\n__T__%{time_namelookup}\t%{time_connect}\t%{time_appconnect}\t%{time_starttransfer}\t%{time_total}\t%{http_code}\t%{size_download}"


def server_timing(values):
    """Every Server-Timing entry as {name: dur}."""
    out = {}
    for value in values:
        for part in value.split(","):
            m = re.match(r"\s*([^;\s]+)(?:;dur=([\d.]+))?", part)
            if m and m.group(2) is not None:
                out[m.group(1)] = float(m.group(2))
    return out


def measure(url):
    # April's request: a new process, no keepalive, follow redirects
    proc = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-D", "-", "--max-time", "20", "--no-keepalive", "-L",
         "-H", "Cache-Control: no-cache", "-H", "User-Agent: emdash-bench/2.0", "-w", CURL_FMT, url],
        capture_output=True, text=True,
    )
    head, _, timing = proc.stdout.rpartition("\n__T__")
    headers, timings = {}, []
    for line in head.splitlines():  # with -L, the last response's headers win
        name, sep, value = line.partition(":")
        if not sep:
            continue
        name = name.strip().lower()
        if name == "server-timing":
            timings.append(value.strip())
        headers[name] = value.strip()
    try:
        dns, connect, appconnect, start, total, status, size = timing.split("\t")
    except ValueError:
        dns = connect = appconnect = start = total = "0"
        status, size = "000", "0"
    ms = lambda s: round(float(s) * 1000, 1)
    st = server_timing(timings)
    return {
        "status": status, "size": size,
        "dns_ms": ms(dns), "tcp_ms": round(ms(connect) - ms(dns), 1),
        "ssl_ms": round(ms(appconnect) - ms(connect), 1),
        "server_ms": round(ms(start) - ms(appconnect), 1),
        "ttfb_ms": ms(start), "total_ms": ms(total),
        "colo": headers.get("cf-ray", "").rpartition("-")[2],
        "placement": headers.get("cf-placement", ""),
        "x_cache": headers.get("x-cache", ""),
        "cf_cache_status": headers.get("cf-cache-status", ""),
        "age": headers.get("age", ""),
        "render": st.get("render", ""), "db_count": st.get("db.count", ""),
        "db_total": st.get("db.total", ""), "db_last": st.get("db.last", ""),
        "server_timing": ", ".join(timings)[:500],
    }


def plan():
    jobs = []
    for site, base in SITES.items():
        for label, (emdash_path, wp_path) in PAGES.items():
            path = wp_path if site == "wp" else emdash_path
            for arm in ARMS:
                url = base + path
                if arm == "uncached":
                    url += f"?nc={uuid.uuid4().hex}"
                jobs.append((arm, site, label, url))
    random.shuffle(jobs)
    return jobs


def main():
    now = datetime.now(timezone.utc)
    if now >= END:
        print(f"[{now:%FT%TZ}] past {END:%FT%TZ}, not measuring")
        return
    try:
        if time.time() < float(open(PAUSE_FILE).read()):
            print(f"[{now:%FT%TZ}] paused after errors, skipping this run")
            return
    except (OSError, ValueError):
        pass
    jobs = plan()
    if "--dry-run" in sys.argv:
        for job in jobs:
            print(*job)
        return
    run = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    new_file = not os.path.exists(RESULTS)
    errors = {"cf": 0, "kv": 0}
    with open(RESULTS, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        for seq, (arm, site, label, url) in enumerate(jobs):
            row = measure(url)
            row.update(run=run, seq=seq, arm=arm, site=site, page=label, url=url,
                       time=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            writer.writerow(row)
            f.flush()
            if site in errors and row["status"] != "200":
                errors[site] += 1
                if errors[site] >= MAX_ERRORS:
                    open(PAUSE_FILE, "w").write(str(time.time() + PAUSE_S))
                    print(f"[{run}] {MAX_ERRORS} errors from {site}: stopping this run, pausing an hour")
                    return
            time.sleep(GAP_S)
    print(f"[{run}] measured {len(jobs)} URLs, errors {errors}")


if __name__ == "__main__":
    main()
