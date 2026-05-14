use std::collections::HashMap;

use crate::config::{AgentTypeConfig, SandboxColors};
use crate::types::{
    AgentInfo, AgentStatus, NamePromptState, WizardState, WizardStep,
};

/// Map a color name from config to an ANSI escape code.
fn color_name_to_ansi(name: &str) -> &'static str {
    match name {
        "red" => "\x1b[31m",
        "green" => "\x1b[32m",
        "yellow" => "\x1b[33m",
        "blue" => "\x1b[34m",
        "magenta" => "\x1b[35m",
        "cyan" => "\x1b[36m",
        "white" => "\x1b[37m",
        _ => "\x1b[37m",  // default to white
    }
}

/// ANSI background sequence for the wizard's selection block.
///
/// Forces a black foreground for light backgrounds (yellow/cyan/white) so
/// the highlighted text stays readable. Dark backgrounds keep the default
/// foreground.
fn selection_bg_for_color(name: &str) -> &'static str {
    match name {
        "red" => "\x1b[41m",
        "green" => "\x1b[42m",
        "yellow" => "\x1b[30;43m",
        "blue" => "\x1b[44m",
        "magenta" => "\x1b[45m",
        "cyan" => "\x1b[30;46m",
        "white" => "\x1b[30;47m",
        _ => "\x1b[30;47m",
    }
}

const RESET: &str = "\x1b[0m";
const BOLD: &str = "\x1b[1m";
const REVERSE: &str = "\x1b[7m";
const BOLD_REVERSE: &str = "\x1b[1;7m";
const DIM: &str = "\x1b[2m";
const CYAN: &str = "\x1b[36m";
const KEY_COLOR: &str = "\x1b[1;36m"; // bold cyan for key hints
const BLUE_BOLD: &str = "\x1b[1;34m"; // blue bold for swimlane headers

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
    agent_types: &HashMap<String, AgentTypeConfig>,
    sandbox_colors: &SandboxColors,
) {
    if rows == 0 || cols == 0 {
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
            } else {
                render_status_bar(cols, status_message, agents, focused, detail);
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
    } else {
        render_status_bar(cols, status_message, agents, focused, detail);
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
        BOLD_REVERSE, "", title, "", RESET,
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
            print!("{:>width$}\x1b[33m{}{}", "", msg_display, RESET, width = pad);
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
        if last_dir != Some(&agent.project_dir) {
            virtual_rows.push(None);
            header_dirs.push(agent.project_dir.clone());
            last_dir = Some(&agent.project_dir);
        }
        virtual_rows.push(Some(i));
        header_dirs.push(String::new());
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
                // Swimlane header row
                let dir = &header_dirs[vrow];
                let short = collapse_tilde(dir);
                let fill_len = cols.saturating_sub(short.len() + 5);
                println!(
                    " {}\u{250c} {} {}{}",
                    BLUE_BOLD, short, repeat_char('\u{2500}', fill_len), RESET,
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
                let status_color = agent.status.color();
                let needs_attention = matches!(
                    agent.status,
                    AgentStatus::WaitingForInput | AgentStatus::PermissionRequired
                );

                // Build type label column — always visible.
                // Color comes from the runtime sandbox_level (wizard selection) when set,
                // mapped through sandbox_colors; falls back to the per-type config color.
                let type_col = if let Some(cfg) = agent_types.get(&agent.agent_type) {
                    if !cfg.sandboxed {
                        format!(" \x1b[1;31m{}!{}", pad_left(&cfg.short_label, col_type.saturating_sub(2)), RESET)
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
                            pad_left(backend.display_name(), col_sandbox)
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
                        "{}{}{} {}",
                        prefix, pad_left(&idx_str, col_idx), type_col,
                        pad_left(&agent.name, col_name),
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
                        REVERSE, main_part,
                        status_color, if needs_attention { BOLD } else { "" },
                        status_str,
                        trailing, RESET,
                    );
                    if fill > 0 {
                        print!("{}{:>fill$}{}", REVERSE, "", RESET, fill = fill);
                    }
                    println!();
                } else {
                    // For non-selected rows, use display_name (with group suffix) in the name column
                    let name_field = if agent.group.is_some() {
                        let base = pad_left(&agent.name, col_name.saturating_sub(agent.group.as_ref().map_or(0, |g| g.len() + 3)));
                        if let Some(ref group) = agent.group {
                            format!("{} {}[{}]{}", base, DIM, group, RESET)
                        } else {
                            base
                        }
                    } else {
                        pad_left(&agent.name, col_name)
                    };

                    // Wrap the plain sandbox content with its color attribute
                    // for non-selected rows. NOSB is bold-red, sandboxed
                    // backends are dim, unknown/no-config is plain.
                    let sandbox_col = if show_sandbox {
                        if let Some(cfg) = agent_types.get(&agent.agent_type) {
                            if !cfg.sandboxed {
                                format!("\x1b[1;31m{}{} ", sandbox_plain, RESET)
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
                    " \x1b[1;31m[UNSANDBOXED]\x1b[0m".to_string()
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
                (agent.agent_type.as_str(), RESET, String::new())
            };
        let detail_status = agent.status_display();
        println!(
            " {}Agent:{} {}  {}{}{}{} {}{}{}",
            CYAN, RESET, agent.name,
            type_color, type_display, RESET, sandbox_info,
            agent.status.color(), detail_status, RESET,
        );
        row += 1;
    }
    // Show "Profile" (sandbox isolation level — paranoid/normal/permissive)
    // and "Provider" (env-var bundle — anthropic/vertex/zai/...) on
    // SEPARATE lines. They're orthogonal axes; conflating them confused users
    // (gh#81). Either may be `(default)` independently.
    if row < max_rows {
        let profile = agent.sandbox_level.as_deref().unwrap_or("(default)");
        println!(" {}Profile:{} {}", CYAN, RESET, profile);
        row += 1;
    }
    if row < max_rows {
        let provider = agent.provider.as_deref().unwrap_or("(default)");
        println!(" {}Provider:{} {}", CYAN, RESET, provider);
        row += 1;
    }
    if row < max_rows {
        println!(" {}Dir:{} {}", CYAN, RESET, agent.project_dir);
        row += 1;
    }
    if row < max_rows {
        let started = agent.started_at.map_or("-".to_string(), format_elapsed);
        println!(" {}Started:{} {}", CYAN, RESET, started);
        row += 1;
    }
    if row < max_rows {
        if let Some(ref err) = agent.last_error {
            println!(" {}Error:{} \x1b[31m{}{}", CYAN, RESET, truncate(err, cols.saturating_sub(10)), RESET);
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
        CYAN, prompt.label, RESET, input_part, hint,
        KEY_COLOR, RESET, KEY_COLOR, RESET,
    );

    let visible_len = strip_ansi_len(&text);
    let padding = cols.saturating_sub(visible_len + 1);
    print!("\x1b[44m {}{:>pad$}{}", text, "", RESET, pad = padding);
    println!();
}

/// A key hint entry: (key label, description).
type KeyHint = (&'static str, &'static str);

/// Format a list of key hints with ANSI key coloring for the full status bar.
fn format_key_hints(hints: &[KeyHint]) -> String {
    hints
        .iter()
        .map(|(key, label)| format!("{}[{}]{} {}", KEY_COLOR, key, RESET, label))
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

/// Return the context-appropriate key hints.
fn status_bar_hints(empty: bool, focused: bool, detail: bool) -> Vec<KeyHint> {
    if empty {
        vec![("n", "New-defaults"), ("N", "New-wizard"), ("U", "New-unsandboxed"), ("Q", "Save+Quit"), ("?", "Help")]
    } else if focused {
        vec![("Alt-f", "Unfocus"), ("Alt+1-9", "Switch-agent"), ("Alt+PgDn/Up", "Cycle"), ("r", "Rename"), ("x", "Kill"), ("i", "Info"), ("n", "New"), ("U", "New-unsandboxed"), ("Q", "Save+Quit"), ("?", "Help")]
    } else if detail {
        vec![("i", "Hide info"), ("f/Enter", "Focus"), ("1-9", "Focus-N"), ("j/k", "Nav"), ("r", "Rename"), ("x", "Kill"), ("n", "New"), ("U", "New-unsandboxed"), ("Q", "Save+Quit"), ("?", "Help")]
    } else {
        vec![("n", "New-defaults"), ("N", "New-wizard"), ("U", "New-unsandboxed"), ("f/Enter", "Focus"), ("1-9", "Focus-N"), ("r", "Rename"), ("x", "Kill"), ("i", "Info"), ("Q", "Save+Quit"), ("?", "Help")]
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
) {
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
    print!("{} {}{:>pad$}{}", REVERSE, display, "", RESET, pad = padding);
    println!();
}

/// Print a blank REVERSE-styled line, used to pad single-line overlays
/// (e.g. the name prompt) so the bottom bar always occupies 2 rows.
fn print_status_pad_line(cols: usize) {
    let padding = cols.saturating_sub(1);
    print!("{} {:>pad$}{}", REVERSE, "", RESET, pad = padding);
    println!();
}

// ── Overlay: Wizard (LINCE-47) ─────────────────────────────────────

pub fn render_wizard(
    wizard: &WizardState,
    rows: usize,
    cols: usize,
    _agent_types: &HashMap<String, AgentTypeConfig>,
    sandbox_colors: &SandboxColors,
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
                        "\x1b[41m"
                    } else {
                        REVERSE
                    };
                    push_box_line(&mut lines, &format!("  {}> {}{}", bg, label, RESET), box_width);
                } else {
                    let prefix = if matches!(backend, crate::sandbox_backend::SandboxBackend::None) {
                        "\x1b[31m"
                    } else {
                        ""
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
        WizardStep::ProjectDir => {
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
                    // Truncate long paths to fit the box.
                    let max_len = box_width.saturating_sub(6);
                    let display: &str = if entry.len() > max_len {
                        // Truncate from the left (show the distinguishing tail).
                        // Advance past any mid-char byte to a valid UTF-8 boundary.
                        let mut start = entry.len() - max_len;
                        while !entry.is_char_boundary(start) && start < entry.len() {
                            start += 1;
                        }
                        &entry[start..]
                    } else {
                        entry
                    };
                    push_box_line(&mut lines, &format!("  {} {}", marker, display), box_width);
                }
                if wizard.completions.len() > max_show {
                    push_box_line(
                        &mut lines,
                        &format!("    (+{} more)", wizard.completions.len() - max_show),
                        box_width,
                    );
                }
            } else {
                push_box_line(&mut lines, "  (default: current directory)", box_width);
                push_box_line(&mut lines, "  [Tab] autocomplete path", box_width);
            }
            push_box_line(&mut lines, "", box_width);
            push_box_line(&mut lines, "  [Enter] Next  [Esc] Cancel", box_width);
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
    if rows == 0 || cols == 0 {
        return;
    }

    let box_width: usize = 48.min(cols.saturating_sub(4));
    let mut lines: Vec<String> = Vec::new();

    push_title_border(&mut lines, " Keybindings ", box_width);
    push_box_line(&mut lines, "", box_width);

    push_box_line(&mut lines, &format!("  {}Navigation{}", BOLD, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}j / Down{}   Move selection down", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}k / Up{}     Move selection up", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}1-9{}        Select & focus agent #", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}Alt+1-9{}    Global: switch to agent #", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}Alt+PgDn/Up{} Cycle to next/prev agent", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, "", box_width);

    push_box_line(&mut lines, &format!("  {}Actions{}", BOLD, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}Enter / f{}  Focus agent pane", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}i{}          Toggle info panel", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}r{}          Rename selected agent", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}x{}          Kill agent", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}h / Esc{}    Unfocus / close / back", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, "", box_width);

    push_box_line(&mut lines, &format!("  {}Create{}", BOLD, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}n{}          New agent (name prompt)", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}N{}          New agent wizard", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}U{}          Quick unsandboxed (skip wizard)", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, "", box_width);

    push_box_line(&mut lines, &format!("  {}Other{}", BOLD, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}Q{}          Save state & quit Zellij", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, &format!("  {}?{}          Toggle this help", KEY_COLOR, RESET), box_width);
    push_box_line(&mut lines, "", box_width);

    let help = format!("  Press {}?{} or {}Esc{} to close", KEY_COLOR, RESET, KEY_COLOR, RESET);
    lines.push(format!("\u{2502}{}\u{2502}", pad_to_width(&help, box_width.saturating_sub(2))));
    push_bottom_border(&mut lines, box_width);

    render_centered_box(&lines, rows, cols, box_width);
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
