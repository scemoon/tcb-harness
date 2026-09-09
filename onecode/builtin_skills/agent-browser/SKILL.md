---
name: agent-browser
description: Browser automation via Playwright for web interaction and testing
enabled: true
triggers:
  - browser
  - playwrith
  - screenshot
  - web page
  - navigate
  - open url
  - click element
  - fill form
  - scrape
  - headless
allowed_tools:
  - Bash
  - Read
  - Write
phases:
  - verify
  - deliver
---

# Agent Browser

## When to Use

- Navigating to a web page and interacting with it
- Taking screenshots of pages
- Filling and submitting forms
- Clicking buttons, links, and other elements
- Extracting dynamic content that requires JS execution
- End-to-end testing of web applications
- Scraping SPAs (Single Page Applications)

Use **WebFetch** instead for simple GET requests that don't need interaction.

## Setup

```bash
pip install playwright
playwright install chromium
```

Check if already installed:

```bash
python -c "import playwright; print(playwright.__file__)"
```

## Basic Usage

### Navigate and Screenshot

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://example.com")
    page.screenshot(path="screenshot.png", full_page=True)
    browser.close()
```

### Fill Form and Submit

```python
page.fill("input[name='username']", "myuser")
page.fill("input[name='password']", "mypass")
page.click("button[type='submit']")
page.wait_for_url("**/dashboard")
```

### Extract Content

```python
# Get text content
title = page.text_content("h1")
items = page.query_selector_all(".item")
for item in items:
    print(item.inner_text())

# Get HTML
html = page.content()

# Evaluate JavaScript
result = page.evaluate("() => document.title")
```

### Wait Strategies

```python
page.wait_for_selector(".results")       # element appears
page.wait_for_load_state("networkidle")  # no network activity
page.wait_for_timeout(2000)              # sleep 2s
page.wait_for_url("**/success")          # URL pattern
```

## Selectors

```python
# CSS
page.click(".btn-primary")
page.click("button[data-id='submit']")

# Text
page.click("text=Submit")
page.click("button:has-text('Continue')")

# XPath
page.click("xpath=//button[@name='login']")

# Role (recommended)
page.get_by_role("button", name="Submit").click()
page.get_by_label("Email").fill("user@example.com")
page.get_by_placeholder("Search...").fill("query")
```

## Common Patterns

### Login Flow

```python
page.goto("https://example.com/login")
page.fill("#email", email)
page.fill("#password", password)
page.click("button[type='submit']")
page.wait_for_url("**/dashboard")
print("Logined:", page.url)
page.screenshot(path="after_login.png")
```

### Paginated Scraping

```python
results = []
while True:
    items = page.query_selector_all(".result-item")
    for item in items:
        results.append(item.inner_text())
    next_btn = page.query_selector(".pagination .next")
    if not next_btn or next_btn.is_disabled():
        break
    next_btn.click()
    page.wait_for_load_state("networkidle")
```

### Multi-page Navigation

```python
pages = ["https://example.com/page1", "https://example.com/page2"]
for url in pages:
    page.goto(url, wait_until="domcontentloaded")
    page.screenshot(path=f"screenshot-{url.split('/')[-1]}.png")
```

## Executing via Bash

For quick one-off tasks, use `python -c`:

```bash
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://example.com')
    print(page.title())
    browser.close()
"
```

Or save a script and execute:

```bash
cat > /tmp/browser_script.py << 'EOF'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    ...
    browser.close()
EOF
python /tmp/browser_script.py
```

## Error Handling

```python
try:
    page.goto(url, timeout=30000)
except Exception as e:
    print(f"Navigation failed: {e}")
    page.screenshot(path="error.png")

try:
    page.click(".missing-button", timeout=5000)
except Exception:
    print("Button not found, trying alternative...")
    page.click(".fallback-button")
```

## Best Practices

- Always use `headless=True` unless user asks for visible browser
- Set reasonable timeouts (10-30s for navigation)
- Close browser after use to free resources
- Screenshot on errors for debugging
- Prefer `get_by_role/get_by_label` over fragile CSS selectors
- Wait for network idle before extracting content
