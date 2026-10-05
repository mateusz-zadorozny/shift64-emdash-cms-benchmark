#!/usr/bin/env python3
"""Local D1 query waterfall for the built site (issue #11).

Runs a production build under `wrangler dev` (local D1, Miniflare) with
bench-entry.mjs in front of it. The wrapper delays every D1 call by a fixed
latency and records when each one starts and ends, so you see the request's
real query waterfall: which queries run one after another, which overlap, and
which run after the response headers (Server-Timing can't show those).

    npm run build && python3 benchmark/waterfall/waterfall.py snapshot main
    python3 benchmark/waterfall/waterfall.py prepare-db --build main [--mirror-prod]
    python3 benchmark/waterfall/waterfall.py run main --latency 20
    python3 benchmark/waterfall/waterfall.py report .bench/results/main-*.json --waterfall
    python3 benchmark/waterfall/waterfall.py diff .bench/results/a.json .bench/results/b.json

Everything lives in .bench/ (gitignored). The wrangler.jsonc bindings point at
production, but `wrangler dev` without --remote only touches local copies.

--mirror-prod copies production's public content tables into the local
database (read-only SELECTs via `wrangler d1 execute --remote`), so query
counts match production: they depend on data, e.g. a post with an author but
no byline credit costs two extra queries. Secrets in `options` are not read
and comment authors are anonymized.
"""
import argparse, json, os, re, shutil, signal, sqlite3, statistics, subprocess, sys, time, uuid
import difflib, urllib.error, urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORK = REPO / ".bench"
PAGES = ["/", "/posts/", "/posts/architektura-emdash-typescript-astro", "/category/technologia"]
ACCEPT = {
    "browser": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "curl": "*/*",
}
MIRROR_TABLES = [
    "ec_posts", "ec_pages", "media", "_emdash_bylines", "_emdash_content_bylines",
    "taxonomies", "content_taxonomies", "_emdash_taxonomy_defs", "_emdash_collections",
    "_emdash_fields", "_emdash_menus", "_emdash_menu_items", "_emdash_widget_areas",
    "_emdash_widgets", "_emdash_sections", "_emdash_comments", "_plugin_state", "_emdash_seo",
]
PUBLIC_OPTIONS = ["site:title", "site:tagline", "emdash:site_url", "byline_fields_version",
                  "emdash:setup_complete", "emdash:seed_complete"]


# --- server -------------------------------------------------------------------

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def get(url, headers=None, timeout=60):
    try:
        with OPENER.open(urllib.request.Request(url, headers=headers or {}), timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class Server:
    """`wrangler dev` for a snapshot, with its own copy of a database state."""

    def __init__(self, build, state, latency, port=8799):
        self.base = f"http://127.0.0.1:{port}"
        config = WORK / "builds" / build / "dist" / "server" / "wrangler.bench.json"
        if not config.exists():
            sys.exit(f"no snapshot '{build}' — run: waterfall.py snapshot {build}")
        self.log = open(WORK / "wrangler.log", "w")
        self.proc = subprocess.Popen(
            [str(REPO / "node_modules" / ".bin" / "wrangler"), "dev", "-c", str(config),
             "--persist-to", str(state), "--port", str(port), "--ip", "127.0.0.1",
             "--var", f"BENCH_D1_LATENCY_MS:{latency}", "--show-interactive-dev-session=false"],
            cwd=REPO, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True,
        )

    def __enter__(self):
        for _ in range(240):
            try:
                get(self.base + "/favicon.svg", timeout=2)
                return self
            except Exception:
                time.sleep(0.5)
        self.__exit__()
        sys.exit(f"wrangler dev did not start, see {self.log.name}")

    def __exit__(self, *exc):
        os.killpg(self.proc.pid, signal.SIGTERM)
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(self.proc.pid, signal.SIGKILL)


def sqlite_file(state):
    files = [p for p in (state / "v3" / "d1" / "miniflare-D1DatabaseObject").glob("*.sqlite")
             if p.name != "metadata.sqlite"]
    if len(files) != 1:
        sys.exit(f"expected one D1 file in {state}, found {files}")
    return files[0]


# --- commands -------------------------------------------------------------------

def cmd_snapshot(a):
    """Copy the current dist/ (run `npm run build` first) and wire the wrapper."""
    dest = WORK / "builds" / a.name
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(REPO / "dist", dest / "dist")
    server = dest / "dist" / "server"
    shutil.copy(HERE / "bench-entry.mjs", server / "bench-entry.mjs")
    config = json.loads((server / "wrangler.json").read_text())
    for key in ("configPath", "userConfigPath", "topLevelName", "definedEnvironments",
                "routes", "triggers", "placement"):
        config.pop(key, None)
    config.update(main="bench-entry.mjs", name="emdash-bench", vars={})
    (server / "wrangler.bench.json").write_text(json.dumps(config, indent=1))
    print(f"snapshot {a.name} -> {dest}")


def cmd_prepare_db(a):
    """Fresh local D1: migrate, apply seed/seed.json, optionally mirror production."""
    state = WORK / ("state-prod" if a.mirror_prod else "state-seed")
    shutil.rmtree(state, ignore_errors=True)
    with Server(a.build, state, latency=0) as server:
        get(server.base + "/")  # first request runs EmDash's migrations
    db = sqlite_file(state)
    subprocess.run(["npx", "emdash", "seed", "seed/seed.json", "-d", str(db), "--on-conflict", "update"],
                   cwd=REPO, check=True)
    if a.mirror_prod:
        mirror_prod(db)
    print(f"database ready: {state}")


def remote_select(sql):
    out = subprocess.run(
        ["npx", "wrangler", "d1", "execute", "emdash-cms-pl", "--remote", "--json", "--command", sql],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)[0]["results"]


def mirror_prod(db_path):
    db = sqlite3.connect(db_path)
    for table in MIRROR_TABLES:
        rows = remote_select(f"SELECT * FROM {table}")
        if table == "_emdash_comments":
            for r in rows:
                for col, value in (("author_email", "anon@example.com"), ("ip_hash", "anon"),
                                   ("user_agent", "anon")):
                    if r.get(col) is not None:
                        r[col] = value
        db.execute(f"DELETE FROM {table}")
        for r in rows:
            cols = ", ".join(f'"{c}"' for c in r)
            db.execute(f"INSERT INTO {table} ({cols}) VALUES ({', '.join('?' * len(r))})", list(r.values()))
        print(f"  {table}: {len(rows)} rows")
    names = ", ".join(f"'{n}'" for n in PUBLIC_OPTIONS)
    for r in remote_select(f"SELECT name, value FROM options WHERE name IN ({names})"):
        db.execute("INSERT OR REPLACE INTO options (name, value) VALUES (?, ?)", (r["name"], r["value"]))
    db.commit()
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def cmd_run(a):
    """Request each page (unique ?nc= per request) and save the waterfall reports."""
    template = WORK / f"state-{a.db}"
    if not template.exists():
        sys.exit(f"no {template.name} — run: waterfall.py prepare-db --build {a.build}"
                 + (" --mirror-prod" if a.db == "prod" else ""))
    state = WORK / "state-run"
    shutil.rmtree(state, ignore_errors=True)
    shutil.copytree(template, state)
    accepts = list(ACCEPT) if a.accept == "both" else [a.accept]
    results = []
    with Server(a.build, state, latency=a.latency) as server:
        for accept in accepts:
            for page in a.pages.split(","):
                for i in range(a.warmup + a.rounds):
                    rid = uuid.uuid4().hex
                    sep = "&" if "?" in page else "?"
                    status, body = get(f"{server.base}{page}{sep}nc={rid}",
                                       {"x-bench-id": rid, "Accept": ACCEPT[accept]})
                    for _ in range(100):
                        code, raw = get(f"{server.base}/__waterfall/{rid}", timeout=5)
                        if code == 200:
                            break
                        time.sleep(0.05)
                    else:
                        sys.exit(f"no report for {page}")
                    report = json.loads(raw)
                    report.update(build=a.build, accept=accept, page=page,
                                  warmup=i < a.warmup, latency=a.latency)
                    if i == a.warmup:
                        report["html"] = body.decode("utf-8", "replace")
                    results.append(report)
    out = WORK / "results" / f"{a.build}-{a.db}-L{a.latency}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=1))
    print(out)
    report_table(results)


def phase(e, r):
    if e["end"] <= r["tHeaders"] + 0.5:
        return "pre"
    return "body" if e["end"] <= r["tBodyEnd"] + 0.5 else "late"


def report_table(results):
    groups = defaultdict(list)
    for r in results:
        if not r["warmup"]:
            groups[(r["build"], r["accept"], r["page"])].append(r)
    print(f"{'build':<14} {'accept':<8} {'page':<45} {'D1 calls pre/body':>17} "
          f"{'queries':>7} {'headers ms':>10} {'body end ms':>11}")
    for (build, accept, page), rs in sorted(groups.items()):
        med = lambda f: statistics.median(f(r) for r in rs)
        pre = med(lambda r: sum(phase(e, r) == "pre" for e in r["events"]))
        body = med(lambda r: sum(phase(e, r) == "body" for e in r["events"]))
        stmts = med(lambda r: sum(len(e["sql"]) if e["kind"] == "batch" else 1
                                  for e in r["events"] if phase(e, r) != "late"))
        print(f"{build:<14} {accept:<8} {page:<45} {pre:>9.0f} / {body:<5.0f} {stmts:>7.0f} "
              f"{med(lambda r: r['tHeaders']):>10.0f} {med(lambda r: r['tBodyEnd']):>11.0f}")


def short_sql(sql, width):
    if isinstance(sql, list):
        return f"BATCH[{len(sql)}] " + " || ".join(short_sql(s, 40) for s in sql)
    s = re.sub(r"\s+", " ", sql or "").strip()
    return s if len(s) <= width else s[: width - 1] + "…"


def cmd_report(a):
    results = [r for f in a.files for r in json.loads(Path(f).read_text())]
    report_table(results)
    if not a.waterfall:
        return
    last = {}
    for r in results:
        if not r["warmup"]:
            last[(r["build"], r["accept"], r["page"])] = r
    for (build, accept, page), r in sorted(last.items()):
        if (a.page and page != a.page) or (a.accept and accept != a.accept):
            continue
        print(f"\n{build} | {accept} | {page} | headers {r['tHeaders']:.0f} ms, "
              f"body end {r['tBodyEnd']:.0f} ms")
        for i, e in enumerate(sorted(r["events"], key=lambda e: (e["start"], e["end"])), 1):
            params = str(e.get("params") or "")[:60]
            print(f"{i:>3} {phase(e, r):<4} {e['start']:>5.0f}→{e['end']:>5.0f}  "
                  f"{short_sql(e['sql'], 100)}  {params}")


def normalize_html(html):
    """Drop what differs between any two renders: timing comment, cache-buster,
    server-island tokens/ids, stylesheet tags (order depends on chunking)."""
    html = re.sub(r"<!-- timings:.*?-->", "", html)
    html = re.sub(r"nc=[0-9a-f]{32}", "nc=X", html)
    html = re.sub(r"(_server-islands/\w+)\?e=[^\"']*", r"\1?X", html)
    html = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "UUID", html)
    html = re.sub(r"<lastBuildDate>.*?</lastBuildDate>", "", html)
    return re.sub(r'<link rel="stylesheet"[^>]*>|<style>.*?</style>', "", html, flags=re.S)


def cmd_diff(a):
    """Compare the HTML saved by two runs, page by page."""
    load = lambda f: {(r["accept"], r["page"]): r["html"]
                      for r in json.loads(Path(f).read_text()) if r.get("html") is not None}
    before, after = load(a.before), load(a.after)
    changed = 0
    for key in sorted(before.keys() & after.keys()):
        diff = list(difflib.unified_diff(normalize_html(before[key]).splitlines(),
                                         normalize_html(after[key]).splitlines(), lineterm="", n=0))
        changed += bool(diff)
        print(f"{key[0]:<8} {key[1]:<45} {'identical' if not diff else f'{len(diff)} diff lines'}")
        for line in diff[:6]:
            print("   ", line[:200])
    sys.exit(1 if changed else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("snapshot")
    p.add_argument("name")
    p.set_defaults(fn=cmd_snapshot)
    p = sub.add_parser("prepare-db")
    p.add_argument("--build", required=True, help="snapshot used to run the migrations")
    p.add_argument("--mirror-prod", action="store_true")
    p.set_defaults(fn=cmd_prepare_db)
    p = sub.add_parser("run")
    p.add_argument("build")
    p.add_argument("--db", choices=["seed", "prod"], default="prod")
    p.add_argument("--latency", type=int, default=20, help="ms added to each D1 call")
    p.add_argument("--rounds", type=int, default=5)
    p.add_argument("--warmup", type=int, default=2)
    p.add_argument("--accept", choices=[*ACCEPT, "both"], default="both")
    p.add_argument("--pages", default=",".join(PAGES))
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("report")
    p.add_argument("files", nargs="+")
    p.add_argument("--waterfall", action="store_true")
    p.add_argument("--page")
    p.add_argument("--accept")
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("diff")
    p.add_argument("before")
    p.add_argument("after")
    p.set_defaults(fn=cmd_diff)
    a = ap.parse_args()
    WORK.mkdir(exist_ok=True)
    a.fn(a)


if __name__ == "__main__":
    main()
