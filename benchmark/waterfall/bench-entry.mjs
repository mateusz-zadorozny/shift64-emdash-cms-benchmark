// Benchmark-only wrapper around the built worker. waterfall.py copies it next
// to dist/server/entry.mjs; it is never deployed.
//
// 1. Delays every physical D1 call (statement all/first/run/raw, batch, exec)
//    by BENCH_D1_LATENCY_MS, so a local run has production-like round trips.
// 2. Records each call's start/end (ms from request start), the SQL and its
//    params, and when the response headers, first chunk and body end happened.
//    Send a request with `x-bench-id: <id>`, then read `/__waterfall/<id>`.
//
// Send requests one at a time: a call is attributed to the request that is
// current when it finishes.

import { env } from "cloudflare:workers";
import worker from "./entry.mjs";
export { PluginBridge } from "./entry.mjs";

const LATENCY = Number(env.BENCH_D1_LATENCY_MS ?? 20);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const now = () => performance.now();

let current = null;
const reports = new Map();

function record(kind, sql, params, start, end) {
	if (!current) return;
	current.events.push({ kind, sql, params, start: start - current.t0, end: end - current.t0 });
}

function patchStatements(proto) {
	for (const method of ["all", "first", "run", "raw"]) {
		const original = proto[method];
		if (typeof original !== "function") continue;
		proto[method] = async function (...args) {
			const start = now();
			await sleep(LATENCY);
			try {
				return await original.apply(this, args);
			} finally {
				record(method, this.statement, this.params, start, now());
			}
		};
	}
}

function patchBatch(proto) {
	const original = proto.batch;
	if (typeof original !== "function") return;
	proto.batch = async function (statements) {
		const start = now();
		await sleep(LATENCY);
		try {
			return await original.call(this, statements);
		} finally {
			record(
				"batch",
				statements.map((s) => s.statement),
				statements.map((s) => s.params),
				start,
				now(),
			);
		}
	};
}

function patchExec(proto) {
	const original = proto.exec;
	if (typeof original !== "function") return;
	proto.exec = async function (sql) {
		const start = now();
		await sleep(LATENCY);
		try {
			return await original.call(this, sql);
		} finally {
			record("exec", sql, [], start, now());
		}
	};
}

// Patch the prototypes, so every D1Database / session / statement is covered
const db = env.DB;
const dbProto = Object.getPrototypeOf(db);
const stmtProto = Object.getPrototypeOf(db.prepare("select 1"));
patchStatements(stmtProto);
patchBatch(dbProto);
patchExec(dbProto);
if (typeof db.withSession === "function") {
	const session = db.withSession("first-unconstrained");
	const sessionProto = Object.getPrototypeOf(session);
	if (sessionProto !== dbProto) patchBatch(sessionProto);
	const sessionStmtProto = Object.getPrototypeOf(session.prepare("select 1"));
	if (sessionStmtProto !== stmtProto) patchStatements(sessionStmtProto);
}

export default {
	async fetch(request, env, ctx) {
		const url = new URL(request.url);
		if (url.pathname.startsWith("/__waterfall/")) {
			const report = reports.get(url.pathname.slice("/__waterfall/".length));
			return report ? Response.json(report) : new Response("pending", { status: 404 });
		}
		const id = request.headers.get("x-bench-id");
		if (!id) return worker.fetch(request, env, ctx);

		const req = { t0: now(), events: [] };
		current = req;
		const response = await worker.fetch(request, env, ctx);
		const report = {
			id,
			path: url.pathname + url.search,
			status: response.status,
			serverTiming: response.headers.get("server-timing"),
			tHeaders: now() - req.t0,
			tFirstChunk: null,
			tBodyEnd: null,
			events: req.events,
		};
		if (!response.body) {
			report.tBodyEnd = report.tHeaders;
			reports.set(id, report);
			return response;
		}
		const timing = new TransformStream({
			transform(chunk, controller) {
				report.tFirstChunk ??= now() - req.t0;
				controller.enqueue(chunk);
			},
			flush() {
				report.tBodyEnd = now() - req.t0;
				reports.set(id, report);
			},
		});
		return new Response(response.body.pipeThrough(timing), response);
	},
	scheduled: worker.scheduled,
};
