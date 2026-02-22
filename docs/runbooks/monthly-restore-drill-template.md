# Monthly Restore Drill Template

Date:
Environment:
Operator:
Reviewer:

## 1. Backup Inputs

- PostgreSQL backup file:
- Qdrant backup file:
- Data artifact backup file:

## 2. Restore Steps

1. Restore PostgreSQL dump:
2. Restore Qdrant storage snapshot:
3. Restore `data/` artifact tarball:
4. Start services and run health checks:

## 3. Verification Checklist

- `GET /health` returns `200`.
- `GET /metrics` is reachable according to current auth/network policy.
- Sample project metadata exists in PostgreSQL.
- Sample evidence retrieval from Qdrant succeeds.
- Sample exported artifact exists under `data/`.

## 4. Drill Results

- Result: `PASS` / `FAIL`
- RTO (minutes):
- RPO (minutes):
- Issues found:
- Corrective actions:

## 5. Sign-off

- Operator signature:
- Reviewer signature:
