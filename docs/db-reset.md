## Local DB reset (drop_old / schema break)

This repo uses **SQLAlchemy `Base.metadata.create_all()`** (via `flow-db apply`) to ensure tables exist.

Important limitation: `create_all()` **does not migrate existing tables/columns**. When we change models
in a non-backward-compatible way (like splitting deploy runs vs test runs into new tables), the expected
workflow is to **drop & recreate** the local DB schema.

### Preconditions

- Configure DB connection via `.env` (see `.env.example`).
- Install mysql extras:

```bash
pip install -e ".[mysql]"
```

### Inspect current DB URL (masked)

```bash
flow-db url
```

### Recent model additions

- `fe_deploy_run.flow_logs` / `fe_test_run.flow_logs` (JSON): persisted flow-level hook logs
- `fe_deploy_run.global_ns` / `fe_test_run.global_ns` (JSON): run result context snapshot (dictionary stripped)
  (`on_start` / `on_complete` / `on_failure`). After pulling model changes, run `flow-db apply`
  on an existing DB only if your MySQL user can `ALTER TABLE`; otherwise use drop & recreate below.

### Drop & recreate schema (recommended)

Option A (fastest): drop the whole database and recreate it.

1. Drop/create database in MySQL (replace `flow_engine` if you changed `MYSQL_DATABASE`):

```sql
DROP DATABASE IF EXISTS flow_engine;
CREATE DATABASE flow_engine CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

1. Recreate tables from models:

```bash
flow-db apply
```

### Drop tables only (if you can’t drop the DB)

Drop all tables created by this repo, then re-run `flow-db apply`.

1. List tables:

```sql
SHOW TABLES;
```

1. Drop (order doesn’t matter because we don’t use foreign keys):

```sql
DROP TABLE IF EXISTS
  fe_flow_deployment,
  fe_worker,
  fe_worker_assignment,
  fe_flow_run,
  fe_flow_test_batch_plan,
  fe_flow_test_batch,
  fe_flow_test_plan;
```

1. Recreate:

```bash
flow-db apply
```

### Notes

- **This reset is destructive**. For this refactor, we intentionally chose **drop_old** (no history migration).
- If you only added a **new table**, `flow-db apply` is enough.
- If you changed existing columns (rename/remove/type change), you must reset or run the migration SQL above;
  otherwise you’ll see runtime errors or missing fields despite code changes.

