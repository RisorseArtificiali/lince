# Telebridge

Telegram bridge for Claude Code - control Claude from Telegram.

## System Requirements

- **ffmpeg** (required for voice message transcription)
  - Debian/Ubuntu: `sudo apt install ffmpeg`
  - Fedora: `sudo dnf install ffmpeg`
  - Arch: `sudo pacman -S ffmpeg`
  - macOS: `brew install ffmpeg`

## Installation

```bash
cd telebridge
uv sync
```

## Configuration

1. Copy `config.example.toml` to `config.toml`
2. Create a `.env` file with your secrets:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
ALLOWED_USERS=123456789,987654321
```

3. Get your bot token from [@BotFather](https://t.me/BotFather)
4. Find your Telegram user ID from [@userinfobot](https://t.me/userinfobot)

## Usage

```bash
uv run telebridge
```

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run pyright
```

## License

MIT
