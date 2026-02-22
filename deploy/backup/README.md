# Backup and Restore

This project now includes reproducible backup scripts for PostgreSQL, Qdrant, and file artifacts in `data/`.

## 1. PostgreSQL backup

Run:

```bash
docker compose --profile ops run --rm pg-backup
```

Output file:

```text
./backups/postgres-bidexpert-YYYYMMDD-HHMMSS.dump
```

Restore example:

```bash
cat ./backups/postgres-bidexpert-YYYYMMDD-HHMMSS.dump \
  | docker compose exec -T postgres pg_restore -U bidexpert -d bidexpert --clean --if-exists
```

## 2. Qdrant storage backup

Run:

```bash
docker compose --profile ops run --rm qdrant-backup
```

Output file:

```text
./backups/qdrant-storage-YYYYMMDD-HHMMSS.tar.gz
```

Restore example (service stopped):

```bash
docker compose stop qdrant
docker run --rm -v bidexpert_qdrant_data:/qdrant/storage -v "$PWD/backups:/backups" alpine:3.20 \
  sh -ec 'rm -rf /qdrant/storage/* && tar -xzf /backups/qdrant-storage-YYYYMMDD-HHMMSS.tar.gz -C /qdrant/storage'
docker compose start qdrant
```

## 3. File artifact backup (`data/`)

Run:

```bash
docker compose --profile ops run --rm data-backup
```

Output file:

```text
./backups/data-artifacts-YYYYMMDD-HHMMSS.tar.gz
```

Restore example (service stopped):

```bash
docker compose stop api worker
docker run --rm -v "$PWD/data:/data" -v "$PWD/backups:/backups" alpine:3.20 \
  sh -ec 'rm -rf /data/* && tar -xzf /backups/data-artifacts-YYYYMMDD-HHMMSS.tar.gz -C /data'
docker compose start api worker
```

## 4. Suggested schedule

- Daily incremental-like backups: run all three scripts once every day.
- Weekly retention: keep at least 4 weekly snapshots.
- Monthly drill: execute a restore in a non-production environment and record evidence using:
  `docs/runbooks/monthly-restore-drill-template.md`.
