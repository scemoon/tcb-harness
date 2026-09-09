# pytest-bdd Configuration

pytest-bdd 配置和示例。

## 目录结构

```
pybdd/
├── pytest.ini              # pytest 配置
├── conftest.py             # fixtures
├── steps/                  # step definitions
│   ├── .gitkeep
│   └── test_example_steps.py
└── example/                 # 示例 feature
    └── auth/
        └── login.feature
```

## 使用方法

```bash
# 运行所有 BDD 场景
pytest pybdd/ --verbose

# 运行特定 FR
pytest pybdd/ -k "FR-001"

# 生成 step definitions
pytest-bdd generate pybdd/example/auth/login.feature
```

## 场景标签

每个 FR 需包含 4 类场景：

| 标签 | 含义 |
|------|------|
| `@positive` | 处理逻辑 |
| `@negative` | 异常处理 |
| `@edge` | 边界情况 |
| `@logic` | 逻辑一致性 |
