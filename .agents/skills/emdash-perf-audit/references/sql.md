# Read-only detection queries

Run these against one of two databases:

- **The local mirror** (fast, no production load):
  ```bash
  DB=$(find .bench/state-prod -name "*.sqlite" -size +50k | head -1)
  sqlite3 "$DB" "<query>"
  ```
- **Production**, when the mirror may be stale:
  ```bash
  npx wrangler d1 execute <database_name from wrangler.jsonc> --remote --command "<query>"
  ```

Use SELECT only. The schema was checked against EmDash 1.1.0. If a column is missing, read the schema with `.schema <table>` instead of guessing.

## posts-without-byline (trap 3)

```sql
SELECT p.slug FROM ec_posts p
WHERE p.status = 'published' AND p.deleted_at IS NULL
  AND NOT EXISTS (SELECT 1 FROM _emdash_content_bylines cb
                  WHERE cb.collection_slug = 'posts' AND cb.content_id = p.id);
```

## byline-fields (trap 4)

```sql
SELECT slug, label, type FROM _emdash_byline_fields ORDER BY sort_order;
```

## byline-fields-version (trap 5)

```sql
SELECT name, value FROM options WHERE name = 'byline_fields_version';
```

## posts-without-tags (trap 6)

```sql
SELECT p.slug FROM ec_posts p
WHERE p.status = 'published' AND p.deleted_at IS NULL
  AND NOT EXISTS (SELECT 1 FROM content_taxonomies ct
                  JOIN taxonomies t ON t.id = ct.taxonomy_id
                  WHERE ct.collection = 'posts' AND ct.entry_id = p.id AND t.name = 'tag');
```

For other taxonomies or collections, swap `'tag'` for the taxonomy name from the seed (`SELECT DISTINCT name FROM taxonomies`) and `ec_posts` / `'posts'` for the collection.

## Content size (context for the report)

```sql
SELECT (SELECT count(*) FROM ec_posts WHERE deleted_at IS NULL) AS posts,
       (SELECT count(*) FROM taxonomies) AS terms,
       (SELECT count(*) FROM _emdash_comments) AS comments;
```
