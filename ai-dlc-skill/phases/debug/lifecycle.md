# AI-DLC Phase 5: Debug (调试)

TCB 云函数日志排查与 requestId 追踪。

## Goal

通过系统化的日志排查流程，快速定位 TCB 云函数问题根因：
- 函数部署失败
- 函数执行异常/超时
- 特定请求调用链追踪
- 数据库/存储操作问题

## Flow

```
接收排查任务 (requestId / 函数名 / 环境)
    │
    ▼
收集环境信息
    - tcb env info
    - tcb env list
    │
    ▼
确认函数状态
    - tcb fn list --env $TCB_ENV_ID
    - tcb fn detail --name <fn> --env $TCB_ENV_ID
    │
    ▼
基础日志查询 (无 requestId 时)
    - tcb fn logs --name <fn> --limit 50 --env $TCB_ENV_ID
    - tcb fn logs --name <fn> --keyword error --env $TCB_ENV_ID
    │
    ▼
高级日志查询 (有 requestId 时) → CLS
    - 控制台: SCF_logset → SCF_RequestId:<requestId>
    - 或 API: cdh cls search --request-id <id> --function <fn>
    │
    ▼
分析日志输出
    - SCF_RequestId, SCF_Message, SCF_Duration, SCF_StatusCode
    - 定位错误行、耗时、调用链
    │
    ▼
输出诊断报告
    - 问题根因
    - 相关日志片段
    - 修复建议
```

## Method 1: CLI 基础日志查询

### 环境检查

```bash
tcb env info
tcb env list
```

### 函数列表与详情

```bash
tcb fn list --env $TCB_ENV_ID
tcb fn detail --name <function-name> --env $TCB_ENV_ID
```

### 函数日志 (TCB CLI)

```bash
tcb fn logs --name <function-name> --env $TCB_ENV_ID
tcb fn logs --name <function-name> --limit 100 --env $TCB_ENV_ID
tcb fn logs --name <function-name> --keyword error --env $TCB_ENV_ID
tcb fn logs --name <function-name> --tail --env $TCB_ENV_ID
```

**限制**: TCB CLI `tcb fn logs` 不支持通过 requestId 查询。

## Method 2: CLS 日志检索 (requestId 追踪)

### 为什么需要 CLS

腾讯云 SCF 日志自动投递至日志服务 CLS，支持：
- 通过 `SCF_RequestId` 检索特定调用
- 时间范围检索
- 多条件组合检索
- 调用链分析

### CLS 控制台查询 (手动)

1. 登录 [腾讯云日志服务控制台](https://console.cloud.tencent.com/cls)
2. 选择地域（与 SCF 函数相同）
3. 进入 `SCF_logset` 日志集
4. 选择对应的日志主题：`SCF_logtopic_{函数名}_{命名空间}`
5. 检索条件：
   ```
   SCF_RequestId:req-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```

### CLS 日志字段

| 字段名 | 类型 | 含义 |
|--------|------|------|
| `SCF_RequestId` | text | 请求 ID（调用链追踪键） |
| `SCF_FunctionName` | text | 函数名称 |
| `SCF_Namespace` | text | 命名空间 |
| `SCF_Message` | text | 日志内容 |
| `SCF_StartTime` | long | 调用开始时间 (Unix ms) |
| `SCF_Duration` | long | 运行时间 (ms) |
| `SCF_StatusCode` | long | HTTP 状态码 |
| `SCF_Level` | text | 日志级别 (INFO/WARN/ERROR) |
| `SCF_MemUsage` | double | 内存使用 (bytes) |
| `SCF_RetryNum` | long | 重试次数 |

### CLI + CLS API 查询 (自动化)

使用 `cdh cls search` 工具：

```bash
cdh cls search --request-id req-xxxxx --function hello --env $TCB_ENV_ID
cdh cls search --function hello --keyword error --limit 100 --env $TCB_ENV_ID
cdh cls search --function hello --start-time "2026-08-04 10:00:00" --end-time "2026-08-04 12:00:00"
```

### Python API 调用

```python
from cdh.tools.cls_search import CLSLogSearcher

searcher = CLSLogSearcher(region="ap-shanghai")

# 通过 requestId 查询
logs = searcher.search_by_request_id(
    request_id="req-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    function_name="hello"
)

# 关键词查询
logs = searcher.search_scf_logs(
    query="ERROR",
    function_name="hello",
    limit=100
)

for log in logs:
    print(f"[{log['time']}] {log['message']}")
```

## Method 3: SCF 控制台查询

1. 进入 [SCF 控制台](https://console.cloud.tencent.com/scf)
2. 选择函数 → **日志页签**
3. 点击 **高级检索**
4. 输入检索条件：`SCF_RequestId:req-xxxxx`

## Debug Workflow Examples

### Workflow: 函数执行报错

```bash
# 1. 获取函数详情
tcb fn detail --name hello --env $TCB_ENV_ID

# 2. 查看最近日志
tcb fn logs --name hello --limit 100 --env $TCB_ENV_ID

# 3. 查看错误日志
tcb fn logs --name hello --keyword error --env $TCB_ENV_ID

# 4. 重新调用并观察
tcb fn invoke --name hello --params '{}' --env $TCB_ENV_ID
```

### Workflow: 特定请求调用链追踪

```bash
# 1. 获取 requestId（通常在错误响应或客户端日志中）
# 例如: req-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# 2. CLS 控制台查询
# 登录 https://console.cloud.tencent.com/cls
# 检索: SCF_RequestId:req-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# 3. 或使用 CLI/API
cdh cls search --request-id req-xxxxxxxx --function hello --limit 50
```

### Workflow: 性能问题排查

```bash
# 1. 查看超时/慢请求日志
tcb fn logs --name hello --limit 100 --env $TCB_ENV_ID

# 2. 通过 CLS 查询耗时
# 检索条件: SCF_FunctionName:hello AND SCF_Duration:>5000

# 3. 查看内存使用
# 检索条件: SCF_FunctionName:hello AND SCF_MemUsage:>1000000000
```

## MCP Tool 调用

当 MCP server 连接时，可使用：

```javascript
// 获取函数日志 (TCB MCP)
const logs = await MCPTool(server="cloudbase", tool="get_function_logs", arguments={
  name: "hello",
  envId: "env-xxxxx",
  limit: 50
});

// CLS 日志检索 (需额外配置)
const traces = await MCPTool(server="cloudbase", tool="search_logs", arguments={
  requestId: "req-xxxxx",
  functionName: "hello",
  region: "ap-shanghai"
});
```

## Output Template

```markdown
# TCB Debug Report

## 问题概述
- **函数**: <function-name>
- **环境**: <env-id>
- **时间**: <timestamp>
- **问题类型**: <deployment/ invocation/ timeout/ error>

## 环境信息
```
<tcb env info 输出>
```

## 函数状态
```
<tcb fn detail 输出>
```

## 日志分析
### 基础日志
```
<相关日志片段>
```

### CLS 调用链 (如有 requestId)
```
<requestId 关联日志>
```

## 根因分析
<问题根因描述>

## 修复建议
1. <建议1>
2. <建议2>
3. <建议3>

## 相关链接
- [SCF 控制台](https://console.cloud.tencent.com/scf)
- [CLS 日志服务](https://console.cloud.tencent.com/cls)
- [函数详情](https://console.cloud.tencent.com/scf/detail/<region>/<env-id>/<function-name>)
```

## 常见问题快速检索

| 场景 | 检索条件 |
|------|----------|
| 特定请求追踪 | `SCF_RequestId:<requestId>` |
| 错误日志 | `SCF_Message:error OR SCF_Level:ERROR` |
| 超时请求 | `SCF_Duration:>60000` |
| 内存超限 | `SCF_MemUsage:>1536000000` |
| HTTP 5xx | `SCF_StatusCode:>=500` |
| 特定函数 | `SCF_FunctionName:<functionName>` |
| 特定命名空间 | `SCF_Namespace:<namespace>` |

## Gate

**排查完成标准:**
- [ ] 环境信息已确认
- [ ] 函数状态已确认
- [ ] 相关日志已获取
- [ ] 问题根因已定位
- [ ] 修复建议已给出
