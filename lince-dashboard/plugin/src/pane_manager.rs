use zellij_tile::prelude::*;

use crate::config::{AgentLayout, FocusMode};
use crate::types::AgentInfo;

/// Hide agent floating panes. If `except` is provided, skip that agent.
pub fn hide_agent_panes(agents: &[AgentInfo], except: Option<&str>, _agent_layout: &AgentLayout) {
    for agent in agents {
        if except.map_or(false, |id| agent.id == id) {
            continue;
        }
        if let Some(pid) = agent.pane_id {
            hide_pane_with_id(PaneId::Terminal(pid));
        }
    }
}

/// Show and focus the given agent's pane, hiding all other agent panes.
pub fn focus_agent(
    agent: &AgentInfo,
    all_agents: &[AgentInfo],
    focus_mode: &FocusMode,
    agent_layout: &AgentLayout,
    viewport: Option<Viewport>,
) -> bool {
    let pid = match agent.pane_id {
        Some(pid) => pid,
        None => return false,
    };

    // Hide all other agent panes first.
    hide_agent_panes(all_agents, Some(&agent.id), agent_layout);

    if agent_layout.is_tiled() {
        // Tiled layout: overlay the agent's floating pane on the viewport area (B).
        show_pane_with_id(PaneId::Terminal(pid), true, true);
        focus_terminal_pane(pid, true, true);
        change_floating_panes_coordinates(vec![
            (PaneId::Terminal(pid), viewport.map(Viewport::coordinates).unwrap_or_else(crate::agent::default_agent_pane_coords)),
        ]);
    } else {
        match focus_mode {
            FocusMode::Floating => {
                show_pane_with_id(PaneId::Terminal(pid), true, true);
                focus_terminal_pane(pid, true, true);
                change_floating_panes_coordinates(vec![
                    (PaneId::Terminal(pid), crate::agent::default_agent_pane_coords()),
                ]);
            }
            FocusMode::Replace => {
                focus_terminal_pane(pid, false, true);
            }
        }
    }
    true
}

/// Hide the given agent's pane and return focus to the dashboard.
pub fn unfocus_agent(agent: &AgentInfo, focus_mode: &FocusMode, agent_layout: &AgentLayout) {
    if let Some(pid) = agent.pane_id {
        if agent_layout.is_tiled() {
            // Hide the floating overlay → underlying viewport pane (B) reappears.
            hide_pane_with_id(PaneId::Terminal(pid));
        } else {
            match focus_mode {
                FocusMode::Floating => {
                    hide_pane_with_id(PaneId::Terminal(pid));
                }
                FocusMode::Replace => {
                    // In replace mode, hiding isn't needed — the dashboard tab
                    // regains focus automatically when the plugin re-renders.
                }
            }
        }
    }
}

/// Geometry is taken from the layout, never inferred from sidebar percentages.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Viewport {
    pub x: usize,
    pub y: usize,
    pub width: usize,
    pub height: usize,
}

impl Viewport {
    pub fn coordinates(self) -> FloatingPaneCoordinates {
        FloatingPaneCoordinates::default()
            .with_x_fixed(self.x).with_y_fixed(self.y)
            .with_width_fixed(self.width).with_height_fixed(self.height)
    }
}

pub fn find_viewport(manifest: &PaneManifest, own_id: u32) -> Option<Viewport> {
    let panes = manifest.panes.values().find(|panes| {
        panes.iter().any(|p| p.is_plugin && p.id == own_id)
    })?;
    let pane = panes.iter().find(|p| !p.is_plugin && !p.is_floating && !p.is_suppressed
        && (p.title == "lince-viewport" || p.terminal_command.as_deref()
            .map_or(false, |c| c.split_whitespace().any(|part| part.ends_with("lince-viewport-placeholder")))))?;
    (pane.pane_columns > 0 && pane.pane_rows > 0).then_some(Viewport {
        x: pane.pane_x, y: pane.pane_y,
        width: pane.pane_columns, height: pane.pane_rows,
    })
}

#[cfg(test)]
mod viewport_tests {
    use super::*;
    #[test]
    fn viewport_uses_own_tab_and_actual_geometry() {
        let mut own = PaneInfo::default();
        own.is_plugin = true;
        own.id = 7;
        let mut viewport = PaneInfo::default();
        viewport.title = "lince-viewport".into();
        viewport.pane_x = 25;
        viewport.pane_y = 0;
        viewport.pane_columns = 75;
        viewport.pane_rows = 39;
        let mut manifest = PaneManifest::default();
        manifest.panes.insert(0, vec![viewport.clone()]);
        manifest.panes.insert(1, vec![own, viewport]);
        assert_eq!(find_viewport(&manifest, 7), Some(Viewport { x: 25, y: 0, width: 75, height: 39 }));
        assert_eq!(find_viewport(&manifest, 99), None);
        manifest.panes.get_mut(&1).unwrap()[1].pane_columns = 60;
        assert_eq!(find_viewport(&manifest, 7).unwrap().width, 60);
    }
}
