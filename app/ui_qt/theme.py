# app/ui_qt/theme.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    # Palette
    bg: str = "#121417"
    panel: str = "#161a1f"
    sidebar: str = "#0e1114"
    border: str = "#1f2328"
    text: str = "#e6e6e6"

    nav_hover: str = "#1a1f25"
    nav_pressed: str = "#222832"
    nav_active_bg: str = "#222832"
    nav_active_border: str = "#2d3440"

    # Typography
    font_family: str = "Segoe UI, Inter, Arial"
    font_size_px: int = 14

    # Radii / spacing
    radius_px: int = 8
    nav_radius_px: int = 6


def build_qss(t: Theme) -> str:
    """Return the app stylesheet (QSS) built from a Theme."""
    return f"""
/* =========================
   Global
   ========================= */
QWidget {{
    background-color: {t.bg};
    color: {t.text};
    font-family: {t.font_family};
    font-size: {t.font_size_px}px;
}}

/* =========================
   Sidebar
   ========================= */
#Sidebar {{
    background-color: {t.sidebar};
    border-right: 1px solid {t.border};
}}

#SidebarTitle {{
    font-size: 16px;
    font-weight: 600;
    padding-bottom: 8px;
}}

/* Nav buttons */
#NavButton {{
    background-color: transparent;
    border: none;
    text-align: left;
    padding: 8px 10px;
    border-radius: {t.nav_radius_px}px;
}}

#NavButton:hover {{
    background-color: {t.nav_hover};
}}

#NavButton:pressed {{
    background-color: {t.nav_pressed};
}}

#NavButton[active="true"] {{
    background-color: {t.nav_active_bg};
    border: 1px solid {t.nav_active_border};
}}

/* =========================
   Ribbon / Header
   ========================= */
#Ribbon {{
    background-color: {t.panel};
    border: 1px solid {t.border};
    border-radius: {t.radius_px}px;
}}

#RibbonTitle {{
    font-size: 16px;
    font-weight: 600;
}}

/* =========================
   Pages
   ========================= */
#Page {{
    background-color: {t.panel};
    border: 1px solid {t.border};
    border-radius: {t.radius_px}px;
}}

#PageTitle {{
    font-size: 18px;
    font-weight: 600;
}}
""".strip()
