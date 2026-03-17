"""Terminal ANSI → PNG renderer.

Converts ANSI escape sequences to PNG images with proper font fallback support.
Handles 16/256/RGB color modes and multi-font rendering (JetBrains Mono, CJK, Symbola).
"""

import asyncio
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

_FONTS_DIR = Path(__file__).parent / "fonts"

# Font fallback chain (highest priority first):
#   1. JetBrains Mono — Latin, symbols, box-drawing, blocks
#   2. Noto Sans Mono CJK SC — CJK characters
#   3. Symbola — remaining special symbols
_FONT_PATHS: list[Path] = [
    _FONTS_DIR / "JetBrainsMono-Regular.ttf",
    _FONTS_DIR / "NotoSansMonoCJKsc-Regular.otf",
    _FONTS_DIR / "Symbola.ttf",
]

# Pre-computed codepoint sets for characters NOT in JetBrains Mono.
# Tier 2: present in Noto Sans Mono CJK SC
_NOTO_CODEPOINTS: set[int] = {
    0x23BF,  # ⎿ DENTISTRY SYMBOL LIGHT VERTICAL AND BOTTOM RIGHT
}
# Tier 3: only in Symbola
_SYMBOLA_CODEPOINTS: set[int] = {
    0x23F5,  # ⏵ BLACK MEDIUM RIGHT-POINTING TRIANGLE
    0x2714,  # ✔ HEAVY CHECK MARK
    0x274C,  # ❌ CROSS MARK
}

# ANSI color mapping (basic 16 colors)
_ANSI_COLORS: dict[int, tuple[int, int, int]] = {
    # Standard colors (30-37, 40-47)
    0: (0, 0, 0),  # Black
    1: (205, 49, 49),  # Red
    2: (13, 188, 121),  # Green
    3: (229, 229, 16),  # Yellow
    4: (36, 114, 200),  # Blue
    5: (188, 63, 188),  # Magenta
    6: (17, 168, 205),  # Cyan
    7: (229, 229, 229),  # White
    # Bright colors (90-97, 100-107)
    8: (102, 102, 102),  # Bright Black
    9: (241, 76, 76),  # Bright Red
    10: (35, 209, 139),  # Bright Green
    11: (245, 245, 67),  # Bright Yellow
    12: (59, 142, 234),  # Bright Blue
    13: (214, 112, 214),  # Bright Magenta
    14: (41, 184, 219),  # Bright Cyan
    15: (255, 255, 255),  # Bright White
}

# Default colors for terminals
_DEFAULT_FG = (212, 212, 212)  # Light gray
_DEFAULT_BG = (30, 30, 30)  # Dark gray


@dataclass
class TextStyle:
    """Text styling information from ANSI codes."""

    fg_color: tuple[int, int, int] = _DEFAULT_FG
    bg_color: tuple[int, int, int] | None = None


@dataclass
class StyledSegment:
    """A text segment with its styling."""

    text: str
    style: TextStyle
    font_tier: int


class TerminalRenderer:
    """Render ANSI text to PNG with multi-font support."""

    ANSI_PATTERN = re.compile(r"\x1b\[([0-9;]*)m")

    def __init__(self, fonts_dir: Path | None = None):
        """Initialize renderer with optional custom fonts directory.

        Args:
            fonts_dir: Path to fonts directory. If None, uses default.
        """
        self._fonts_dir = fonts_dir or _FONTS_DIR
        self._fonts: list[ImageFont.FreeTypeFont | ImageFont.ImageFont] = []

    def parse_ansi_codes(self, text: str) -> list[StyledSegment]:
        """Parse ANSI escape codes into styled segments.

        Args:
            text: Text with ANSI escape sequences

        Returns:
            List of StyledSegment objects
        """
        segments: list[StyledSegment] = []
        current_style = TextStyle()
        pos = 0

        for match in self.ANSI_PATTERN.finditer(text):
            # Add text before this escape code
            text_before = text[pos : match.start()]
            if text_before:
                for seg_text, tier in self._split_line_segments_plain(text_before):
                    if seg_text:
                        segments.append(StyledSegment(seg_text, current_style, tier))

            # Parse escape code
            codes = match.group(1)
            if codes:
                current_style = self._apply_ansi_codes(current_style, codes)
            else:
                current_style = TextStyle()

            pos = match.end()

        # Add remaining text after last escape code
        text_after = text[pos:]
        if text_after:
            for seg_text, tier in self._split_line_segments_plain(text_after):
                if seg_text:
                    segments.append(StyledSegment(seg_text, current_style, tier))

        return segments if segments else [StyledSegment("", TextStyle(), 0)]

    def _apply_ansi_codes(self, style: TextStyle, codes: str) -> TextStyle:
        """Apply ANSI color codes to a text style.

        Args:
            style: Current TextStyle
            codes: ANSI code string (e.g., "31;42" or "38;5;123")

        Returns:
            New TextStyle with applied codes
        """
        new_style = TextStyle(
            fg_color=style.fg_color,
            bg_color=style.bg_color,
        )

        parts = [int(c) for c in codes.split(";") if c]
        i = 0
        while i < len(parts):
            code = parts[i]

            if code == 0:  # Reset
                new_style = TextStyle()
            elif 30 <= code <= 37:  # Foreground color
                new_style.fg_color = _ANSI_COLORS[code - 30]
            elif code == 38:  # Extended foreground color
                if i + 1 < len(parts) and parts[i + 1] == 5:  # 256 color
                    if i + 2 < len(parts):
                        color_idx = parts[i + 2] % 256
                        if color_idx < 16:
                            new_style.fg_color = _ANSI_COLORS[color_idx]
                        else:
                            new_style.fg_color = self._approximate_256_color(color_idx)
                        i += 2
                elif i + 1 < len(parts) and parts[i + 1] == 2:  # RGB color
                    if i + 4 < len(parts):
                        new_style.fg_color = (parts[i + 2], parts[i + 3], parts[i + 4])
                        i += 4
            elif code == 39:  # Default foreground
                new_style.fg_color = _DEFAULT_FG
            elif 40 <= code <= 47:  # Background color
                new_style.bg_color = _ANSI_COLORS[code - 40]
            elif code == 48:  # Extended background color
                if i + 1 < len(parts) and parts[i + 1] == 5:  # 256 color
                    if i + 2 < len(parts):
                        color_idx = parts[i + 2] % 256
                        if color_idx < 16:
                            new_style.bg_color = _ANSI_COLORS[color_idx]
                        else:
                            new_style.bg_color = self._approximate_256_color(color_idx)
                        i += 2
                elif i + 1 < len(parts) and parts[i + 1] == 2:  # RGB color
                    if i + 4 < len(parts):
                        new_style.bg_color = (parts[i + 2], parts[i + 3], parts[i + 4])
                        i += 4
            elif code == 49:  # Default background
                new_style.bg_color = None
            elif 90 <= code <= 97:  # Bright foreground color
                new_style.fg_color = _ANSI_COLORS[code - 90 + 8]
            elif 100 <= code <= 107:  # Bright background color
                new_style.bg_color = _ANSI_COLORS[code - 100 + 8]

            i += 1

        return new_style

    def _approximate_256_color(self, idx: int) -> tuple[int, int, int]:
        """Approximate a 256-color palette index to RGB.

        Args:
            idx: Color index (0-255)

        Returns:
            RGB tuple
        """
        if idx < 16:
            return _ANSI_COLORS[idx]
        elif idx < 232:
            # 216 color cube: 16 + 36*r + 6*g + b
            idx -= 16
            r = (idx // 36) * 51
            g = ((idx % 36) // 6) * 51
            b = (idx % 6) * 51
            return (r, g, b)
        else:
            # Grayscale: 232-255
            gray = 8 + (idx - 232) * 10
            return (gray, gray, gray)

    def _load_font(self, size: int) -> list[ImageFont.FreeTypeFont | ImageFont.ImageFont]:
        """Load fonts with system fallback.

        Args:
            size: Font size in pixels

        Returns:
            List of loaded fonts (tier 0, 1, 2)
        """
        fonts = []
        for path in _FONT_PATHS:
            try:
                fonts.append(ImageFont.truetype(str(path), size))
            except OSError:
                logger.warning("Failed to load font %s, using default", path)
                fonts.append(ImageFont.load_default())
        return fonts

    def _font_tier(self, ch: str) -> int:
        """Determine font tier for a character.

        Args:
            ch: Single character

        Returns:
            0 (JetBrains), 1 (Noto CJK), or 2 (Symbola)
        """
        cp = ord(ch)
        if cp in _SYMBOLA_CODEPOINTS:
            return 2
        if (
            cp in _NOTO_CODEPOINTS
            or cp >= 0x1100
            and (
                cp <= 0x11FF  # Hangul Jamo
                or 0x2E80 <= cp <= 0x9FFF  # CJK radicals, kangxi, ideographs
                or 0xAC00 <= cp <= 0xD7AF  # Hangul Syllables
                or 0xF900 <= cp <= 0xFAFF  # CJK compat ideographs
                or 0xFE30 <= cp <= 0xFE4F  # CJK compat forms
                or 0xFF00 <= cp <= 0xFFEF  # fullwidth forms
                or 0x20000 <= cp <= 0x2FA1F  # CJK extension B+
            )
        ):
            return 1
        return 0

    def _split_line_segments_plain(self, line: str) -> list[tuple[str, int]]:
        """Split a line into (text, font_tier) segments.

        Consecutive characters sharing the same tier are merged.

        Args:
            line: Text line

        Returns:
            List of (text, tier) tuples
        """
        if not line:
            return [("", 0)]
        segments: list[tuple[str, int]] = []
        cur_tier = self._font_tier(line[0])
        start = 0
        for i in range(1, len(line)):
            tier = self._font_tier(line[i])
            if tier != cur_tier:
                segments.append((line[start:i], cur_tier))
                cur_tier = tier
                start = i
        segments.append((line[start:], cur_tier))
        return segments

    async def render_to_png(self, ansi_text: str, font_size: int = 28) -> bytes:
        """Render ANSI text to PNG image.

        Args:
            ansi_text: Text with ANSI escape sequences
            font_size: Font size in pixels

        Returns:
            PNG image bytes
        """

        def _render() -> bytes:
            fonts = self._load_font(font_size)

            lines = ansi_text.split("\n")
            padding = 16

            # Parse lines into styled segments
            line_segments = [self.parse_ansi_codes(line) for line in lines]

            # Measure text size
            dummy = Image.new("RGB", (1, 1))
            draw = ImageDraw.Draw(dummy)
            line_height = int(font_size * 1.4)
            max_width = 0
            for segments in line_segments:
                w = 0
                for seg in segments:
                    bbox = draw.textbbox((0, 0), seg.text, font=fonts[seg.font_tier])
                    w += bbox[2] - bbox[0]
                max_width = max(max_width, w)

            img_width = int(max_width) + padding * 2
            img_height = line_height * len(lines) + padding * 2

            img = Image.new("RGB", (img_width, img_height), _DEFAULT_BG)
            draw = ImageDraw.Draw(img)

            y = padding
            for segments in line_segments:
                x = padding
                for seg in segments:
                    f = fonts[seg.font_tier]

                    # Draw background if specified
                    if seg.style.bg_color:
                        bbox = draw.textbbox((x, y), seg.text, font=f)
                        draw.rectangle(
                            [bbox[0], y, bbox[2], y + line_height],
                            fill=seg.style.bg_color
                        )

                    # Draw text with foreground color
                    draw.text((x, y), seg.text, fill=seg.style.fg_color, font=f)

                    bbox = draw.textbbox((0, 0), seg.text, font=f)
                    x += bbox[2] - bbox[0]
                y += line_height

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        # Run CPU-intensive rendering in thread pool to avoid blocking
        return await asyncio.to_thread(_render)
