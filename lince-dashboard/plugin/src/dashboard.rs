// One rendering sink for both the local pane and a passive dialog surface.
macro_rules! print { ($($arg:tt)*) => { crate::render_output::write(format_args!($($arg)*)) }; }
macro_rules! println {
    () => { crate::render_output::write(format_args!("\n")) };
    ($($arg:tt)*) => { crate::render_output::write(format_args!("{}\n", format_args!($($arg)*))) };
}
use std::collections::HashMap;

use crate::config::{AgentTypeConfig, SandboxColors};
use crate::types::{
    AgentInfo, AgentStatus, NamePromptState, ProjectDirMode, RelayPhase, WizardState, WizardStep,
};

use crate::theme;
use unicode_width::UnicodeWidthChar;

fn color_name_to_ansi(name: &str) -> String { theme::color(name) }
fn selection_bg_for_color(_name: &str) -> String { theme::selection() }

const RESET: &str = "\x1b[0m";
const BOLD: &str = "\x1b[1m";
const DIM: &str = "\x1b[2m";
/// Truncate a string to fit within `max_width` *visible* characters, appending
/// "..." if truncated. ANSI CSI sequences (e.g. `\x1b[1;31m`) are copied verbatim
/// and never count toward width — without this, a cut landing inside a CSI
/// sequence leaves the terminal waiting for a final byte and silently consumes
/// leading bytes from the *next* line of output (gh#95).
fn truncate(s: &str, max_width: usize) -> String {
    let visible = strip_ansi_len(s);
    if visible <= max_width {
        return s.to_string();
    }
    if max_width == 0 {
        return String::new();
    }

    // Two regimes:
    //   * max_width >= 3 → emit (max_width - 3) visible chars + "..."
    //   * max_width <  3 → emit max_width visible chars, no ellipsis (room is
    //     too small for one). Matches the spirit of the previous behaviour.
    let (budget, append_ellipsis) = if max_width >= 3 {
        (max_width - 3, true)
    } else {
        (max_width, false)
    };

    let mut out = String::with_capacity(s.len());
    let mut visible_emitted: usize = 0;
    let mut chars = s.chars();
    let mut had_escape = false;
    while let Some(c) = chars.next() {
        if c == '\x1b' {
            // Copy the entire CSI sequence verbatim — `\x1b[` followed by
            // params/intermediates, terminated by an ASCII letter (the "final
            // byte" 0x40-0x7E). Match strip_ansi_len's parser exactly so
            // visible counting and verbatim copying stay in lockstep.
            had_escape = true;
            out.push(c);
            for esc_c in chars.by_ref() {
                out.push(esc_c);
                if esc_c.is_ascii_alphabetic() {
                    break;
                }
            }
            continue;
        }
        if visible_emitted >= budget {
            break;
        }
        out.push(c);
        visible_emitted += 1;
    }
    if had_escape {
        // Close any attribute the original string may have left dangling so
        // the appended ellipsis (and any caller content downstream) renders
        // cleanly. Cheap insurance — RESET is a 4-byte sequence.
        out.push_str(RESET);
    }
    if append_ellipsis {
        out.push_str("...");
    }
    out
}

/// Truncate `s` from the LEFT to at most `max_len` visible chars, prefixing an
/// ellipsis (`…`) so the distinguishing tail of a path stays visible. Returns
/// `s` unchanged when it already fits or `max_len <= 1`. Char-based, so it
/// never splits a multi-byte UTF-8 sequence.
fn truncate_left(s: &str, max_len: usize) -> String {
    if s.chars().count() > max_len && max_len > 1 {
        let skip = s.chars().count() - max_len + 1;
        let tail: String = s.chars().skip(skip).collect();
        format!("\u{2026}{}", tail)
    } else {
        s.to_string()
    }
}

/// Pad or truncate a string to exactly `width` characters, left-aligned.
fn pad_left(s: &str, width: usize) -> String {
    let truncated = truncate(s, width);
    format!("{:<width$}", truncated, width = width)
}

/// Compute the visible length of a string (ignoring ANSI escape sequences).
fn strip_ansi_len(s: &str) -> usize {
    let mut len = 0;
    let mut in_escape = false;
    for c in s.chars() {
        if in_escape {
            if c.is_ascii_alphabetic() {
                in_escape = false;
            }
        } else if c == '\x1b' {
            in_escape = true;
        } else {
            len += 1;
        }
    }
    len
}

/// Pad a string to exactly `width` visible characters (ANSI-aware, left-aligned).
fn pad_to_width(s: &str, width: usize) -> String {
    let visible_len = strip_ansi_len(s);
    if visible_len >= width {
        s.to_string()
    } else {
        format!("{}{}", s, " ".repeat(width - visible_len))
    }
}

/// Repeat a character n times.
fn repeat_char(c: char, n: usize) -> String {
    std::iter::repeat(c).take(n).collect()
}

/// Format a Unix timestamp as human-readable relative time (e.g. "5m ago", "2h 15m ago").
fn format_elapsed(timestamp: u64) -> String {
    let now = crate::config::now_secs();
    if now == 0 || timestamp == 0 {
        return "-".to_string();
    }
    let elapsed = now.saturating_sub(timestamp);
    if elapsed < 60 {
        format!("{}s ago", elapsed)
    } else if elapsed < 3600 {
        format!("{}m ago", elapsed / 60)
    } else if elapsed < 86400 {
        let h = elapsed / 3600;
        let m = (elapsed % 3600) / 60;
        if m > 0 { format!("{}h {}m ago", h, m) } else { format!("{}h ago", h) }
    } else {
        let d = elapsed / 86400;
        let h = (elapsed % 86400) / 3600;
        if h > 0 { format!("{}d {}h ago", d, h) } else { format!("{}d ago", d) }
    }
}

/// Shorten a filesystem path by replacing $HOME with ~.
/// In WASI, std::env::var("HOME") may not work, so we gracefully skip shortening.
use crate::config::collapse_tilde;

// ── Shared overlay helpers ─────────────────────────────────────────

/// Push a title border line onto a lines buffer (e.g. `─── Title ───`).
fn push_title_border(lines: &mut Vec<String>, title: &str, w: usize) {
    let border_fill = w.saturating_sub(title.len() + 2);
    let left_border = border_fill / 2;
    let right_border = border_fill - left_border;
    lines.push(format!(
        "{}{}{}{}{}",
        BOLD,
        repeat_char('\u{2500}', left_border + 1),
        title,
        repeat_char('\u{2500}', right_border + 1),
        RESET,
    ));
}

/// Push a bordered content line (`│ content │`).
fn push_box_line(lines: &mut Vec<String>, content: &str, w: usize) {
    lines.push(format!(
        "\u{2502}{}\u{2502}",
        pad_to_width(&truncate(content, w.saturating_sub(4)), w.saturating_sub(2))
    ));
}

/// Push a bottom border (`────────`).
fn push_bottom_border(lines: &mut Vec<String>, w: usize) {
    lines.push(repeat_char('\u{2500}', w));
}

/// Render pre-built lines centered on screen.
fn render_centered_box(lines: &[String], rows: usize, cols: usize, box_width: usize) {
    let start_col = if cols > box_width { (cols - box_width) / 2 } else { 0 };
    let start_row = if rows > lines.len() { (rows - lines.len()) / 2 } else { 0 };

    for r in 0..rows {
        if r >= start_row && r < start_row + lines.len() {
            print!("{:>width$}{}", "", &lines[r - start_row], width = start_col);
            println!();
        } else {
            println!();
        }
    }
}

// ── Main dashboard ─────────────────────────────────────────────────

/// Render the full dashboard to stdout.
pub fn render_dashboard(
    agents: &[AgentInfo],
    selected: usize,
    focused: Option<&str>,
    detail: Option<&str>,
    rows: usize,
    cols: usize,
    status_message: Option<&str>,
    name_prompt: Option<&NamePromptState>,
    relay_phase: Option<&RelayPhase>,
    agent_types: &HashMap<String, AgentTypeConfig>,
    sandbox_colors: &SandboxColors,
    compact: bool,
    info_scroll: usize,
) {
    if rows == 0 || cols == 0 {
        return;
    }

    if compact || detail.is_some() {
        render_compact(agents, selected, focused, detail, rows, cols, status_message,
            name_prompt, relay_phase, agent_types, info_scroll);
        return;
    }
    render_header(agents.len(), cols);

    if rows < 6 {
        // Not enough room for the full layout. Reserve 2 rows for the status
        // bar at the bottom (or fall back to a single line / nothing on
        // extremely small terminals).
        let status_lines: usize = if rows >= 3 { 2 } else if rows == 2 { 1 } else { 0 };
        let blank_lines = rows.saturating_sub(1 + status_lines); // header + status
        for _ in 0..blank_lines {
            println!();
        }
        if status_lines == 2 {
            if let Some(prompt) = name_prompt {
                render_name_prompt_bar(prompt, cols);
                print_status_pad_line(cols);
            } else if let Some(RelayPhase::MessagePrompt { input }) = relay_phase {
                render_relay_message_prompt(input, cols);
                print_status_pad_line(cols);
            } else {
                let rp = matches!(relay_phase, Some(RelayPhase::DeliveryPending { .. }));
                render_status_bar(cols, status_message, agents, focused, detail, rp);
            }
        } else if status_lines == 1 {
            if let Some(prompt) = name_prompt {
                render_name_prompt_bar(prompt, cols);
            } else {
                // Single-line compact fallback: just print the first half of hints.
                let is_empty = agents.is_empty();
                let is_focused = focused.is_some();
                let is_detail = detail.is_some();
                let hints = status_bar_hints(is_empty, is_focused, is_detail);
                let mid = hints.len().div_ceil(2);
                let (first_half, _) = hints.split_at(mid);
                let text = format_key_hints(first_half);
                print_status_line(&text, first_half, cols);
            }
        }
        return;
    }

    println!(); // separator

    let detail_panel_rows = if detail.is_some() { 10 } else { 0 };
    let available = rows.saturating_sub(5); // header + 2 seps + 2-line statusbar
    let table_rows = available.saturating_sub(detail_panel_rows);

    if agents.is_empty() {
        render_empty_state(table_rows, cols);
    } else {
        render_agent_table(agents, selected, focused, table_rows, cols, agent_types, sandbox_colors);
    }

    if let Some(detail_id) = detail {
        if let Some(agent) = agents.iter().find(|a| a.id == detail_id) {
            render_detail_panel(agent, cols, detail_panel_rows, agent_types);
        }
    }

    println!(); // separator
    if let Some(prompt) = name_prompt {
        render_name_prompt_bar(prompt, cols);
        print_status_pad_line(cols);
    } else if let Some(RelayPhase::MessagePrompt { input }) = relay_phase {
        render_relay_message_prompt(input, cols);
        print_status_pad_line(cols);
    } else {
        let rp = matches!(relay_phase, Some(RelayPhase::DeliveryPending { .. }));
        render_status_bar(cols, status_message, agents, focused, detail, rp);
    }
}

fn render_header(agent_count: usize, cols: usize) {
    let title = if agent_count > 0 {
        format!("LINCE Dashboard  ({} agents)", agent_count)
    } else {
        "LINCE Dashboard".to_string()
    };

    let padding_left = if cols > title.len() { (cols - title.len()) / 2 } else { 0 };
    let padding_right = cols.saturating_sub(padding_left + title.len());

    print!(
        "{}{:>left$}{}{:>right$}{}",
        theme::selection(), "", title, "", RESET,
        left = padding_left, right = padding_right,
    );
    println!();
}

fn render_empty_state(table_rows: usize, cols: usize) {
    let msg = "No agents running. Press [n] to create one.";
    let mid = table_rows / 2;

    for r in 0..table_rows {
        if r == mid {
            let msg_display = truncate(msg, cols);
            let pad = if cols > msg_display.len() { (cols - msg_display.len()) / 2 } else { 0 };
            print!("{:>width$}{}{}{}", "", theme::color("yellow"), msg_display, RESET, width = pad);
            println!();
        } else {
            println!();
        }
    }
}

/// Render the agent table (#, Name, Status), grouped by project_dir swimlanes.
fn render_agent_table(
    agents: &[AgentInfo],
    selected: usize,
    focused: Option<&str>,
    table_rows: usize,
    cols: usize,
    agent_types: &HashMap<String, AgentTypeConfig>,
    sandbox_colors: &SandboxColors,
) {
    let col_idx: usize = 3;
    let col_type: usize = 5;  // 3 chars label + "!" marker + space
    let col_sandbox: usize = 6; // "bwrap" / "nono" / "NOSB" + padding
    let col_name: usize = 20;
    let col_provider: usize = 12;
    let col_status: usize = 12;

    // Show optional columns only when terminal is wide enough
    let base_width: usize = 1 + col_idx + 1 + col_type + 1 + col_name + 1 + col_status;
    let show_sandbox = cols >= base_width + 1 + col_sandbox;
    let show_provider = cols >= base_width + 1 + col_sandbox + 1 + col_provider;

    let hdr_sandbox = if show_sandbox { format!("{} ", pad_left("Sbox", col_sandbox)) } else { String::new() };
    let hdr_provider = if show_provider { format!("{} ", pad_left("Provider", col_provider)) } else { String::new() };
    let hdr = format!(
        " {} {} {} {} {}{}",
        pad_left("#", col_idx), pad_left("Agent", col_type),
        pad_left("Name", col_name),
        pad_left("Status", col_status),
        hdr_sandbox, hdr_provider,
    );
    println!("{}{}{}", BOLD, truncate(&hdr, cols), RESET);

    let data_rows = table_rows.saturating_sub(1);

    // Build virtual rows with swimlane headers interleaved.
    // Always show headers — even with a single project directory,
    // the header shows which directory the agents are working in.
    let mut virtual_rows: Vec<Option<usize>> = Vec::new();
    let mut header_dirs: Vec<String> = Vec::new();
    let mut last_dir: Option<&str> = None;
    for (i, agent) in agents.iter().enumerate() {
        // Compare/display normalized so legacy `path/` and new `path` group together.
        let key = agent.project_dir.trim_end_matches('/');
        if last_dir != Some(key) {
            virtual_rows.push(None);
            header_dirs.push(key.to_string());
            last_dir = Some(key);
        }
        virtual_rows.push(Some(i));
        header_dirs.push(String::new());
    }

    // Assign each unique workdir a stable cycle index (order of first
    // appearance) so its header color is independent of scroll position and
    // survives a `Q` + restart (which preserves agent order via
    // `restore_agents` → `sort_agents_by_dir`).
    let mut dir_color_idx: HashMap<&str, usize> = HashMap::new();
    for (i, slot) in virtual_rows.iter().enumerate() {
        if slot.is_none() {
            let d = header_dirs[i].as_str();
            let next_idx = dir_color_idx.len();
            dir_color_idx.entry(d).or_insert(next_idx);
        }
    }

    // Find the virtual row index of the selected agent
    let selected_vrow = virtual_rows.iter().position(|v| *v == Some(selected)).unwrap_or(0);

    // Compute scroll offset in virtual row space
    let scroll_offset = if selected_vrow >= data_rows {
        // Try to keep the selected row visible, but also show its swimlane header if possible
        let mut offset = selected_vrow - data_rows + 1;
        // If the row just above offset is a header for the selected agent's swimlane, include it
        if offset > 0 && virtual_rows.get(offset.saturating_sub(1)) == Some(&None) {
            offset -= 1;
        }
        offset
    } else {
        0
    };

    let mut rendered_rows = 0;
    let mut vrow = scroll_offset;

    while rendered_rows < data_rows {
        if vrow >= virtual_rows.len() {
            println!();
            rendered_rows += 1;
            continue;
        }

        match virtual_rows[vrow] {
            None => {
                // Swimlane header row — color cycles per workdir in order of
                // first appearance (palette wraps modulo its length).
                let dir = &header_dirs[vrow];
                let idx = dir_color_idx.get(dir.as_str()).copied().unwrap_or(0);
                let header_color = theme::group(idx);
                let short = collapse_tilde(dir);
                let fill_len = cols.saturating_sub(short.len() + 5);
                println!(
                    " {}\u{250c} {} {}{}",
                    header_color, short, repeat_char('\u{2500}', fill_len), RESET,
                );
                rendered_rows += 1;
            }
            Some(agent_idx) => {
                let agent = &agents[agent_idx];

                let is_selected = agent_idx == selected;
                let is_focused = focused.map_or(false, |f| f == agent.id);
                let prefix = if is_focused { ">" } else { " " };
                let idx_str = format!("{}", agent_idx + 1);
                let status_label = agent.status_display();
                let status_color = theme::status(&agent.status);
                let needs_attention = matches!(
                    agent.status,
                    AgentStatus::WaitingForInput | AgentStatus::PermissionRequired
                );

                // Build type label column — always visible.
                // Color comes from the runtime sandbox_level (wizard selection) when set,
                // mapped through sandbox_colors; falls back to the per-type config color.
                let type_col = if let Some(cfg) = agent_types.get(&agent.agent_type) {
                    if !cfg.sandboxed {
                        format!(" {}{}!{}", theme::color("red"), pad_left(&cfg.short_label, col_type.saturating_sub(2)), RESET)
                    } else {
                        let color_name = if let Some(ref level) = agent.sandbox_level {
                            sandbox_colors.for_level(level)
                        } else {
                            &cfg.color
                        };
                        format!(" {}{} {}", color_name_to_ansi(color_name), pad_left(&cfg.short_label, col_type.saturating_sub(2)), RESET)
                    }
                } else {
                    format!(" {}??? {}", RESET, RESET)
                };

                // Build optional sandbox/provider column content. Plain text
                // (no color attrs) is computed once and reused; the colored
                // form for non-selected rows is built inline below. The
                // selected branch deliberately renders these columns without
                // their per-cell color so the row's REVERSE attribute isn't
                // broken by an interior \x1b[0m (gh#95).
                let sandbox_plain = if show_sandbox {
                    if let Some(cfg) = agent_types.get(&agent.agent_type) {
                        if !cfg.sandboxed {
                            pad_left("NOSB", col_sandbox)
                        } else {
                            let backend = agent.sandbox_backend.as_ref().unwrap_or(&cfg.sandbox_backend);
                            // '!' = the effective-policy record (#221) says a
                            // requested boundary was NOT enforced for this run.
                            let degraded = agent
                                .enforced
                                .as_ref()
                                .map_or(false, |p| !p.fully_enforced());
                            if degraded {
                                pad_left(&format!("{}!", backend.display_name()), col_sandbox)
                            } else {
                                pad_left(backend.display_name(), col_sandbox)
                            }
                        }
                    } else {
                        pad_left("-", col_sandbox)
                    }
                } else {
                    String::new()
                };

                // Provider column has no color attributes today, so the plain
                // and colored forms coincide.
                let provider_plain = if show_provider {
                    pad_left(agent.provider.as_deref().unwrap_or("-"), col_provider)
                } else {
                    String::new()
                };

                // #166: per-instance marker (distinctive emoji) prefix on the
                // name column — the same glyph shown in the pane title, so the
                // list entry and the pane share one identity. Reclaim 2 columns
                // from the name pad for the marker + separating space.
                let icon_pre = if agent.icon.is_empty() {
                    String::new()
                } else {
                    format!("{} ", agent.icon)
                };
                let name_col = if agent.icon.is_empty() {
                    col_name
                } else {
                    col_name.saturating_sub(2)
                };

                if is_selected {
                    // Trailing without color attrs — preserves the REVERSE that
                    // wraps the whole row. The trailing space-separators match
                    // the non-selected layout.
                    let mut trailing = String::new();
                    if show_sandbox {
                        trailing.push(' ');
                        trailing.push_str(&sandbox_plain);
                    }
                    if show_provider {
                        trailing.push(' ');
                        trailing.push_str(&provider_plain);
                    }

                    let main_part = format!(
                        "{}{}{} {}{}",
                        prefix, pad_left(&idx_str, col_idx), type_col,
                        icon_pre, pad_left(&agent.name, name_col),
                    );
                    let status_str = pad_left(&status_label, col_status);
                    let main_visible = strip_ansi_len(&main_part);
                    let trailing_visible = strip_ansi_len(&trailing);
                    let plain_len = main_visible + 1 + status_str.len() + trailing_visible;
                    let fill = cols.saturating_sub(plain_len);

                    // status_color is the only colour we keep inside REVERSE so
                    // the user still sees the urgency cue (red/yellow text on
                    // the inverted background). \x1b[39m clears the fg back to
                    // default while leaving REVERSE on, so the tail of the row
                    // doesn't render in status_color too.
                    print!(
                        "{}{} {}{}{}\x1b[39;22m{}{}",
                        theme::selection(), main_part,
                        status_color, if needs_attention { BOLD } else { "" },
                        status_str,
                        trailing, RESET,
                    );
                    if fill > 0 {
                        print!("{}{:>fill$}{}", theme::selection(), "", RESET, fill = fill);
                    }
                    println!();
                } else {
                    // For non-selected rows, use display_name (with group suffix) in the name column
                    let name_field = if agent.group.is_some() {
                        let base = pad_left(&agent.name, name_col.saturating_sub(agent.group.as_ref().map_or(0, |g| g.len() + 3)));
                        if let Some(ref group) = agent.group {
                            format!("{}{} {}[{}]{}", icon_pre, base, DIM, group, RESET)
                        } else {
                            format!("{}{}", icon_pre, base)
                        }
                    } else {
                        format!("{}{}", icon_pre, pad_left(&agent.name, name_col))
                    };

                    // Wrap the plain sandbox content with its color attribute
                    // for non-selected rows. NOSB is bold-red, sandboxed
                    // backends are dim, unknown/no-config is plain.
                    let sandbox_col = if show_sandbox {
                        if let Some(cfg) = agent_types.get(&agent.agent_type) {
                            if !cfg.sandboxed {
                                format!("{}{}{} ", theme::color("red"), sandbox_plain, RESET)
                            } else {
                                format!("\x1b[2m{}{} ", sandbox_plain, RESET)
                            }
                        } else {
                            format!("{} ", sandbox_plain)
                        }
                    } else {
                        String::new()
                    };
                    let provider_col = if show_provider {
                        format!("{} ", provider_plain)
                    } else {
                        String::new()
                    };

                    let line = format!(
                        "{}{}{} {} {}{}{}{} {}{}",
                        prefix, pad_left(&idx_str, col_idx), type_col, name_field,
                        status_color, if needs_attention { BOLD } else { "" },
                        pad_left(&status_label, col_status), RESET,
                        sandbox_col, provider_col,
                    );
                    println!("{}", truncate(&line, cols));
                }
                rendered_rows += 1;
            }
        }
        vrow += 1;
    }
}

/// Render the detail panel for a specific agent below the table.
fn render_detail_panel(agent: &AgentInfo, cols: usize, max_rows: usize, agent_types: &HashMap<String, AgentTypeConfig>) {
    if max_rows == 0 {
        return;
    }

    let sep: String = repeat_char('\u{2500}', cols);
    println!("{}{}{}", DIM, sep, RESET);

    let mut row = 1;

    // Agent name, type, status, and sandbox backend
    if row < max_rows {
        let (type_display, type_color, sandbox_info) =
            if let Some(cfg) = agent_types.get(&agent.agent_type) {
                let sandbox_str = if !cfg.sandboxed {
                    format!(" {}[UNSANDBOXED]{}", theme::color("red"), RESET)
                } else {
                    let backend = agent.sandbox_backend.as_ref().unwrap_or(&cfg.sandbox_backend);
                    format!(" \x1b[2m[{}]\x1b[0m", backend.display_name())
                };
                (
                    cfg.display_name.as_str(),
                    color_name_to_ansi(&cfg.color),
                    sandbox_str,
                )
            } else {
                (agent.agent_type.as_str(), RESET.to_string(), String::new())
            };
        let detail_status = agent.status_display();
        println!(
            " {}Agent:{} {}  {}{}{}{} {}{}{}",
            theme::color("cyan"), RESET, agent.name,
            type_color, type_display, RESET, sandbox_info,
            theme::status(&agent.status), detail_status, RESET,
        );
        row += 1;
    }
    // Show "Profile" (sandbox isolation level — paranoid/normal/permissive)
    // and "Provider" (env-var bundle — anthropic/vertex/zai/...) on
    // SEPARATE lines. They're orthogonal axes; conflating them confused users
    // (gh#81). Either may be `(default)` independently.
    if row < max_rows {
        let profile = agent.sandbox_level.as_deref().unwrap_or("(default)");
        println!(" {}Profile:{} {}", theme::color("cyan"), RESET, profile);
        row += 1;
    }
    // Effective-policy badge (#221): the boundary the kernel actually
    // enforced for THIS run (requested view = `lince config resolve`).
    if row < max_rows {
        if let Some(ref p) = agent.enforced {
            let color = theme::color(if p.fully_enforced() { "green" } else { "yellow" });
            let mut extra = String::new();
            if let Some(ref lim) = p.net_limitation {
                if lim != "unavailable" {
                    extra.push_str(&format!(" net:{}", lim));
                }
            }
            if let Some(ref reason) = p.degraded_reason {
                extra.push_str(&format!(" {}{}{}", theme::color("yellow"), reason, RESET));
            }
            if !p.experimental.is_empty() {
                extra.push_str(&format!(
                    " {}override: {}{}",
                    theme::color("yellow"), p.experimental.join(", "), RESET
                ));
            }
            let line = format!(
                " {}Enforced:{} {}{}{} [{}]{}",
                theme::color("cyan"), RESET, color, p.badge(), RESET, p.backend, extra,
            );
            println!("{}", truncate(&line, cols));
            row += 1;
        }
    }
    if row < max_rows {
        let provider = agent.provider.as_deref().unwrap_or("(default)");
        println!(" {}Provider:{} {}", theme::color("cyan"), RESET, provider);
        row += 1;
    }
    if row < max_rows {
        println!(" {}Dir:{} {}", theme::color("cyan"), RESET, agent.project_dir);
        row += 1;
    }
    if row < max_rows {
        let started = agent.started_at.map_or("-".to_string(), format_elapsed);
        println!(" {}Started:{} {}", theme::color("cyan"), RESET, started);
        row += 1;
    }
    if row < max_rows {
        if let Some(ref err) = agent.last_error {
            println!(" {}Error:{} {}{}{}", theme::color("cyan"), RESET, theme::color("red"), truncate(err, cols.saturating_sub(10)), RESET);
            row += 1;
        }
    }
    for _ in row..max_rows {
        println!();
    }
}

/// Render the inline name prompt as a status bar replacement (LINCE-55).
fn render_name_prompt_bar(prompt: &NamePromptState, cols: usize) {
    let cursor = "\u{2588}"; // solid block cursor
    let input_part = if prompt.input.is_empty() {
        format!("{}{}{}{}", DIM, prompt.default_name, RESET, cursor)
    } else {
        format!("{}{}", prompt.input, cursor)
    };

    let hint = if prompt.input.is_empty() {
        String::new()
    } else {
        format!("  {}(default: {}){}", DIM, prompt.default_name, RESET)
    };

    let text = format!(
        " {}{}:{} {}{}  {}[Enter]{} OK  {}[Esc]{} Cancel",
        theme::color("cyan"), prompt.label, RESET, input_part, hint,
        theme::color("cyan"), RESET, theme::color("cyan"), RESET,
    );

    let visible_len = strip_ansi_len(&text);
    let padding = cols.saturating_sub(visible_len + 1);
    print!("{} {}{:>pad$}{}", theme::selection(), text, "", RESET, pad = padding);
    println!();
}

/// Render the relay message-count prompt bar (blue background).
/// Pattern matches render_name_prompt_bar: cursor block, dim default, hints.
fn render_relay_message_prompt(input: &str, cols: usize) {
    let cursor = "\u{2588}"; // solid block cursor
    let input_part = if input.is_empty() {
        format!("{}1{}{}", DIM, RESET, cursor) // default "1" in dim
    } else {
        format!("{}{}", input, cursor)
    };

    let text = format!(
        " {}Relay:{} Messages (1-9): {}  {}[Enter]{} OK  {}[Esc]{} Cancel",
        theme::color("cyan"), RESET, input_part,
        theme::color("cyan"), RESET, theme::color("cyan"), RESET,
    );

    let visible_len = strip_ansi_len(&text);
    let padding = cols.saturating_sub(visible_len + 1);
    print!("{} {}{:>pad$}{}", theme::selection(), text, "", RESET, pad = padding);
    println!();
}

/// A key hint entry: (key label, description).
type KeyHint = (&'static str, &'static str);

/// Format a list of key hints with ANSI key coloring for the full status bar.
fn format_key_hints(hints: &[KeyHint]) -> String {
    hints
        .iter()
        .map(|(key, label)| format!("{}[{}]{} {}", theme::color("cyan"), key, RESET, label))
        .collect::<Vec<_>>()
        .join("  ")
}

/// Format a list of key hints as compact text (no ANSI).
fn format_key_hints_short(hints: &[KeyHint]) -> String {
    hints
        .iter()
        .map(|(key, label)| format!("{}:{}", key, label))
        .collect::<Vec<_>>()
        .join(" ")
}

/// Key hints shown during the relay DeliveryPending phase.
fn relay_pending_hints() -> Vec<KeyHint> {
    vec![("s", "Relay"), ("f/Enter", "Deliver"), ("j/k", "Nav"), ("1-9", "Quick"), ("Esc", "Cancel")]
}

/// Return the context-appropriate key hints.
fn status_bar_hints(empty: bool, focused: bool, detail: bool) -> Vec<KeyHint> {
    if empty {
        vec![("n", "New-defaults"), ("N", "New-wizard"), ("Alt+q", "Save+Quit"), ("q", "Quit-no-save"), ("?", "Help")]
    } else if focused {
        vec![("Alt-f", "Unfocus"), ("Alt+1-9", "Switch-agent"), ("Alt+PgDn/Up", "Cycle"), ("r", "Rename"), ("x", "Kill"), ("i", "Info"), ("n", "New"), ("Alt+q", "Save+Quit"), ("q", "Quit-no-save"), ("?", "Help")]
    } else if detail {
        vec![("i", "Hide info"), ("f/Enter", "Focus"), ("1-9", "Focus-N"), ("j/k", "Nav"), ("r", "Rename"), ("x", "Kill"), ("n", "New"), ("Alt+q", "Save+Quit"), ("q", "Quit-no-save"), ("?", "Help")]
    } else {
        vec![("n", "New-defaults"), ("N", "New-wizard"), ("f/Enter", "Focus"), ("1-9", "Focus-N"), ("r", "Rename"), ("x", "Kill"), ("i", "Info"), ("Alt+q", "Save+Quit"), ("q", "Quit-no-save"), ("?", "Help")]
    }
}

/// Context-sensitive status bar (always rendered as 2 lines for legibility on
/// narrow windows). Hints are split into two roughly equal halves; an
/// optional status message is prefixed to the first line.
fn render_status_bar(
    cols: usize,
    status_message: Option<&str>,
    agents: &[AgentInfo],
    focused: Option<&str>,
    detail: Option<&str>,
    relay_pending: bool,
) {
    if relay_pending {
        let hints = relay_pending_hints();
        let text = format_key_hints(&hints);
        print_status_line(&text, &hints, cols);
        return;
    }

    let is_empty = agents.is_empty();
    let is_focused = focused.is_some();
    let is_detail = detail.is_some();
    let hints = status_bar_hints(is_empty, is_focused, is_detail);

    let mid = hints.len().div_ceil(2);
    let (first_half, second_half) = hints.split_at(mid);

    let line1 = if let Some(msg) = status_message {
        let key_hints = format!(" {}", format_key_hints(first_half));
        let hints_visible = strip_ansi_len(&key_hints);
        let msg_max = cols.saturating_sub(hints_visible + 2);
        format!("{}{}", truncate(msg, msg_max), key_hints)
    } else {
        format_key_hints(first_half)
    };
    print_status_line(&line1, first_half, cols);

    let line2 = format_key_hints(second_half);
    print_status_line(&line2, second_half, cols);
}

/// Print one status-bar line with REVERSE background, falling back to the
/// compact `key:label` format if the rich text overflows.
fn print_status_line(text: &str, hints: &[KeyHint], cols: usize) {
    let visible_len = strip_ansi_len(text);
    let display = if visible_len > cols.saturating_sub(2) {
        let short = format_key_hints_short(hints);
        truncate(&short, cols.saturating_sub(2))
    } else {
        text.to_string()
    };

    let display_visible = strip_ansi_len(&display);
    let padding = cols.saturating_sub(display_visible + 1);
    print!("{} {}{:>pad$}{}", theme::selection(), display, "", RESET, pad = padding);
    println!();
}

/// Print a blank REVERSE-styled line, used to pad single-line overlays
/// (e.g. the name prompt) so the bottom bar always occupies 2 rows.
fn print_status_pad_line(cols: usize) {
    let padding = cols.saturating_sub(1);
    print!("{} {:>pad$}{}", theme::selection(), "", RESET, pad = padding);
    println!();
}

// ── Overlay: Wizard (LINCE-47) ─────────────────────────────────────

pub fn render_wizard(
    wizard: &WizardState,
    rows: usize,
    cols: usize,
    _agent_types: &HashMap<String, AgentTypeConfig>,
    sandbox_colors: &SandboxColors,
    quick_start: bool,
) {
    if rows == 0 || cols == 0 {
        return;
    }

    let box_width: usize = 60.min(cols.saturating_sub(4));
    let mut lines: Vec<String> = Vec::new();

    push_title_border(&mut lines, " New Agent Wizard ", box_width);
    push_box_line(&mut lines, "", box_width);

    // Compute step number / total from the active-steps list so the counter
    // honors all skip rules (single agent type, unsandboxed, no profiles, ...)
    // without nested conditionals.
    let active = wizard.active_steps();
    let total_steps = active.len();
    let step_num = active.iter().position(|s| s == &wizard.step).map(|i| i + 1).unwrap_or(0);
    let step_label = match wizard.step {
        WizardStep::AgentType => "Agent Type",
        WizardStep::SandboxBackend => "Sandbox Backend",
        WizardStep::SandboxLevel => "Sandbox Level (Profile)",
        WizardStep::Name => "Agent Name",
        // gh#81: this step picks an env-var bundle, not a sandbox profile.
        WizardStep::Provider => "Provider",
        WizardStep::ProjectDir => "Project Directory",
        WizardStep::Confirm => "Confirm",
    };

    let header = format!("  Step {}/{}: {}", step_num, total_steps, step_label);
    push_box_line(&mut lines, &header, box_width);
    if quick_start || !matches!(wizard.step, WizardStep::Name | WizardStep::ProjectDir) {
        push_box_line(&mut lines, "  [n] Use defaults; ask only for name", box_width);
    }

    match wizard.step {
        WizardStep::AgentType => {
            // Step 1 lists deduplicated *base* agents (e.g., "Claude Code"). All rows
            // share the "normal" sandbox-level color so the wizard's palette stays
            // consistent with the runtime indicator and the table coloring (gh#63):
            // backend and level are picked in steps 2 and 3, where the palette reveals
            // its meaning. Avoids per-agent colors flickering between this step and
            // the table when an agent's `cfg.color` differs from the level palette.
            let normal_color = sandbox_colors.for_level("normal");
            for (i, (_key, display_name)) in wizard.available_agent_types.iter().enumerate() {
                let is_selected = i == wizard.agent_type_index;
                if is_selected {
                    let bg = selection_bg_for_color(normal_color);
                    push_box_line(&mut lines, &format!("  {}> {}{}", bg, display_name, RESET), box_width);
                } else {
                    let color = color_name_to_ansi(normal_color);
                    push_box_line(&mut lines, &format!("    {}{}{}", color, display_name, RESET), box_width);
                }
            }
            push_box_line(&mut lines, "", box_width);
            push_box_line(&mut lines, "  [j/k] Select  [Enter] Next  [Esc] Cancel", box_width);
        }
        WizardStep::SandboxBackend => {
            for (i, backend) in wizard.available_sandbox_backends.iter().enumerate() {
                let is_selected = i == wizard.sandbox_backend_index;
                // Use red as a visual cue for the unsandboxed (None) choice; sandboxed
                // backends use neutral default styling — the color reveal comes in step 3.
                let label = backend.display_name();
                if is_selected {
                    let bg = if matches!(backend, crate::sandbox_backend::SandboxBackend::None) {
                        theme::selection()
                    } else {
                        theme::selection()
                    };
                    push_box_line(&mut lines, &format!("  {}> {}{}", bg, label, RESET), box_width);
                } else {
                    let prefix = if matches!(backend, crate::sandbox_backend::SandboxBackend::None) {
                        theme::color("red")
                    } else {
                        String::new()
                    };
                    push_box_line(&mut lines, &format!("    {}{}{}", prefix, label, RESET), box_width);
                }
            }
            push_box_line(&mut lines, "", box_width);
            push_box_line(&mut lines, "  [j/k] Select  [Enter] Next  [Bksp] Back  [Esc] Cancel", box_width);
        }
        WizardStep::SandboxLevel => {
            for (i, level) in wizard.available_sandbox_levels.iter().enumerate() {
                let is_selected = i == wizard.sandbox_level_index;
                let color_name = sandbox_colors.for_level(level);
                if is_selected {
                    let bg = selection_bg_for_color(color_name);
                    push_box_line(&mut lines, &format!("  {}> {}{}", bg, level, RESET), box_width);
                } else {
                    let color = color_name_to_ansi(color_name);
                    push_box_line(&mut lines, &format!("    {}{}{}", color, level, RESET), box_width);
                }
            }
            push_box_line(&mut lines, "", box_width);
            push_box_line(&mut lines, "  [j/k] Select  [Enter] Next  [Esc] Cancel", box_width);
        }
        WizardStep::Confirm => {
            let base_display = wizard.selected_base_agent();
            let provider_display = wizard.selected_provider().unwrap_or("(none)");
            let dir_display = if wizard.project_dir.is_empty() { "(current dir)" } else { &wizard.project_dir };
            // Show base agent + backend separately rather than the resolved
            // `<base>-unsandboxed` key — matches the user's mental model.
            push_box_line(&mut lines, &format!("  Type:     {}", base_display), box_width);
            if let Some(backend) = wizard.selected_sandbox_backend() {
                push_box_line(&mut lines, &format!("  Backend:  {}", backend.display_name()), box_width);
            }
            // Profile (sandbox isolation level) is meaningful only when a sandboxed backend is selected.
            if !wizard.is_unsandboxed_choice() {
                if let Some(level) = wizard.selected_sandbox_level() {
                    push_box_line(&mut lines, &format!("  Profile:  {}", level), box_width);
                }
            }
            let effective_name = if wizard.name.is_empty() { &wizard.default_name } else { &wizard.name };
            push_box_line(&mut lines, &format!("  Name:     {}", effective_name), box_width);
            // Provider is the env-var bundle (gh#81 — distinct from Profile/sandbox-level above).
            push_box_line(&mut lines, &format!("  Provider: {}", provider_display), box_width);
            push_box_line(&mut lines, &format!("  Dir:      {}", dir_display), box_width);
            push_box_line(&mut lines, "", box_width);
            push_box_line(
                &mut lines,
                "  [Enter] Create  [!] Create+save defaults  [Bksp] Back  [Esc] Cancel",
                box_width,
            );
        }
        WizardStep::Provider => {
            // Render provider list with selection marker. Providers named
            // after sandbox levels (paranoid/normal/permissive) historically
            // picked up the level palette; we keep that color hint for
            // visual continuity even though the two concepts are distinct
            // (gh#63 / gh#81). Most provider names are env-bundle names
            // (anthropic / vertex / zai) which fall through to the default color.
            for (i, name) in wizard.available_providers.iter().enumerate() {
                let marker = if i == wizard.provider_index { ">" } else { " " };
                let color = color_name_to_ansi(sandbox_colors.for_level(name));
                push_box_line(
                    &mut lines,
                    &format!("  {} {}{}{}", marker, color, name, RESET),
                    box_width,
                );
            }
            push_box_line(&mut lines, "", box_width);
            push_box_line(
                &mut lines,
                "  Provider = env-var bundle (e.g. anthropic, vertex, zai).",
                box_width,
            );
            push_box_line(&mut lines, "  [j/k] Select  [Enter] Next  [Esc] Cancel", box_width);
        }
        WizardStep::ProjectDir => match wizard.project_dir_mode {
            // ── Recents picker (#127) ──────────────────────────────────
            ProjectDirMode::List => {
                push_box_line(
                    &mut lines,
                    &format!("  Filter: {}_", wizard.project_dir_filter),
                    box_width,
                );
                push_box_line(&mut lines, "", box_width);

                let filtered = wizard.filtered_project_dirs();
                if filtered.is_empty() {
                    push_box_line(
                        &mut lines,
                        "  (no match — [Enter] types it as a new path)",
                        box_width,
                    );
                } else {
                    push_box_line(&mut lines, "  RECENTS", box_width);
                    // Scrolling window of up to 6 rows around the selection.
                    let max_show = 6;
                    let total = filtered.len();
                    let sel = wizard.project_dir_index.min(total.saturating_sub(1));
                    let start = if sel >= max_show { sel + 1 - max_show } else { 0 };
                    for (i, entry) in filtered.iter().enumerate().skip(start).take(max_show) {
                        let marker = if i == sel { ">" } else { " " };
                        let short = collapse_tilde(entry);
                        // Truncate from the left to keep the distinguishing tail.
                        let disp = truncate_left(&short, box_width.saturating_sub(6));
                        push_box_line(&mut lines, &format!("  {} {}", marker, disp), box_width);
                    }
                    if total > start + max_show {
                        push_box_line(
                            &mut lines,
                            &format!("    (+{} more)", total - (start + max_show)),
                            box_width,
                        );
                    }
                }
                push_box_line(&mut lines, "", box_width);
                // `[i] free text` only applies while the filter is empty (that's
                // when `i` switches modes); once filtering, Backspace backs out.
                let hint = if wizard.project_dir_filter.is_empty() {
                    "  [type] filter  [\u{2191}/\u{2193}] move  [Enter] select  [i] free text"
                } else {
                    "  [type] filter  [\u{2191}/\u{2193}] move  [Enter] select  [\u{232b}] back"
                };
                push_box_line(&mut lines, hint, box_width);
            }
            // ── Free-text input (legacy escape hatch) ──────────────────
            ProjectDirMode::Input => {
                // Horizontal scroll: show the tail of the input when it overflows.
                let input_prefix = "  > ";
                let input_suffix = "_";
                let max_visible = box_width.saturating_sub(4 + input_prefix.len() + input_suffix.len());
                let dir_display = if wizard.project_dir.chars().count() > max_visible && max_visible > 1 {
                    let skip = wizard.project_dir.chars().count() - max_visible + 1;
                    let s: String = wizard.project_dir.chars().skip(skip).collect();
                    format!("\u{2026}{}", s) // …prefix
                } else {
                    wizard.project_dir.clone()
                };
                push_box_line(&mut lines, &format!("{}{}{}", input_prefix, dir_display, input_suffix), box_width);

                // Show completion suggestions (max 5 visible).
                if !wizard.completions.is_empty() {
                    let max_show = 5.min(wizard.completions.len());
                    for (i, entry) in wizard.completions.iter().take(max_show).enumerate() {
                        let marker = if wizard.completion_index == Some(i) { ">" } else { " " };
                        let display = truncate_left(entry, box_width.saturating_sub(6));
                        push_box_line(&mut lines, &format!("  {} {}", marker, display), box_width);
                    }
                    if wizard.completions.len() > max_show {
                        push_box_line(
                            &mut lines,
                            &format!("    (+{} more)", wizard.completions.len() - max_show),
                            box_width,
                        );
                    }
                } else if wizard.project_dir_suggested {
                    // #168: the field is pre-filled from the selected agent's dir.
                    push_box_line(&mut lines, "  (from selected agent — Backspace to clear)", box_width);
                    push_box_line(&mut lines, "  [Tab] autocomplete path", box_width);
                } else {
                    push_box_line(&mut lines, "  (default: current directory)", box_width);
                    push_box_line(&mut lines, "  [Tab] autocomplete path", box_width);
                }
                // Validation error line (set by the ProjectDir Enter handler when
                // the path is empty/relative/tilde-prefixed). Bold red, cleared as
                // soon as the user edits the field.
                if let Some(ref err) = wizard.project_dir_error {
                    push_box_line(&mut lines, "", box_width);
                    push_box_line(
                        &mut lines,
                        &format!("  {}✗ {}{}", theme::color("red"), err, RESET),
                        box_width,
                    );
                }
                push_box_line(&mut lines, "", box_width);
                push_box_line(&mut lines, "  [Enter] Next  [Esc] Cancel", box_width);
            }
        }
        WizardStep::Name => {
            // Horizontal scroll for name input too.
            let input_prefix = "  > ";
            let input_suffix = "_";
            let max_visible = box_width.saturating_sub(4 + input_prefix.len() + input_suffix.len());
            let name_display = if wizard.name.chars().count() > max_visible && max_visible > 1 {
                let skip = wizard.name.chars().count() - max_visible + 1;
                let s: String = wizard.name.chars().skip(skip).collect();
                format!("\u{2026}{}", s)
            } else {
                wizard.name.clone()
            };
            push_box_line(&mut lines, &format!("{}{}{}", input_prefix, name_display, input_suffix), box_width);
            push_box_line(&mut lines, &format!("  (leave empty for \"{}\")", wizard.default_name), box_width);
            push_box_line(&mut lines, "", box_width);
            push_box_line(&mut lines, "  [Enter] Next  [Esc] Cancel", box_width);
        }
    }

    push_bottom_border(&mut lines, box_width);
    render_centered_box(&lines, rows, cols, box_width);
}

// ── Overlay: Help (keybinding reference) ────────────────────────────

pub fn render_help_overlay(rows: usize, cols: usize) {
    if rows == 0 || cols == 0 { return; }
    let hints = ["LINCE — Keybindings", "Alt+d        Expanded agent list",
        "Alt+i/h      Info / help", "Alt+s        Toggle sidebar",
        "Alt+b        Bar: hidden / summary / full", "Alt+n        New agent wizard",
        "j/k, arrows  Select agent", "1-9, Enter/f Focus agent", "Alt+1-9      Switch from any pane",
        "Alt+PgUp/Dn  Cycle agents", "i            Info (PgUp/Dn scroll)",
        "n            New agent", "N            New agent wizard", "r            Rename selected",
        "x            Kill selected", "s            Relay last message", "S            Relay N messages",
        "Alt+q / Q    Save and quit", "q (list)     Quit without saving", "Esc / ?      Close help"];
    for row in 0..rows {
        println!("{}", clip_cells(hints.get(row).copied().unwrap_or(""), cols));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Plain text fits — return as-is.
    #[test]
    fn truncate_plain_no_op() {
        assert_eq!(truncate("hello", 10), "hello");
    }

    /// Plain text too long — visible-width truncation with ellipsis.
    #[test]
    fn truncate_plain_long() {
        assert_eq!(truncate("hello world", 8), "hello...");
        assert_eq!(strip_ansi_len(&truncate("hello world", 8)), 8);
    }

    /// Embedded CSI sequences must NOT count as visible chars and must NOT
    /// be cut mid-sequence. Regression test for gh#95: a half-formed CSI
    /// leaks into the next println, swallowing leading bytes of the next row.
    #[test]
    fn truncate_preserves_csi_and_visible_width() {
        let red = "\x1b[1;31m";
        let reset = "\x1b[0m";
        let input = format!("{red}BSU!{reset} agent name");
        // Visible: "BSU! agent name" = 15 chars. Pre-fix this would count the
        // raw bytes (~26) and cut inside the CSI.
        let out = truncate(&input, 10);
        assert_eq!(strip_ansi_len(&out), 10, "visible width must be exactly 10");
        // Original CSI must be present intact (no truncated escape).
        assert!(out.contains(red), "leading CSI must survive verbatim");
    }

    /// When truncation actually happens, RESET is emitted after the copied
    /// content so the ellipsis (and downstream output) can't render with
    /// whatever attribute the input string left dangling.
    #[test]
    fn truncate_closes_dangling_attribute() {
        let input = "\x1b[1;31mBSU! is a label longer than the budget".to_string();
        let out = truncate(&input, 10);
        assert!(out.contains("\x1b[0m"), "must emit RESET before ellipsis");
    }

    /// Width below 3 uses no ellipsis (matches old behaviour for tiny widths).
    #[test]
    fn truncate_tiny_width_no_ellipsis() {
        assert_eq!(strip_ansi_len(&truncate("hello", 2)), 2);
        assert!(!truncate("hello", 2).contains("..."));
    }

    /// strip_ansi_len's parser definition — the truncate copy loop relies on
    /// this matching exactly (escape-final-byte = ASCII alphabetic), so make
    /// the contract explicit.
    #[test]
    fn strip_ansi_len_matches_truncate_loop_contract() {
        assert_eq!(strip_ansi_len("\x1b[1;31mhi\x1b[0m"), 2);
    }
}

#[cfg(test)]
pub(crate) fn preview_agent(name: &str, status: AgentStatus) -> AgentInfo {
    AgentInfo {
        id: name.into(), name: name.into(), agent_type: "claude".into(),
        provider: None, project_dir: "/work/lince".into(), status, pane_id: None,
        started_at: None, last_error: None, exit_code: None, group: None,
        last_polled_event: None, sandbox_level: Some("normal".into()),
        sandbox_backend: None, transcript_path: None, icon: String::new(), enforced: None,
    }
}

#[cfg(test)]
mod previews {
    use super::*;
    /// Real renderer output used by tests/render-theme-previews.py.
    #[test]
    #[ignore]
    fn theme_previews() {
        let agents = vec![preview_agent("lince-1", AgentStatus::Running),
            preview_agent("review", AgentStatus::WaitingForInput),
            preview_agent("fix-auth", AgentStatus::PermissionRequired)];
        for name in ["default", "minimal-mono", "dracula", "gruvbox"] {
            println!("PREVIEW:{name}");
            theme::set(name, None);
            render_dashboard(&agents, 0, Some("lince-1"), None, 14, 76,
                None, None, None, &crate::config::embedded_agent_types(), &SandboxColors::default(), false, 0);
            println!("\nENDPREVIEW");
        }
    }
}

/// Cell-aware clipping for dense views. Never forwards controls from agent names.
pub(crate) fn clip_cells(text: &str, width: usize) -> String {
    let mut used = 0;
    text.chars().filter(|c| !c.is_control()).take_while(|c| {
        used += c.width().unwrap_or(0);
        used <= width
    }).collect()
}

pub(crate) fn status_letter(status: &AgentStatus) -> char {
    match status {
        AgentStatus::Unknown => '-', AgentStatus::Running => 'R',
        AgentStatus::WaitingForInput => 'I', AgentStatus::PermissionRequired => 'P',
        AgentStatus::Stopped => 'S',
    }
}

pub(crate) fn compact_name(agent: &AgentInfo, types: &HashMap<String, AgentTypeConfig>) -> String {
    let label = types.get(&agent.agent_type).map(|cfg| cfg.short_label.as_str()).unwrap_or("???");
    let name: String = agent.name.chars().filter(|c| !c.is_control()).take(5).collect();
    format!("{}-{name}", clip_cells(label, 3))
}

pub(crate) fn sandbox_badge(agent: &AgentInfo, types: &HashMap<String, AgentTypeConfig>) -> String {
    use crate::sandbox_backend::SandboxBackend;
    if matches!(agent.sandbox_backend, Some(SandboxBackend::None))
        || types.get(&agent.agent_type).map_or(false, |cfg| !cfg.sandboxed) {
        return "NOSB".into();
    }
    agent.sandbox_level.clone().or_else(|| types.get(&agent.agent_type).and_then(|cfg| cfg.sandbox_level.clone()))
        .unwrap_or_else(|| "unknown".into())
}

pub(crate) fn needs_attention(status: &AgentStatus) -> bool {
    matches!(status, AgentStatus::WaitingForInput | AgentStatus::PermissionRequired)
}

fn render_compact(
    agents: &[AgentInfo], selected: usize, focused: Option<&str>, detail: Option<&str>,
    rows: usize, cols: usize, message: Option<&str>, prompt: Option<&NamePromptState>,
    relay: Option<&RelayPhase>, types: &HashMap<String, AgentTypeConfig>, info_scroll: usize,
) {
    let available = rows.saturating_sub(1);
    if let Some(agent) = detail.and_then(|id| agents.iter().find(|a| a.id == id)) {
        // Information occupies the whole sidebar; no ten-row table reservation.
        let lines = vec![format!("Name: {}", agent.name), format!("ID: {}", agent.id),
            format!("Type: {}", agent.agent_type), format!("Status: {}", agent.status_display()),
            format!("Sandbox: {}", sandbox_badge(agent, types)),
            format!("Backend: {}", agent.sandbox_backend.as_ref().map(|b| b.display_name()).unwrap_or("unknown")),
            format!("Provider: {}", agent.provider.as_deref().unwrap_or("default")),
            format!("Directory: {}", agent.project_dir),
            format!("Started: {}", agent.started_at.map(format_elapsed).unwrap_or_else(|| "-".into())),
            format!("Enforced: {}", agent.enforced.as_ref().map(|p| p.badge()).unwrap_or_else(|| "unknown".into())),
            format!("Error: {}", agent.last_error.as_deref().unwrap_or("-"))];
        let wrapped: Vec<String> = lines.iter().flat_map(|line| wrap_cells(line, cols)).collect();
        let offset = info_scroll.min(wrapped.len().saturating_sub(available));
        for r in 0..available {
            println!("{}", wrapped.get(offset + r).map(String::as_str).unwrap_or(""));
        }
    } else {
        // Virtual rows preserve project grouping without repeating paths per agent.
        let mut lines: Vec<(Option<usize>, String)> = Vec::new();
        let mut previous = "";
        let mut group_index = 0;
        let number_width = agents.len().to_string().len();
        for (i, agent) in agents.iter().enumerate() {
            if agent.project_dir != previous {
                previous = &agent.project_dir;
                let leaf = previous.trim_end_matches('/').rsplit('/').next().unwrap_or(previous);
                let duplicate = agents.iter().any(|a| a.project_dir != previous
                    && a.project_dir.trim_end_matches('/').rsplit('/').next() == Some(leaf));
                let heading = if duplicate { previous } else { leaf };
                let heading = clip_cells(&format!("┌ {heading} "), cols);
                let width: usize = heading.chars().map(|c| c.width().unwrap_or(0)).sum();
                lines.push((None, format!("{BOLD}{}{}{}{RESET}", theme::group(group_index),
                    heading, "─".repeat(cols.saturating_sub(width)))));
                group_index += 1;
            }
            let badge = sandbox_badge(agent, types);
            let marker = if badge != "normal" { '!' } else { ' ' };
            let focus = if focused == Some(agent.id.as_str()) { '*' } else if i == selected { '>' } else { ' ' };
            let label = types.get(&agent.agent_type).map(|cfg| cfg.short_label.as_str()).unwrap_or("???");
            let name = clip_cells(&format!("{focus}{marker}{:>number_width$} {}", i + 1, clip_cells(label, 3)), cols.saturating_sub(2));
            let width: usize = name.chars().map(|c| c.width().unwrap_or(0)).sum();
            let text = if cols < 3 { status_letter(&agent.status).to_string() } else {
                format!("{}{} {}{}{}", name, " ".repeat(cols.saturating_sub(width + 2)),
                    theme::status(&agent.status), status_letter(&agent.status), RESET)
            };
            let selected_style = if i == selected { theme::selection() } else { String::new() };
            lines.push((Some(i), format!("{selected_style}{text}{RESET}")));
        }
        if agents.is_empty() { lines.push((None, clip_cells("n: new agent  ?: help", cols))); }
        let selected_row = lines.iter().position(|(i, _)| *i == Some(selected)).unwrap_or(0);
        let offset = selected_row.saturating_sub(available.saturating_sub(1));
        for r in 0..available {
            println!("{}", lines.get(offset + r).map(|(_, line)| line.as_str()).unwrap_or(""));
        }
    }
    if let Some(prompt) = prompt {
        render_name_prompt_bar(prompt, cols);
    } else if let Some(RelayPhase::MessagePrompt { input }) = relay {
        render_relay_message_prompt(input, cols);
    } else {
        let waiting = agents.iter().filter(|a| needs_attention(&a.status)).count();
        let footer = if detail.is_some() { "PgUp/PgDn scroll i:close".into() } else { message.map(str::to_string).unwrap_or_else(||
            if matches!(relay, Some(RelayPhase::DeliveryPending { .. })) {
                "Enter:send Esc:cancel".into()
            } else { format!("!{waiting} Alt+d:list i:info") }) };
        print!("{}", clip_cells(&footer, cols));
    }
}

#[cfg(test)]
mod compact_tests {
    use super::*;
    #[test]
    fn generated_names_and_unicode_do_not_lose_identity() {
        let mut agent = preview_agent("lince-12", AgentStatus::Unknown);
        let types = crate::config::embedded_agent_types();
        assert_eq!(compact_name(&agent, &types), "CLA-lince");
        agent.agent_type = "codex".into();
        agent.name = "pippo-long".into();
        assert_eq!(compact_name(&agent, &types), "CDX-pippo");
        agent.name = "界界界界界界".into();
        assert_eq!(compact_name(&agent, &types), "CDX-界界界界界");
        assert_eq!(clip_cells("界abc", 1), "");
        assert_eq!(clip_cells("a\nb", 2), "ab");
    }
    #[test]
    fn statuses_and_sandbox_are_not_color_only() {
        let mut agent = preview_agent("lince-1", AgentStatus::PermissionRequired);
        assert_eq!(status_letter(&agent.status), 'P');
        assert!(needs_attention(&agent.status));
        assert!(!needs_attention(&AgentStatus::Unknown));
        agent.sandbox_backend = Some(crate::sandbox_backend::SandboxBackend::None);
        assert_eq!(sandbox_badge(&agent, &HashMap::new()), "NOSB");
    }
}

fn wrap_cells(text: &str, cols: usize) -> Vec<String> {
    if cols == 0 { return Vec::new(); }
    let mut lines = Vec::new();
    let mut line = String::new();
    let mut width = 0;
    for c in text.chars().filter(|c| !c.is_control()) {
        let cell_width = c.width().unwrap_or(0);
        if width + cell_width > cols && !line.is_empty() {
            lines.push(std::mem::take(&mut line));
            width = 0;
        }
        if cell_width <= cols { line.push(c); width += cell_width; }
    }
    lines.push(line);
    lines
}

#[cfg(test)]
mod dense_render_tests {
    use super::*;
    fn visible_width(line: &str) -> usize {
        let mut escape = false;
        line.chars().filter(|c| {
            if *c == '\x1b' { escape = true; return false; }
            if escape { if c.is_ascii_alphabetic() { escape = false; } return false; }
            true
        }).map(|c| c.width().unwrap_or(0)).sum()
    }
    #[test]
    fn compact_frame_fits_even_tiny_or_unicode_viewports() {
        let agents = vec![preview_agent("界界界界界", AgentStatus::PermissionRequired)];
        for rows in [1, 3, 8] {
            for cols in [1, 2, 18, 25, 40] {
                let frame = crate::render_output::capture(|| render_dashboard(&agents, 0, None,
                    None, rows, cols, None, None, None, &HashMap::new(), &SandboxColors::default(), true, 0));
                assert!(frame.lines().count() <= rows);
                assert!(frame.lines().all(|line| visible_width(line) <= cols), "{rows}x{cols}: {frame:?}");
            }
        }
    }
    #[test]
    fn compact_projects_have_colored_rules_and_global_agent_numbers() {
        theme::set("default", None);
        let mut agents: Vec<_> = (1..=12).map(|i| preview_agent(&format!("lince-{i}"), AgentStatus::Running)).collect();
        agents[11].project_dir = "/work/other".into();
        let frame = crate::render_output::capture(|| render_dashboard(&agents, 11, None,
            None, 18, 28, None, None, None, &crate::config::embedded_agent_types(), &SandboxColors::default(), true, 0));
        assert!(frame.contains(&format!("{BOLD}{}┌ lince ", theme::group(0))));
        assert!(frame.contains(&format!("{BOLD}{}┌ other ", theme::group(1))));
        assert!(frame.contains(" 1 CLA"));
        assert!(frame.contains("12 CLA"));
        assert!(!frame.contains("lince-12"));
        assert!(!frame.contains("P-1"));
        assert!(frame.contains("───"));
        assert!(frame.lines().all(|line| visible_width(line) <= 28));
    }
    #[test]
    fn detail_pages_wrap_long_paths_without_losing_cells() {
        assert_eq!(wrap_cells("ab界cd", 4), vec!["ab界", "cd"]);
        let mut agent = preview_agent("lince-1", AgentStatus::Unknown);
        agent.project_dir = format!("/work/{}/tail", "long-directory/".repeat(8));
        let render = |scroll| crate::render_output::capture(|| render_dashboard(&[agent.clone()], 0,
            None, Some("lince-1"), 8, 25, None, None, None, &HashMap::new(), &SandboxColors::default(), false, scroll));
        assert!(render(0).contains("Name:"));
        assert_ne!(render(0), render(8));
        assert!(render(999).contains("tail"));
    }
}
