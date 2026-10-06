// The bindings src/utils/html-cache.ts reads through `cloudflare:workers`.
// tsconfig doesn't load @cloudflare/workers-types (it clashes with the DOM
// types), so only what we use is declared here.
declare module "cloudflare:workers" {
	export const env: {
		SESSION: {
			get(key: string): Promise<string | null>;
			put(key: string, value: string): Promise<void>;
		};
		CF_VERSION_METADATA?: { id: string };
	};
}
