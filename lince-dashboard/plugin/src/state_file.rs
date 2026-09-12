use crate::config::{run_typed_command, shell_escape};
use crate::types::{SavedAgentInfo, SavedState, SavedView, SessionDefaults};

const STATE_FILE_NAME: &str = ".lince-dashboard";
const STATE_VERSION: u32 = 3;

pub const CMD_SAVE_STATE: &str = "save_state";
pub const CMD_LOAD_STATE: &str = "load_state";
pub const CMD_DELETE_STATE: &str = "delete_state";

/// Build the state file path from the launch directory.
fn state_file_path(launch_dir: &str) -> String {
    format!("{}/{}", launch_dir.trim_end_matches('/'), STATE_FILE_NAME)
}

/// Kick off an async save of agent state via `run_command`.
/// The actual write happens on the host side via `sh -c 'printf ... > file'`.
/// The plugin receives the result in `Event::RunCommandResult` with context
/// `type=save_state`.
pub fn save_state_async(
    launch_dir: &str,
    agents: Vec<SavedAgentInfo>,
    next_agent_id: u32,
    session_defaults: Option<SessionDefaults>,
    view: Option<SavedView>,
) -> Result<(), String> {
    let path = state_file_path(launch_dir);

    let state = SavedState {
        version: STATE_VERSION,
        view,
        agents,
        next_agent_id,
        session_defaults,
    };

    let json =
        serde_json::to_string_pretty(&state).map_err(|e| format!("Serialize error: {}", e))?;

    // Use sh -c with a heredoc-style write to avoid shell escaping issues.
    let script = format!(
        "cat > '{}' <<'__LINCE_EOF__'\n{}\n__LINCE_EOF__",
        shell_escape(&path),
        json
    );

    run_typed_command(&["sh", "-c", &script], CMD_SAVE_STATE);

    Ok(())
}

/// Kick off an async load of saved state via `run_command`.
/// The plugin receives stdout (file contents) in `Event::RunCommandResult`
/// with context `type=load_state`.
pub fn load_state_async(launch_dir: &str) {
    let path = state_file_path(launch_dir);
    run_typed_command(&["cat", &path], CMD_LOAD_STATE);
}

/// Delete the state file (currently unused but kept for future use).
#[allow(dead_code)]
pub fn delete_state_file_async(launch_dir: &str) {
    let path = state_file_path(launch_dir);
    run_typed_command(&["rm", "-f", &path], CMD_DELETE_STATE);
}

/// Parse loaded state from stdout bytes returned by `cat`.
/// Supports both v1 (no agent_type field) and v2 (with agent_type) formats.
/// v1 entries get `agent_type = "claude"` via serde default.
pub fn parse_loaded_state(stdout: &[u8]) -> Result<SavedState, String> {
    let content = String::from_utf8_lossy(stdout);
    let mut state: SavedState =
        serde_json::from_str(content.trim()).map_err(|e| format!("Parse error: {}", e))?;
    // Normalize version to current — v1 files are transparently upgraded
    state.version = STATE_VERSION;
    Ok(state)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn saved_view_round_trips_all_presentations() {
        use crate::types::StatusBarMode;
        for sidebar in [false, true] {
            for mode in [StatusBarMode::Hidden, StatusBarMode::Summary, StatusBarMode::Full] {
                let state = SavedState { version: 3, agents: vec![], next_agent_id: 0,
                    session_defaults: None, view: Some(SavedView { sidebar_visible: sidebar, statusbar_mode: mode }) };
                let restored = parse_loaded_state(&serde_json::to_vec(&state).unwrap()).unwrap().view.unwrap();
                assert_eq!(restored.sidebar_visible, sidebar);
                assert_eq!(restored.statusbar_mode, mode);
                assert_eq!(mode.next().next().next(), mode);
            }
        }
    }

    /// Pre-#81 state files spelled the env-bundle field as `profile`. The
    /// rename added `#[serde(alias = "profile")]` on `SavedAgentInfo.provider`
    /// so old `.lince-dashboard` files keep loading transparently.
    #[test]
    fn loads_pre_issue81_state_file_with_profile_field() {
        let json = br#"{
            "version": 2,
            "agents": [
                {
                    "name": "agent-1",
                    "agent_type": "claude",
                    "profile": "vertex",
                    "project_dir": "/tmp/proj"
                }
            ],
            "next_agent_id": 1
        }"#;
        let state = parse_loaded_state(json).expect("legacy state must load");
        assert_eq!(state.agents.len(), 1);
        assert_eq!(state.agents[0].provider.as_deref(), Some("vertex"));
    }

    /// gh#62: v2 state files (no `session_defaults`) must load and yield
    /// `None` for the new field — backward compat for existing projects.
    #[test]
    fn v2_state_file_loads_with_none_session_defaults() {
        let json = br#"{
            "version": 2,
            "agents": [],
            "next_agent_id": 0
        }"#;
        let state = parse_loaded_state(json).expect("v2 state must load");
        assert!(state.session_defaults.is_none());
        assert!(state.view.is_none());
    }

    /// gh#62: v3 state file with `session_defaults` round-trips through
    /// serde so the `n` shortcut can reapply the wizard's last choice.
    #[test]
    fn v3_session_defaults_round_trip() {
        let json = br#"{
            "version": 3,
            "agents": [],
            "next_agent_id": 0,
            "session_defaults": {
                "agent_type": "codex",
                "provider": "zai",
                "project_dir": "/tmp/proj",
                "sandbox_level": "permissive",
                "sandbox_backend": "nono"
            }
        }"#;
        let state = parse_loaded_state(json).expect("v3 state must load");
        let sd = state.session_defaults.expect("session_defaults must be Some");
        assert_eq!(sd.agent_type, "codex");
        assert_eq!(sd.provider.as_deref(), Some("zai"));
        assert_eq!(sd.project_dir, "/tmp/proj");
        assert_eq!(sd.sandbox_level.as_deref(), Some("permissive"));
    }

    /// New state files use `provider`. Round-trip serialization writes
    /// `provider` and reads it back without falling through the alias.
    #[test]
    fn round_trips_provider_field() {
        let json = br#"{
            "version": 2,
            "agents": [
                {
                    "name": "agent-1",
                    "agent_type": "claude",
                    "provider": "zai",
                    "project_dir": "/tmp/proj"
                }
            ],
            "next_agent_id": 1
        }"#;
        let state = parse_loaded_state(json).expect("canonical state must load");
        assert_eq!(state.agents[0].provider.as_deref(), Some("zai"));
    }
}
