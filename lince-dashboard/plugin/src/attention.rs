//! Read-only UI snapshot. Only the controller owns agents, hooks and persistence.
use serde::{Deserialize, Serialize};
use zellij_tile::prelude::*;
use crate::{dashboard, theme};
use crate::config::DashboardConfig;
use crate::types::{AgentInfo, AgentStatus};
use unicode_width::UnicodeWidthChar;

pub const SNAPSHOT: &str = "lince-ui-snapshot";
pub const REFRESH: &str = "lince-ui-refresh";
pub const OPEN: &str = "lince-ui-open";

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Snapshot {
    #[serde(default)]
    pub summary_only: bool,
    #[serde(default)]
    pub suppress_attention_blink: bool,
    #[serde(default)]
    pub agents_only: bool,
    #[serde(default)]
    pub voice: Option<String>,
    pub theme: String,
    pub agents: Vec<Entry>,
    pub warning: Option<String>,
    #[serde(default)]
    pub mailbox: String,
    #[serde(default)]
    pub provenance: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Entry {
    pub slot: usize,
    pub label: String,
    pub status: char,
    pub attention: bool,
    pub focused: bool,
    pub sandbox: String,
    pub sandbox_color: String,
    #[serde(default)]
    pub provenance: String,
}
impl Snapshot {
    pub fn from_agents(agents: &[AgentInfo], focused: Option<&str>, config: &DashboardConfig, warning: Option<&str>) -> Self {
        Self {
            summary_only: false,
            suppress_attention_blink: !config.attention_blink,
            agents_only: false,
            voice: None,
            mailbox: "Mailbox off".into(),
            provenance: "—".into(),
            theme: config.theme.clone(), warning: warning.map(str::to_owned),
            agents: agents.iter().enumerate().map(|(i, a)| Entry {
                slot: i + 1, label: dashboard::compact_name(a),
                status: dashboard::status_letter(&a.status),
                attention: dashboard::needs_attention(&a.status),
                focused: focused == Some(a.id.as_str()),
                sandbox: dashboard::sandbox_badge(a, &config.agent_types),
                sandbox_color: dashboard::permission_color(&dashboard::sandbox_badge(a, &config.agent_types)).into(),
                provenance: String::new(),
            }).collect(),
        }
    }

    fn summary(&self, _down: bool, lower_row: bool, _single_row: bool) -> Vec<(String, String)> {
        vec![(if lower_row { self.mailbox.clone() } else { self.voice.clone().unwrap_or_default() },
              if lower_row { theme::attention_count() } else { theme::color("cyan") })]
    }
    fn groups(&self, dot: bool) -> Vec<Vec<(String, String)>> {
        let mut groups = vec![self.summary(dot, true, true)];
        for entry in &self.agents {
            let name_color = theme::permission_name(&entry.sandbox_color);
            let (symbol, color) = dashboard::attention_symbol(entry.status, dot && !self.suppress_attention_blink)
                .unwrap_or_else(|| (entry.status, entry.color()));
            // Match the selected-row treatment in the sidebar: the focused
            // agent is a full highlighted tab, with the selection foreground
            // retained for contrast instead of the normal white name colour.
            let selected = entry.focused.then(theme::selection);
            let tab_color = |color: String| selected.clone().unwrap_or(color);
            groups.push(vec![
                ("|".into(), theme::color("white")),
                (format!("{}{} ", if entry.focused { '*' } else { ' ' }, entry.slot),
                    tab_color(name_color.clone())),
                (entry.label.clone(), tab_color(name_color)),
                (format!(" {}{symbol}", entry.provenance), tab_color(color)),
            ]);
        }
        if let Some(warning) = &self.warning {
            groups.push(vec![(format!(" | ! {warning}"), theme::color("yellow"))]);
        }
        groups
    }
    fn styled_lines(&self, rows: usize, cols: usize, down: bool) -> Vec<String> {
        if rows == 0 || cols == 0 { return Vec::new(); }
        let width = |text: &str| text.chars().map(|c| c.width().unwrap_or(0)).sum::<usize>();
        let cell_width = |group: &Vec<(String, String)>| -> usize {
            group.iter().map(|(text, _)| width(text)).sum()
        };
        let append = |line: &mut String, group: &Vec<(String, String)>, mut space: usize| {
            let initial = space;
            for (text, color) in group {
                let clipped = dashboard::clip_cells(text, space);
                space = space.saturating_sub(width(&clipped));
                line.push_str(&format!("{color}{clipped}\x1b[0m"));
                if clipped != dashboard::clip_cells(text, usize::MAX) { break; }
            }
            initial - space
        };
        // Deterministic narrow layout: keep the details hint first, then split
        // remaining width between mailbox/voice and agent entries. Both fixed
        // side columns keep their position while names and voice levels change.
        let right_width = if cols >= 72 { 28.min(cols / 3) } else { 13.min(cols) };
        let left_width = if self.agents_only { 0 } else { 24.min((cols - right_width) / 2) };
        let center_width = cols - right_width - left_width;
        let mut center = vec![String::new(); rows.min(2)];
        let mut used = vec![0; center.len()];
        if !self.summary_only && center_width > 0 {
            let mut row = 0;
            for group in self.groups(down).iter().skip(1) {
                let cells = cell_width(group);
                if cells > center_width.saturating_sub(used[row]) && used[row] > 0 && row + 1 < center.len() {
                    row += 1;
                }
                used[row] += append(&mut center[row], group, center_width.saturating_sub(used[row]));
                if used[row] == center_width && row + 1 == center.len() { break; }
            }
        }
        let mut lines = Vec::new();
        for row in 0..center.len() {
            let mut line = String::new();
            let left = self.summary(down, row == 1 || center.len() == 1, center.len() == 1);
            let taken = append(&mut line, &left, left_width);
            line.push_str(&" ".repeat(left_width.saturating_sub(taken)));
            line.push_str(&center[row]);
            line.push_str(&" ".repeat(center_width.saturating_sub(used[row])));
            let right = if row == 0 { "Alt+d details" } else if self.provenance.is_empty() { "—" } else { &self.provenance };
            append(&mut line, &vec![(right.into(), theme::color("cyan"))], right_width);
            lines.push(line);
        }
        lines
    }
    pub fn render(&self, rows: usize, cols: usize, down: bool) {
        for (row, line) in self.styled_lines(rows, cols, down).iter().enumerate() {
            crate::render_output::write(format_args!("\x1b[{};1H{}", row + 1, line));
        }
    }

}

impl Entry {
    fn color(&self) -> String {
        theme::status(&match self.status {
            'R' => AgentStatus::Running,
            'I' => AgentStatus::WaitingForInput,
            'P' => AgentStatus::PermissionRequired,
            'S' => AgentStatus::Stopped,
            _ => AgentStatus::Unknown,
        })
    }
}

/// Each bar uses its local controller, or the only controller in the session.
/// This supports ordinary extra tabs without broadcasting snapshots across
/// multiple independent dashboards in the same session.
pub fn controller_for(manifest: &PaneManifest, own_id: u32) -> Option<u32> {
    let local = manifest.panes.values().find(|ps| ps.iter().any(|p| p.is_plugin && p.id == own_id));
    let is_controller = |p: &&PaneInfo| p.is_plugin && p.title == "lince-controller";
    if let Some(id) = local.and_then(|ps| ps.iter().find(is_controller)).map(|p| p.id) { return Some(id); }
    let mut controllers = manifest.panes.values().flatten().filter(is_controller);
    let first = controllers.next()?.id;
    controllers.next().is_none().then_some(first)
}

pub fn send(id: u32, name: &str, payload: &str) {
    pipe_message_to_plugin(MessageToPlugin::new(name).with_destination_plugin_id(id).with_payload(payload));
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::AgentStatus;

    fn plain(value: &str) -> String {
        let mut escape = false;
        value.chars().filter(|c| {
            if *c == '\x1b' { escape = true; return false; }
            if escape { if c.is_ascii_alphabetic() { escape = false; } return false; }
            true
        }).collect()
    }
    fn sample() -> Snapshot {
        let agents = vec![dashboard::preview_agent("reviewer", AgentStatus::Running),
            dashboard::preview_agent("coder", AgentStatus::PermissionRequired)];
        let mut snapshot = Snapshot::from_agents(&agents, Some("reviewer"), &DashboardConfig::default(), None);
        snapshot.mailbox = "Mail 2  Work 1  !0".into();
        snapshot.voice = Some("VP-###···".into());
        snapshot.provenance = "← coder · ask #abcd1234".into();
        snapshot.agents[0].provenance = "←".into();
        snapshot
    }
    #[test]
    fn three_areas_preserve_voice_mailbox_and_focused_provenance() {
        let snapshot = sample();
        let lines: Vec<_> = snapshot.styled_lines(2, 120, false).iter().map(|s| plain(s)).collect();
        assert!(lines[0].starts_with("VP-###···"));
        assert!(lines[1].starts_with("Mail 2  Work 1  !0"));
        assert!(lines[0].ends_with("Alt+d details"));
        assert!(lines[1].ends_with("← coder · ask #abcd1234"));
        assert!(lines.join("").contains("←R"));
        assert!(!lines.join("").contains("!1 1"));
    }
    #[test]
    fn unicode_and_controls_never_exceed_terminal_width() {
        let mut snapshot = sample();
        snapshot.agents[0].label = "界界\x1b[2J\nlong".into();
        for cols in 0..160 {
            for rows in 0..3 {
                for line in snapshot.styled_lines(rows, cols, false) {
                    let text = plain(&line);
                    assert!(text.chars().map(|c| c.width().unwrap_or(0)).sum::<usize>() <= cols);
                    assert!(!text.contains('\n'));
                }
            }
        }
    }
    #[test]
    fn details_hint_survives_narrow_width_and_empty_mailbox() {
        for cols in 13..80 {
            let lines = sample().styled_lines(2, cols, false);
            assert!(plain(&lines[0]).ends_with("Alt+d details"));
        }
        assert!(plain(&Snapshot::default().styled_lines(2, 80, false)[0]).contains("Alt+d details"));
    }
    #[test]
    fn all_visible_modes_keep_reserved_right_area() {
        let mut snapshot = sample();
        snapshot.summary_only = true;
        let lines = snapshot.styled_lines(2, 120, false).join("");
        assert!(lines.contains("VP-"));
        assert!(lines.contains("Mail 2"));
        assert!(!lines.contains("reviewer"));
        assert!(lines.contains("Alt+d details"));
        snapshot.summary_only = false;
        snapshot.agents_only = true;
        let lines = snapshot.styled_lines(2, 120, false).join("");
        assert!(!lines.contains("VP-"));
        assert!(!lines.contains("Mail 2"));
        assert!(lines.contains("reviewer"));
        assert!(lines.contains("Alt+d details"));
    }
    #[test]
    fn focus_and_blink_do_not_move_columns_or_reorder_agents() {
        let mut snapshot = sample();
        snapshot.suppress_attention_blink = true;
        assert_eq!(snapshot.styled_lines(2, 120, false), snapshot.styled_lines(2, 120, true));
        let before = plain(&snapshot.styled_lines(2, 120, false)[0]);
        snapshot.agents[0].focused = false;
        snapshot.agents[1].focused = true;
        let after = plain(&snapshot.styled_lines(2, 120, false)[0]);
        assert_eq!(before.replace('*', " "), after.replace('*', " "));
        assert_eq!(before.find("Alt+d"), after.find("Alt+d"));
    }
    #[test]
    fn color_selection_and_snapshot_roundtrip_remain_intact() {
        let snapshot = sample();
        for palette in ["default", "minimal-mono", "dracula", "gruvbox"] {
            theme::set(palette, None);
            let groups = snapshot.groups(false);
            assert_eq!(groups[1][1].1, theme::selection());
            assert_eq!(groups[1][2].1, theme::selection());
            assert!(groups[2][3].0.contains('P'));
        }
        let decoded: Snapshot = serde_json::from_str(&serde_json::to_string(&snapshot).unwrap()).unwrap();
        assert_eq!(decoded, snapshot);
    }
}
