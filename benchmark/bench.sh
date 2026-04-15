c#!/bin/bash
#
# EmDash vs WordPress — TTFB Benchmark
#
# Measures connection time + server TTFB for matching pages on both sites.
# Designed to run via cron every 10 minutes.
#
# Usage:
#   bash benchmark/bench.sh              # single run
#   crontab: */10 * * * * cd /path/to/emdash-cms-pl && bash benchmark/bench.sh
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$SCRIPT_DIR/results.csv"
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

# Create CSV header if file doesn't exist
if [ ! -f "$LOG" ]; then
  echo "timestamp,site,page,url,dns_ms,tcp_ms,ssl_ms,server_ms,ttfb_ms,total_ms,status,size_bytes" > "$LOG"
fi

# ── URLs ──────────────────────────────────────────────────
# Format: site|page_label|url
URLS=(
  "cf|home|https://emdashcms.pl/"
  "wp|home|https://emdash.pl/"
  "cf|co-to-jest-emdash-cms|https://emdashcms.pl/posts/co-to-jest-emdash-cms"
  "wp|co-to-jest-emdash-cms|https://emdash.pl/co-to-jest-emdash-cms/"
  "cf|emdash-vs-wordpress|https://emdashcms.pl/posts/emdash-vs-wordpress"
  "wp|emdash-vs-wordpress|https://emdash.pl/emdash-vs-wordpress/"
  "cf|jak-zainstalowac|https://emdashcms.pl/posts/jak-zainstalowac-emdash-cms"
  "wp|jak-zainstalowac|https://emdash.pl/jak-zainstalowac-emdash-cms/"
  "cf|bezpieczenstwo|https://emdashcms.pl/posts/bezpieczenstwo-wtyczek-emdash"
  "wp|bezpieczenstwo|https://emdash.pl/bezpieczenstwo-wtyczek-emdash/"
  "cf|serverless|https://emdashcms.pl/posts/emdash-serverless-cloudflare-workers"
  "wp|serverless|https://emdash.pl/emdash-serverless-cloudflare-workers/"
  "cf|migracja|https://emdashcms.pl/posts/migracja-z-wordpress-do-emdash"
  "wp|migracja|https://emdash.pl/migracja-z-wordpress-do-emdash/"
  "cf|open-source|https://emdashcms.pl/posts/emdash-open-source-licencja-mit"
  "wp|open-source|https://emdash.pl/emdash-open-source-licencja-mit/"
  "cf|wtyczki|https://emdashcms.pl/posts/wtyczki-emdash-cms"
  "wp|wtyczki|https://emdash.pl/wtyczki-emdash-cms/"
  "cf|ai|https://emdashcms.pl/posts/emdash-sztuczna-inteligencja-ai"
  "wp|ai|https://emdash.pl/emdash-sztuczna-inteligencja-ai/"
  "cf|monetyzacja|https://emdashcms.pl/posts/monetyzacja-tresci-x402-emdash"
  "wp|monetyzacja|https://emdash.pl/monetyzacja-tresci-x402-emdash/"
  "cf|architektura|https://emdashcms.pl/posts/architektura-emdash-typescript-astro"
  "wp|architektura|https://emdash.pl/architektura-emdash-typescript-astro/"
  "cf|przyszlosc|https://emdashcms.pl/posts/przyszlosc-cms-emdash"
  "wp|przyszlosc|https://emdash.pl/przyszlosc-cms-emdash/"
)

# ── Randomize order ───────────────────────────────────────
# Shuffle to avoid systematic bias (DNS cache, ordering effects)
# Works on both Linux (sort -R) and macOS (awk fallback)
if sort -R /dev/null 2>/dev/null; then
  SHUFFLED=($(for i in $(seq 0 $((${#URLS[@]} - 1))); do echo "$i"; done | sort -R))
else
  SHUFFLED=($(for i in $(seq 0 $((${#URLS[@]} - 1))); do echo "$RANDOM $i"; done | sort -n | awk '{print $2}'))
fi

# ── curl format ───────────────────────────────────────────
# All times in seconds from curl, we convert to ms
CURL_FMT='%{time_namelookup}\t%{time_connect}\t%{time_appconnect}\t%{time_starttransfer}\t%{time_total}\t%{http_code}\t%{size_download}'

# ── Run measurements ──────────────────────────────────────
for idx in "${SHUFFLED[@]}"; do
  entry="${URLS[$idx]}"
  IFS='|' read -r site page url <<< "$entry"

  # Fresh curl: no keepalive, no cache, follow redirects, timeout 15s
  result=$(curl -s -o /dev/null -w "$CURL_FMT" \
    --max-time 15 \
    --no-keepalive \
    -H "Cache-Control: no-cache" \
    -H "User-Agent: emdash-bench/1.0" \
    -L "$url" 2>/dev/null) || result="0\t0\t0\t0\t0\t0\t0"

  # Parse curl output
  IFS=$'\t' read -r dns connect appconnect starttransfer total status size <<< "$result"

  # Convert to milliseconds (multiply by 1000), compute breakdowns
  dns_ms=$(echo "$dns * 1000" | bc)
  tcp_ms=$(echo "($connect - $dns) * 1000" | bc)
  ssl_ms=$(echo "($appconnect - $connect) * 1000" | bc)
  server_ms=$(echo "($starttransfer - $appconnect) * 1000" | bc)
  ttfb_ms=$(echo "$starttransfer * 1000" | bc)
  total_ms=$(echo "$total * 1000" | bc)

  # Append to CSV
  echo "$TIMESTAMP,$site,$page,$url,$dns_ms,$tcp_ms,$ssl_ms,$server_ms,$ttfb_ms,$total_ms,$status,$size" >> "$LOG"
done

echo "[$TIMESTAMP] Measured ${#URLS[@]} URLs → $LOG"
