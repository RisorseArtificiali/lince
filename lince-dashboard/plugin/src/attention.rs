//! Read-only UI snapshot. Only the controller owns agents, hooks and persistence.
use serde::{Deserialize, Serialize};
use zellij_tile::prelude::*;
use crate::{dashboard, theme};
use crate::config::DashboardConfig;
use crate::types::AgentInfo;

pub const SNAPSHOT: &str = "lince-ui-snapshot";
pub const REFRESH: &str = "lince-ui-refresh";
pub const OPEN: &str = "lince-ui-open";

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Snapshot {
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
}
impl Snapshot {
    pub fn from_agents(agents: &[AgentInfo], focused: Option<&str>, config: &DashboardConfig, warning: Option<&str>) -> Self {
        Self {
            theme: config.theme.clone(), warning: warning.map(str::to_owned),
            agents: agents.iter().enumerate().map(|(i, a)| Entry {
                slot: i + 1, label: dashboard::compact_name(a),
                status: dashboard::status_letter(&a.status),
                attention: dashboard::needs_attention(&a.status),
                focused: focused == Some(a.id.as_str()),
                sandbox: dashboard::sandbox_badge(a, &config.agent_types),
            }).collect(),
        }
    }

    pub fn plain_line(&self, cols: usize) -> String {
        if cols == 0 { return String::new(); }
        let waiting: Vec<_> = self.agents.iter().filter(|a| a.attention).collect();
        // Always reserve the leading count, then identity of each waiting agent.
        let mut line = format!("!{}", waiting.len());
        for entry in &waiting { line.push_str(&format!(" {}{}", entry.slot, entry.status)); }
        if let Some(active) = self.agents.iter().find(|a| a.focused) {
            line.push_str(&format!(" | *{} {} [{}]", active.slot, active.label, active.sandbox));
        }
        for entry in &self.agents {
            if !entry.focused {
                line.push_str(&format!(" | {}:{} {}", entry.slot, entry.label, entry.status));
            }
        }
        if let Some(warning) = &self.warning { line.push_str(&format!(" | ! {warning}")); }
        line.push_str(" | Alt+d menu");
        dashboard::clip_cells(&line, cols)
    }
    pub fn render(&self, cols: usize) {
        let color = if self.agents.iter().any(|a| a.status == 'P') { "red" }
            else if self.agents.iter().any(|a| a.attention) { "yellow" } else { "cyan" };
        print!("{}{}\x1b[0m", theme::color(color), self.plain_line(cols));
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
    fn waiting_count_identity_and_unknown_survive_narrow_width() {
        let agents = vec![dashboard::preview_agent("one", AgentStatus::Unknown),
            dashboard::preview_agent("two", AgentStatus::WaitingForInput),
            dashboard::preview_agent("three", AgentStatus::PermissionRequired)];
        let snapshot = Snapshot::from_agents(&agents, Some("one"), &DashboardConfig::default(), None);
        assert_eq!(snapshot.plain_line(8), "!2 2I 3P");
        assert!(snapshot.plain_line(80).contains("*1"));
        assert_eq!(snapshot.plain_line(0), "");
        let decoded: Snapshot = serde_json::from_str(&serde_json::to_string(&snapshot).unwrap()).unwrap();
        assert_eq!(decoded, snapshot);
    }
    #[test]
    fn empty_bar_still_explains_how_to_open_menu() {
        assert!(Snapshot::default().plain_line(80).contains("Alt+d menu"));
    }
}
