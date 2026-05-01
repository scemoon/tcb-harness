# Automation Guide — 自动化测试指南

## 目录

1. [概述](#概述)
2. [接口自动化](#接口自动化)
3. [小程序 UI 自动化（Midscene）](#小程序-ui-自动化midscene)
4. [Web UI 自动化（Playwright）](#web-ui-自动化playwright)
5. [CI/CD 集成](#cicd-集成)
6. [部署配置](#部署配置)

---

## 概述

### 鹰眼（Eagle Eye）追踪确认

本 skill 采用与腾讯云鹰眼兼容的 Trace ID 格式（32位十六进制），确保与微信内部系统互通。

**确认清单：**

| 确认项 | 状态 | 说明 |
|--------|------|------|
| Trace ID 生成 | ✅ 遵循鹰眼格式 | 见 tracing-guide.md |
| Trace Header | ✅ 兼容鹰眼约定 | X-Trace-ID / X-Parent-Span-ID |
| 云函数中间件 | ✅ withTrace() 包裹 | 见 cloud/middleware/trace.js |
| 日志规范 | ✅ JSON 结构化输出 | 兼容鹰眼采集 |
| 存储方案 | ⚠️ 用户配置 | CLS / ES / MongoDB 按需选择 |

**E2E 测试确认：**

| 平台 | 工具 | 配置状态 |
|------|------|---------|
| 小程序 | Midscene.js | jest preset 已配置 |
| Web | Playwright | playwright.config.ts 已配置 |

**如需启用鹰眼监控：**
1. 确认腾讯云账号已开通 鹰眼服务
2. 在 deploy-config.json 中配置 tracing.collector.type = "cls"
3. 参考 tracing-guide.md 部署 trace-collector 云函数

**E2E 测试执行：**
```bash
# 小程序 E2E（需微信开发者工具）
npx jest tests/e2e/miniprogram --preset=@midscene/jest/mac-miniprogram

# Web E2E
npx playwright test
```


---

### 三大自动化层次

| 层次 | 工具 | 适用场景 | 执行环境 |
|------|------|---------|---------|
| 接口自动化 | Jest + SuperTest | 云函数 API、数据库操作 | Node.js |
| 小程序 UI | **Midscene.js** | 页面交互、流程验证 | Node.js + 微信开发者工具 |
| Web UI | **Playwright** | 浏览器交互、E2E 验证 | Node.js + Chromium |

### Midscene.js vs Playwright

| 维度 | Midscene.js | Playwright |
|------|------------|-----------|
| 适用平台 | 微信小程序 | Web（浏览器） |
| AI 驱动 | ✅ AI 自动生成断言 | ❌ 手动编写 |
| 调试体验 | 可视化 + 截图对比 | Playwright DevTools |
| 语言 | TypeScript/JavaScript | TypeScript/JavaScript |
| 学习成本 | 低（自然语言描述） | 中（API 编写） |

---

## 接口自动化

### 工具选型

| 工具 | 用途 | 说明 |
|------|------|------|
| Jest | 测试框架 | 断言、Mock、覆盖率 |
| SuperTest | HTTP 客户端 | 调用云函数 API |
| jest-mock-cloudbase | CloudBase Mock | Mock wx-server-sdk |

### 项目配置

```bash
cd tests/integration
npm init -y
npm install --save-dev jest @types/jest ts-node supertest
npm install --save-dev @cloudbase/node-sdk
```

### jest.config.ts

```typescript
// jest.config.ts
import type { Config } from 'jest'

const config: Config = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['**/*.test.ts'],
  collectCoverageFrom: ['**/cloud/**/*.ts', '!**/node_modules/**'],
  coverageThreshold: {
    global: { branches: 70, functions: 80, lines: 80, statements: 80 }
  },
  setupFilesAfterEnv: ['<rootDir>/setup.ts'],
}

export default config
```

### setup.ts

```typescript
// setup.ts
// Mock CloudBase 环境变量
process.env.SCF_NAMESPACE = 'test-env'
```

### API 测试示例

```typescript
// tests/integration/api/order.test.ts
import { describe, it, expect, beforeAll } from '@jest/globals'

// 直接调用云函数（通过本地模拟或测试环境）
const BASE_URL = process.env.API_BASE_URL || 'https://test-env.tcloud.com'

describe('Order API', () => {
  let authOpenid: string

  beforeAll(async () => {
    // 获取测试用户 OPENID（通过云函数或测试账号）
    authOpenid = 'test_openid_001'
  })

  describe('POST /create-order', () => {
    it('should create order with valid items', async () => {
      const res = await fetch(`${BASE_URL}/create-order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items: [
            { productId: 'p001', quantity: 2, price: 99.9 }
          ],
          _traceContext: { traceId: 'TEST_TRACE_ID' }
        })
      })

      const data = await res.json()

      expect(res.status).toBe(200)
      expect(data.code).toBe(0)
      expect(data.data.orderId).toBeDefined()
      expect(data.data.totalAmount).toBe(199.8)
    })

    it('should reject empty items', async () => {
      const res = await fetch(`${BASE_URL}/create-order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: [] })
      })

      const data = await res.json()
      expect(data.code).toBe(400)
      expect(data.message).toContain('empty')
    })

    it('should reject without trace context in logs', async () => {
      // 验证 Trace ID 是否被正确记录
      const res = await fetch(`${BASE_URL}/create-order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: [{ productId: 'p001', quantity: 1, price: 10 }] })
      })

      const data = await res.json()
      expect(data.code).toBe(0)

      // 验证数据库中该订单包含 traceId
      const order = await db.collection('orders').doc(data.data.orderId).get()
      expect(order.data.traceId).toBe('TEST_TRACE_ID')
    })
  })
})
```

### Mock 云函数

```typescript
// tests/integration/mocks/cloud-function.ts
export function mockCloudFunction(name: string, handler: Function) {
  // 在测试环境中劫持 wx.cloud.callFunction
  jest.mock(`wx-server-sdk`, () => ({
    init: jest.fn(),
    database: () => mockDb,
    getWXContext: () => ({
      OPENID: 'test_openid_001',
      APPID: 'test_appid',
      ENV_ID: 'test-env'
    })
  }))
}
```

---

## 小程序 UI 自动化（Midscene）

### 什么是 Midscene

Midscene 是字节跳动开源的小程序自动化测试工具，通过 AI 驱动的自然语言描述实现页面交互和断言。

**特点：**
- 自然语言描述操作：`"点击确认按钮"`
- AI 自动生成断言
- 截图对比 + 视觉回归
- 支持云函数 Mock

### 安装

```bash
npm install -D @midscene/web @midscene/jest
```

### jest-midscene preset

```typescript
// jest.config.ts
export default {
  preset: '@midscene/jest/mac-miniprogram',
  // 或针对 Windows
  // preset: '@midscene/jest/win-miniprogram',
}
```

### Midscene 测试示例

```typescript
// tests/e2e/miniprogram/home.test.ts
import { describe, it } from '@jest/globals'

describe('首页流程', () => {
  it('浏览首页并进入商品详情', async () => {
    // 1. 首页加载
    await page.goto('/pages/home/index')

    // 2. 等待页面渲染
    await page.waitForPageReady()

    // 3. 自然语言交互
    await ai('点击搜索框')
    await ai('在搜索框输入"iPhone"')
    await ai('点击搜索按钮')
    await ai('点击第1个商品')

    // 4. 验证进入了商品详情页
    await ai('页面应该显示商品名称')
    await ai('页面应该显示商品价格')
  })

  it('创建订单流程', async () => {
    await page.goto('/pages/product-detail/index?id=p001')
    await page.waitForPageReady()

    // 加入购物车
    await ai('点击加入购物车按钮')
    await ai('应该出现toast提示"添加成功"')

    // 结算
    await ai('点击去结算按钮')
    await ai('点击提交订单按钮')

    // 验证订单创建成功
    await ai('应该出现确认弹窗')
    await ai('点击确定')
    await ai('页面应该跳转到订单详情页')
  })
})
```

### Midscene 配置

```typescript
// midscene.config.ts
export default {
  // AI 模型配置（使用 CloudBase AI 或 OpenAI）
  aiModel: {
    provider: 'cloudbase',
    model: 'hunyuan',
    apiKey: process.env.AI_API_KEY,
  },

  // 截图对比配置
  screenshot: {
    dir: './tests/e2e/screenshots',
    diffDir: './tests/e2e/screenshots/diff',
    threshold: 0.1,  // 差异阈值 10%
  },

  // 云函数 Mock
  cloudMock: {
    enabled: true,
    mockData: './tests/e2e/mock-data',
  },

  // 等待超时
  timeout: {
    action: 30000,    // 操作 30s 超时
    navigation: 15000, // 导航 15s 超时
  },
}
```

### Mock 云函数数据

```json
// tests/e2e/mock-data/create-order.json
{
  "success": true,
  "result": {
    "orderId": "mock_order_001",
    "totalAmount": 199.8,
    "status": "created"
  }
}
```

### Midscene CI 模式

```bash
# CI 环境使用无头模式
export MIDSCENE_HEADLESS=true
npx jest tests/e2e/miniprogram --preset=@midscene/jest/mac-miniprogram
```

---

## Web UI 自动化（Playwright）

### 安装

```bash
npm install -D @playwright/test
npx playwright install chromium --with-deps
```

### playwright.config.ts

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e/web',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['html', { outputFolder: 'tests/e2e/reports' }], ['list']],

  use: {
    baseURL: process.env.WEB_BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 5'] },
    },
  ],

  webServer: process.env.CI
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://localhost:3000',
        reuseExistingServer: !process.env.CI,
      },
})
```

### Playwright 测试示例

```typescript
// tests/e2e/web/home.spec.ts
import { test, expect } from '@playwright/test'

test.describe('首页流程', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('首页正确加载', async ({ page }) => {
    await expect(page.locator('text=欢迎使用 TCB App')).toBeVisible()
    await expect(page.locator('button:has-text("搜索")')).toBeVisible()
  })

  test('搜索功能', async ({ page }) => {
    const input = page.locator('input[type="text"]')
    await input.fill('iPhone')
    await page.locator('button:has-text("搜索")').click()
    // 等待搜索结果加载
    await expect(page).toHaveURL(/\/search.*iPhone/)
  })

  test('登录流程', async ({ page }) => {
    await page.locator('text=登录').click()
    await expect(page).toHaveURL(/\/login/)

    await page.locator('input[name="email"]').fill('test@example.com')
    await page.locator('input[name="password"]').fill('password123')
    await page.locator('button:has-text("登录")').click()

    await expect(page).toHaveURL('/')
    await expect(page.locator('text=个人中心')).toBeVisible()
  })
})

test.describe('订单流程', () => {
  test('创建订单', async ({ page }) => {
    await page.goto('/product/p001')

    await page.locator('button:has-text("立即购买")').click()
    await expect(page).toHaveURL(/\/order\/confirm/)

    await page.locator('button:has-text("提交订单")').click()
    await page.waitForURL(/\/order\/.*\/success/)

    await expect(page.locator('text=订单创建成功')).toBeVisible()
  })
})
```

### Page Object 模式

```typescript
// tests/e2e/web/pages/OrderPage.ts
import { Page, expect } from '@playwright/test'

export class OrderPage {
  constructor(private page: Page) {}

  async submit() {
    await this.page.locator('button:has-text("提交订单")').click()
  }

  async expectSuccess() {
    await expect(this.page.locator('text=订单创建成功')).toBeVisible()
  }

  async expectError(message: string) {
    await expect(this.page.locator(`text=${message}`)).toBeVisible()
  }
}

// 使用
test('order flow', async ({ page }) => {
  const orderPage = new OrderPage(page)
  await page.goto('/order/confirm')
  await orderPage.submit()
  await orderPage.expectSuccess()
})
```

### Playwright CloudBase 集成

```typescript
// tests/e2e/web/utils/cloudbase.ts
import { test as base } from '@playwright/test'

// 扩展 test fixture，注入 CloudBase Mock
export const test = base.extend<{
  cloudbaseMock: CloudBaseMock
}>({
  cloudbaseMock: async ({ page }, use) => {
    const mock = new CloudBaseMock(page)
    await mock.setup()
    await use(mock)
    await mock.cleanup()
  }
})

class CloudBaseMock {
  constructor(private page: Page) {}

  async setup() {
    await this.page.addInitScript(() => {
      // Mock wx.cloud 在 Web 端
      ;(window as any).cloudbase = {
        callFunction: async ({ name, data }: any) => {
          // 读取 Mock 数据
          return { code: 0, result: { ...mockData[name], ...data } }
        }
      }
    })
  }
}
```

---

## CI/CD 集成

### GitHub Actions 示例

```yaml
# .github/workflows/test.yml
name: Test

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  api-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      - run: npm ci
      - run: npm test -- --coverage
      - uses: codecov/codecov-action@v4

  midscene-test:
    runs-on: ubuntu-latest
    needs: api-test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - name: Install WeChat DevTools
        run: |
          # 安装微信开发者工具 CLI
          # 略，具体见微信官方文档
      - name: Run Midscene tests
        env:
          MIDSCENE_HEADLESS: true
        run: npx jest tests/e2e/miniprogram --preset=@midscene/jest/mac-miniprogram

  playwright-test:
    runs-on: ubuntu-latest
    needs: api-test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - run: npx playwright test
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-reports
          path: tests/e2e/reports/
```

---

## 部署配置

```json
// deploy-config.json 中自动化配置
"automation": {
  "enabled": true,
  "tools": {
    "api": {
      "framework": "jest",
      "config": "./tests/integration/jest.config.ts",
      "coverageThreshold": {
        "branches": 70,
        "lines": 80
      }
    },
    "miniprogram": {
      "framework": "midscene",
      "preset": "@midscene/jest/mac-miniprogram",
      "aiModel": {
        "provider": "cloudbase",
        "model": "hunyuan"
      },
      "screenshots": {
        "dir": "./tests/e2e/screenshots",
        "threshold": 0.1
      }
    },
    "web": {
      "framework": "playwright",
      "config": "./playwright.config.ts",
      "browsers": ["chromium", "mobile-chrome"],
      "baseUrl": "${WEB_URL}"
    }
  },
  "e2e": {
    "miniprogram": {
      "enabled": true,
      "preset": "@midscene/jest/mac-miniprogram"
    },
    "web": {
      "enabled": true,
      "config": "./playwright.config.ts"
    }
  },
  "ci": {
    "triggerOnPush": true,
    "triggerBranches": ["main", "develop"],
    "failFast": true
  }
}
```
