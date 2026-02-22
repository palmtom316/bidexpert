# Production Emergency Runbook

## 1. API 5xx 异常升高

1. 检查 `deploy/monitoring/prometheus-alerts.yml` 中 `BidExpertHigh5xxRate` 是否触发。
2. 查看 API 日志并确认最近发布版本与迁移状态。
3. 执行健康检查：`curl -k https://localhost:8443/health`。
4. 如需快速止血，临时降低流量并回滚到上一个稳定镜像。

## 2. 429 限流异常升高

1. 检查 `BidExpertHigh429Rate` 告警是否触发。
2. 核对当前 `BIDEXPERT_API_RATE_LIMIT_*` 配置与网关限流规则。
3. 判断是否为恶意流量，必要时在网关追加 IP 封禁。

## 3. Celery 任务失败率升高

1. 检查 `BidExpertTaskFailureRateHigh` 告警。
2. 查看 worker 日志定位失败任务名与重试次数。
3. 重点确认 Redis、Qdrant、第三方模型 API 可用性。
4. 如为短时依赖故障，观察自动重试恢复情况后再做人工补偿。

## 4. 灾备恢复

1. 按 `deploy/backup/README.md` 执行 PostgreSQL、Qdrant、`data/` 恢复。
2. 在演练/故障恢复后填写：`docs/runbooks/monthly-restore-drill-template.md`。

## 5. 变更封板

1. 故障期间暂停非紧急发布。
2. 恢复后补充 RCA（根因分析）、防复发措施和责任人。
