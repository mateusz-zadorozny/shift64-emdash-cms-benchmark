#!/usr/bin/env python3
"""
EmDash vs WordPress — TTFB Benchmark Analysis

Reads results.csv and produces:
- Mean, median, stddev, min, max, P95, P99 for server_ms and ttfb_ms
- Per-page comparison
- Consistency score (coefficient of variation)

Usage:
  python3 benchmark/analyze.py                          # local results.csv
  python3 benchmark/analyze.py /root/results.csv        # custom path
"""

import csv
import sys
import math
from collections import defaultdict

def percentile(data, p):
    """Calculate p-th percentile (0-100)."""
    if not data:
        return 0
    s = sorted(data)
    k = (len(s) - 1) * p / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)

def stddev(data):
    """Standard deviation."""
    if len(data) < 2:
        return 0
    mean = sum(data) / len(data)
    return math.sqrt(sum((x - mean) ** 2 for x in data) / (len(data) - 1))

def stats(data):
    """Return dict of statistics."""
    if not data:
        return {}
    return {
        'n': len(data),
        'mean': sum(data) / len(data),
        'median': percentile(data, 50),
        'stddev': stddev(data),
        'min': min(data),
        'max': max(data),
        'p95': percentile(data, 95),
        'p99': percentile(data, 99),
        'cv': (stddev(data) / (sum(data) / len(data)) * 100) if sum(data) > 0 else 0,
    }

def fmt(val, suffix='ms'):
    """Format number."""
    return f"{val:.0f}{suffix}"

# ── Load data ─────────────────────────────────────────────
csv_path = sys.argv[1] if len(sys.argv) > 1 else 'benchmark/results.csv'

rows = []
with open(csv_path) as f:
    reader = csv.DictReader(f)
    for row in reader:
        row['server_ms'] = float(row['server_ms'])
        row['ttfb_ms'] = float(row['ttfb_ms'])
        row['total_ms'] = float(row['total_ms'])
        row['dns_ms'] = float(row['dns_ms'])
        row['tcp_ms'] = float(row['tcp_ms'])
        row['ssl_ms'] = float(row['ssl_ms'])
        rows.append(row)

if not rows:
    print("No data found.")
    sys.exit(1)

# ── Group by site ─────────────────────────────────────────
by_site = defaultdict(list)
by_site_page = defaultdict(lambda: defaultdict(list))

for r in rows:
    by_site[r['site']].append(r)
    by_site_page[r['site']][r['page']].append(r)

# Count unique timestamps (runs)
runs = len(set(r['timestamp'] for r in rows))
time_range = sorted(set(r['timestamp'] for r in rows))

print("=" * 70)
print("  EmDash (CF Workers) vs WordPress — TTFB Benchmark")
print("=" * 70)
print(f"  Data:  {csv_path}")
print(f"  Runs:  {runs} ({time_range[0]} → {time_range[-1]})")
print(f"  Total: {len(rows)} measurements")
print()

# ── Overall comparison ────────────────────────────────────
print("─" * 70)
print("  OVERALL: Server Processing Time (server_ms)")
print("  = TTFB minus DNS/TCP/SSL — pure server work")
print("─" * 70)
print()
print(f"  {'':20s} {'CF (EmDash)':>14s}  {'WP':>14s}  {'Δ':>10s}")
print(f"  {'':20s} {'─'*14:>14s}  {'─'*14:>14s}  {'─'*10:>10s}")

cf_server = [r['server_ms'] for r in by_site.get('cf', [])]
wp_server = [r['server_ms'] for r in by_site.get('wp', [])]
cf_s = stats(cf_server)
wp_s = stats(wp_server)

for label, key in [('Samples', 'n'), ('Mean', 'mean'), ('Median', 'median'),
                    ('Std Dev', 'stddev'), ('Min', 'min'), ('Max', 'max'),
                    ('P95', 'p95'), ('P99', 'p99'), ('CV (consistency)', 'cv')]:
    cf_val = cf_s.get(key, 0)
    wp_val = wp_s.get(key, 0)
    if key == 'n':
        print(f"  {label:20s} {cf_val:>14d}  {wp_val:>14d}")
    elif key == 'cv':
        print(f"  {label:20s} {cf_val:>13.1f}%  {wp_val:>13.1f}%")
    else:
        diff = cf_val - wp_val
        sign = '+' if diff > 0 else ''
        print(f"  {label:20s} {fmt(cf_val):>14s}  {fmt(wp_val):>14s}  {sign}{diff:>.0f}ms")

print()

# ── Total TTFB (what the user sees) ───────────────────────
print("─" * 70)
print("  OVERALL: Total TTFB (ttfb_ms)")
print("  = DNS + TCP + SSL + Server — what the user actually waits for")
print("─" * 70)
print()

cf_ttfb = [r['ttfb_ms'] for r in by_site.get('cf', [])]
wp_ttfb = [r['ttfb_ms'] for r in by_site.get('wp', [])]
cf_t = stats(cf_ttfb)
wp_t = stats(wp_ttfb)

print(f"  {'':20s} {'CF (EmDash)':>14s}  {'WP':>14s}  {'Δ':>10s}")
print(f"  {'':20s} {'─'*14:>14s}  {'─'*14:>14s}  {'─'*10:>10s}")

for label, key in [('Mean', 'mean'), ('Median', 'median'), ('Std Dev', 'stddev'),
                    ('Min', 'min'), ('Max', 'max'), ('P95', 'p95'), ('CV', 'cv')]:
    cf_val = cf_t.get(key, 0)
    wp_val = wp_t.get(key, 0)
    if key == 'cv':
        print(f"  {label:20s} {cf_val:>13.1f}%  {wp_val:>13.1f}%")
    else:
        diff = cf_val - wp_val
        sign = '+' if diff > 0 else ''
        print(f"  {label:20s} {fmt(cf_val):>14s}  {fmt(wp_val):>14s}  {sign}{diff:>.0f}ms")

print()

# ── Network breakdown ─────────────────────────────────────
print("─" * 70)
print("  NETWORK BREAKDOWN (averages)")
print("─" * 70)
print()

for metric, label in [('dns_ms', 'DNS'), ('tcp_ms', 'TCP'), ('ssl_ms', 'SSL'), ('server_ms', 'Server')]:
    cf_vals = [r[metric] for r in by_site.get('cf', [])]
    wp_vals = [r[metric] for r in by_site.get('wp', [])]
    cf_avg = sum(cf_vals) / len(cf_vals) if cf_vals else 0
    wp_avg = sum(wp_vals) / len(wp_vals) if wp_vals else 0
    print(f"  {label:10s}  CF: {fmt(cf_avg):>8s}   WP: {fmt(wp_avg):>8s}")

print()

# ── Per-page comparison ───────────────────────────────────
print("─" * 70)
print("  PER-PAGE: Server Processing Time (mean)")
print("─" * 70)
print()
print(f"  {'Page':24s} {'CF':>8s} {'WP':>8s} {'Δ':>8s} {'Winner':>8s}")
print(f"  {'─'*24:24s} {'─'*8:>8s} {'─'*8:>8s} {'─'*8:>8s} {'─'*8:>8s}")

pages = sorted(set(r['page'] for r in rows))
cf_wins = 0
wp_wins = 0

for page in pages:
    cf_vals = [r['server_ms'] for r in by_site_page.get('cf', {}).get(page, [])]
    wp_vals = [r['server_ms'] for r in by_site_page.get('wp', {}).get(page, [])]
    cf_avg = sum(cf_vals) / len(cf_vals) if cf_vals else 0
    wp_avg = sum(wp_vals) / len(wp_vals) if wp_vals else 0
    diff = cf_avg - wp_avg
    winner = 'CF' if diff < 0 else 'WP'
    if diff < 0:
        cf_wins += 1
    else:
        wp_wins += 1
    sign = '+' if diff > 0 else ''
    print(f"  {page:24s} {fmt(cf_avg):>8s} {fmt(wp_avg):>8s} {sign}{diff:>+7.0f}ms {'◀' if winner == 'CF' else '':>3s}{'◀' if winner == 'WP' else '':>5s}")

print()
print(f"  Score: CF wins {cf_wins}/{len(pages)} pages, WP wins {wp_wins}/{len(pages)} pages")
print()

# ── Consistency analysis ──────────────────────────────────
print("─" * 70)
print("  CONSISTENCY (Coefficient of Variation)")
print("  Lower = more predictable. CV > 50% = highly variable")
print("─" * 70)
print()
print(f"  CF server_ms CV:  {cf_s['cv']:.1f}%  ({'stable' if cf_s['cv'] < 30 else 'variable' if cf_s['cv'] < 60 else 'HIGHLY variable'})")
print(f"  WP server_ms CV:  {wp_s['cv']:.1f}%  ({'stable' if wp_s['cv'] < 30 else 'variable' if wp_s['cv'] < 60 else 'HIGHLY variable'})")
print(f"  CF ttfb_ms CV:    {cf_t['cv']:.1f}%  ({'stable' if cf_t['cv'] < 30 else 'variable' if cf_t['cv'] < 60 else 'HIGHLY variable'})")
print(f"  WP ttfb_ms CV:    {wp_t['cv']:.1f}%  ({'stable' if wp_t['cv'] < 30 else 'variable' if wp_t['cv'] < 60 else 'HIGHLY variable'})")
print()

# ── Verdict ───────────────────────────────────────────────
print("=" * 70)
print("  VERDICT (based on current data)")
print("=" * 70)
print()

faster = 'WP' if wp_s['mean'] < cf_s['mean'] else 'CF'
speed_diff = abs(cf_s['mean'] - wp_s['mean'])
more_consistent = 'WP' if wp_s['cv'] < cf_s['cv'] else 'CF'

print(f"  Faster server:      {faster} (by {speed_diff:.0f}ms avg)")
print(f"  More consistent:    {more_consistent} (CV: {min(cf_s['cv'], wp_s['cv']):.1f}% vs {max(cf_s['cv'], wp_s['cv']):.1f}%)")
print(f"  CF max spike:       {cf_s['max']:.0f}ms  (vs WP max: {wp_s['max']:.0f}ms)")
print()

if runs < 10:
    print(f"  ⚠ Only {runs} runs — collect more data for reliable conclusions.")
    print(f"    At */10 cron: ~24h = 144 runs = {144*26} measurements")
print()
