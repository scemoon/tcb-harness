# MYA 组件开发指南 (MYA-FR-*) — 支付宝小程序

## 技术栈
- 框架: 支付宝原生小程序 / uni-app
- 语言: JavaScript / TypeScript
- 构建: 支付宝开发者工具
- 测试: Jest
- BDD: 手动 + miniprogram-automator

## 关键命令
- 构建: `pnpm --filter mya build`
- 测试: `pnpm --filter mya test`
- 预览: 上传到支付宝小程序预览平台
- Lint: `pnpm --filter mya lint`

## 目录约定
- `src/` → 组件源码
- `tests/unit/` → 单元测试
- `features/` → BDD feature 文件

## FR 命名空间
- Prefix: MYA-FR-NNN
- 范围: 支付宝小程序行为

## 特定约束
- 支付宝小程序有独立的审核流程
- 预览通过小程序预览 QR 码访问
- `BACKEND_URL` 在构建时注入
- 支付功能使用支付宝小程序支付 SDK
