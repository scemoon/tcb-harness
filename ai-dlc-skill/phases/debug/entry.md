---
name: ai-dlc-debug
description: "Debug Phase: TCB/云函数日志排查 → 问题定位与追踪"
entry_point: phases/debug/entry.md
triggers:
  - debug
  - tcb-debug
  - tcb-logs
  - 排查日志
  - 日志排查
  - requestId
  - 调用链
---

# Debug Phase (调试)

TCB 云函数日志排查、requestId 追踪、CLS 日志检索。

## Lifecycle

See `lifecycle.md` for the full phase flow.

## 当被委派时

0. 确认排查目标（函数名、requestId、环境）
1. 收集环境信息 `tcb env info`
2. 列出函数 `tcb fn list --env $TCB_ENV_ID`
3. 基础日志查询 `tcb fn logs --name <fn> --limit 50`
4. **如有 requestId**：通过 CLS 控制台或 API 查询调用链
5. 分析日志输出，定位问题根因
6. 输出诊断报告与修复建议

## 产出

- 问题定位报告
- 相关日志片段
- 修复建议

## TCB Debug Decision Tree

```
需要排查 TCB 问题？
├── 函数部署/运行问题 → tcb fn logs / tcb fn invoke
├── 需要追踪特定请求 → CLS 日志检索 (requestId)
├── 数据库问题 → tcb db query
├── 托管/静态网站问题 → tcb hosting detail
└── MCP 连接问题 → cdh cloudbase status
```
