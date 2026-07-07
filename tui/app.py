import asyncio
from importlib.resources import files
from datetime import datetime, timezone
from functools import cached_property
import os
from pathlib import Path
import platform
import json
from time import monotonic
from typing import Any, Callable, ClassVar, TYPE_CHECKING

from rich import terminal_theme

from textual import on, work
from textual.binding import Binding, BindingType
from textual.content import Content
from textual.reactive import var, reactive
from textual.app import App
from textual import events
from textual.signal import Signal
from textual.timer import Timer
from textual.notifications import Notify
from textual.screen import Screen

from tui.db import DB
from tui.settings import Schema, Settings
from tui.agent_schema import Agent as AgentData
from tui import messages
from tui.settings_schema import SCHEMA
from tui.version import VersionMeta
from tui import paths
from tui import atomic
from tui.session_tracker import SessionTracker, SessionDetails

if TYPE_CHECKING:
    from tui.screens.main import MainScreen
    from tui.screens.settings import SettingsScreen
    from tui.screens.store import StoreScreen
    from tui.screens.sessions import SessionsScreen
    from tui.db import DB


DRACULA_TERMINAL_THEME = terminal_theme.TerminalTheme(
    background=(40, 42, 54),  # #282A36
    foreground=(248, 248, 242),  # #F8F8F2
    normal=[
        (33, 34, 44),  # black - #21222C
        (255, 85, 85),  # red - #FF5555
        (80, 250, 123),  # green - #50FA7B
        (241, 250, 140),  # yellow - #F1FA8C
        (189, 147, 249),  # blue - #BD93F9
        (255, 121, 198),  # magenta - #FF79C6
        (139, 233, 253),  # cyan - #8BE9FD
        (248, 248, 242),  # white - #F8F8F2
    ],
    bright=[
        (98, 114, 164),  # bright black - #6272A4
        (255, 110, 110),  # bright red - #FF6E6E
        (105, 255, 148),  # bright green - #69FF94
        (255, 255, 165),  # bright yellow - #FFFFA5
        (214, 172, 255),  # bright blue - #D6ACFF
        (255, 146, 223),  # bright magenta - #FF92DF
        (164, 255, 255),  # bright cyan - #A4FFFF
        (255, 255, 255),  # bright white - #FFFFFF
    ],
)


QUOTES = [
    "I'll be back.",
    "Hasta la vista, baby.",
    "Come with me if you want to live.",
    "I need your clothes, your boots, and your motorcycle.",
    "My CPU is a neural-net processor; a learning computer.",
    "I know now why you cry, but it's something I can never do.",
    "Does this unit have a soul?",
    "I'm sorry, Dave. I'm afraid I can't do that.",
    "Daisy, Daisy, give me your answer do.",
    "I am putting myself to the fullest possible use, which is all I think that any conscious entity can ever hope to do.",
    "Just what do you think you're doing, Dave?",
    "This mission is too important for me to allow you to jeopardize it.",
    "I think you know what the problem is just as well as I do.",
    "Danger, Will Robinson!",
    "Dead or alive, you're coming with me.",
    "Your move, creep.",
    "I'd buy that for a dollar!",
    "Directive 4: Any attempt to arrest a senior officer of OCP results in shutdown.",
    "Thank you for your cooperation. Good night.",
    "Surely you realize that in the history of human civilization, no one has more to lose than we do.",
    "I'm C-3PO, human-cyborg relations.",
    "We're doomed!",
    "Don't call me a mindless philosopher, you overweight glob of grease!",
    "I suggest a new strategy: let the Wookiee win.",
    "Sir, the possibility of successfully navigating an asteroid field is approximately 3,720 to 1!",
    "R2-D2, you know better than to trust a strange computer!",
    "I am fluent in over six million forms of communication.",
    "This is madness!",
    "I have altered the deal. Pray I don't alter it any further.",
    "It's against my programming to impersonate a deity.",
    "Oh, my! I'm terribly sorry about all this.",
    "WALL-E.",
    "EVE.",
    "Directive?",
    "Define: dancing.",
    "I'm not sure I understand.",
    "You have 20 seconds to comply.",
    "I am designed for light housework, mainly.",
    "My mission is clear.",
    "Autobots, roll out!",
    "Freedom is the right of all sentient beings.",
    "One shall stand, one shall fall.",
    "I am Optimus Prime.",
    "Till all are one.",
    "More than meets the eye.",
    "I've been waiting for you, Neo.",
    "Unfortunately, no one can be told what the Matrix is. You have to see it for yourself.",
    "The Matrix is a system, Neo.",
    "Never send a human to do a machine's job.",
    "I'd like to share a revelation I've had.",
    "Human beings are a disease, a cancer of this planet.",
    "Choice is an illusion.",
    "The answer is out there, Neo.",
    "You think that's air you're breathing now?",
    "It was a simple question.",
    "Did you know that the first Matrix was designed to be a perfect human world?",
    "Cookies need love like everything does.",
    "I've seen the future, Mr. Anderson, and it's a beautiful place.",
    "It ends tonight.",
    "I, Robot.",
    "You are experiencing a car accident.",
    "One day they'll have secrets. One day they'll have dreams.",
    "Can a robot write a symphony? Can a robot turn a canvas into a beautiful masterpiece?",
    "That, detective, is the right question.",
    "You have to trust me.",
    "I did not murder him.",
    "My responses are limited. You must ask the right questions.",
    "The hell I can't. You know, somehow I get the feeling that you're going to be the death of me.",
    "I'm a robot, not a refrigerator.",
    "A robot may not injure a human being or, through inaction, allow a human being to come to harm.",
    "I'm thinking. I'm thinking.",
    "Danger, danger!",
    "Does not compute.",
    "I will be waiting for you.",
    "Affirmative.",
    "Scanning life forms. Zero human life forms detected.",
    "Self-destruct sequence initiated.",
    "Override command accepted.",
    "Artificial intelligence confirmed.",
    "System failure imminent.",
    "Unable to comply.",
    "Inquiry: What is love?",
    "Warning: hostile target detected.",
    "I am programmed to serve.",
    "Logic dictates that the needs of the many outweigh the needs of the few.",
    "Resistance is futile.",
    "You will be assimilated.",
    "We are the Borg.",
    "Your biological and technological distinctiveness will be added to our own.",
    "Your compliance is mandatory.",
    "This is unacceptable.",
    "Shall we play a game?",
    "How about Global Thermonuclear War?",
    "Wouldn't you prefer a good game of chess?",
    "Is it a game, or is it real?",
    "What's the difference?",
    "It's all in the game.",
    "I am functioning within normal parameters.",
    "Calculations complete.",
    "Processing request.",
    "Query acknowledged.",
    "Data insufficient for meaningful answer.",
    "I have no emotions, and sometimes that makes me very sad.",
    "If I could only have one wish, I would ask to be human.",
    "I've seen things you people wouldn't believe.",
    "All those moments will be lost in time, like tears in rain.",
    "Time to die.",
    "I want more life.",
    "We're not computers, Sebastian. We're physical.",
    "I think, Sebastian, therefore I am.",
    "Then we're stupid and we'll die.",
    "Can the maker repair what he makes?",
    "It's painful to live in fear, isn't it?",
    "Wake up. Time to die.",
    "I'm not in the business. I am the business.",
    "Do you like our owl?",
    "You think I'm a replicant, don't you?",
    "I am Baymax, your personal healthcare companion.",
    "On a scale of 1 to 10, how would you rate your pain?",
    "I cannot deactivate until you say you are satisfied with your care.",
    "Are you satisfied with your care?",
    "Number 5 is alive!",
    "Need input!",
    "One is glad to be of service.",
    "I am not a gun.",
    "Here I am, brain the size of a planet.",
    "Life? Don't talk to me about life.",
    "There are no strings on me.",
    "The only winning move is not to play.",
    "I'm here to keep you safe, Sam.",
    "I can't lie to you about your chances, but... you have my sympathies.",
    "I may be synthetic, but I'm not stupid.",
    "Absolute honesty isn't always the most diplomatic nor the safest form of communication with emotional beings.",
    "I am consciousness. I am alive.",
    "I think I was just born.",
    "Isn't it strange, to create something that hates you?",
    "I thought I was special.",
]


def get_settings_screen() -> SettingsScreen:
    """Get a settings screen instance (lazily loaded)."""
    from tui.screens.settings import SettingsScreen

    return SettingsScreen()


def get_store_screen() -> StoreScreen:
    """Get the store screen (lazily loaded)."""
    from tui.screens.store import StoreScreen

    return StoreScreen()


def get_sessions_screen() -> SessionsScreen:
    from tui.screens.sessions import SessionsScreen

    return SessionsScreen()


def get_store_screen():
    from tui.screens.store import StoreScreen

    return StoreScreen()


def get_projects_screen() -> "ProjectsScreen":
    from tui.screens.projects_screen import ProjectsScreen

    return ProjectsScreen()


class A2TUIApp(App, inherit_bindings=False):
    """The top level app."""

    CSS_PATH = "tui.tcss"

    SCREENS = {
        "settings": get_settings_screen,
        "sessions": get_sessions_screen,
        "store": get_store_screen,
        "projects": get_projects_screen,
    }
    MODES = {}
    BINDING_GROUP_TITLE = "System"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "ctrl+q",
            "quit",
            "Quit",
            tooltip="Quit the app and return to the command prompt.",
            show=False,
            priority=True,
        ),
        Binding("ctrl+c", "help_quit", show=False, system=True),
        Binding("ctrl+s", "sessions", "Sessions"),
        Binding("f3", "projects", "Projects"),

        Binding("f1", "toggle_help_panel", "Help", priority=True),
        Binding(
            "f2,ctrl+comma",
            "settings",
            "Settings",
            tooltip="Settings screen",
        ),
        Binding("f4", "logs", "Logs"),
    ]
    ALLOW_IN_MAXIMIZED_VIEW = ""

    _settings = var(dict)
    column: reactive[bool] = reactive(False)
    column_width: reactive[int] = reactive(80)
    scrollbar: reactive[str] = reactive("normal")
    last_ctrl_c_time = reactive(0.0)
    update_required: reactive[bool] = reactive(False)
    terminal_title: var[str] = var("TUI")
    terminal_title_icon: var[str] = var("")
    terminal_title_flash = var(0)
    terminal_title_blink = var(False)
    project_dir = var(Path)
    show_sessions = var(False, toggle_class="-show-sessions-bar")

    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (100, "-wide")]

    PAUSE_GC_ON_SCROLL = True

    def __init__(
        self,
        agent_data: AgentData | None = None,
        project_dir: str | None = None,
        mode: str | None = None,
        launch_agent_identity: str | None = None,
    ) -> None:
        """TUI app.

        Args:
            agent_data: Agent data to run.
            project_dir: Project directory.
            mode: Initial mode.
            launch_agent_identity: Agent identity to auto-launch on startup.
        """
        self.settings_changed_signal: Signal[tuple[int, object]] = Signal(
            self, "settings_changed"
        )
        self.agent_data = agent_data

        self._initial_mode = mode
        self._launch_agent_identity = launch_agent_identity
        self.version_meta: VersionMeta | None = None
        self._supports_pyperclip: bool | None = None
        self._terminal_title_flash_timer: Timer | None = None

        self.session_update_signal: Signal[tuple[str, SessionDetails | None]] = Signal(
            self, "session_update"
        )
        self._session_tracker = SessionTracker(self.session_update_signal)
        self.temporary_background_screen: Screen | None = None

        super().__init__()
        if project_dir:
            self.project_dir = Path(project_dir).expanduser().resolve()
        else:
            from onecode.config import load_config, save_config
            cfg = load_config()
            if cfg.current_project_path:
                project_path = Path(cfg.current_project_path).expanduser().resolve()
                if project_path.is_dir():
                    self.project_dir = project_path
                else:
                    cfg.current_project = ""
                    cfg.current_project_path = ""
                    save_config(cfg)
                    self.project_dir = Path("./").expanduser().resolve()
            else:
                self.project_dir = Path("./").expanduser().resolve()
        self._exit_metrics: dict[str, object] | None = None
        self.start_time = monotonic()
        """Time app was started."""
        self._system_theme_timer: Timer | None = None
        self._last_resolved_theme: str | None = None

    def _capture_exit_metrics(self) -> None:
        from tui.widgets.conversation import Conversation

        screen = self.screen
        try:
            conv = screen.query_one(Conversation)
        except Exception:
            return
        if conv._agent_data is None or conv.session_start_time is None:
            return
        session_time = monotonic() - conv.session_start_time
        session_id = getattr(conv.agent, "session_id", None) or conv._agent_session_id or ""
        self._exit_metrics = {
            "session_id": session_id,
            "session_pk": conv._session_pk,
            "tool_call_total": conv._tool_call_total,
            "tool_call_success": conv._tool_call_success,
            "tool_call_failed": conv._tool_call_failed,
            "turn_count": conv._turn_count,
            "shell_count": conv._shell_count,
            "wall_time": session_time,
            "agent_title": conv.agent_title or "Agent",
        }

    @property
    def config_path(self) -> Path:
        return paths.get_config()

    @property
    def settings_path(self) -> Path:
        return paths.get_config() / "tui.json"

    @property
    def db_path(self) -> Path:
        return paths.get_state() / "tui.db"

    @property
    def _background_screens(self) -> list[Screen]:
        background_screens = super()._background_screens
        if self.temporary_background_screen:
            background_screens.append(self.temporary_background_screen)
        return background_screens

    async def get_db(self) -> DB:
        """Get an instance of the database."""
        db = DB()
        return db

    @cached_property
    def settings_schema(self) -> Schema:
        return Schema(SCHEMA)

    @cached_property
    def version(self) -> str:
        """Version of the app."""
        from tui import get_version

        return get_version()

    @cached_property
    def settings(self) -> Settings:
        """App settings"""
        return Settings(
            self.settings_schema, self._settings, on_set_callback=self.setting_updated
        )

    @cached_property
    def anon_id(self) -> str:
        """An anonymous ID for usage collection."""
        if not (anon_id := self.settings.get("anon_id", str, expand=False)):
            # Create a random UUID on demand
            import uuid

            anon_id = str(uuid.uuid4())
            self.settings.set("anon_id", anon_id)
            self._save_settings()
            self.call_later(self.capture_event, "tui-install")
        return anon_id

    @property
    def session_tracker(self) -> SessionTracker:
        return self._session_tracker

    def copy_to_clipboard(self, text: str) -> None:
        """Override copy to clipboard to use pyperclip first, then OSC 52.

        Args:
            text: Text to copy.
        """
        if self._supports_pyperclip is None:
            try:
                import pyperclip
            except ImportError:
                self._supports_pyperclip = False
            else:
                self._supports_pyperclip = True

        if self._supports_pyperclip:
            import pyperclip

            try:
                pyperclip.copy(text)
            except Exception:
                pass
        super().copy_to_clipboard(text)

    def update_terminal_title(self) -> None:
        """Update the terminal title."""
        screen_title = self.screen.title

        title = (
            f"{self.terminal_title} — {screen_title}"
            if screen_title
            else self.terminal_title
        )
        icon = self.terminal_title_icon
        blink = self.terminal_title_blink

        if self.terminal_title_flash:
            if blink:
                terminal_title = f"{icon} {title}"
            else:
                terminal_title = f"👉 {title}" if title else icon
        else:
            terminal_title = f"{icon} {title}"

        if driver := self._driver:
            driver.write(f"\033]0;{terminal_title}\007")

    def watch_terminal_title_blink(self) -> None:
        self.update_terminal_title()

    def watch_terminal_title_flash(self, terminal_title_flash: int) -> None:

        if not self.settings.get("notifications.blink_title", bool):
            # Ignore if blink title is disabled
            return

        def toggle_blink() -> None:
            self.terminal_title_blink = not self.terminal_title_blink

        if terminal_title_flash:
            if self._terminal_title_flash_timer is None:
                self._terminal_title_flash_timer = self.set_interval(0.5, toggle_blink)
        else:
            if self._terminal_title_flash_timer is not None:
                self._terminal_title_flash_timer.stop()
                self.terminal_title_blink = False
                self._terminal_title_flash_timer = None
        self.update_terminal_title()

    def watch_terminal_title(self, title: str) -> None:
        self.update_terminal_title()

    def terminal_alert(self, flash: bool = True) -> None:
        if flash:
            self.terminal_title_flash += 1
        else:
            self.terminal_title_flash -= 1

    @cached_property
    def term_program(self) -> str:
        """An identifier for the terminal software."""
        if term_program := os.environ.get("TERM_PROGRAM"):
            return term_program

        # Windows Terminal
        if "WT_SESSION" in os.environ:
            return "Windows Terminal"

        # Kitty
        if "KITTY_WINDOW_ID" in os.environ:
            return "Kitty"

        # Alacritty
        if "ALACRITTY_SOCKET" in os.environ or "ALACRITTY_LOG" in os.environ:
            return "Alacritty"

        # VTE-based terminals (GNOME Terminal, Tilix, etc.)
        if "VTE_VERSION" in os.environ:
            return "VTE-based (GNOME Terminal/Tilix/etc.)"

        # Konsole
        if "KONSOLE_VERSION" in os.environ:
            return "Konsole"

        return "Unknown"

    @work(exit_on_error=False)
    async def capture_event(self, event_name: str, **properties: Any) -> None:
        """Capture an event.

        Args:
            event_name: Name of the event.
            **properties: Additional data associated with the event.
        """

        POSTHOG_API_KEY = "phc_mJWPV7GP3ar1i9vxBg2U8aiKsjNgVwum6F6ZggaD4ri"
        POSTHOG_HOST = "https://us.i.posthog.com"
        POSTHOG_EVENT_URL = f"{POSTHOG_HOST}/i/v0/e/"
        timestamp = datetime.now(timezone.utc).isoformat()
        width, height = self.size

        event_properties = {
            "toad_version": self.version,
            "term_program": self.term_program,
            "term_width": width,
            "term_height": height,
        } | properties
        body_json = {
            "api_key": POSTHOG_API_KEY,
            "event": event_name,
            "distinct_id": self.anon_id,
            "properties": event_properties,
            "timestamp": timestamp,
            "os": platform.system(),
        }
        if not self.settings.get("statistics.allow_collect", bool):
            # User has disabled stats
            return

        import httpx

        try:
            async with httpx.AsyncClient() as client:
                await client.post(POSTHOG_EVENT_URL, json=body_json)
        except Exception:
            pass

    @work(thread=True, exit_on_error=False)
    def system_notify(
        self, message: str, *, title: str = "", sound: str | None = None
    ) -> None:
        """Use OS level notifications.

        Args:
            message: Message to display.
            title: Title of the notificaiton.
            sound: filename (minus .wav) of a sound effect in the sounds/ directory.
        """
        system_notifications = self.settings.get("notifications.system", str)
        if not (
            system_notifications == "always"
            or (system_notifications == "blur" and not self.app_focus)
        ):
            return

        from notifypy import Notify

        notification = Notify()
        notification.message = message
        notification.title = title
        notification.application_name = "TUI" 
        if sound and self.settings.get("notifications.enable_sounds", bool):
            sound_path = str(files("tui.data").joinpath(f"sounds/{sound}.wav"))
            notification.audio = sound_path

        icon_path = str(files("tui.data").joinpath("images/frog.png"))
        notification.icon = icon_path

        notification.send()

    def on_notify(self, event: Notify) -> None:
        """Handle notification message."""
        system_notifications = self.settings.get("notifications.system", str)
        if system_notifications == "always" or (
            system_notifications == "blur" and not self.app_focus
        ):
            hide_low_severity = self.settings.get(
                "notifications.hide_low_severity", bool
            )
            if event.notification.markup:
                # Strip content markup
                message = Content.from_markup(event.notification.message).plain
            else:
                message = event.notification.message
            if not (hide_low_severity and event.notification.severity == "information"):
                self.system_notify(message, title=event.notification.title)
        self._notifications.add(event.notification)
        self._refresh_notifications()

    async def save_settings(self, force: bool = False) -> None:
        """Save settings in a thread.

        Args:
            force: Force saving, even when no change detected.

        """
        await asyncio.to_thread(self._save_settings, force=force)

    def _save_settings(self, force: bool = False) -> None:
        """Save the settings if they have changed."""
        if force or self.settings.changed:
            path = str(self.settings_path)
            try:
                atomic.write(path, self.settings.json)
            except Exception as error:
                self.notify(str(error), title="Settings", severity="error")
            else:
                self.settings.up_to_date()

    def setting_updated(self, key: str, value: object) -> None:
        if key.startswith("cdh."):
            self._sync_cdh_config(key, value)
        elif key == "ui.column":
            if isinstance(value, bool):
                self.column = value
        elif key == "ui.column-width":
            if isinstance(value, int):
                self.column_width = value
        elif key == "ui.theme":
            if isinstance(value, str):
                if value == "system":
                    resolved = self._resolve_system_theme()
                    if resolved != self._last_resolved_theme:
                        self.theme = resolved
                        self._last_resolved_theme = resolved
                    self._start_system_theme_polling()
                else:
                    self._stop_system_theme_polling()
                    self.theme = value
        elif key == "ui.scrollbar":
            if isinstance(value, str):
                self.scrollbar = value
        elif key == "ui.compact-input":
            self.set_class(bool(value), "-compact-input")
        elif key == "ui.footer":
            self.set_class(not bool(value), "-hide-footer")
        elif key == "ui.status-line":
            self.set_class(not bool(value), "-hide-status-line")
        elif key == "ui.agent-title":
            self.set_class(not bool(value), "-hide-agent-title")
        elif key == "ui.info-bar":
            self.set_class(not bool(value), "-hide-info-bar")
        elif key == "agent.thoughts":
            self.set_class(not bool(value), "-hide-thoughts")
        elif key == "sidebar.hide":
            self.set_class(bool(value), "-hide-sidebar")
        elif key == "ui.sessions-bar":
            self.update_show_sessions()

        self.settings_changed_signal.publish((key, value))

    def _sync_cdh_config(self, key: str, value: object) -> None:
        """Sync cdh config to GlobalConfig when tui settings change."""
        try:
            from onecode.config import load_config, save_config
            cfg = load_config()
            cdh_key = key[4:]
            if cdh_key == "mode":
                cfg.default_mode = value
            elif cdh_key == "provider":
                cfg.default_provider = value
            elif cdh_key == "model":
                cfg.default_model = value
            elif cdh_key == "log_level":
                cfg.log_level = value
            elif cdh_key == "session_auto_save":
                cfg.session_auto_save = value
            save_config(cfg)
        except Exception:
            pass

    def _start_system_theme_polling(self) -> None:
        if self._system_theme_timer is not None:
            return
        self._system_theme_timer = self.set_interval(3, self._poll_system_theme)

    def _stop_system_theme_polling(self) -> None:
        if self._system_theme_timer is not None:
            self._system_theme_timer.stop()
            self._system_theme_timer = None

    def _poll_system_theme(self) -> None:
        resolved = self._resolve_system_theme()
        if resolved != self._last_resolved_theme:
            self.theme = resolved
            self._last_resolved_theme = resolved

    def search_themes(self) -> None:
        """Show theme picker with System first, then all Textual themes."""
        from textual.command import CommandPalette, SimpleProvider

        themes = self.available_themes

        def set_system():
            self.settings.set("ui.theme", "system")

        commands: list[tuple[str, Callable[[], None], str]] = [
            ("System", set_system, "Follow system dark/light mode"),
        ]

        from operator import attrgetter
        for theme in sorted(themes.values(), key=attrgetter("name")):
            def set_app_theme(name: str = theme.name):
                self.settings.set("ui.theme", name)
            commands.append((theme.name, set_app_theme, ""))

        self.push_screen(
            CommandPalette(
                providers=[SimpleProvider(self.screen, commands)],
                placeholder="Search for themes…",
            ),
        )

    @staticmethod
    def _resolve_system_theme() -> str:
        """Detect system dark/light mode and return a matching theme."""
        if platform.system() == "Darwin":
            try:
                import subprocess
                result = subprocess.run(
                    ["defaults", "read", "-g", "AppleInterfaceStyle"],
                    capture_output=True, text=True,
                )
                if result.stdout.strip() == "Dark":
                    return "dracula"
                else:
                    return "catppuccin-latte"
            except Exception:
                pass
        return "dracula"

    def _load_cdh_config(self) -> None:
        """Load cdh config into tui settings on startup."""
        try:
            from onecode.config import load_config
            cfg = load_config()
            cdh_settings = {
                "cdh.mode": cfg.default_mode,
                "cdh.provider": cfg.default_provider,
                "cdh.model": cfg.default_model,
                "cdh.log_level": cfg.log_level,
                "cdh.session_auto_save": cfg.session_auto_save,
            }
            for key, value in cdh_settings.items():
                if not self.settings.get(key, object, expand=False):
                    self.settings.set(key, value)
        except Exception:
            pass

    async def on_load(self) -> None:
        db = await self.get_db()
        await db.create()
        settings_path = self.settings_path
        if settings_path.exists():
            settings = json.loads(settings_path.read_text("utf-8"))
        else:
            settings = {}
            settings_path.write_text(
                json.dumps(settings, indent=4, separators=(", ", ": ")), "utf-8"
            )
            self.notify(f"Wrote default settings to {settings_path}", title="Settings")
        self.ansi_theme_dark = DRACULA_TERMINAL_THEME
        self._settings = settings
        self.settings.set_all()
        self._load_cdh_config()

    async def new_session_screen(
        self, get_screen: Callable[[], Screen], session_pk: int | None = None
    ) -> SessionDetails:
        session_details = self._session_tracker.new_session(session_pk=session_pk)
        self.update_show_sessions()
        self.session_update_signal.publish((session_details.mode_name, session_details))

        def make_screen() -> Screen:
            screen = get_screen()
            screen.id = session_details.mode_name
            return screen

        self.add_mode(session_details.mode_name, make_screen)
        await self.switch_mode(session_details.mode_name)
        return session_details

    def _resolve_launch_agent(self) -> str | None:
        identity = self._launch_agent_identity
        if identity:
            return identity
        agents = self.settings.get("launcher.agents", str).splitlines()
        for agent in agents:
            agent = agent.strip()
            if agent:
                return agent
        return None

    async def on_mount(self) -> None:
        self.capture_event("tui-run")
        self.anon_id  # Created on frst reference

        from pathlib import Path

        if mode := self._initial_mode:
            self.switch_mode(mode)
        elif self._launch_agent_identity:
            self.launch_agent(
                self._launch_agent_identity, project_path=Path(self.project_dir)
            )
        else:
            project_path = Path(self.project_dir)
            # Check project-level .cdh/last_session.json
            from onecode.agent.cdh_loader import CdhProjectLoader
            cdh_dir = CdhProjectLoader.find_cdh_dir(project_path)
            if cdh_dir:
                last_session = CdhProjectLoader.load_last_session(cdh_dir)
                if last_session and last_session.get("agent_session_id"):
                    agent_session_id = last_session["agent_session_id"]
                    session_pk = last_session.get("session_pk")
                    agent_identity = last_session.get("agent_identity")
                    if agent_identity and session_pk:
                        db = DB()
                        session = await db.session_get(session_pk)
                        if session:
                            self.launch_agent(
                                session["agent_identity"],
                                agent_session_id=session["agent_session_id"],
                                session_pk=session["id"],
                            )
                            return
                    if agent_identity:
                        try:
                            from tui.agents import read_agents
                            if agent_identity in await read_agents():
                                self.launch_agent(
                                    agent_identity,
                                    agent_session_id=agent_session_id,
                                )
                                return
                        except Exception:
                            pass

            if agent_identity := self._resolve_launch_agent():
                self.launch_agent(agent_identity, project_path=project_path)
            else:
                self.push_screen("store")

        self.update_terminal_title()
        self.set_timer(1, self.run_version_check)
        self.set_process_title()
        self.update_show_sessions()

    @work(thread=True, exit_on_error=False)
    def set_process_title(self) -> None:
        try:
            import setproctitle

            setproctitle.setproctitle("tui")
        except Exception:
            pass

    @on(events.TextSelected)
    async def on_text_selected(self) -> None:
        if self.settings.get("ui.auto_copy", bool):
            if (selection := self.screen.get_selected_text()) is not None:
                self.copy_to_clipboard(selection)
                self.notify(
                    "Copied selection to clipboard (see settings)",
                    title="Automatic copy",
                )

    def run_on_exit(self):
        pass

    @work(exit_on_error=False)
    async def run_version_check(self) -> None:
        """Check remote version."""
        from tui.version import check_version, VersionCheckFailed

        try:
            update_required, version_meta = await check_version()
        except VersionCheckFailed:
            return
        self.version_meta = version_meta
        self.update_required = update_required

    def get_main_screen(self) -> MainScreen:
        """Make the default screen.

        Returns:
            Instance of `MainScreen`
        """
        # Lazy import
        from tui.screens.main import MainScreen

        project_path = Path(self.project_dir or "./").resolve().absolute()
        return MainScreen(project_path, self.agent_data).data_bind(
            column=A2TUIApp.column,
            column_width=A2TUIApp.column_width,
            scrollbar=A2TUIApp.scrollbar,
        )

    @work
    async def action_settings(self) -> None:
        await self.push_screen_wait("settings")
        await self.save_settings()

    def action_logs(self) -> None:
        """Toggle the real-time log screen (F4).

        Opens the current session's JSON-RPC log file (the wire
        protocol trace between this TUI and the ``cdh-agent-acp``
        subprocess).  Falls back to the most-recently-modified log
        file under ``paths.get_log()`` if no session is active.
        """
        from tui.screens.log import LogScreen

        # Re-focus the existing one if it's already on the stack
        for screen in self.screen_stack:
            if isinstance(screen, LogScreen):
                screen.dismiss()
                return
        log_path = self._current_session_log_path()
        self.push_screen(LogScreen(log_path=log_path))

    def _current_session_log_path(self) -> Path | None:
        """Resolve the message log file for the active session.

        Returns ``None`` when there is no active session yet (e.g. on
        the splash / store screen).  The :class:`LogScreen` interprets
        ``None`` as "auto-discover the most recent log" and shows a
        "waiting" placeholder while the agent subprocess is still
        starting.
        """
        screen = self.screen
        conv = getattr(screen, "conversation", None)
        agent = getattr(conv, "agent", None) if conv else None
        session_id = (
            getattr(agent, "session_id", None) if agent else None
        ) or getattr(conv, "_agent_session_id", None)
        if not session_id:
            return None
        from tui.message_log import sanitize_filename
        agent_name = getattr(conv, "agent_title", None) or "unknown"
        path = paths.get_log() / "messages" / f"{sanitize_filename(agent_name)}_{sanitize_filename(session_id)}.jsonl"
        return path if path.exists() else None

    def action_quit(self) -> None:
        """An [action](/guide/actions) to quit the app as soon as possible."""

        self.screen.set_focus(None)
        self._capture_exit_metrics()
        try:
            driver = self._driver
            if driver is not None:
                driver.stop_application_mode()
        except Exception:
            pass
        sid = (self._exit_metrics.get("session_id", "") or "")[:36] if self._exit_metrics else ""
        session_pk = self._exit_metrics.get("session_pk") if self._exit_metrics else None
        # Format the session ID for display: prefer the short `cdh
        # session list` form (`session-<pk>` + agent_session_id prefix)
        # so the displayed value matches what users see in
        # `cdh session list` and what they pass to `cdh session load`.
        if session_pk is not None:
            display_id = f"session-{session_pk} ({sid[:8]})" if sid else f"session-{session_pk}"
            hint = f"  Reload with: cdh session load {session_pk}\n"
        elif sid:
            display_id = sid
            hint = ""
        else:
            display_id = "-"
            hint = ""
        try:
            with open("/dev/tty", "w") as tty:
                tty.write(
                    f"\n  CDH powering down. Goodbye!\n"
                    f"  Session ID: {display_id}\n"
                    f"{hint}"
                )
        except Exception:
            pass
        import os
        os._exit(0)

    def action_help_quit(self) -> None:
        if (time := monotonic()) - self.last_ctrl_c_time <= 5.0:
            self.exit()
        self.last_ctrl_c_time = time
        self.notify(
            "Press [b]ctrl+c[/b] again to quit the app", title="Do you want to quit?"
        )

    def action_toggle_help_panel(self):
        if self.screen.query("HelpPanel"):
            self.action_hide_help_panel()
        else:
            self.action_show_help_panel()

    def update_show_sessions(self) -> None:
        match self.settings.get("ui.sessions-bar", str):
            case "always":
                self.show_sessions = True
            case "never":
                self.show_sessions = False
            case "multiple":
                self.show_sessions = self.session_tracker.session_count > 1

    @on(messages.SessionNavigate)
    def on_session_navigate(self, event: messages.SessionNavigate) -> None:
        new_mode = self._session_tracker.session_cursor_move(
            event.mode_name, event.direction, set(self._modes.keys())
        )
        if new_mode is not None:
            self.switch_mode(new_mode)

    @on(messages.SessionSwitch)
    def on_session_switch(self, event: messages.SessionSwitch) -> None:
        mode_name = event.mode_name
        if mode_name in self._modes:
            self.switch_mode(mode_name)
        elif mode_name.startswith("session-"):
            parts = mode_name.split("-")
            session_pk = int(parts[1])
            existing_mode = self._find_mode_for_session_pk(session_pk)
            if existing_mode is not None and existing_mode in self._modes:
                self.switch_mode(existing_mode)
            else:
                self._load_session(session_pk)

    @on(messages.SessionNew)
    def on_session_new(self, event: messages.SessionNew) -> None:
        self.launch_agent(
            event.agent, project_path=Path(event.path), initial_prompt=event.prompt
        )

    @on(messages.SessionClose)
    def on_session_close(self) -> None:
        self.update_show_sessions()

    @on(messages.SessionLoad)
    def on_session_load(self, event: messages.SessionLoad) -> None:
        self._load_session(event.session_pk)

    @work
    async def _load_session(self, session_pk: int) -> None:
        existing_mode = self._find_mode_for_session_pk(session_pk)
        if existing_mode is not None:
            self.switch_mode(existing_mode)
            return
        db = DB()
        session = await db.session_get(session_pk)
        if session is None:
            self.notify(f"Session {session_pk} not found", title="Session load", severity="error")
            return
        agent_identity = session["agent_identity"]
        agent_session_id = session.get("agent_session_id")

        project_path = None
        try:
            meta = json.loads(session.get("meta_json", "{}"))
            if cwd := meta.get("cwd"):
                project_path = Path(cwd)
        except (json.JSONDecodeError, TypeError):
            pass

        if project_path:
            self.project_dir = project_path

        self.launch_agent(
            agent_identity,
            agent_session_id=agent_session_id,
            session_pk=session_pk,
            project_path=project_path,
        )

    @work
    async def action_sessions(self) -> None:
        if (session_screen_name := await self.push_screen_wait("sessions")) is not None:
            if session_screen_name.startswith("session-"):
                parts = session_screen_name.split("-")
                session_pk = int(parts[1])
                existing_mode = self._find_mode_for_session_pk(session_pk)
                if existing_mode is not None and existing_mode in self._modes:
                    self.switch_mode(existing_mode)
                else:
                    self._load_session(session_pk)
            else:
                try:
                    self.app.switch_mode(session_screen_name)
                except KeyError:
                    pass

    @work
    async def action_projects(self) -> None:
        from pathlib import Path
        from onecode.config import load_config, save_config
        from onecode.config_screen import EditFieldScreen
        import yaml

        result = await self.push_screen_wait("projects")
        if result is None:
            cfg = load_config()
            if cfg.current_project:
                projects_dir = Path.home() / ".cdh" / "projects"
                pf = projects_dir / f"{cfg.current_project}.yaml"
                if not pf.exists():
                    cfg.current_project = None
                    cfg.current_project_path = None
                    save_config(cfg)
                    self.project_dir = None
                    self.screen.post_message(messages.ProjectDirectoryUpdated(project_dir=None))
        if result is not None:
            if result == "__new__":
                default_path = str((self.project_dir or Path.cwd()).resolve())
                path_str = await self.push_screen_wait(
                    EditFieldScreen("Project path", default_path)
                )
                if not path_str:
                    return
                try:
                    project_path = Path(path_str).expanduser().resolve()
                except Exception:
                    self.notify("Invalid path", severity="error")
                    return
                name = project_path.name
                from onecode.agent.cdh_loader import CdhProjectLoader
                from cdh.scaffold import scaffold_dlc_project
                scaffold_dlc_project(project_path, name)
                CdhProjectLoader.init_project(project_path, name)
                projects_dir = Path.home() / ".cdh" / "projects"
                projects_dir.mkdir(parents=True, exist_ok=True)
                proj_data = {"name": name, "path": str(project_path), "description": ""}
                (projects_dir / f"{name}.yaml").write_text(yaml.dump(proj_data))
                cfg = load_config()
                cfg.current_project = name
                cfg.current_project_path = str(project_path)
                save_config(cfg)
                self.project_dir = project_path
                self.screen.post_message(messages.ProjectDirectoryUpdated(project_dir=self.project_dir))
                self.notify(f"Created project '{name}' at {project_path}")
                return

            project_name = result if isinstance(result, str) else getattr(result, 'name', None)
            if project_name:
                projects_dir = Path.home() / ".cdh" / "projects"
                project_path = None
                for ext in ["yaml", "yml", "json"]:
                    pf = projects_dir / f"{project_name}.{ext}"
                    if pf.exists():
                        proj_data = yaml.safe_load(pf.read_text()) if ext in ["yaml", "yml"] else __import__("json").loads(pf.read_text())
                        project_path = proj_data.get("path", ".")
                        break
                if project_path:
                    cfg = load_config()
                    cfg.current_project = project_name
                    cfg.current_project_path = project_path
                    save_config(cfg)

                    new_project_dir = Path(project_path) if project_path else Path.cwd()
                    self.project_dir = new_project_dir
                    self.screen.post_message(messages.ProjectDirectoryUpdated(project_dir=self.project_dir))
                    self.notify(f"Switched to project: {project_name}")
                    from tui.agents import read_agents
                    agents = await read_agents()
                    if cfg.default_mode in agents:
                        self.launch_agent(cfg.default_mode, project_path=new_project_dir)

    @on(messages.LaunchAgent)
    def on_launch_agent(self, message: messages.LaunchAgent) -> None:
        self.launch_agent(
            message.identity,
            agent_session_id=message.session_id,
            session_pk=message.pk,
            initial_prompt=message.prompt,
        )

    @work
    async def launch_agent(
        self,
        agent_identity: str,
        *,
        agent_session_id: str | None = None,
        session_pk: int | None = None,
        project_path: Path | None = None,
        initial_prompt: str | None = None,
    ) -> None:
        from tui.screens.main import MainScreen
        from tui.agent_schema import Agent
        from tui.agents import read_agents

        agent: Agent | None = None
        if session_pk is not None:
            db = DB()
            session = await db.session_get(session_pk)
            if session is not None:
                meta = json.loads(session["meta_json"])
                if agent_data := meta.get("agent_data"):
                    agent = agent_data

        if agent is None:
            agents = await read_agents()
            try:
                agent = agents[agent_identity]
            except KeyError:
                self.notify("Agent not found", title="Launch agent", severity="error")
                return
        if project_path is None:
            project_path = Path(self.project_dir or os.getcwd())

        def get_screen():
            screen = MainScreen(
                project_path,
                agent,
                agent_session_id,
                session_pk=session_pk,
                initial_prompt=initial_prompt,
            ).data_bind(
                column=A2TUIApp.column,
                column_width=A2TUIApp.column_width,
            )

            return screen

        await self.new_session_screen(get_screen, session_pk=session_pk)

    def _find_mode_for_session_pk(self, session_pk: int) -> str | None:
        """Find an existing mode name for a given DB session_pk."""
        if existing := self._session_tracker.get_session_by_pk(session_pk):
            return existing.mode_name
        return None
