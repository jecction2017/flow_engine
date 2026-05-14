# Database seed fixtures

This directory mirrors the layout expected by `flow_engine.db.migrate_data` (profiles, dict, lookup, flows, starlark_user).

Seed a local MySQL database from the repo checkout root:

```bash
flow-db migrate-data --data-dir tests/fixtures/db_seed
```

The repository root `data/` directory is kept empty (placeholder only); default `flow-db migrate-data` without `--data-dir` imports nothing beyond empty trees.
