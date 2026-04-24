# Database Migrations

This project keeps the initial database-centered refactor migrations as plain
PostgreSQL SQL files so they stay easy to inspect and explain in a thesis demo.

Apply them in order:

1. `0001_initial_schema.sql`
2. `0002_seed_baseline.sql`

Example:

```bash
psql postgresql://attendance:attendance@localhost:5168/attendance \
  -f database/migrations/0001_initial_schema.sql

psql postgresql://attendance:attendance@localhost:5168/attendance \
  -f database/migrations/0002_seed_baseline.sql
```

Notes:

- `database/session.py` still supports auto-creating tables for incremental local
  development, but PostgreSQL deployments should prefer these SQL migrations.
- CSV files in `logs/` are now legacy inputs or export targets, not the primary
  operational data store.
