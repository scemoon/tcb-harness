from __future__ import annotations

from textual.theme import Theme


CDH_DARK = Theme(
    name="cdh-dark",
    dark=True,
    primary="#7aa2f7",
    secondary="#7dcfff",
    accent="#bb9af7",
    warning="#e0af68",
    error="#f7768e",
    success="#9ece6a",
    foreground="#c0caf5",
    background="#0f0f1a",
    surface="#1a1b26",
    boost="#3C3C3C",
    variables={
        "surface_alt": "#151728",
        "text_bright": "#a9b1d6",
        "text_dim": "#565f89",
        "border": "#3C3C3C",
        "border_focus": "#7aa2f7",
        "info": "#89b4fa",
        "highlight_bg": "#3b4261",
        "highlight_text": "#c0caf5",
        "overlay": "rgba(0, 0, 0, 0.6)",
    },
)

CDH_LIGHT = Theme(
    name="cdh-light",
    dark=False,
    primary="#4a9eff",
    secondary="#00b4d8",
    accent="#6c63ff",
    warning="#e67700",
    error="#c92a2a",
    success="#2b8a3e",
    foreground="#1a1b26",
    background="#f8f9fa",
    surface="#ffffff",
    boost="#CCCCCC",
    variables={
        "surface_alt": "#e9ecef",
        "text_bright": "#495057",
        "text_dim": "#868e96",
        "border": "#CCCCCC",
        "border_focus": "#4a9eff",
        "info": "#4a9eff",
        "highlight_bg": "#dee2e6",
        "highlight_text": "#1a1b26",
        "overlay": "rgba(0, 0, 0, 0.15)",
    },
)

THEMES = {"cdh-dark": CDH_DARK, "cdh-light": CDH_LIGHT}
