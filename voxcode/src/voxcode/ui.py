"""Terminal UI using rich."""

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


STATUS_STYLES = {
    "idle": ("dim", "IDLE"),
    "listening": ("green", "LISTENING"),
    "recording": ("red bold", "RECORDING"),
    "transcribing": ("yellow", "TRANSCRIBING"),
    "paused": ("dim yellow", "PAUSED"),
    "loading": ("cyan", "LOADING MODEL..."),
}


class VoxCodeUI:
    """Rich-based terminal UI for VoxCode."""

    def __init__(self):
        self.console = Console()
        self.mode: str = "vad"
        self.status: str = "idle"
        self.audio_level: float = 0.0
        self.buffer: str = ""
        self.last_sent: str = ""
        self.detected_language: str = ""
        self.ptt_active: bool = False
        self.ptt_target: str | None = None  # "pane" or "clipboard"
        self.target_pane: str = ""
        self._live: Live | None = None

    def _render(self) -> Panel:
        table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        table.add_column("label", style="bold", width=12)
        table.add_column("value")

        # Mode
        mode_icon = "VAD" if self.mode == "vad" else "PTT"
        style, label = STATUS_STYLES.get(self.status, ("white", self.status.upper()))
        if self.ptt_active and self.ptt_target:
            target_label = "→ pane" if self.ptt_target == "pane" else "→ clipboard"
            table.add_row("Mode:", f"{mode_icon}  [{style}]{label} {target_label}[/]")
        else:
            table.add_row("Mode:", f"{mode_icon}  [{style}]{label}[/]")

        # Audio level bar
        bar_len = 35
        filled = int(self.audio_level * bar_len)
        bar_color = "green" if self.audio_level < 0.5 else ("yellow" if self.audio_level < 0.8 else "red")
        bar = f"[{bar_color}]{'█' * filled}[/][dim]{'░' * (bar_len - filled)}[/]"
        table.add_row("Level:", bar)

        # Language
        if self.detected_language:
            table.add_row("Lang:", self.detected_language)

        # Target pane
        if self.target_pane:
            table.add_row("Pane:", f"[dim]{self.target_pane}[/]")

        # Buffer
        if self.buffer:
            display_buf = self.buffer if len(self.buffer) <= 200 else f"...{self.buffer[-197:]}"
            table.add_row("Buffer:", display_buf)

        # Last sent
        if self.last_sent:
            display_sent = self.last_sent if len(self.last_sent) <= 100 else f"{self.last_sent[:97]}..."
            table.add_row("Sent:", f"[dim]{display_sent}[/]")

        # Keybindings help
        if self.mode == "ptt":
            keys = "[dim][Space] record→pane  [Tab] record→clipboard  [Enter] send  [c] clear  [q] quit[/]"
        else:
            keys = "[dim][Enter] send  [c] clear  [q] quit  | voice: comando:invia/cancella/pausa[/]"
        table.add_row("Keys:", keys)

        return Panel(table, title="[bold blue]VoxCode[/]", border_style="blue", expand=False)

    def start(self):
        self._live = Live(self._render(), console=self.console, refresh_per_second=10)
        self._live.start()

    def update(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        if self._live:
            self._live.update(self._render())

    def stop(self):
        if self._live:
            self._live.stop()
            self._live = None

    def print_message(self, message: str, style: str = ""):
        """Print a message outside the live display."""
        if self._live:
            self._live.console.print(message, style=style)
        else:
            self.console.print(message, style=style)
