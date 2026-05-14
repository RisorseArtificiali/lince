mod agent;
mod config;
mod dashboard;
mod pane_manager;
mod sandbox_backend;
mod state_file;
mod types;

use std::collections::BTreeMap;
use zellij_tile::prelude::*;

use crate::config::{DashboardConfig, StatusMethod, DEFAULT_AGENT_TYPE};
use crate::sandbox_backend::DetectedBackends;

const PIPE_CLAUDE_STATUS: &str = "claude-status";
const PIPE_LINCE_STATUS: &str = "lince-status";
const PIPE_VOXCODE_TEXT: &str = "voxcode-text";
const PIPE_FOCUS_AGENT: &str = "focus-agent";
const PIPE_CYCLE_AGENT: &str = "cycle-agent";
const CMD_GET_CWD: &str = "get_cwd";
const CMD_LOAD_CONFIG: &str = "load_config";

use crate::types::{
    AgentInfo, AgentStatus, NamePromptState, SavedAgentInfo, SessionDefaults,
    StatusMessage, WizardState, WizardStep,
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
            launch_dir: None,
            pending_restore: None,
            agent_types_loaded: false,
            detected_backends: None,
            init_kicked: false,
            cwd_retries: 0,
            cwd_retry_exhausted: false,
            session_defaults: None,
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

                // File-based status polling fallback
                if self.config.status_method == StatusMethod::File {
                    if self.poll_status_files() {
                        needs_render = true;
                    }
                }

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
                            // Kick off async provider discovery (reads sandbox config via shell).
                            config::discover_providers_async(
                                self.config.sandbox_config_path.as_deref(),
                                Some(&dir),
                            );
                            // Kick off async load of agent type defaults.
                            config::load_agent_defaults_async(
                                self.config.sandbox_config_path.as_deref(),
                            );
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
                    Some(config::CMD_DISCOVER_PROVIDERS) => {
                        // Each config file's output is separated by NUL.
                        // Parse each independently to avoid duplicate-section TOML errors.
                        for chunk in stdout.split(|&b| b == 0) {
                            if chunk.is_empty() { continue; }
                            let content = String::from_utf8_lossy(chunk);
                            let (by_agent, details_by_agent) = config::parse_providers_from_toml(&content);
                            self.config.merge_providers(&by_agent, &details_by_agent);
                        }
                        true
                    }
                    Some(config::CMD_LOAD_AGENT_DEFAULTS) => {
                        let agent_types = config::parse_agent_defaults(&stdout);
                        if !agent_types.is_empty() {
                            self.config.agent_types = agent_types;
                        }
                        self.agent_types_loaded = true;
                        // Pre-warm the custom sandbox-level cache now that we know the
                        // bases. Discovery is async and idempotent — the wizard re-fires
                        // it on open as a refresh, but doing it here means the cache is
                        // usually populated before the user ever presses N.
                        let bases: Vec<String> = self.config.base_agents()
                            .into_iter().map(|(b, _)| b).collect();
                        config::discover_sandbox_levels_async(&bases);
                        // Flush any buffered restore that was waiting for agent types.
                        if let Some(saved_agents) = self.pending_restore.take() {
                            self.restore_agents(saved_agents);
                        }
                        true
                    }
                    Some(config::CMD_DISCOVER_SANDBOX_LEVELS) => {
                        if exit_code == Some(0) {
                            // Replace entire cache: each discovery call covers all
                            // bases × both backends atomically. A profile removed
                            // since the last run won't appear in the new map and
                            // would otherwise stick around as a stale level.
                            self.config.discovered_sandbox_levels =
                                config::parse_discovered_sandbox_levels(&stdout);
                            // Refresh the wizard's level list ONLY if the user hasn't
                            // moved past SandboxLevel yet — otherwise we'd risk
                            // clobbering an already-confirmed choice if discovery
                            // shifted the list (e.g., file removed mid-wizard).
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
                                .map(|l| config::collapse_tilde(l))
                                .collect();
                            matches.sort();

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

impl State {
    /// Sort agents by project_dir, then by name within each group.
    /// Preserves the selected agent across the sort.
    fn sort_agents_by_dir(&mut self) {
        let selected_id = self.agents.get(self.selected_index).map(|a| a.id.clone());

        self.agents.sort_by(|a, b| {
            a.project_dir.cmp(&b.project_dir).then(a.name.cmp(&b.name))
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
                let default_name = format!("{}-{}", base, self.next_agent_id + 1);
                self.name_prompt = Some(NamePromptState {
                    input: String::new(),
                    default_name,
                    label: "Name",
                });
                true
            }
            BareKey::Char('U') => {
                // Quick-spawn an unsandboxed agent. Skips the wizard entirely,
                // ignores `session_defaults` (which are tied to the sandboxed
                // workflow), and never touches them — `n` keeps spawning what
                // the user picked via `!` in the wizard. Useful as a one-shot
                // escape hatch for greenfield bootstrap where the sandbox
                // would otherwise block tool caches (~/.npm, ~/.cargo, ...).
                let base = agent::agent_type_base_name(
                    self.effective_default_agent_type()
                ).to_string();
                let unsandboxed_type = format!("{}-unsandboxed", base);
                if !self.config.agent_types.contains_key(&unsandboxed_type) {
                    self.status_message = Some(format!(
                        "U: no [agents.{}] configured — add it to use this shortcut",
                        unsandboxed_type
                    ));
                    return true;
                }
                let name = format!("{}-{}", base, self.next_agent_id + 1);
                let project_dir = self.config.default_project_dir.clone().unwrap_or_default();
                self.spawn_wizard_agent(
                    name,
                    &unsandboxed_type,
                    self.config.default_provider.clone(),
                    project_dir,
                    None,
                    Some(sandbox_backend::SandboxBackend::None),
                );
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
            BareKey::Char('N') => {
                let default_dir = self.config.default_project_dir.clone()
                    .unwrap_or_default();
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
                // Levels are backend-aware: discovered custom levels from
                // `~/.config/nono/profiles/` and `~/.agent-sandbox/profiles/` are merged with
                // the standard 3. Discovery is async — the cache may be empty at this point;
                // CMD_DISCOVER_SANDBOX_LEVELS handler refreshes the wizard when results arrive.
                let default_backend = available_sandbox_backends.get(sandbox_backend_index);
                let available_sandbox_levels = self.config.supported_sandbox_levels(default_base, default_backend);
                let sandbox_level_index = {
                    let pinned = self.config.agent_types.get(default_base)
                        .and_then(|c| c.sandbox_level.as_deref());
                    pinned
                        .and_then(|p| available_sandbox_levels.iter().position(|l| l == p))
                        .unwrap_or(0)
                };
                // Kick off async discovery for ALL bases (cache covers any future wizard moves).
                let discover_bases: Vec<String> = self.config.base_agents()
                    .into_iter().map(|(b, _)| b).collect();
                config::discover_sandbox_levels_async(&discover_bases);
                let default_name = format!("{}-{}", default_base, self.next_agent_id + 1);
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
                            let title = agent::pane_title(&name, &agent.agent_type, &self.config.agent_types, agent.sandbox_level.as_deref());
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
                    // Update default name to reflect the new base.
                    wizard.default_name = format!("{}-{}", base, self.next_agent_id + 1);
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
            WizardStep::ProjectDir => match bare {
                BareKey::Enter => {
                    // If completions are showing and one is highlighted, accept it first.
                    if let Some(idx) = wizard.completion_index {
                        if let Some(selected) = wizard.completions.get(idx).cloned() {
                            wizard.project_dir = selected;
                        }
                        wizard.clear_completions();
                    } else if let Some(next) = wizard.next_step() {
                        wizard.step = next;
                    }
                }
                BareKey::Tab => {
                    if wizard.completions.is_empty() {
                        // First Tab press: request completions from the shell.
                        config::complete_path_async(&wizard.project_dir);
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
                    if wizard.project_dir.is_empty() {
                        if let Some(prev) = wizard.prev_step() {
                            wizard.step = prev;
                        }
                    } else {
                        wizard.project_dir.pop();
                        wizard.clear_completions();
                    }
                }
                BareKey::Char(c) => {
                    wizard.project_dir.push(c);
                    wizard.clear_completions();
                }
                _ => {}
            },
            WizardStep::Confirm => match bare {
                BareKey::Enter | BareKey::Char('!') => {
                    // Clone values out before dropping the borrow.
                    let name = wizard.name.clone();
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

    /// Poll status files for all agents (file-based fallback, LINCE-42).
    /// Returns true if any agent state changed.
    fn poll_status_files(&mut self) -> bool {
        let mut changed = false;
        let status_dir = &self.config.status_file_dir;
        for agent in self.agents.iter_mut() {
            // Check both file naming conventions:
            // Claude hook writes "claude-{id}.state", wrapper writes "{id}.state"
            let path_claude = format!("{}/claude-{}.state", status_dir, agent.id);
            let path_wrapper = format!("{}/{}.state", status_dir, agent.id);
            let content_opt = std::fs::read_to_string(&path_claude)
                .or_else(|_| std::fs::read_to_string(&path_wrapper))
                .ok();
            if let Some(content) = content_opt {
                let event = content.trim().to_string();
                if !event.is_empty() {
                    // Skip if the event hasn't changed since last poll
                    if agent.last_polled_event.as_ref() == Some(&event) {
                        continue;
                    }
                    agent.last_polled_event = Some(event.clone());
                    let msg = StatusMessage {
                        agent_id: agent.id.clone(),
                        event,
                        timestamp: None,
                        error: None,
                    };
                    let new_status = msg.to_agent_status(self.config.event_map_for(&agent.agent_type));
                    if agent.status != new_status {
                        agent.status = new_status;
                        changed = true;
                    }
                }
            }
        }
        changed
    }

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
