mod agent;
mod config;
mod dashboard;
mod pane_manager;
mod recents;
mod sandbox_backend;
mod state_file;
mod types;

use std::collections::BTreeMap;
use zellij_tile::prelude::*;

use crate::config::{DashboardConfig, DEFAULT_AGENT_TYPE};
use crate::sandbox_backend::DetectedBackends;

const PIPE_CLAUDE_STATUS: &str = "claude-status";
const PIPE_LINCE_STATUS: &str = "lince-status";
const PIPE_VOXCODE_TEXT: &str = "voxcode-text";
const PIPE_FOCUS_AGENT: &str = "focus-agent";
const PIPE_CYCLE_AGENT: &str = "cycle-agent";
const CMD_GET_CWD: &str = "get_cwd";
const CMD_LOAD_CONFIG: &str = "load_config";

use crate::types::{
    AgentInfo, AgentStatus, NamePromptState, ProjectDirMode, RelayPhase, RelayState,
    SavedAgentInfo, SessionDefaults, StatusMessage, WizardState, WizardStep,
};

struct State {
    config: DashboardConfig,
    config_error: Option<String>,
    config_path: Option<String>,
    config_mtime: u64,
    agents: Vec<AgentInfo>,
    selected_index: usize,
    focused_agent: Option<String>,
    show_detail: bool,
    show_help: bool,
    status_message: Option<String>,
    next_agent_id: u32,
    wizard: Option<WizardState>,
    name_prompt: Option<NamePromptState>,
    /// When set, the name_prompt acts as a rename prompt for this agent id.
    rename_target: Option<String>,
    /// Active relay state machine (None = idle). LINCE-87/88/89 relay feature.
    relay_state: Option<RelayState>,
    launch_dir: Option<String>,
    /// Buffered saved state awaiting agent type defaults before restore.
    /// Set when load_state completes before load_agent_defaults.
    pending_restore: Option<Vec<SavedAgentInfo>>,
    /// Whether agent type defaults have been loaded at least once.
    agent_types_loaded: bool,
    /// Detected sandbox backends (populated async after permissions granted).
    detected_backends: Option<DetectedBackends>,
    /// Whether the init sequence (CWD detection + backend detection) has been kicked off.
    /// Zellij >= 0.44 may auto-grant permissions without emitting PermissionRequestResult.
    init_kicked: bool,
    /// Number of CWD retry attempts via Timer fallback.
    cwd_retries: u8,
    /// Stop retrying CWD after max attempts.
    cwd_retry_exhausted: bool,
    /// Per-project `n` quick-spawn defaults captured via wizard `!` (gh#62).
    /// When `Some`, the `n` shortcut spawns with these values instead of
    /// resolving from `[dashboard].default_*` config fields.
    session_defaults: Option<SessionDefaults>,
    /// Global most-recently-used project dirs, loaded from
    /// `~/.config/lince-dashboard/recents.json` and offered by the wizard's
    /// Project dir picker (#127).
    recent_project_dirs: Vec<String>,
}

impl Default for State {
    fn default() -> Self {
        Self {
            config: DashboardConfig::default(),
            config_error: None,
            config_path: None,
            config_mtime: 0,
            agents: Vec::new(),
            selected_index: 0,
            focused_agent: None,
            show_detail: false,
            show_help: false,
            status_message: None,
            next_agent_id: 0,
            wizard: None,
            name_prompt: None,
            rename_target: None,
            relay_state: None,
            launch_dir: None,
            pending_restore: None,
            agent_types_loaded: false,
            detected_backends: None,
            init_kicked: false,
            cwd_retries: 0,
            cwd_retry_exhausted: false,
            session_defaults: None,
            recent_project_dirs: Vec::new(),
        }
    }
}

/// Wrap-around list navigation helper.
fn wrap_next(current: usize, len: usize) -> usize {
    if len == 0 { 0 } else { (current + 1) % len }
}

fn wrap_prev(current: usize, len: usize) -> usize {
    if len == 0 { 0 } else if current == 0 { len - 1 } else { current - 1 }
}

impl State {
    /// Resolve the effective default agent type.
    ///
    /// Precedence (gh#62):
    /// 1. User-configured `[dashboard].default_agent_type`, if it names a
    ///    registered agent type.
    /// 2. `DEFAULT_AGENT_TYPE` ("claude") if registered.
    /// 3. First registered type whose base name matches `DEFAULT_AGENT_TYPE`
    ///    (e.g. `claude-unsandboxed`).
    /// 4. First available type (sorted), as a last-resort fallback.
    fn effective_default_agent_type(&self) -> &str {
        if let Some(configured) = self.config.default_agent_type.as_deref() {
            if self.config.agent_types.contains_key(configured) {
                return configured;
            }
        }
        if self.config.agent_types.contains_key(DEFAULT_AGENT_TYPE) {
            return DEFAULT_AGENT_TYPE;
        }
        // Find first type whose base name matches the default (e.g. "claude-nono" matches "claude")
        let mut keys: Vec<&String> = self.config.agent_types.keys().collect();
        keys.sort();
        for k in &keys {
            if agent::agent_type_base_name(k) == agent::agent_type_base_name(DEFAULT_AGENT_TYPE) {
                return k.as_str();
            }
        }
        // Last resort: first available type
        keys.first().map(|k| k.as_str()).unwrap_or(DEFAULT_AGENT_TYPE)
    }
}

register_plugin!(State);

impl ZellijPlugin for State {
    fn load(&mut self, configuration: BTreeMap<String, String>) {
        if let Some(raw_path) = configuration.get("config_path") {
            let path = config::expand_tilde(raw_path);
            self.config_path = Some(path);
            // Config will be loaded async via run_command after permissions are granted.
            // Direct std::fs calls fail in WASI sandbox.
        }
        subscribe(&[
            EventType::Key,
            EventType::Timer,
            EventType::PaneUpdate,
            EventType::ModeUpdate,
            EventType::RunCommandResult,
            EventType::PermissionRequestResult,
        ]);
        request_permission(&[
            PermissionType::RunCommands,
            PermissionType::ChangeApplicationState,
            PermissionType::ReadApplicationState,
            PermissionType::MessageAndLaunchOtherPlugins,
            PermissionType::OpenTerminalsOrPlugins,
            PermissionType::ReadCliPipes,
            PermissionType::WriteToStdin,
        ]);

        // Eagerly try to init right away — Zellij >= 0.44 auto-grants
        // permissions for local file plugins, so run_command may already work.
        config::run_typed_command(&["pwd"], CMD_GET_CWD);
        sandbox_backend::detect_backend_async();
        // Load the global recents list for the wizard's Project dir picker.
        // Independent of launch_dir — the file lives under ~/.config.
        recents::load_recents_async();
        // Load config async (std::fs fails in WASI sandbox)
        if let Some(ref path) = self.config_path {
            let script = format!("cat {} 2>/dev/null", config::shell_path_expr(path));
            config::run_typed_command(&["sh", "-c", &script], CMD_LOAD_CONFIG);
        }
        self.init_kicked = true;

        // Always start timer: serves both file-polling and config hot-reload
        set_timeout(5.0);
    }

    fn update(&mut self, event: Event) -> bool {
        match event {
            Event::PermissionRequestResult(PermissionStatus::Granted) => {
                let _ = std::fs::OpenOptions::new()
                    .create(true).append(true).open("/tmp/lince-debug.log")
                    .and_then(|mut f| { use std::io::Write; f.write_all(b"PermissionRequestResult: GRANTED\n") });
                // Now that we have permissions, detect CWD via `pwd`.
                config::run_typed_command(&["pwd"], CMD_GET_CWD);
                // Detect available sandbox backends (agent-sandbox, nono).
                sandbox_backend::detect_backend_async();
                self.init_kicked = true;
                true
            }
            Event::Key(key) => self.handle_key(key),
            Event::PaneUpdate(manifest) => {
                let changed = agent::reconcile_panes(&mut self.agents, &manifest, &self.config.agent_layout, &self.config.agent_types);
                if changed {
                    self.sort_agents_by_dir();
                }
                changed
            }
            Event::Timer(_elapsed) => {
                let mut needs_render = false;

                // Fallback: if PermissionRequestResult never fired (Zellij >= 0.44
                // auto-grants local plugins without emitting the event), retry init.
                if !self.init_kicked {
                    self.init_kicked = true;
                    config::run_typed_command(&["pwd"], CMD_GET_CWD);
                    sandbox_backend::detect_backend_async();
                } else if self.launch_dir.is_none() && !self.cwd_retry_exhausted {
                    // CWD command was sent but no result yet — retry a few times
                    self.cwd_retries += 1;
                    if self.cwd_retries <= 3 {
                        config::run_typed_command(&["pwd"], CMD_GET_CWD);
                    } else {
                        self.cwd_retry_exhausted = true;
                    }
                }

                // Config hot-reload: re-read via async run_command (std::fs unavailable in WASI).
                // Only re-load if we haven't loaded yet (config_mtime == 0).
                // Full hot-reload on every timer tick would be wasteful.
                if self.config_mtime == 0 {
                    if let Some(ref path) = self.config_path {
                        let script = format!("cat {} 2>/dev/null", config::shell_path_expr(path));
                        config::run_typed_command(&["sh", "-c", &script], CMD_LOAD_CONFIG);
                    }
                }

                // Status polling: kick off an async `cat` of the .state files.
                // `std::fs` can't reach the host filesystem from the WASI plugin
                // sandbox, so the read goes through a host shell command; results
                // land in the CMD_POLL_STATUS handler.
                //
                // Polling runs UNCONDITIONALLY, not just for `status_method =
                // "file"`. The hooks always write `.state` files to a host-shared
                // dir (/tmp/lince-dashboard), so polling is the one status channel
                // that reliably works. The `zellij pipe` fast-path runs from
                // *inside* the agent sandbox (bwrap) and can't reach Zellij's IPC
                // socket — the socket dir isn't bind-mounted, only /tmp is — so on
                // a sandboxed agent the pipe is silently dropped and the Status
                // column would otherwise stay "-" forever. The pipe still updates
                // status instantly when it does work (unsandboxed agents); polling
                // reconciles everything else within the timer period.
                config::poll_status_files_async(&self.config.status_file_dir);

                // Clear transient status messages after timeout
                if self.status_message.is_some() && self.config_error.is_none() {
                    self.status_message = None;
                    needs_render = true;
                }

                set_timeout(5.0); // re-arm for config reload + polling
                needs_render
            }
            Event::RunCommandResult(exit_code, stdout, stderr, context) => {
                let cmd_type = context.get(config::CMD_TYPE_KEY).map(|s| s.as_str());
                match cmd_type {
                    Some(CMD_LOAD_CONFIG) => {
                        if exit_code == Some(0) && !stdout.is_empty() {
                            let content = String::from_utf8_lossy(&stdout);
                            let (cfg, err) = DashboardConfig::parse_toml(&content);
                            // Preserve async-loaded fields that config.toml doesn't contain.
                            let prev_agent_types = std::mem::take(&mut self.config.agent_types);
                            let prev_providers = std::mem::take(&mut self.config.providers_by_agent);
                            let prev_details = std::mem::take(&mut self.config.provider_details_by_agent);
                            self.config = cfg;
                            self.config_error = err;
                            if self.config.agent_types.is_empty() {
                                self.config.agent_types = prev_agent_types;
                            }
                            if self.config.providers_by_agent.is_empty() {
                                self.config.providers_by_agent = prev_providers;
                            }
                            if self.config.provider_details_by_agent.is_empty() {
                                self.config.provider_details_by_agent = prev_details;
                            }
                        }
                        // Mark as loaded so timer doesn't retry
                        self.config_mtime = 1;
                        true
                    }
                    Some(CMD_GET_CWD) if exit_code == Some(0) => {
                        let dir = String::from_utf8_lossy(&stdout).trim().to_string();
                        if !dir.is_empty() {
                            // Kick off the single async resolution call (#202):
                            // agent types + providers + sandbox levels all come
                            // from `lince-config resolve --json`.
                            config::resolve_config_async(Some(&dir));
                            // Kick off async load of saved state.
                            state_file::load_state_async(&dir);
                            self.launch_dir = Some(dir);
                        }
                        true
                    }
                    Some(state_file::CMD_LOAD_STATE) => {
                        if exit_code == Some(0) && !stdout.is_empty() {
                            match state_file::parse_loaded_state(&stdout) {
                                Ok(saved) => {
                                    self.next_agent_id = saved.next_agent_id;
                                    self.session_defaults = saved.session_defaults;
                                    if self.agent_types_loaded {
                                        // Agent types already available — restore immediately.
                                        self.restore_agents(saved.agents);
                                    } else {
                                        // Agent types not loaded yet — buffer for later.
                                        self.pending_restore = Some(saved.agents);
                                    }
                                }
                                Err(e) => {
                                    self.status_message = Some(format!("Restore: {}", e));
                                    set_timeout(5.0);
                                }
                            }
                        }
                        // exit_code != 0 means file not found — normal, ignore.
                        true
                    }
                    Some(state_file::CMD_SAVE_STATE) => {
                        if exit_code == Some(0) {
                            quit_zellij();
                        } else {
                            let err = String::from_utf8_lossy(&stderr);
                            self.status_message = Some(format!("Save failed: {}", err.trim()));
                            set_timeout(5.0);
                        }
                        true
                    }
                    Some(state_file::CMD_DELETE_STATE) => {
                        // Nothing to do, just acknowledge.
                        false
                    }
                    Some(config::CMD_RESOLVE_CONFIG) => {
                        // Single resolution point (#202): agent types, providers,
                        // and custom sandbox levels all arrive in one JSON payload
                        // from `lince-config resolve --json`.
                        let mut applied = false;
                        if exit_code == Some(0) && !stdout.is_empty() {
                            let content = String::from_utf8_lossy(&stdout);
                            match config::apply_resolved_view(&mut self.config, &content) {
                                Ok(warnings) => {
                                    applied = true;
                                    if let Some(w) = warnings.first() {
                                        self.config_error =
                                            Some(format!("config: {}", w));
                                    }
                                }
                                Err(e) => {
                                    self.config_error = Some(format!(
                                        "lince-config resolve: {} — using built-in defaults",
                                        e
                                    ));
                                }
                            }
                        } else {
                            let err = String::from_utf8_lossy(&stderr);
                            self.config_error = Some(format!(
                                "lince-config resolve failed ({}) — using built-in defaults. \
                                 Install it: lince-config/install.sh",
                                err.trim().lines().last().unwrap_or("not found")
                            ));
                        }
                        if !applied && self.config.agent_types.is_empty() {
                            // Last-resort fallback (#198 precedent): compiled-in
                            // shipped defaults keep the dashboard usable.
                            self.config.agent_types = config::embedded_agent_types().clone();
                        }
                        self.agent_types_loaded = true;
                        // Flush any buffered restore that was waiting for agent types.
                        if let Some(saved_agents) = self.pending_restore.take() {
                            self.restore_agents(saved_agents);
                        }
                        // Refresh the wizard's level list ONLY if the user hasn't
                        // moved past SandboxLevel yet — otherwise we'd risk
                        // clobbering an already-confirmed choice if resolution
                        // shifted the list (e.g., profile file removed mid-wizard).
                        if applied {
                            if let Some(ref mut wizard) = self.wizard {
                                let on_or_before_level = matches!(
                                    wizard.step,
                                    WizardStep::AgentType
                                        | WizardStep::SandboxBackend
                                        | WizardStep::SandboxLevel
                                );
                                if on_or_before_level {
                                    let base = wizard.selected_base_agent().to_string();
                                    let backend = wizard.selected_sandbox_backend();
                                    let preserved = wizard.selected_sandbox_level().map(|s| s.to_string());
                                    wizard.available_sandbox_levels = self.config
                                        .supported_sandbox_levels(&base, backend.as_ref());
                                    wizard.sandbox_level_index = preserved
                                        .as_deref()
                                        .and_then(|p| wizard.available_sandbox_levels.iter().position(|l| l == p))
                                        .unwrap_or(0);
                                }
                            }
                        }
                        true
                    }
                    Some(sandbox_backend::CMD_DETECT_BACKEND) => {
                        if exit_code == Some(0) {
                            let detected = DetectedBackends::from_stdout(&stdout);
                            self.detected_backends = Some(detected);
                            // If a wizard is open, its `available_sandbox_backends` was
                            // computed against `None` detection (TOML-pin fallback) — refresh
                            // it now that we know what's actually installed. Re-clamp the
                            // selected index to keep it valid if the list shape changed.
                            if let Some(ref mut wizard) = self.wizard {
                                let base = wizard.selected_base_agent().to_string();
                                wizard.available_sandbox_backends = self.config
                                    .available_backends_for_base(&base, self.detected_backends.as_ref());
                                if wizard.sandbox_backend_index >= wizard.available_sandbox_backends.len() {
                                    wizard.sandbox_backend_index = self.config
                                        .default_backend_index_for_base(&base, &wizard.available_sandbox_backends);
                                }
                            }
                        }
                        true
                    }
                    Some(config::CMD_PATH_COMPLETE) => {
                        // #125: capture the launch dir before borrowing the
                        // wizard, to absolutize relative completer matches below.
                        let launch_dir = self.launch_dir.clone();
                        if let Some(ref mut wizard) = self.wizard {
                            // Discard stale results if the input changed since the request.
                            let expected = context.get("prefix").map(|s| s.as_str());
                            if expected.is_some() && expected != Some(&wizard.project_dir) {
                                return true; // stale — ignore
                            }

                            let output = String::from_utf8_lossy(&stdout);
                            let mut matches: Vec<String> = output
                                .lines()
                                .filter(|l| !l.is_empty())
                                // Normalize the trailing-slash inconsistency
                                // between the legacy glob path completer (which
                                // returns `path/`) and the multi-root `find`
                                // (which returns `path`). Otherwise two agents
                                // pointed at the same project but spawned from
                                // different code paths end up in distinct
                                // swimlanes — see also `sort_agents_by_dir`.
                                .map(|l| l.trim_end_matches('/').to_string())
                                // #125: resolve relative legacy-glob matches
                                // against the launch dir before collapsing, so
                                // every candidate is absolute and passes the
                                // ProjectDir absolute-path check. Runs before
                                // `collapse_tilde`, so a plain `/` test suffices
                                // — the raw completer output never contains `~`.
                                .map(|l| config::absolutize_under(launch_dir.as_deref(), &l))
                                .map(|l| config::collapse_tilde(&l))
                                .collect();
                            matches.sort();
                            matches.dedup();

                            if matches.len() == 1 {
                                // Single match: auto-fill directly.
                                wizard.project_dir = matches.remove(0);
                                wizard.clear_completions();
                            } else if matches.len() > 1 {
                                // Fill common prefix and show candidates.
                                let prefix = config::common_prefix(&matches);
                                if prefix.len() > wizard.project_dir.len() {
                                    wizard.project_dir = prefix;
                                }
                                wizard.completions = matches;
                                wizard.completion_index = None;
                            }
                            // If no matches, leave state unchanged.
                        }
                        true
                    }
                    Some(config::CMD_POLL_STATUS) if exit_code == Some(0) => {
                        // Output: one `<basename>\t<event>` line per .state file.
                        // The claude hook writes `claude-{id}.state` (basename
                        // `claude-{id}`); the agent wrapper writes `{id}.state`
                        // (basename `{id}`). Match both per agent.
                        let output = String::from_utf8_lossy(&stdout);
                        let mut file_events: std::collections::HashMap<&str, &str> =
                            std::collections::HashMap::new();
                        // Effective-policy records (#221): `POLICY\t<id>\t<json>`.
                        let mut policy_records: std::collections::HashMap<&str, &str> =
                            std::collections::HashMap::new();
                        for line in output.lines() {
                            if let Some(rest) = line.strip_prefix("POLICY\t") {
                                if let Some((id, json)) = rest.split_once('\t') {
                                    if !json.trim().is_empty() {
                                        policy_records.insert(id, json);
                                    }
                                }
                                continue;
                            }
                            if let Some((name, event)) = line.split_once('\t') {
                                let event = event.trim();
                                if !event.is_empty() {
                                    file_events.insert(name, event);
                                }
                            }
                        }
                        let mut changed = false;
                        for agent in self.agents.iter_mut() {
                            if let Some(json) = policy_records.get(agent.id.as_str()) {
                                if let Ok(p) = serde_json::from_str::<types::EnforcedPolicy>(json) {
                                    if agent.enforced.as_ref() != Some(&p) {
                                        agent.enforced = Some(p);
                                        changed = true;
                                    }
                                }
                            }
                            let claude_key = format!("claude-{}", agent.id);
                            let event = file_events
                                .get(claude_key.as_str())
                                .or_else(|| file_events.get(agent.id.as_str()))
                                .copied();
                            if let Some(event) = event {
                                if agent.last_polled_event.as_deref() == Some(event) {
                                    continue;
                                }
                                agent.last_polled_event = Some(event.to_string());
                                let msg = StatusMessage {
                                    agent_id: agent.id.clone(),
                                    event: event.to_string(),
                                    timestamp: None,
                                    error: None,
                                    session_id: None,
                                    transcript_path: None,
                                };
                                let new_status = msg.to_agent_status(
                                    self.config.event_map_for(&agent.agent_type),
                                );
                                if agent.status != new_status {
                                    agent.status = new_status;
                                    changed = true;
                                }
                            }
                        }
                        changed
                    }
                    Some(cmd_type) if cmd_type == config::CMD_EXTRACT_TRANSCRIPT => {
                        // Only process if relay is still in Extracting phase
                        let Some(ref rs) = self.relay_state else { return false };
                        let RelayPhase::Extracting { source_agent_id, source_agent_name, message_count } = &rs.phase else { return false };

                        let output = String::from_utf8_lossy(&stdout);
                        let source_name = source_agent_name.clone();
                        let source_id = source_agent_id.clone();
                        let count = *message_count;
                        let src_idx = rs.source_index;

                        if exit_code != Some(0) || output.contains("[error]") || output.trim().is_empty() {
                            self.relay_state = None;
                            self.status_message = Some("Transcript extraction failed".to_string());
                            set_timeout(3.0);
                            return true;
                        }

                        self.relay_state = Some(RelayState {
                            phase: RelayPhase::DeliveryPending {
                                source_agent_name: source_name,
                                captured_text: output.trim_end().to_string(),
                                message_count: count,
                            },
                            source_index: src_idx,
                        });
                        self.status_message = Some(format!(
                            "Extracted {} messages from {}. Select target (f/Enter/1-9), Esc cancel",
                            count, source_id
                        ));
                        true
                    }
                    Some(recents::CMD_LOAD_RECENTS) => {
                        self.recent_project_dirs = recents::parse_loaded_recents(&stdout);
                        // No re-render needed: recents are only consumed when
                        // the wizard opens, which seeds from this field.
                        false
                    }
                    Some(recents::CMD_SAVE_RECENTS) => {
                        // Fire-and-forget persistence; nothing to do on ack.
                        false
                    }
                    _ => false,
                }
            }
            _ => false,
        }
    }

    fn render(&mut self, rows: usize, cols: usize) {
        // If help overlay is active, render it and return
        if self.show_help {
            dashboard::render_help_overlay(rows, cols);
            return;
        }

        // If wizard is active, render the wizard overlay instead of the dashboard
        if let Some(ref wizard) = self.wizard {
            dashboard::render_wizard(
                wizard,
                rows,
                cols,
                &self.config.agent_types,
                &self.config.sandbox_colors,
            );
            return;
        }

        let config_warning = self.config_error.as_deref();
        let effective_status = self.status_message.as_deref().or(config_warning);

        let detail_id = if self.show_detail {
            self.agents.get(self.selected_index).map(|a| a.id.as_str())
        } else {
            None
        };

        dashboard::render_dashboard(
            &self.agents,
            self.selected_index,
            self.focused_agent.as_deref(),
            detail_id,
            rows,
            cols,
            effective_status,
            self.name_prompt.as_ref(),
            self.relay_state.as_ref().map(|r| &r.phase),
            &self.config.agent_types,
            &self.config.sandbox_colors,
        );
    }

    fn pipe(&mut self, pipe_message: PipeMessage) -> bool {
        // Close the CLI pipe so `zellij pipe` command can return
        unblock_cli_pipe_input(&pipe_message.name);
        cli_pipe_output(&pipe_message.name, "");

        match pipe_message.name.as_str() {
            PIPE_FOCUS_AGENT => {
                if let Some(payload) = &pipe_message.payload {
                    if let Ok(idx) = payload.parse::<usize>() {
                        if idx > 0 && idx <= self.agents.len() {
                            self.focus_agent_by_index(idx - 1);
                            return true;
                        }
                    }
                }
                false
            }
            PIPE_CYCLE_AGENT => {
                if let Some(payload) = &pipe_message.payload {
                    let next = match payload.as_str() {
                        "next" => true,
                        "prev" => false,
                        _ => return false,
                    };
                    if self.agents.is_empty() {
                        return false;
                    }
                    let new_idx = if next {
                        (self.selected_index + 1) % self.agents.len()
                    } else {
                        if self.selected_index == 0 {
                            self.agents.len() - 1
                        } else {
                            self.selected_index - 1
                        }
                    };
                    self.focus_agent_by_index(new_idx);
                    return true;
                }
                false
            }
            PIPE_CLAUDE_STATUS | PIPE_LINCE_STATUS => {
                if let Some(payload) = pipe_message.payload {
                    self.handle_status_message(&payload);
                    return true;
                }
                false
            }
            PIPE_VOXCODE_TEXT => {
                if let Some(payload) = pipe_message.payload {
                    self.handle_voxcode_text(&payload);
                    return true;
                }
                false
            }
            _ => false,
        }
    }
}

/// Group/sort key for agent workdirs. Strips a trailing `/` so paths that
/// differ only by that (e.g. `synoptic/` from the legacy glob completer vs
/// `synoptic` from the multi-root `find`) land in the same swimlane in the
/// dashboard. Doesn't mutate `agent.project_dir` — only the comparison.
fn workdir_key(s: &str) -> &str {
    s.trim_end_matches('/')
}

impl State {
    /// Sort agents by project_dir, then by name within each group.
    /// Preserves the selected agent across the sort.
    /// Record a freshly-spawned agent's project dir into the global recents
    /// (MRU), then persist asynchronously. Only fires on user-initiated spawns
    /// — never on session restore (#127).
    fn record_recent_project_dir(&mut self, dir: &str) {
        if recents::push_recent(&mut self.recent_project_dirs, dir) {
            recents::save_recents_async(&self.recent_project_dirs);
        }
    }

    fn sort_agents_by_dir(&mut self) {
        let selected_id = self.agents.get(self.selected_index).map(|a| a.id.clone());

        self.agents.sort_by(|a, b| {
            workdir_key(&a.project_dir).cmp(workdir_key(&b.project_dir))
                .then(a.name.cmp(&b.name))
        });

        if let Some(id) = selected_id {
            if let Some(pos) = self.agents.iter().position(|a| a.id == id) {
                self.selected_index = pos;
            }
        }
    }

    fn handle_key(&mut self, key: KeyWithModifier) -> bool {
        // If wizard is active, route all keys there
        if self.wizard.is_some() {
            return self.handle_wizard_key(key);
        }

        // If name prompt is active, route keys there (LINCE-55)
        if self.name_prompt.is_some() {
            return self.handle_name_prompt_key(key);
        }

        // If relay is active, route all keys there
        if self.relay_state.is_some() {
            return self.handle_relay_key(key);
        }

        let bare = &key.bare_key;
        let no_mods = key.key_modifiers.is_empty();

        if !no_mods {
            return false;
        }

        match bare {
            BareKey::Char('n') => {
                // gh#62: when session_defaults is set, use the session's agent_type
                // to seed the default name; otherwise fall back to the static default.
                let effective_type: String = match self.session_defaults.as_ref() {
                    Some(sd) if self.config.agent_types.contains_key(&sd.agent_type) => {
                        sd.agent_type.clone()
                    }
                    _ => self.effective_default_agent_type().to_string(),
                };
                let base = agent::agent_type_base_name(&effective_type);
                // #167: derive the default name from the working-directory
                // basename. Mirror the spawn's own dir resolution so the name
                // matches where the agent actually starts: session default dir →
                // config default → dashboard launch dir → ".".
                let default_dir = self
                    .session_defaults
                    .as_ref()
                    .map(|sd| sd.project_dir.clone())
                    .filter(|d| !d.is_empty())
                    .or_else(|| self.config.default_project_dir.clone().filter(|d| !d.is_empty()))
                    .or_else(|| self.launch_dir.clone().filter(|d| !d.is_empty()))
                    .unwrap_or_else(|| String::from("."));
                let default_name =
                    agent::suggest_agent_name(&default_dir, &self.agents, self.next_agent_id, base);
                self.name_prompt = Some(NamePromptState {
                    input: String::new(),
                    default_name,
                    label: "Name",
                });
                true
            }
            BareKey::Char('r') => {
                if let Some(agent) = self.agents.get(self.selected_index) {
                    self.rename_target = Some(agent.id.clone());
                    self.name_prompt = Some(NamePromptState {
                        input: String::new(),
                        default_name: agent.name.clone(),
                        label: "Rename",
                    });
                }
                true
            }
            BareKey::Char('s') => {
                self.start_relay(1);
                true
            }
            BareKey::Char('S') => {
                self.start_relay_with_prompt();
                true
            }
            BareKey::Char('N') => {
                // #168: pre-fill the project dir from the selected agent when
                // there is one; otherwise fall back to the config default.
                let mut default_dir = self.config.default_project_dir.clone()
                    .unwrap_or_default();
                let mut project_dir_suggested = false;
                if let Some(sel) = self.agents.get(self.selected_index) {
                    if !sel.project_dir.is_empty() {
                        default_dir = sel.project_dir.clone();
                        project_dir_suggested = true;
                    }
                }
                // Step 1 list: deduplicated base agents (e.g. "claude", not "claude-unsandboxed").
                let agent_type_list = self.config.base_agents();
                // Prefer the configured default_agent_type's base (gh#62) when it
                // appears in the list; fall back to DEFAULT_AGENT_TYPE; fall back to 0.
                let configured_base = self.config.default_agent_type.as_deref()
                    .map(agent::agent_type_base_name);
                let default_at_index = configured_base
                    .and_then(|base| agent_type_list.iter().position(|(k, _)| k == base))
                    .or_else(|| agent_type_list.iter().position(|(k, _)| k == DEFAULT_AGENT_TYPE))
                    .unwrap_or(0);
                let default_base = agent_type_list.get(default_at_index)
                    .map(|(k, _)| k.as_str())
                    .unwrap_or(DEFAULT_AGENT_TYPE);
                // Step 2 list: backends available for the default base on this host.
                let available_sandbox_backends = self.config.available_backends_for_base(
                    default_base,
                    self.detected_backends.as_ref(),
                );
                let sandbox_backend_index = self.config
                    .default_backend_index_for_base(default_base, &available_sandbox_backends);
                // Resolve initial effective agent_type (depends on backend choice).
                let effective_type = if available_sandbox_backends
                    .get(sandbox_backend_index)
                    .map_or(false, |b| matches!(b, sandbox_backend::SandboxBackend::None))
                {
                    format!("{}-unsandboxed", default_base)
                } else {
                    default_base.to_string()
                };
                let available_providers = self.config.providers_for_agent_type(&effective_type);
                let default_provider_index = self.config.default_provider.as_ref()
                    .and_then(|dp| available_providers.iter().position(|p| p == dp))
                    .unwrap_or(0);
                // Sandbox levels follow the canonical sandboxed entry (skipped when backend = None).
                // Levels are backend-aware: custom levels discovered by the resolver
                // (lince-config resolve --json) are merged with the standard 3.
                // Resolution is async — the cache may be empty at this point;
                // the CMD_RESOLVE_CONFIG handler refreshes the wizard when results arrive.
                let default_backend = available_sandbox_backends.get(sandbox_backend_index);
                let available_sandbox_levels = self.config.supported_sandbox_levels(default_base, default_backend);
                let sandbox_level_index = {
                    let pinned = self.config.agent_types.get(default_base)
                        .and_then(|c| c.sandbox_level.as_deref());
                    pinned
                        .and_then(|p| available_sandbox_levels.iter().position(|l| l == p))
                        .unwrap_or(0)
                };
                // Re-run resolution as a refresh (covers custom levels added since boot).
                config::resolve_config_async(self.launch_dir.as_deref());
                // #167: seed the default name from the (possibly pre-filled)
                // project dir basename. Recomputed when the user changes the
                // ProjectDir field (which now precedes the Name step).
                let default_name = agent::suggest_agent_name(
                    &default_dir,
                    &self.agents,
                    self.next_agent_id,
                    default_base,
                );
                // Seed the project-dir picker from the global recents, then bias
                // toward the focused/selected agent's workdir by moving it to the
                // front so it's pre-highlighted (context default, cf. #168).
                let mut seed_project_dirs = self.recent_project_dirs.clone();
                if let Some(dir) = self
                    .focused_agent
                    .as_ref()
                    .and_then(|name| self.agents.iter().find(|a| &a.name == name))
                    .or_else(|| self.agents.get(self.selected_index))
                    .map(|a| a.project_dir.clone())
                {
                    recents::push_recent(&mut seed_project_dirs, &dir);
                }
                // Show the recents list when we have any; otherwise drop straight
                // to the legacy free-text input (no empty list to navigate).
                let project_dir_mode = if seed_project_dirs.is_empty() {
                    ProjectDirMode::Input
                } else {
                    ProjectDirMode::List
                };
                // Build state, then derive the first step from active_steps() so the
                // skip rules don't drift between init and key handlers.
                let mut state = WizardState {
                    step: WizardStep::AgentType, // placeholder — replaced below
                    available_agent_types: agent_type_list,
                    agent_type_index: default_at_index,
                    available_sandbox_backends,
                    sandbox_backend_index,
                    available_sandbox_levels,
                    sandbox_level_index,
                    name: String::new(),
                    default_name,
                    available_providers,
                    provider_index: default_provider_index,
                    project_dir: default_dir,
                    completions: Vec::new(),
                    completion_index: None,
                    project_dir_error: None,
                    project_dir_suggested,
                    available_project_dirs: seed_project_dirs,
                    project_dir_index: 0,
                    project_dir_filter: String::new(),
                    project_dir_mode,
                };
                state.step = state.active_steps().into_iter().next().unwrap_or(WizardStep::Name);
                self.wizard = Some(state);
                true
            }
            BareKey::Char('x') => {
                if let Some(agent) = self.agents.get(self.selected_index) {
                    let name = agent.name.clone();
                    agent::stop_agent(agent);
                    self.agents.remove(self.selected_index);
                    if self.selected_index > 0 && self.selected_index >= self.agents.len() {
                        self.selected_index = self.agents.len().saturating_sub(1);
                    }
                    self.sort_agents_by_dir();
                    self.status_message = Some(format!("Killed {}", name));
                }
                true
            }
            BareKey::Char('j') | BareKey::Down => {
                self.selected_index = wrap_next(self.selected_index, self.agents.len());
                true
            }
            BareKey::Char('k') | BareKey::Up => {
                self.selected_index = wrap_prev(self.selected_index, self.agents.len());
                true
            }
            BareKey::Char('f') | BareKey::Enter => {
                self.focus_selected();
                true
            }
            BareKey::Char('h') | BareKey::Esc => {
                // Layered dismissal: help > unfocus (detail is toggled only by 'i')
                if self.show_help {
                    self.show_help = false;
                } else {
                    self.unfocus_current();
                }
                self.status_message = None;
                true
            }
            BareKey::Char('i') => {
                // Toggle auto-detail panel (show/hide for selected agent)
                self.show_detail = !self.show_detail;
                true
            }
            BareKey::Char('?') => {
                self.show_help = !self.show_help;
                true
            }
            BareKey::Char('Q') => {
                self.save_and_quit();
                true
            }
            // Number keys 1-9: quick select + focus agent
            BareKey::Char(c @ '1'..='9') => {
                let idx = (*c as u8 - b'1') as usize;
                if idx < self.agents.len() {
                    self.focus_agent_by_index(idx);
                    true
                } else {
                    false
                }
            }
            _ => false,
        }
    }

    /// Handle keyboard input while the inline name prompt is active.
    fn handle_name_prompt_key(&mut self, key: KeyWithModifier) -> bool {
        let bare = key.bare_key;
        let no_mods = key.key_modifiers.is_empty();

        if !no_mods {
            return false;
        }

        let prompt = match self.name_prompt.as_mut() {
            Some(p) => p,
            None => return false,
        };

        match bare {
            BareKey::Esc => {
                self.name_prompt = None;
                self.rename_target = None;
                return true;
            }
            BareKey::Enter => {
                let name = if prompt.input.is_empty() {
                    prompt.default_name.clone()
                } else {
                    prompt.input.clone()
                };
                self.name_prompt = None;

                if let Some(agent_id) = self.rename_target.take() {
                    // Rename mode: update agent name + Zellij pane title.
                    if let Some(agent) = self.agents.iter_mut().find(|a| a.id == agent_id) {
                        agent.name = name.clone();
                        if let Some(pid) = agent.pane_id {
                            let title = agent::pane_title(&name, &agent.agent_type, &self.config.agent_types, agent.sandbox_level.as_deref(), &agent.icon);
                            rename_pane_with_id(PaneId::Terminal(pid), &title);
                        }
                        self.status_message = Some(format!("Renamed to {}", name));
                    }
                    self.sort_agents_by_dir();
                } else {
                    // New agent mode (gh#62): session_defaults wins over static config.
                    // Use the saved wizard choices verbatim (agent_type, provider,
                    // project_dir, sandbox_level, sandbox_backend); fall back to
                    // the static `[dashboard].default_*` chain otherwise.
                    let (effective_type, provider, project_dir, sandbox_level, sandbox_backend) =
                        match self.session_defaults.as_ref() {
                            Some(sd) if self.config.agent_types.contains_key(&sd.agent_type) => (
                                sd.agent_type.clone(),
                                sd.provider.clone(),
                                sd.project_dir.clone(),
                                sd.sandbox_level.clone(),
                                sd.sandbox_backend.clone(),
                            ),
                            _ => (
                                self.effective_default_agent_type().to_string(),
                                self.config.default_provider.clone(),
                                self.config.default_project_dir.clone().unwrap_or_default(),
                                None,
                                None,
                            ),
                        };
                    match agent::spawn_agent_custom(
                        &self.config,
                        &mut self.next_agent_id,
                        &self.agents,
                        name,
                        &effective_type,
                        provider,
                        project_dir,
                        self.launch_dir.as_deref(),
                        sandbox_level,
                        sandbox_backend,
                    ) {
                        Ok(info) => {
                            self.status_message = Some(format!("Spawned {}", info.name));
                            self.record_recent_project_dir(&info.project_dir);
                            self.agents.push(info);
                            self.sort_agents_by_dir();
                            self.hide_all_agent_panes();
                        }
                        Err(e) => {
                            self.status_message = Some(e);
                        }
                    }
                }
                return true;
            }
            BareKey::Backspace => {
                prompt.input.pop();
            }
            BareKey::Char(c) => {
                prompt.input.push(c);
            }
            _ => {}
        }
        true
    }

    /// Handle keyboard input while the wizard overlay is active.
    fn handle_wizard_key(&mut self, key: KeyWithModifier) -> bool {
        let bare = key.bare_key;
        let no_mods = key.key_modifiers.is_empty();

        if !no_mods {
            return false;
        }

        let wizard = match self.wizard.as_mut() {
            Some(w) => w,
            None => return false,
        };

        match bare {
            BareKey::Esc => {
                // If completions are showing, dismiss them instead of closing the wizard.
                if !wizard.completions.is_empty() {
                    wizard.clear_completions();
                    return true;
                }
                self.wizard = None;
                self.status_message = Some("Wizard cancelled".to_string());
                set_timeout(3.0);
                return true;
            }
            _ => {}
        }

        match wizard.step {
            WizardStep::AgentType => match bare {
                BareKey::Enter | BareKey::Tab => {
                    let base = wizard.selected_base_agent().to_string();
                    // Re-resolve sandbox backends for the selected base BEFORE advancing.
                    wizard.available_sandbox_backends = self.config
                        .available_backends_for_base(&base, self.detected_backends.as_ref());
                    wizard.sandbox_backend_index = self.config
                        .default_backend_index_for_base(&base, &wizard.available_sandbox_backends);
                    // Re-resolve sandbox levels (backend-aware: includes custom levels
                    // discovered for the freshly-resolved backend index).
                    let backend_for_levels = wizard.available_sandbox_backends
                        .get(wizard.sandbox_backend_index);
                    wizard.available_sandbox_levels = self.config
                        .supported_sandbox_levels(&base, backend_for_levels);
                    wizard.sandbox_level_index = {
                        let pinned = self.config.agent_types.get(&base)
                            .and_then(|c| c.sandbox_level.as_deref());
                        pinned
                            .and_then(|p| wizard.available_sandbox_levels.iter().position(|l| l == p))
                            .unwrap_or(0)
                    };
                    // Resolve profiles against the effective agent_type *now* — if the
                    // SandboxBackend step is skipped (single backend), its resolution
                    // hook never fires and the wizard would carry the previous agent's
                    // profile list. The SandboxBackend Enter handler still re-resolves
                    // when shown, which is fine and cheap.
                    let effective = wizard.effective_agent_type();
                    wizard.available_providers = self.config.providers_for_agent_type(&effective);
                    wizard.provider_index = self.config.default_provider.as_ref()
                        .and_then(|dp| wizard.available_providers.iter().position(|p| p == dp))
                        .unwrap_or(0);
                    // #167: keep the default name dir-derived (the basename
                    // doesn't depend on agent type). `base` only matters as the
                    // fallback when project_dir has no usable basename. Skipped
                    // if the user already typed a custom name.
                    if wizard.name.is_empty() {
                        wizard.default_name = agent::suggest_agent_name(
                            &wizard.project_dir,
                            &self.agents,
                            self.next_agent_id,
                            &base,
                        );
                    }
                    if let Some(next) = wizard.next_step() {
                        wizard.step = next;
                    }
                }
                BareKey::Up | BareKey::Char('k') => {
                    if wizard.agent_type_index > 0 {
                        wizard.agent_type_index -= 1;
                    } else {
                        wizard.agent_type_index = wizard.available_agent_types.len().saturating_sub(1);
                    }
                }
                BareKey::Down | BareKey::Char('j') => {
                    let len = wizard.available_agent_types.len();
                    if len > 0 {
                        wizard.agent_type_index = (wizard.agent_type_index + 1) % len;
                    }
                }
                _ => {}
            },
            WizardStep::SandboxBackend => match bare {
                BareKey::Enter | BareKey::Tab => {
                    // Resolve profiles against the *effective* agent_type now that the
                    // user has committed to a backend (sandboxed canonical vs unsandboxed).
                    let effective = wizard.effective_agent_type();
                    wizard.available_providers = self.config.providers_for_agent_type(&effective);
                    wizard.provider_index = self.config.default_provider.as_ref()
                        .and_then(|dp| wizard.available_providers.iter().position(|p| p == dp))
                        .unwrap_or(0);
                    // Re-resolve sandbox levels for the just-chosen backend (custom levels
                    // are backend-specific: nono profile dirs differ from agent-sandbox).
                    let base = wizard.selected_base_agent().to_string();
                    let backend_for_levels = wizard.selected_sandbox_backend();
                    let preserved = wizard.selected_sandbox_level().map(|s| s.to_string());
                    wizard.available_sandbox_levels = self.config
                        .supported_sandbox_levels(&base, backend_for_levels.as_ref());
                    wizard.sandbox_level_index = preserved
                        .as_deref()
                        .and_then(|p| wizard.available_sandbox_levels.iter().position(|l| l == p))
                        .or_else(|| {
                            let pinned = self.config.agent_types.get(&base)
                                .and_then(|c| c.sandbox_level.as_deref());
                            pinned.and_then(|p| wizard.available_sandbox_levels.iter().position(|l| l == p))
                        })
                        .unwrap_or(0);
                    if let Some(next) = wizard.next_step() {
                        wizard.step = next;
                    }
                }
                BareKey::Backspace => {
                    if let Some(prev) = wizard.prev_step() {
                        wizard.step = prev;
                    }
                }
                BareKey::Up | BareKey::Char('k') => {
                    let len = wizard.available_sandbox_backends.len();
                    if len > 0 {
                        wizard.sandbox_backend_index = if wizard.sandbox_backend_index == 0 {
                            len - 1
                        } else {
                            wizard.sandbox_backend_index - 1
                        };
                    }
                }
                BareKey::Down | BareKey::Char('j') => {
                    let len = wizard.available_sandbox_backends.len();
                    if len > 0 {
                        wizard.sandbox_backend_index = (wizard.sandbox_backend_index + 1) % len;
                    }
                }
                _ => {}
            },
            WizardStep::SandboxLevel => match bare {
                BareKey::Enter | BareKey::Tab => {
                    if let Some(next) = wizard.next_step() {
                        wizard.step = next;
                    }
                }
                BareKey::Backspace => {
                    if let Some(prev) = wizard.prev_step() {
                        wizard.step = prev;
                    }
                }
                BareKey::Up | BareKey::Char('k') => {
                    let len = wizard.available_sandbox_levels.len();
                    if len > 0 {
                        wizard.sandbox_level_index = if wizard.sandbox_level_index == 0 {
                            len - 1
                        } else {
                            wizard.sandbox_level_index - 1
                        };
                    }
                }
                BareKey::Down | BareKey::Char('j') => {
                    let len = wizard.available_sandbox_levels.len();
                    if len > 0 {
                        wizard.sandbox_level_index = (wizard.sandbox_level_index + 1) % len;
                    }
                }
                _ => {}
            },
            WizardStep::Name => match bare {
                BareKey::Enter | BareKey::Tab => {
                    if let Some(next) = wizard.next_step() {
                        wizard.step = next;
                    }
                }
                BareKey::Backspace => {
                    if wizard.name.is_empty() {
                        if let Some(prev) = wizard.prev_step() {
                            wizard.step = prev;
                        }
                    } else {
                        wizard.name.pop();
                    }
                }
                BareKey::Char(c) => {
                    wizard.name.push(c);
                }
                _ => {}
            },
            WizardStep::Provider => match bare {
                BareKey::Enter | BareKey::Tab => {
                    if let Some(next) = wizard.next_step() {
                        wizard.step = next;
                    }
                }
                BareKey::Backspace => {
                    if let Some(prev) = wizard.prev_step() {
                        wizard.step = prev;
                    }
                }
                BareKey::Up | BareKey::Char('k') => {
                    if wizard.provider_index > 0 {
                        wizard.provider_index -= 1;
                    } else {
                        wizard.provider_index = wizard.available_providers.len().saturating_sub(1);
                    }
                }
                BareKey::Down | BareKey::Char('j') => {
                    let len = wizard.available_providers.len();
                    if len > 0 {
                        wizard.provider_index = (wizard.provider_index + 1) % len;
                    }
                }
                _ => {}
            },
            // Dual-mode (#127): a navigable recents picker (List) with a
            // free-text escape hatch (Input). When there are no recents the
            // wizard opens straight in Input mode (legacy behavior intact).
            WizardStep::ProjectDir => match wizard.project_dir_mode {
                // ── Recents picker (#127) ──────────────────────────────
                ProjectDirMode::List => match bare {
                    BareKey::Down => {
                        let len = wizard.filtered_project_dirs().len();
                        if len > 0 {
                            wizard.project_dir_index = (wizard.project_dir_index + 1) % len;
                        }
                    }
                    BareKey::Up => {
                        let len = wizard.filtered_project_dirs().len();
                        if len > 0 {
                            wizard.project_dir_index = (wizard.project_dir_index + len - 1) % len;
                        }
                    }
                    BareKey::Enter => {
                        let selected = wizard
                            .filtered_project_dirs()
                            .get(wizard.project_dir_index)
                            .map(|s| s.to_string());
                        if let Some(dir) = selected {
                            wizard.project_dir = dir;
                            wizard.project_dir_error = None;
                            wizard.project_dir_suggested = false;
                            // #167: refresh the dir-derived default name unless the
                            // user already typed a custom one.
                            if wizard.name.is_empty() {
                                let base = wizard.selected_base_agent().to_string();
                                wizard.default_name = agent::suggest_agent_name(
                                    &wizard.project_dir,
                                    &self.agents,
                                    self.next_agent_id,
                                    &base,
                                );
                            }
                            if let Some(next) = wizard.next_step() {
                                wizard.step = next;
                            }
                        } else {
                            // Filter matched nothing → hand the typed text over to
                            // free-text input so the user can finish a fresh path
                            // instead of hitting a dead end.
                            wizard.project_dir = wizard.project_dir_filter.trim().to_string();
                            wizard.project_dir_filter.clear();
                            wizard.project_dir_index = 0;
                            wizard.project_dir_suggested = false;
                            wizard.project_dir_mode = ProjectDirMode::Input;
                        }
                    }
                    // `i` switches to free-text ONLY as the first keystroke (filter
                    // still empty). Once filtering has begun, `i` is a normal filter
                    // character — otherwise paths containing "i" (most of them)
                    // couldn't be filtered.
                    BareKey::Char('i') if wizard.project_dir_filter.is_empty() => {
                        wizard.project_dir_mode = ProjectDirMode::Input;
                    }
                    BareKey::Char(c) => {
                        wizard.project_dir_filter.push(c);
                        wizard.project_dir_index = 0;
                    }
                    BareKey::Backspace => {
                        if wizard.project_dir_filter.is_empty() {
                            if let Some(prev) = wizard.prev_step() {
                                wizard.step = prev;
                            }
                        } else {
                            wizard.project_dir_filter.pop();
                            wizard.project_dir_index = 0;
                        }
                    }
                    _ => {}
                },
                // ── Free-text input (legacy escape hatch) ──────────────
                ProjectDirMode::Input => match bare {
                    BareKey::Enter => {
                        // If completions are showing and one is highlighted, accept it first.
                        if let Some(idx) = wizard.completion_index {
                            if let Some(selected) = wizard.completions.get(idx).cloned() {
                                wizard.project_dir = selected;
                            }
                            wizard.clear_completions();
                            wizard.project_dir_error = None;
                            wizard.project_dir_suggested = false;
                        } else {
                            // Validate BEFORE advancing. Sandbox backends (nono on
                            // macOS, agent-sandbox/bwrap on Linux) require absolute
                            // paths — catch typos here so the user sees the cause
                            // and can correct without spawning a doomed agent.
                            //
                            // Tilde handling: the path completer collapses absolute
                            // matches back to `~/...` for readability. Expand it
                            // transparently here so the wizard accepts `~/...` input.
                            let trimmed_owned = wizard.project_dir.trim().to_string();
                            if trimmed_owned.starts_with('~') {
                                let expanded = config::expand_tilde(&trimmed_owned);
                                if expanded.starts_with('/') {
                                    wizard.project_dir = expanded;
                                }
                            }
                            let trimmed = wizard.project_dir.trim();
                            let err = if trimmed.is_empty() {
                                Some("Project dir is required.")
                            } else if trimmed.starts_with('~') {
                                // Tilde survived expansion → $HOME unavailable in
                                // this plugin process. Ask for the full path.
                                Some("Project dir does not expand `~`. Use the full /Users/... path (Tab to autocomplete).")
                            } else if !trimmed.starts_with('/') {
                                Some("Project dir must be an absolute path (Tab to autocomplete).")
                            } else {
                                None
                            };
                            if let Some(msg) = err {
                                wizard.project_dir_error = Some(msg.to_string());
                                // Stay on ProjectDir — Backspace to edit, Tab to autocomplete.
                                return true;
                            }
                            wizard.project_dir_error = None;
                            // #167: refresh the dir-derived default name unless the
                            // user already typed a custom one.
                            if wizard.name.is_empty() {
                                let base = wizard.selected_base_agent().to_string();
                                wizard.default_name = agent::suggest_agent_name(
                                    &wizard.project_dir,
                                    &self.agents,
                                    self.next_agent_id,
                                    &base,
                                );
                            }
                            if let Some(next) = wizard.next_step() {
                                wizard.step = next;
                            }
                        }
                    }
                    BareKey::Tab => {
                        wizard.project_dir_suggested = false;
                        if wizard.completions.is_empty() {
                            // First Tab press: request completions from the shell.
                            config::complete_path_async(
                                &wizard.project_dir,
                                &self.config.project_search_roots,
                                self.config.project_search_max_depth,
                            );
                        } else {
                            // Subsequent Tab presses: cycle through suggestions.
                            let len = wizard.completions.len();
                            wizard.completion_index = Some(match wizard.completion_index {
                                Some(i) => (i + 1) % len,
                                None => 0,
                            });
                        }
                    }
                    BareKey::Backspace => {
                        if wizard.project_dir_suggested && !wizard.project_dir.is_empty() {
                            // #168: first Backspace on a pristine pre-fill clears the
                            // whole field (ready for a fresh path) instead of deleting
                            // one char or navigating back.
                            wizard.project_dir = String::new();
                            wizard.project_dir_suggested = false;
                            wizard.clear_completions();
                            wizard.project_dir_error = None;
                        } else if wizard.project_dir.is_empty() {
                            // Back out to the recents list if we have any (#127),
                            // else step backward through the wizard.
                            if wizard.available_project_dirs.is_empty() {
                                if let Some(prev) = wizard.prev_step() {
                                    wizard.step = prev;
                                }
                            } else {
                                wizard.project_dir_mode = ProjectDirMode::List;
                                wizard.clear_completions();
                                wizard.project_dir_error = None;
                            }
                        } else {
                            wizard.project_dir.pop();
                            wizard.clear_completions();
                            wizard.project_dir_error = None;
                        }
                    }
                    BareKey::Char(c) => {
                        wizard.project_dir_suggested = false;
                        wizard.project_dir.push(c);
                        wizard.clear_completions();
                        wizard.project_dir_error = None;
                    }
                    _ => {}
                },
            },
            WizardStep::Confirm => match bare {
                BareKey::Enter | BareKey::Char('!') => {
                    // Clone values out before dropping the borrow.
                    // #167: an empty Name field uses the dir-derived default the
                    // wizard advertised (e.g. `myPrj-1`), NOT the legacy
                    // `<type>-<id>` — spawn_agent_custom only falls back to the
                    // latter when this string is also empty.
                    let name = if wizard.name.is_empty() {
                        wizard.default_name.clone()
                    } else {
                        wizard.name.clone()
                    };
                    let agent_type = wizard.effective_agent_type();
                    let provider = wizard.selected_provider().map(|s| s.to_string());
                    let project_dir = wizard.project_dir.clone();
                    let backend_choice = wizard.selected_sandbox_backend();
                    // Skip level when the chosen backend is `None` (unsandboxed) — it's a no-op.
                    let sandbox_level = if matches!(backend_choice, Some(sandbox_backend::SandboxBackend::None)) {
                        None
                    } else {
                        wizard.selected_sandbox_level().map(|s| s.to_string())
                    };
                    let sandbox_backend = backend_choice;
                    // gh#62: `!` makes these choices the active `n` quick-spawn
                    // defaults for the rest of the session and persists them in
                    // `.lince-dashboard` on the next `Q`.
                    let save_defaults = matches!(bare, BareKey::Char('!'));
                    if save_defaults {
                        self.session_defaults = Some(SessionDefaults {
                            agent_type: agent_type.clone(),
                            provider: provider.clone(),
                            project_dir: project_dir.clone(),
                            sandbox_level: sandbox_level.clone(),
                            sandbox_backend: sandbox_backend.clone(),
                        });
                    }
                    self.wizard = None;
                    self.spawn_wizard_agent(
                        name,
                        &agent_type,
                        provider,
                        project_dir,
                        sandbox_level,
                        sandbox_backend,
                    );
                    if save_defaults {
                        // Append the defaults-saved note to whatever spawn_wizard_agent
                        // wrote (typically "Spawned <name>") to keep both signals visible.
                        let prev = self.status_message.take().unwrap_or_default();
                        self.status_message = Some(if prev.is_empty() {
                            "Defaults saved for n".to_string()
                        } else {
                            format!("{} · defaults saved for n", prev)
                        });
                    }
                    return true;
                }
                BareKey::Backspace => {
                    if let Some(prev) = wizard.prev_step() {
                        wizard.step = prev;
                    }
                }
                _ => {}
            },
        }
        true
    }

    /// Spawn an agent using custom values from the wizard.
    fn spawn_wizard_agent(
        &mut self,
        name: String,
        agent_type: &str,
        provider: Option<String>,
        project_dir: String,
        sandbox_level_override: Option<String>,
        sandbox_backend_override: Option<sandbox_backend::SandboxBackend>,
    ) {
        match agent::spawn_agent_custom(
            &self.config,
            &mut self.next_agent_id,
            &self.agents,
            name,
            agent_type,
            provider,
            project_dir,
            self.launch_dir.as_deref(),
            sandbox_level_override,
            sandbox_backend_override,
        ) {
            Ok(info) => {
                self.status_message = Some(format!("Spawned {}", info.name));
                self.record_recent_project_dir(&info.project_dir);
                self.agents.push(info);
                self.sort_agents_by_dir();
                self.hide_all_agent_panes();
            }
            Err(e) => {
                self.status_message = Some(e);
            }
        }
    }

    /// Focus the currently selected agent's pane.
    fn focus_selected(&mut self) {
        if let Some(agent) = self.agents.get(self.selected_index) {
            if pane_manager::focus_agent(
                agent, &self.agents, &self.config.focus_mode, &self.config.agent_layout,
            ) {
                self.focused_agent = Some(agent.id.clone());
                self.status_message = Some(format!("Focused {}", agent.name));
            }
        }
    }

    /// Focus agent by 0-based index, unfocusing the current one first.
    /// Used by both the 1-9 key handler (dashboard focus) and the Alt+1-9
    /// pipe message (global keybinding via Zellij config.kdl MessagePlugin).
    fn focus_agent_by_index(&mut self, idx: usize) {
        if idx >= self.agents.len() {
            return;
        }
        // Unfocus current agent if any.
        self.unfocus_current();
        self.selected_index = idx;
        self.focus_selected();
    }

    /// Hide all agent floating panes (used after spawn to prevent unwanted pane visibility).
    fn hide_all_agent_panes(&mut self) {
        pane_manager::hide_agent_panes(&self.agents, None, &self.config.agent_layout);
        self.focused_agent = None;
    }

    /// Unfocus the currently focused agent (hide its pane).
    fn unfocus_current(&mut self) {
        if let Some(focused_id) = self.focused_agent.take() {
            if let Some(agent) = self.agents.iter().find(|a| a.id == focused_id) {
                pane_manager::unfocus_agent(agent, &self.config.focus_mode, &self.config.agent_layout);
            }
        }
    }


    /// Handle a "claude-status" pipe message (LINCE-42, LINCE-48, LINCE-53).
    fn handle_status_message(&mut self, payload: &str) {
        let msg: StatusMessage = match serde_json::from_str(payload) {
            Ok(m) => m,
            Err(_) => return, // silently ignore malformed messages
        };

        let agent = match self.agents.iter_mut().find(|a| a.id == msg.agent_id) {
            Some(a) => a,
            None => return, // unknown agent, ignore
        };

        // LINCE-118 + LINCE-119: legacy event handling removed.
        // - `ignore_wrapper_start` / `start` aliases: gone, alongside the
        //   `Starting` state and the wrapper-start suppression hack.
        // - `subagent_start` / `subagent_stop`: rich subagent counter gone
        //   together with `AgentInfo.running_subagents`.
        // - `tokens_in`/`tokens_out`, `tool_name`, `model`: dropped from
        //   both `StatusMessage` and `AgentInfo`.
        // Everything funnels through the canonical 5-state mapping now.
        let new_status = msg.to_agent_status(self.config.event_map_for(&agent.agent_type));
        agent.status = new_status;

        if let Some(e) = msg.error {
            agent.last_error = Some(e);
        }

        // Forward transcript_path from hook events to agent state.
        // Updated on every hook event (not just SessionStart) for robustness —
        // the field is stable within a session so repeated writes are benign.
        if let Some(tp) = msg.transcript_path {
            if !tp.is_empty() {
                agent.transcript_path = Some(tp);
            }
        }
    }

    /// Handle a "voxcode-text" pipe message — relay text to active agent (LINCE-43).
    fn handle_voxcode_text(&mut self, text: &str) {
        // Find the target agent index: focused > selected > none
        let target_idx = if let Some(ref focused_id) = self.focused_agent {
            self.agents.iter().position(|a| &a.id == focused_id)
        } else if self.selected_index < self.agents.len() {
            Some(self.selected_index)
        } else {
            None
        };

        let Some(idx) = target_idx else {
            self.status_message = Some("No agent to receive text".to_string());
            set_timeout(3.0);
            return;
        };

        let Some(pid) = self.agents[idx].pane_id else {
            self.status_message = Some("Agent has no pane".to_string());
            set_timeout(3.0);
            return;
        };

        write_chars_to_pane_id(text, PaneId::Terminal(pid));

        // Show the agent pane after delivering text
        if pane_manager::focus_agent(
            &self.agents[idx], &self.agents,
            &self.config.focus_mode, &self.config.agent_layout,
        ) {
            self.focused_agent = Some(self.agents[idx].id.clone());
            self.selected_index = idx;
        }
    }

    /// Start relay: extract last `count` messages from selected agent's transcript.
    /// LINCE-87/88/89 inter-agent message relay.
    fn start_relay(&mut self, count: usize) {
        let agent = match self.agents.get(self.selected_index) {
            Some(a) => a,
            None => {
                self.status_message = Some("No agent selected".to_string());
                set_timeout(3.0);
                return;
            }
        };

        let tp = match &agent.transcript_path {
            Some(p) if !p.is_empty() => p.clone(),
            _ => {
                self.status_message = Some(format!(
                    "Transcript not available for {}",
                    agent.name
                ));
                set_timeout(3.0);
                return;
            }
        };

        if self.agents.len() < 2 {
            self.status_message = Some("Need 2+ agents to relay".to_string());
            set_timeout(3.0);
            return;
        }

        let source_id = agent.id.clone();
        let source_name = agent.name.clone();
        let source_index = self.selected_index;

        config::extract_transcript_async(&source_id, &tp, count);

        self.relay_state = Some(RelayState {
            phase: RelayPhase::Extracting {
                source_agent_id: source_id,
                source_agent_name: source_name,
                message_count: count,
            },
            source_index,
        });
        self.status_message = Some("Extracting...".to_string());
    }

    /// Enter relay MessagePrompt phase so user can pick count 1-9.
    fn start_relay_with_prompt(&mut self) {
        let agent = match self.agents.get(self.selected_index) {
            Some(a) => a,
            None => {
                self.status_message = Some("No agent selected".to_string());
                set_timeout(3.0);
                return;
            }
        };

        if agent.transcript_path.as_deref().unwrap_or("").is_empty() {
            self.status_message = Some(format!(
                "Transcript not available for {}",
                agent.name
            ));
            set_timeout(3.0);
            return;
        }

        if self.agents.len() < 2 {
            self.status_message = Some("Need 2+ agents to relay".to_string());
            set_timeout(3.0);
            return;
        }

        let source_index = self.selected_index;
        self.relay_state = Some(RelayState {
            phase: RelayPhase::MessagePrompt { input: String::new() },
            source_index,
        });
    }

    /// Handle keyboard input while relay state machine is active.
    fn handle_relay_key(&mut self, key: KeyWithModifier) -> bool {
        let bare = key.bare_key;
        let no_mods = key.key_modifiers.is_empty();

        if !no_mods {
            return false;
        }

        // Take ownership of the current relay state for processing.
        let rs = match self.relay_state.take() {
            Some(rs) => rs,
            None => return false,
        };

        match &rs.phase {
            RelayPhase::MessagePrompt { .. } => {
                match bare {
                    BareKey::Char(c @ '1'..='9') => {
                        let digit = c.to_string();
                        self.relay_state = Some(RelayState {
                            phase: RelayPhase::MessagePrompt { input: digit },
                            source_index: rs.source_index,
                        });
                    }
                    BareKey::Enter => {
                        let input = match &rs.phase {
                            RelayPhase::MessagePrompt { input } => input.clone(),
                            _ => String::new(),
                        };
                        let count = if input.is_empty() { 1 } else { input.parse::<usize>().unwrap_or(1) };
                        // Restore relay_state so start_relay can validate the agent.
                        self.relay_state = Some(rs);
                        self.start_relay(count);
                    }
                    BareKey::Esc => {
                        // Clear relay_state (already taken).
                    }
                    _ => {
                        // Unrecognized key: put state back.
                        self.relay_state = Some(rs);
                    }
                }
            }
            RelayPhase::Extracting { .. } => {
                match bare {
                    BareKey::Esc => {
                        // Clear relay_state (already taken).
                    }
                    _ => {
                        // Ignore all other keys during extraction.
                        self.relay_state = Some(rs);
                    }
                }
            }
            RelayPhase::DeliveryPending { .. } => {
                let max_idx = self.agents.len().saturating_sub(1);
                match bare {
                    BareKey::Char('f') | BareKey::Enter => {
                        // Restore state for deliver_relay_to_selected.
                        self.relay_state = Some(rs);
                        self.deliver_relay_to_selected();
                    }
                    BareKey::Char('j') => {
                        let new_idx = rs.source_index.saturating_sub(1);
                        self.relay_state = Some(RelayState {
                            phase: rs.phase,
                            source_index: new_idx,
                        });
                    }
                    BareKey::Char('k') => {
                        let new_idx = if rs.source_index < max_idx {
                            rs.source_index + 1
                        } else {
                            max_idx
                        };
                        self.relay_state = Some(RelayState {
                            phase: rs.phase,
                            source_index: new_idx,
                        });
                    }
                    BareKey::Char(c @ '1'..='9') => {
                        let target_idx = (c as u8 - b'1') as usize;
                        self.relay_state = Some(RelayState {
                            phase: rs.phase,
                            source_index: target_idx.min(max_idx),
                        });
                        self.deliver_relay_to_selected();
                    }
                    BareKey::Esc => {
                        // Clear relay_state (already taken).
                    }
                    _ => {
                        self.relay_state = Some(rs);
                    }
                }
            }
        }
        true
    }

    /// Deliver relayed text to the target agent pane.
    fn deliver_relay_to_selected(&mut self) {
        let rs = match self.relay_state.take() {
            Some(rs) => rs,
            None => return,
        };

        let (source_name, captured_text, message_count) = match &rs.phase {
            RelayPhase::DeliveryPending { source_agent_name, captured_text, message_count } => {
                (source_agent_name.clone(), captured_text.clone(), *message_count)
            }
            _ => {
                // Should not happen — put state back.
                self.relay_state = Some(rs);
                return;
            }
        };

        // Validate target index.
        let target_idx = rs.source_index;
        if target_idx >= self.agents.len() {
            self.relay_state = Some(RelayState {
                phase: RelayPhase::DeliveryPending {
                    source_agent_name: source_name,
                    captured_text,
                    message_count,
                },
                source_index: target_idx,
            });
            self.status_message = Some("Invalid target index".to_string());
            set_timeout(3.0);
            return;
        }

        let target = &self.agents[target_idx];

        // Prevent self-relay.
        let source_agent = self.agents.iter().find(|a| a.name == source_name);
        if let Some(src) = source_agent {
            if src.id == target.id {
                self.relay_state = Some(RelayState {
                    phase: RelayPhase::DeliveryPending {
                        source_agent_name: source_name,
                        captured_text,
                        message_count,
                    },
                    source_index: target_idx,
                });
                self.status_message = Some("Cannot relay to self — select another agent".to_string());
                set_timeout(3.0);
                return;
            }
        }

        // Validate target has a pane.
        let target_pid = match target.pane_id {
            Some(pid) => pid,
            None => {
                self.relay_state = Some(RelayState {
                    phase: RelayPhase::DeliveryPending {
                        source_agent_name: source_name,
                        captured_text,
                        message_count,
                    },
                    source_index: target_idx,
                });
                self.status_message = Some(format!("{} has no pane", target.name));
                set_timeout(3.0);
                return;
            }
        };

        let target_name = target.name.clone();
        let target_id = target.id.clone();

        // Wrap text with header/footer.
        let wrapped = format!(
            "--- Relay from {} ({} messages) ---\n{}\n--- End relay ---\n",
            source_name, message_count, captured_text
        );

        write_chars_to_pane_id(&wrapped, PaneId::Terminal(target_pid));

        // Focus target agent pane.
        if let Some(target_agent) = self.agents.get(target_idx) {
            if pane_manager::focus_agent(
                target_agent,
                &self.agents,
                &self.config.focus_mode,
                &self.config.agent_layout,
            ) {
                self.focused_agent = Some(target_id);
                self.selected_index = target_idx;
            }
        }

        self.relay_state = None;
        self.status_message = Some(format!(
            "Relayed {} messages from {} to {}",
            message_count, source_name, target_name
        ));
        set_timeout(3.0);
    }

    /// Poll status files for all agents (file-based fallback, LINCE-42).
    /// Returns true if any agent state changed.
    // Status-file polling is now async — see `config::poll_status_files_async`
    // (kicked off from the Timer handler) and the `CMD_POLL_STATUS` arm in
    // `update()`. The previous synchronous `poll_status_files()` used
    // `std::fs::read_to_string`, which silently reads nothing from a WASI
    // plugin sandbox: the host `/tmp` is not on the plugin's virtual fs.

    /// Save current agent state and quit Zellij.
    /// The actual quit happens in the RunCommandResult handler after
    /// the save command completes successfully.
    fn save_and_quit(&mut self) {
        let dir = match self.launch_dir.as_deref() {
            Some(d) => d,
            None => {
                self.status_message = Some("CWD not detected yet, try again".to_string());
                set_timeout(3.0);
                return;
            }
        };

        let saved: Vec<SavedAgentInfo> = self.agents.iter()
            .filter(|a| a.status != AgentStatus::Stopped)
            .map(SavedAgentInfo::from)
            .collect();

        match state_file::save_state_async(dir, saved, self.next_agent_id, self.session_defaults.clone()) {
            Ok(()) => {
                self.status_message = Some("Saving state...".to_string());
            }
            Err(e) => {
                self.status_message = Some(format!("Save failed: {}", e));
                set_timeout(5.0);
            }
        }
    }

    /// Re-spawn agents from saved state.
    fn restore_agents(&mut self, saved_agents: Vec<SavedAgentInfo>) {
        let mut spawned = 0u32;
        for saved in saved_agents {
            match agent::spawn_agent_custom(
                &self.config,
                &mut self.next_agent_id,
                &self.agents,
                saved.name,
                &saved.agent_type,
                saved.provider,
                saved.project_dir,
                self.launch_dir.as_deref(),
                saved.sandbox_level,
                saved.sandbox_backend,
            ) {
                Ok(mut info) => {
                    info.group = saved.group;
                    self.agents.push(info);
                    spawned += 1;
                }
                Err(e) => {
                    self.status_message = Some(format!("Restore error: {}", e));
                    break;
                }
            }
        }
        if spawned > 0 {
            self.sort_agents_by_dir();
            self.hide_all_agent_panes();
            // Auto-focus the first restored agent
            self.selected_index = 0;
            self.focus_selected();
            self.status_message = Some(format!("Restored {} agents", spawned));
            set_timeout(3.0);
        }
    }
}
