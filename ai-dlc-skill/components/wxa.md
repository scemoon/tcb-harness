# WXA 组件开发指南 (WXA-FR-*) — 微信小程序

## 技术栈
- 框架: 微信原生小程序 / Taro / uni-app
- 语言: JavaScript / TypeScript
- 构建: 微信开发者工具 / Taro CLI
- 测试: Jest / miniprogram-simtest
- BDD: 手动 + 自动化（通过 miniprogram-automator）

## 关键命令
- 构建: `pnpm --filter wxa build`
- 测试: `pnpm --filter wxa test`
- 预览: 上传到微信小程序预览平台
- Lint: `pnpm --filter wxa lint`

## 目录约定
- `src/` → 组件源码
- `tests/unit/` → 单元测试
- `features/` → BDD feature 文件

## FR 命名空间
- Prefix: WXA-FR-NNN
- 范围: 微信小程序行为

## 特定约束
- 微信小程序审核流程（每次上架需要审核）
- 预览通过小程序预览 QR 码访问
- `BACKEND_URL` 在构建时注入到小程序配置
- 不支持 npm 包中的所有 API（仅微信 API）
