# Brownfield 存量项目支持

为已有项目自动生成语义上下文，辅助 AI Agent 理解代码库。

## 使用方式

```bash
# 一键生成 AI-DLC-CONTEXT.md
./brownfield/generate-context.sh

# 单独步骤
./brownfield/scripts/discover.sh       # 组件发现
./brownfield/scripts/extract-api.sh    # API 表面提取
./brownfield/scripts/deps.sh           # 跨组件依赖图
```

## 产出

`AI-DLC-CONTEXT.md` 文件包含：
1. 发现的组件列表 + 技术栈
2. API 端点摘要
3. 跨组件依赖 Mermaid 图
4. 架构速览

## 在 Phase 中的应用

Master Agent 在 `affects` 声明后自动触发 Brownfield Phase：
```
L2+ 且有存量代码 → Task(agent_type="explore", prompt="...brownfield/scripts/...")
```
