# Coding Design Guide — 编码设计指南

## 目录

1. [架构规范](#架构规范)
2. [TDD 工作流](#tdd-工作流)
3. [代码规范](#代码规范)
4. [代码评审](#代码评审)
5. [Claude Code 集成](#claude-code-集成)

---

## 架构规范

### 分层架构

```
┌─────────────────────────────────┐
│           Pages (视图层)          │  页面 WXML/WXSS/JS/JSON
├─────────────────────────────────┤
│        Components (组件层)        │  可复用 UI 组件
├─────────────────────────────────┤
│        Services (服务层)          │  业务逻辑 + CloudBase API 调用
├─────────────────────────────────┤
│        Models (模型层)            │  数据结构定义 + 校验
├─────────────────────────────────┤
│         Utils (工具层)            │  通用工具函数
└─────────────────────────────────┘

       cloud/ (云函数 - 独立部署)
```

### 依赖规则

- **Pages** → 可依赖 Components, Services, Models, Utils
- **Components** → 可依赖 Services, Models, Utils，**禁止**依赖 Pages
- **Services** → 可依赖 Models, Utils，**禁止**依赖 Pages, Components
- **Models** → 可依赖 Utils，**禁止**依赖 Services, Components, Pages
- **Utils** → **禁止**依赖任何其他业务层
- **cloud/** → 独立部署，与前端通过 HTTP 接口通信

### 模块划分原则

1. **按业务域划分 Services** — `services/order.js`, `services/user.js`, `services/product.js`
2. **按数据实体划分 Models** — `models/order.js`, `models/user.js`
3. **Components 分两层** — `components/common/`（通用）和 `components/business/`（业务）
4. **云函数按职责拆分** — 一个云函数只做一件事

---

## TDD 工作流

### 红-绿-重构循环

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   🔴 RED    │────→│  🟢 GREEN   │────→│ 🔵 REFACTOR │
│  写测试     │     │ 最小实现     │     │  重构优化    │
│ (必须失败)  │     │ (测试通过)   │     │ (测试仍通过)  │
└─────────────┘     └─────────────┘     └──────┬──────┘
       ↑                                        │
       └────────── 下一个测试 ←──────────────────┘
```

### TDD 实施步骤

**Step 1 — 写测试 (RED)**

```javascript
// tests/unit/services/order.test.js
const { createOrder } = require('../../../src/services/order')

describe('Order Service', () => {
  it('shall create an order with valid items', async () => {
    const items = [{ productId: 'p1', quantity: 2, price: 100 }]
    const result = await createOrder(items, { openid: 'test_openid' })
    expect(result.orderId).toBeDefined()
    expect(result.totalAmount).toBe(200)
  })

  it('shall reject empty items list', async () => {
    await expect(createOrder([], { openid: 'test_openid' }))
      .rejects.toThrow('Items list cannot be empty')
  })
})
```

**Step 2 — 最小实现 (GREEN)**

```javascript
// src/services/order.js
async function createOrder(items, { openid }) {
  if (!items || items.length === 0) {
    throw new Error('Items list cannot be empty')
  }
  const totalAmount = items.reduce((sum, item) => sum + item.quantity * item.price, 0)
  const db = wx.cloud.database()
  const { _id: orderId } = await db.collection('orders').add({
    data: { items, openid, totalAmount, status: 'created', createdAt: new Date() }
  })
  return { orderId, totalAmount }
}
```

**Step 3 — 重构 (REFACTOR)**

- 提取 `calculateTotal` 到 utils
- 添加输入校验到 model 层
- 确保测试仍然全部通过

### 测试文件组织

```
tests/
├── unit/                    # 纯逻辑测试，无外部依赖
│   ├── services/
│   ├── models/
│   └── utils/
├── integration/             # 需要 CloudBase 环境的测试
│   └── services/
└── e2e/                     # miniprogram-automator 端到端测试
    └── flows/
```

### TDD 纪律检查（Validation）

Before coding phase starts, AI should verify the project uses TDD:

#### Pre-Coding Checklist

- [ ] Tests exist BEFORE code is written (RED phase documented)
- [ ] Test files are in `tests/unit/` following naming convention
- [ ] Each module has corresponding test: `src/services/foo.js` → `tests/unit/services/foo.test.js`
- [ ] Running `npm test` shows failing tests (RED) before implementation
- [ ] After implementation, `npm test` passes (GREEN)
- [ ] Refactoring maintains all tests passing

#### Validation Commands

```bash
# Check that test files exist before implementation files
find tests/unit -name "*.test.js" | sort

# Verify tests run and fail before implementation
npm test -- --testPathPattern="services/order" 2>&1 | grep -E "(FAIL|PASS|RED)"

# After implementation, verify all green
npm test -- --coverage
```

#### TDD Anti-Patterns (P0 Violations)

| Anti-Pattern | Description | Detection |
|--------------|-------------|-----------|
| Code-first | Writing implementation before tests | No failing test before first implementation commit |
| Test-free | Module has no corresponding test | `tests/unit/services/foo.test.js` missing |
| Brittle tests | Tests mock too much, don't catch real bugs | Mock覆盖率>80%且实际bug未被检测到 |
| Golden-path-only | Only happy-path tests, no exception coverage | Exception场景测试数量 < 正常场景×0.3 |

If any P0 violation is detected, AI should:
1. Stop implementation immediately
2. Create the missing test file with a failing test (RED)
3. Confirm RED state with `npm test`
4. Resume implementation (GREEN)
5. Document the correction

### TDD 纪律

1. **不写产品代码，除非是为了让失败的测试通过**
2. **测试中不写多于必要的代码** — 只测一个行为
3. **实现中不写多于必要的代码** — 刚好让测试通过
4. **每个 RED-GREEN 循环控制在 2-5 分钟内**
5. **重构时必须保证所有测试绿色**

---

## 代码规范

### 命名

| 类型 | 规范 | 示例 |
|------|------|------|
| 页面目录 | kebab-case | `pages/order-detail/` |
| 组件目录 | kebab-case | `components/common/loading-modal/` |
| JS 文件 | camelCase | `services/orderManager.js` |
| 云函数目录 | kebab-case | `cloud/create-order/` |
| 集合名 | snake_case | `order_items` |
| CSS class | BEM | `.order-detail__header--highlighted` |
| 常量 | UPPER_SNAKE | `MAX_PAGE_SIZE` |
| 函数 | camelCase | `calculateTotal()` |

### TypeScript 推荐

对于新项目推荐启用 TypeScript：

```json
// project.config.json
{
  "setting": {
    "useCompilerPlugins": ["typescript"]
  }
}
```

类型定义优先放在 `models/` 目录：

```typescript
// models/order.ts
interface OrderItem {
  productId: string
  quantity: number
  price: number
}

interface Order {
  _id: string
  items: OrderItem[]
  openid: string
  totalAmount: number
  status: 'created' | 'paid' | 'shipped' | 'completed'
  createdAt: Date
}
```

### 样式规范

- 使用 WXSS，不引入预处理器（除非项目已配置）
- 颜色值引用设计系统变量（见 ui-design-guide.md）
- 组件样式强制隔离：`styleIsolation: 'isolated'`
- rpx 为主，px 仅用于 1px 边框等特殊场景

### 组件规范

```javascript
// components/common/empty-state/index.js
Component({
  options: {
    styleIsolation: 'isolated',
    multipleSlots: true
  },
  properties: {
    title: { type: String, value: '' },
    description: { type: String, value: '' },
    icon: { type: String, value: 'empty' }
  },
  methods: {
    onTap() {
      this.triggerEvent('action')
    }
  }
})
```

### 云函数规范

```javascript
// cloud/create-order/index.js
const cloud = require('wx-server-sdk')
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV })
const db = cloud.database()

exports.main = async (event, context) => {
  const { items } = event
  const { OPENID } = cloud.getWXContext()

  // Input validation
  if (!items || !Array.isArray(items) || items.length === 0) {
    return { code: 400, message: 'Invalid items' }
  }

  try {
    // Business logic
    const totalAmount = items.reduce((sum, i) => sum + i.quantity * i.price, 0)
    const result = await db.collection('orders').add({
      data: { items, openid: OPENID, totalAmount, status: 'created', createdAt: db.serverDate() }
    })
    return { code: 0, data: { orderId: result._id, totalAmount } }
  } catch (err) {
    console.error('createOrder failed:', err)
    return { code: 500, message: 'Internal error' }
  }
}
```

---

## 代码评审

### 评审清单

#### 功能正确性
- [ ] 实现符合需求文档中的验收标准
- [ ] 边界条件已处理（空值、极值、并发）
- [ ] 错误处理完备（用户可见错误 + 系统日志）

#### 安全性
- [ ] 云函数校验了 OPENID，不信任前端传入的用户身份
- [ ] CloudBase 安全规则已配置（非默认全开）
- [ ] 敏感数据不在前端明文存储
- [ ] 用户输入做了 XSS 防护（rich-text 组件内容过滤）

#### 性能
- [ ] 数据库查询有索引支撑
- [ ] 列表页做了分页（不一次加载全量）
- [ ] 图片使用云存储 CDN + 合适尺寸
- [ ] 分包加载已配置（主包 < 2MB）

#### 可维护性
- [ ] 命名清晰，无缩写歧义
- [ ] 函数单一职责，长度 < 50 行
- [ ] 魔法数字已提取为常量
- [ ] 复杂逻辑有注释说明 "为什么"

#### 测试覆盖
- [ ] 核心逻辑有单元测试
- [ ] 新增/修改的 API 有集成测试
- [ ] 测试覆盖正常 + 异常路径

#### TDD Compliance
- [ ] All new modules have corresponding unit tests
- [ ] Tests follow RED → GREEN → REFACTOR pattern
- [ ] Test coverage ≥ 80% for modified modules
- [ ] No test files modified after implementation files (code-first violation)

### 评审输出格式

```markdown
# Code Review — {模块/文件}

## 评审结果: ✅ 通过 / ⚠️ 修改后通过 / ❌ 需重做

## 问题列表

| # | 严重度 | 文件:行 | 描述 | 建议 |
|---|--------|---------|------|------|
| 1 | P0 | services/order.js:15 | 未校验 OPENID | 从 cloud.getWXContext() 获取 |
| 2 | P1 | pages/detail/detail.js:42 | 魔法数字 20 | 提取为 PAGE_SIZE 常量 |

## 改进建议

1. ...
2. ...
```

---

## Claude Code 集成

### 何时使用 Claude Code

- TDD 编码会话中需要长时间连续实现
- 复杂逻辑需要交互式调试
- 多文件重构需要上下文感知

### 使用方式

1. 读取 `claude-code-cli-openclaw` skill 获取 Claude Code CLI 用法
2. 在项目目录下启动 Claude Code 会话
3. 传入上下文：当前任务（来自 tasks.md）+ 相关设计文档路径
4. Claude Code 完成后，在主会话中验证测试通过状态

### 上下文传递

向 Claude Code 传递的关键上下文：

```
当前任务: {task description from tasks.md}
相关设计: design/{domain}/*.md
代码规范: references/coding-design-guide.md (本文件)
CloudBase 环境: .harness/config.json
```
