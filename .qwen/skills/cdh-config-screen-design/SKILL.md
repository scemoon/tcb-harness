---
name: cdh-config-screen-design
description: How to redesign the CDH config screen TUI with list navigation
source: auto-skill
extracted_at: '2026-05-29T11:52:30.278Z'
---

# CDH Config Screen Design

## Context

The `cdha/config_screen.py` was redesigned from a form-based layout to a list navigation UI.

## Approach: List-Based Navigation

### Key Components

**1. ConfigItem Widget**
- Inherits from `Static, can_focus=True`
- Tracks `item_type`: `"section"` (menu items), `"back"` (navigation), `"field"` (config fields)
- Renders based on type:
  - `"section"`: `"> {self.label}"`
  - `"back"`: `"< {self.label}"`
  - `"field"`: `"  {self.label:<18} {self.value}"`

**2. View State**
- `view: var[str]` — `"menu"` or `"section"`
- `cursor: var[int]` — current selection index
- `_breadcrumb` list tracks navigation path

**3. Bindings**
| Key | Action | Description |
|-----|--------|-------------|
| up/down | cursor_up/cursor_down | Move selection + focus item |
| left | go_back | Navigate back or exit |
| right | go_enter | Enter section |
| enter | confirm | Same as go_enter |
| escape | cancel | Exit app |

**4. Color Scheme (Black/White/Gray)**
```
background:     #000  (pure black)
surface dark:   #222  (breadcrumb)
surface mid:    #333  (header, button-row)
surface light:  #555  (button bg, border)
text:           #fff  (white)
text muted:     #aaa  (breadcrumb)
highlight:      #444  (hover + focus)
```

**5. Layout Structure**
```
Screen { align: center middle; }    # Center the dialog

#dialog        (60w x 25h) — bordered container
#header        (2 rows)    — title bar
#breadcrumb    (1 row)      — navigation path
#content       (1fr)        — scrollable item list
#button-row    (3 rows)    — Save / Reset / Quit
```

**6. Center & Size Constraints**
```css
#dialog {
    width: 60;
    height: 25;
    background: #000;
    border: solid #555;
}

Screen {
    align: center middle;
}
```

**7. Focus & Cursor Management**
- On mount: build menu, call `_clamp_cursor()` which auto-focuses first item
- On up/down: move cursor, call `_highlight_cursor()`, then `items[self.cursor].focus()`
- `_highlight_cursor()` uses CSS class `"-focus"` (not `"focus"`)
- CSS: `ConfigItem:hover, ConfigItem.-focus { background: #444; }`

**8. Section Building**
```python
def _build_section(self, section_id: str) -> None:
    self._section_fields = [ConfigItem("__back__", "Back to Menu", item_type="back")]
    # ... add fields ...
    self.cursor = 0  # Reset cursor for new section
```

## Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `NameError: name 'on' is not defined` | Missing import | `from textual import on` |
| `ImportError: cannot import 'Horizontal'` | Wrong module | `from textual.containers import Horizontal` |
| `MountError: Can't mount before mounted` | `mount()` in `compose()` | Move to `on_mount()` or use `yield` |
| `cursor: pointer` invalid | Textual CSS unsupported | Remove, use `can_focus=True` |
| Widget used in `with` | `Widget` can't be context manager | Use `with Vertical()` or `with Horizontal()` |

## Lessons Learned

- **Cursor focus**: Always call `items[cursor].focus()` after moving cursor
- **View switching**: Rebuild `_section_fields`, reset `cursor = 0`, call `_refresh_items()`
- **CSS class names**: Use `"-focus"` not `"focus"` (prefix dash for custom classes)
- **Import from containers**: `Horizontal`, `Vertical` come from `textual.containers`
- **Compose pattern**: Keep `compose()` simple — yield only, mount in `on_mount()` if needed