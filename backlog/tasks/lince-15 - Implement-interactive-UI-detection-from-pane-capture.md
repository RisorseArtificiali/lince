---
id: LINCE-15
title: Implement interactive UI detection from pane capture
status: To Do
assignee: []
created_date: '2026-03-03 14:34'
labels:
  - telebridge
  - interactive-ui
milestone: m-3
dependencies:
  - LINCE-5
  - LINCE-11
references:
  - ccbot src/ccbot/handlers/interactive_ui.py pattern
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create the detection layer in `telebridge/src/telebridge/interactive_ui.py` that captures the Claude Code terminal pane content and identifies interactive UI prompts.

**Detection mechanism:**
1. Periodically capture pane content via `MultiplexerBridge.capture_pane()`
2. Analyze text for interactive UI patterns using regex/string matching
3. When detected, extract the UI content and type

**Interactive UI types to detect:**
- **Permission prompts**: "Allow X to Y?" with Yes/No options
- **Multi-choice questions**: AskUserQuestion with numbered options
- **Plan mode exit**: Confirmation to proceed with implementation
- **Checkpoint restoration**: List of checkpoints to restore
- **Model selection**: Model picker UI
- **Tool permission**: "Allow tool_name?" with approve/deny

**Detection patterns** (from ccbot):
- Look for separator lines (horizontal rules, box-drawing characters)
- Extract content between separators
- Identify navigation indicators (arrows, selection highlights)
- Match against known prompt templates

**Content extraction:**
- Parse the captured text between UI delimiters
- Extract option labels, descriptions, current selection
- Determine UI type from content pattern

**Polling approach:**
- Status polling task runs every 1-2 seconds (configurable)
- Only active when a session is bound and messages are being exchanged
- Compares current capture with previous to detect changes (avoid duplicate sends)

**Output**: Produces `InteractiveUIState` objects consumed by the inline keyboard renderer (separate task).

```python
@dataclass
class InteractiveUIState:
    ui_type: str          # "permission", "multi_choice", "plan_exit", "checkpoint", "model_select"
    content: str          # Extracted display text
    options: list[str]    # Available choices
    current_selection: int  # Currently highlighted option
    raw_text: str         # Full pane capture for debugging
```
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Captures pane content via MultiplexerBridge.capture_pane()
- [ ] #2 Detects permission prompts, multi-choice, plan exit, checkpoint, model selection
- [ ] #3 Extracts options and current selection from UI text
- [ ] #4 Change detection avoids duplicate UI sends
- [ ] #5 Works with both Zellij and tmux capture output
- [ ] #6 Polling interval configurable
<!-- AC:END -->
