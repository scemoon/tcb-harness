# CloudSpec Templates

Standard templates for project scaffolding and documentation.

## Template Types

| Template | Purpose | Command |
|----------|---------|---------|
| project | New project scaffold | `cloud-spec init` |
| spec | SPEC.md template | `cloud-spec spec new` |
| function | Cloud function boilerplate | `cloud-spec generate function` |
| frontend | Frontend app scaffold | `cloud-spec generate frontend` |
| test | Test file template | `cloud-spec generate test` |

## Usage

```bash
# List available templates
cloud-spec template list

# Create from template
cloud-spec init --template project --name my-app

# Use specific template
cloud-spec generate function --name my_function
```

## Custom Templates

Place custom templates in `.cloud-spec/templates/` in your project.

```
.cloud-spec/templates/
├── project/           # Custom project template
├── spec/             # Custom spec sections
└── ...
```

## Template Variables

Templates support these variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `{{name}}` | Project/resource name | `my-function` |
| `{{snake_name}}` | snake_case version | `my_function` |
| `{{PascalName}}` | PascalCase version | `MyFunction` |
| `{{date}}` | Current date | `2024-01-15` |
| `{{author}}` | From git config | `John Doe` |
| `{{email}}` | From git config | `john@example.com` |
