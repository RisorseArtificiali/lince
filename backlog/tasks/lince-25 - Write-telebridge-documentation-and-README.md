---
id: LINCE-25
title: Write telebridge documentation and README
status: To Do
assignee: []
created_date: '2026-03-03 14:36'
labels:
  - telebridge
  - documentation
milestone: m-6
dependencies:
  - LINCE-20
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create comprehensive documentation for the telebridge module.

**README.md** contents:
1. **Overview**: What telebridge does, architecture diagram (ASCII)
2. **Prerequisites**: Python 3.11+, Telegram bot (link to BotFather), tmux or Zellij, Claude Code CLI, ffmpeg (for voice)
3. **Installation**: `uv pip install -e ".[voice]"` for full install, `uv pip install -e .` without voice
4. **Setup guide**:
   - Create Telegram bot via BotFather
   - Enable forum/topics in the Telegram group
   - Configure `.env` with bot token and allowed users
   - Create `config.toml` from example
   - Install hook: `telebridge install-hook`
   - Start: `telebridge run`
5. **Configuration reference**: All TOML sections with defaults and descriptions
6. **Usage guide**: How to send messages, manage sessions, use voice, handle permissions
7. **Bot commands reference**: All commands with descriptions
8. **Zellij integration**: Layout setup, pane directions
9. **Sandbox integration**: How to enable, security model
10. **Troubleshooting**: Common issues (bot not responding, sessions not binding, voice not working)

**CLAUDE.md update**: Add telebridge to the project CLAUDE.md with build/test commands.

**Config.example.toml**: Ensure all options are documented with comments.

**In-code docstrings**: All public functions and classes should have docstrings (can be brief).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 README.md covers all sections listed above
- [ ] #2 config.example.toml fully documented
- [ ] #3 CLAUDE.md updated with telebridge commands
- [ ] #4 All public functions have docstrings
- [ ] #5 Architecture diagram in ASCII art
- [ ] #6 Troubleshooting section covers common issues
<!-- AC:END -->
