# 项目工程目录架构

## 顶层布局

```
{{project_root}}/
├── apps/
│   ├── native/          # NATIVE-FR-*   Mobile (Flutter/Dart)
│   ├── desktop/         # DESKTOP-FR-*  Desktop (Electron/TypeScript)
│   ├── web/             # WEB-FR-*      Browser (Next.js/TypeScript)
│   ├── backend/         # BE-FR-*       Service (Python / Node / Go)
│   ├── wxa/             # WXA-FR-*      WeChat Mini Program (Vant Weapp/JavaScript)
│   ├── mya/             # MYA-FR-*      Alipay Mini Program (Ant Design Mini/JavaScript)
│   └── tta/             # TTA-FR-*      TikTok Mini Program (TypeScript)
├── aidlc/contracts/           # INT-FR-*      OpenAPI / AsyncAPI / Runtime Contract
│   ├── api/
│   ├── events/
│   └── functions/
├── packages/shared/     # INT-FR-*      从 contracts 生成的共享类型
├── aidlc/features/            # BDD feature 文件
│   └── cross-stack/     # 跨组件集成场景
├── tests/
│   ├── contract/        # 合约测试 (INT-FR 级别, provider-agnostic)
│   └── cross-stack/     # 跨组件 e2e 测试 (对 STACK_URL 运行)
├── aidlc/openspec/            # AI-DLC 生命周期产出物
│   └── changes/{id}/
│       ├── spec-delta.md
│       ├── design.md
│       ├── task-list.md
│       ├── contract-diff.md
│       └── walkthrough.md
├── aidlc/providers/           # 云平台部署配置
│   ├── tcb/
│   └── aliyun/
├── aidlc/tools/               # 脚手架脚本
│   ├── generate_shared.py
│   └── contract_diff.py
├── .opencode/           # OpenCode 配置
│   └── skills/ai-dlc-skill/
├── .cdh/                # CDHA 项目状态
│   ├── config.yaml
│   ├── state.json
│   └── SKILL.md
└── aidlc/AI-DLC-CONTEXT.md    # Brownfield 上下文摘要 (自动生成)
```

## 组件内部结构 (标准模板)

```
apps/{component}/
├── src/              # 实现代码
│   └── {module}/
├── tests/
│   ├── unit/         # TDD 单元测试
│   ├── integration/  # 集成测试 (含 DB)
│   └── e2e/          # E2E 测试 (对 preview URL)
├── features/         # BDD feature 文件
│   └── steps/        # BDD step definitions
├── contracts/        # 组件级合约引用
├── .skill/           # 组件级 Skill (自动生成)
│   └── SKILL.md
├── package.json
└── ...
```

## FR 命名空间 ↔ 目录映射

| FR 前缀 | 目录 | 测试目录 | e2e target |
|---------|------|---------|------------|
| NATIVE-FR-NNN | `apps/native/src/` | `apps/native/tests/` | BACKEND_URL |
| DESKTOP-FR-NNN | `apps/desktop/src/` | `apps/desktop/tests/` | BACKEND_URL |
| WEB-FR-NNN | `apps/web/src/` | `apps/web/tests/` | WEB_URL + BACKEND_URL |
| BE-FR-NNN | `apps/backend/src/` | `apps/backend/tests/` | BACKEND_URL |
| WXA-FR-NNN | `apps/wxa/` | `apps/wxa/tests/` | BACKEND_URL |
| MYA-FR-NNN | `apps/mya/` | `apps/mya/tests/` | BACKEND_URL |
| TTA-FR-NNN | `apps/tta/` | `apps/tta/tests/` | BACKEND_URL |
| INT-FR-NNN | `contracts/` + `packages/shared/` | `tests/contract/` | generated types |
| 跨组件 | `aidlc/features/cross-stack/` | `tests/cross-stack/` | STACK_URL |
