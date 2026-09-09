# Contracts 目录说明

## 三层合约体系

```
contracts/
├── api/              ← OpenAPI 3.1 — HTTP API 合约 (已有)
├── events/           ← AsyncAPI 3.0 — 事件合约 (已有)
└── functions/        ← Runtime Contract — Serverless 函数接口 (新增)
```

## aidlc/contracts/api/
HTTP API 描述，使用 OpenAPI 3.1 格式。
每个文件对应一个 INT-FR-NNN，描述请求/响应 schema。

## aidlc/contracts/events/
事件驱动合约，使用 AsyncAPI 3.0 + CloudEvents 格式。
描述事件的生产/消费关系。

## aidlc/contracts/functions/
Serverless 函数接口描述，Provider-agnostic。
描述函数的触发器、资源需求、环境变量。
部署时根据选择的 provider + compute_mode 自动映射到具体平台。

模板位于 `templates/integration/runtime-contract.yaml`。
