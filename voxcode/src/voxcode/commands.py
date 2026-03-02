"""Voice command parsing with configurable prefix."""

from dataclasses import dataclass
from enum import Enum


class CommandType(Enum):
    CANCEL = "cancel"
    SEND = "send"
    PAUSE = "pause"
    RESUME = "resume"


COMMAND_MAPPINGS: dict[str, CommandType] = {
    # Italian
    "cancella": CommandType.CANCEL,
    "invia": CommandType.SEND,
    "pausa": CommandType.PAUSE,
    "riprendi": CommandType.RESUME,
    # English
    "cancel": CommandType.CANCEL,
    "send": CommandType.SEND,
    "pause": CommandType.PAUSE,
    "resume": CommandType.RESUME,
}


@dataclass
class ParseResult:
    is_command: bool
    command: CommandType | None = None
    text: str = ""


def parse_transcription(text: str, prefix: str = "comando", enabled: bool = True) -> ParseResult:
    """Parse transcribed text for voice commands.

    Commands must start with the prefix followed by a colon or space,
    e.g. "comando: invia" or "comando invia".
    """
    if not enabled or not text.strip():
        return ParseResult(is_command=False, text=text)

    text_lower = text.lower().strip()
    prefix_lower = prefix.lower()

    for separator in [":", " "]:
        pattern = f"{prefix_lower}{separator}"
        if not text_lower.startswith(pattern):
            continue
        command_word = text_lower[len(pattern) :].strip().rstrip(".,!?")
        if command_word in COMMAND_MAPPINGS:
            return ParseResult(is_command=True, command=COMMAND_MAPPINGS[command_word])

    return ParseResult(is_command=False, text=text)
