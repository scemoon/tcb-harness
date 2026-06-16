# TTA 组件开发指南 (TTA-FR-*) — 抖音小程序

## 技术栈
- 框架: 抖音原生小程序 / uni-app
- 语言: JavaScript / TypeScript
- 构建: 抖音开发者工具
- 测试: Jest
- BDD: 手动 + miniprogram-automator

## 关键命令
- 构建: `pnpm --filter tta build`
- 测试: `pnpm --filter tta test`
- 预览: 上传到抖音小程序预览平台
- Lint: `pnpm --filter tta lint`

## 目录约定
- `src/` → 组件源码
- `tests/unit/` → 单元测试
- `features/` → BDD feature 文件

## FR 命名空间
- Prefix: TTA-FR-NNN
- 范围: 抖音小程序行为

## 特定约束
- 抖音小程序审核流程
- 预览通过小程序预览 QR 码访问
- `BACKEND_URL` 在构建时注入
- 视频/直播相关功能使用抖音小程序 API
