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
    pub theme: String,
    pub agents: Vec<Entry>,
    pub warning: Option<String>,
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
}
impl Snapshot {
    pub fn from_agents(agents: &[AgentInfo], focused: Option<&str>, config: &DashboardConfig, warning: Option<&str>) -> Self {
        Self {
            summary_only: false,
            theme: config.theme.clone(), warning: warning.map(str::to_owned),
            agents: agents.iter().enumerate().map(|(i, a)| Entry {
                slot: i + 1, label: dashboard::compact_name(a, &config.agent_types),
                status: dashboard::status_letter(&a.status),
                attention: dashboard::needs_attention(&a.status),
                focused: focused == Some(a.id.as_str()),
                sandbox: dashboard::sandbox_badge(a, &config.agent_types),
                sandbox_color: match dashboard::sandbox_badge(a, &config.agent_types).as_str() {
                    "NOSB" => "red", "normal" => "green", "permissive" => "yellow", _ => "white",
                }.into(),
            }).collect(),
        }
    }

    // Wrap whole entries; reserve the selection marker even when unselected so
    // neither selection nor bounce changes positions or line breaks.
    fn summary(&self, down: bool, lower_row: bool, single_row: bool) -> Vec<(String, String)> {
        let waiting = self.agents.iter().filter(|a| a.attention).count();
        let count = format!("!{waiting}");
        let mut summary = vec![(if lower_row { count } else { " ".repeat(count.len()) }, theme::attention_count())];
        for (i, entry) in self.agents.iter().enumerate() {
            let number = format!("{}{}", if i == 0 { " " } else { "" }, entry.slot);
            let state = if single_row {
                entry.status
            } else if entry.attention {
                if lower_row { entry.status } else { 'v' }
            } else if entry.status == 'R' {
                if lower_row == down { 'R' } else { ' ' }
            } else if lower_row {
                entry.status
            } else { ' ' };
            let color = if entry.attention && !lower_row && !single_row {
                theme::color(if down { "red" } else { "yellow" })
            } else { entry.color() };
            summary.push((format!("{}{state}", if lower_row { number } else { " ".repeat(number.len()) }), color));
        }
        summary
    }
    fn groups(&self) -> Vec<Vec<(String, String)>> {
        let mut groups = vec![self.summary(true, true, true)];
        for entry in &self.agents {
            let name_color = theme::color(&entry.sandbox_color);
            groups.push(vec![
                ("|".into(), theme::color("white")),
                (format!("{}{} ", if entry.focused { '*' } else { ' ' }, entry.slot),
                    if entry.focused { "\x1b[38;5;15m".into() } else { name_color.clone() }),
                (entry.label.clone(), name_color),
                (format!(" {}", entry.status), entry.color()),
            ]);
        }
        if let Some(warning) = &self.warning {
            groups.push(vec![(format!(" | ! {warning}"), theme::color("yellow"))]);
        }
        groups.push(vec![(" | Alt+d menu".into(), theme::color("cyan"))]);
        groups
    }
    #[cfg(test)]
    fn segments(&self) -> Vec<(String, String)> {
        self.groups().into_iter().flatten().collect()
    }
    #[cfg(test)]
    pub fn plain_line(&self, cols: usize) -> String {
        dashboard::clip_cells(&self.segments().into_iter().map(|(text, _)| text).collect::<String>(), cols)
    }
    fn styled_lines(&self, rows: usize, cols: usize, down: bool) -> Vec<String> {
        if rows == 0 || cols == 0 { return Vec::new(); }
        let groups = self.groups();
        let cell_width = |group: &Vec<(String, String)>| -> usize {
            group.iter().map(|(text, _)| text.chars()
                .map(|c| c.width().unwrap_or(0)).sum::<usize>()).sum()
        };
        let append = |line: &mut String, group: &Vec<(String, String)>, mut space: usize| {
            for (text, color) in group {
                let clipped = dashboard::clip_cells(text, space);
                space -= clipped.chars().map(|c| c.width().unwrap_or(0)).sum::<usize>();
                line.push_str(&format!("{color}{clipped}\x1b[0m"));
                if clipped != dashboard::clip_cells(text, usize::MAX) { break; }
            }
        };
        // Reserve the same left column on both rows, even when nobody needs
        // attention. Bouncing letters cannot overwrite or shift agent names.
        let left_width = cell_width(&groups[0]).min(cols);
        let mut lines = vec![String::new(); rows.min(2)];
        if lines.len() == 2 {
            append(&mut lines[0], &self.summary(down, false, false), cols);
            append(&mut lines[1], &self.summary(down, true, false), cols);
        } else {
            append(&mut lines[0], &groups[0], cols);
        }
        if self.summary_only { return lines; }
        let available = cols - left_width;
        let mut remaining = available;
        let mut row = 0;
        for group in groups.iter().skip(1) {
            let width = cell_width(group);
            if width > remaining && remaining < available && row + 1 < lines.len() {
                row += 1;
                remaining = available;
            }
            append(&mut lines[row], group, remaining);
            if width > remaining { break; }
            remaining -= width;
        }
        lines
    }
    #[cfg(test)]
    fn styled_line(&self, cols: usize) -> String {
        self.styled_lines(1, cols, false).join("")
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
    #[test]
    fn summary_only_keeps_animation_without_agent_names() {
        let mut snapshot = Snapshot::default();
        snapshot.summary_only = true;
        snapshot.agents.push(Entry { slot: 1, label: "CDX-pippo".into(), status: 'I',
            attention: true, focused: true, sandbox: "normal".into(), sandbox_color: "green".into() });
        for phase in [false, true] {
            let lines = snapshot.styled_lines(2, 100, phase);
            assert_eq!(lines.len(), 2);
            assert!(lines[0].contains('v'));
            assert!(lines[1].contains("1I"));
            assert!(!lines.join("").contains("CDX"));
            assert!(!lines.join("").contains("Alt+d"));
        }
    }

    #[test]
    fn waiting_count_identity_and_unknown_survive_narrow_width() {
        let agents = vec![dashboard::preview_agent("one", AgentStatus::Unknown),
            dashboard::preview_agent("two", AgentStatus::WaitingForInput),
            dashboard::preview_agent("three", AgentStatus::PermissionRequired)];
        let snapshot = Snapshot::from_agents(&agents, Some("one"), &DashboardConfig::default(), None);
        assert_eq!(snapshot.plain_line(7), "!2 1-2I");
        assert_eq!(snapshot.plain_line(9), "!2 1-2I3P");
        assert!(snapshot.plain_line(80).contains("*1"));
        assert_eq!(snapshot.plain_line(0), "");
        let decoded: Snapshot = serde_json::from_str(&serde_json::to_string(&snapshot).unwrap()).unwrap();
        assert_eq!(decoded, snapshot);
    }
    #[test]
    fn agent_colors_remain_independent_of_the_attention_summary() {
        let agents = vec![dashboard::preview_agent("run", AgentStatus::Running),
            dashboard::preview_agent("input", AgentStatus::WaitingForInput),
            dashboard::preview_agent("permit", AgentStatus::PermissionRequired),
            dashboard::preview_agent("stopped", AgentStatus::Stopped),
            dashboard::preview_agent("unknown", AgentStatus::Unknown)];
        let snapshot = Snapshot::from_agents(&agents, Some("run"), &DashboardConfig::default(), None);
        for palette in ["default", "minimal-mono", "dracula", "gruvbox"] {
            theme::set(palette, None);
            let line = snapshot.styled_line(200);
            assert!(snapshot.plain_line(200).starts_with("!2 1R2I3P4S5-|"));
            assert!(line.starts_with(&format!("{}!2\x1b[0m", theme::attention_count())));
            assert!(line.contains(&format!("{}2I\x1b[0m", theme::status(&AgentStatus::WaitingForInput))));
            assert!(line.contains(&format!("{}3P\x1b[0m", theme::status(&AgentStatus::PermissionRequired))));
            for (entry, agent) in snapshot.agents.iter().zip(&agents) {
                assert_ne!(theme::attention_count(), theme::status(&agent.status));
                assert!(line.contains(&format!("{}{}{}{}\x1b[0m", theme::status(&agent.status), if entry.slot == 1 { " " } else { "" }, entry.slot, entry.status)));
                assert!(line.contains(&format!("{}{}\x1b[0m", theme::color(&entry.sandbox_color), entry.label)));
                assert!(line.contains(&format!("{} {}\x1b[0m", theme::status(&agent.status), entry.status)));
            }
        }
    }
    #[test]
    fn colored_bar_preserves_unicode_clipping_and_plain_text() {
        let agents = vec![dashboard::preview_agent("界界界", AgentStatus::WaitingForInput)];
        let snapshot = Snapshot::from_agents(&agents, Some("界界界"), &DashboardConfig::default(), None);
        for cols in 0..100 {
            let mut escape = false;
            let plain: String = snapshot.styled_line(cols).chars().filter(|c| {
                if *c == '\x1b' { escape = true; return false; }
                if escape { if c.is_ascii_alphabetic() { escape = false; } return false; }
                true
            }).collect();
            assert_eq!(plain, snapshot.plain_line(cols), "width {cols}");
            assert!(plain.chars().map(|c| c.width().unwrap_or(0)).sum::<usize>() <= cols);
        }
    }
    #[test]
    fn labels_use_registry_abbreviations_and_sandbox_colors() {
        let mut config = DashboardConfig::default();
        config.agent_types = crate::config::embedded_agent_types().clone();
        let mut agents: Vec<_> = ["normal", "permissive", "paranoid", "custom", "normal"].into_iter().map(|level| {
            let mut agent = dashboard::preview_agent("pippo-long", AgentStatus::WaitingForInput);
            agent.agent_type = "codex".into();
            agent.sandbox_level = Some(level.into());
            agent
        }).collect();
        agents[4].sandbox_backend = Some(crate::sandbox_backend::SandboxBackend::None);
        let snapshot = Snapshot::from_agents(&agents, None, &config, None);
        assert_eq!(snapshot.agents.iter().map(|a| a.sandbox_color.as_str()).collect::<Vec<_>>(),
            ["green", "yellow", "white", "white", "red"]);
        assert!(snapshot.agents.iter().all(|a| a.label == "CDX-pippo" && a.status == 'I'));
        theme::set("default", None);
        let line = snapshot.styled_line(200);
        assert!(line.contains(&format!("{}CDX-pippo\x1b[0m{} I\x1b[0m", theme::color("green"), theme::color("yellow"))));
    }
    #[test]
    fn selection_keeps_order_width_and_sandbox_name_colors() {
        theme::set("default", None);
        let agents: Vec<_> = (1..=9).map(|i| {
            let mut agent = dashboard::preview_agent(&format!("ag{i}xy"), AgentStatus::WaitingForInput);
            agent.sandbox_level = Some("permissive".into());
            agent
        }).collect();
        let base = Snapshot::from_agents(&agents, None, &DashboardConfig::default(), None);
        let plain = base.plain_line(1000);
        for index in 0..9 {
            let selected = Snapshot::from_agents(&agents, Some(&agents[index].id), &DashboardConfig::default(), None);
            let line = selected.plain_line(1000);
            assert_eq!(line.replace('*', " "), plain);
            assert!(!line.contains("[permissive]"));
            let groups = selected.groups();
            assert_eq!(groups[index + 1][1].1, "\x1b[38;5;15m");
            assert_eq!(groups[index + 1][2].1, theme::color("yellow"));
            for (i, group) in groups.iter().skip(1).take(9).enumerate() {
                if i != index { assert_eq!(group[1].1, group[2].1); }
            }
            for phase in [false, true] {
                let lines = selected.styled_lines(2, 100, phase);
                assert_eq!(lines.len(), 2);
                for entry in &selected.agents {
                    assert!(lines.iter().any(|line| line.contains(&entry.label)));
                }
            }
        }
    }
    #[test]
    fn running_bounces_while_attention_has_fixed_letters_and_flashing_arrows() {
        let agents = vec![dashboard::preview_agent("run", AgentStatus::Running),
            dashboard::preview_agent("input", AgentStatus::WaitingForInput),
            dashboard::preview_agent("permission", AgentStatus::PermissionRequired),
            dashboard::preview_agent("stopped", AgentStatus::Stopped),
            dashboard::preview_agent("unknown", AgentStatus::Unknown)];
        let snapshot = Snapshot::from_agents(&agents, None, &DashboardConfig::default(), None);
        for phase in [false, true] {
            let top = snapshot.summary(phase, false, false);
            let bottom = snapshot.summary(phase, true, false);
            assert_eq!(top[0].0, "  ");
            assert_eq!(bottom[0].0, "!2");
            assert_eq!(top[1].0, if phase { "   " } else { "  R" });
            assert_eq!(bottom[1].0, if phase { " 1R" } else { " 1 " });
            assert_eq!(top[2].0, " v");
            assert_eq!(bottom[2].0, "2I");
            assert_eq!(top[3].0, " v");
            assert_eq!(bottom[3].0, "3P");
            assert_eq!(top[4].0, "  ");
            assert_eq!(bottom[4].0, "4S");
            assert_eq!(bottom[5].0, "5-");
            for i in 0..top.len() {
                if i == 2 || i == 3 {
                    assert_eq!(top[i].1, theme::color(if phase { "red" } else { "yellow" }));
                    assert_eq!(bottom[i].1, snapshot.agents[i - 1].color());
                } else {
                    assert_eq!(top[i].1, bottom[i].1);
                }
                assert_eq!(top[i].0.len(), bottom[i].0.len());
            }
        }
        // In a legacy single-row pane there is nowhere to bounce: stay visible.
        assert_eq!(snapshot.styled_lines(1, 100, false), snapshot.styled_lines(1, 100, true));
        for cols in 0..100 {
            for phase in [false, true] {
                for line in snapshot.styled_lines(2, cols, phase) {
                    let mut escape = false;
                    let plain: String = line.chars().filter(|c| {
                        if *c == '\x1b' { escape = true; return false; }
                        if escape { if c.is_ascii_alphabetic() { escape = false; } return false; }
                        true
                    }).collect();
                    assert!(plain.chars().map(|c| c.width().unwrap_or(0)).sum::<usize>() <= cols);
                }
            }
        }
    }
    #[test]
    fn empty_bar_still_explains_how_to_open_menu() {
        assert!(Snapshot::default().plain_line(80).contains("Alt+d menu"));
    }
}
