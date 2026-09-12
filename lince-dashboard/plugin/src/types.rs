#[derive(Debug, Clone, PartialEq)]
pub enum AgentStatus {
    /// Initial / unobserved state (no hook event received yet, or unknown event).
    Unknown,
    Running,
    WaitingForInput,
    PermissionRequired,
    Stopped,
}

impl AgentStatus {
    /// Legacy default color contract; renderers use theme::status.
    #[cfg(test)]
    pub fn color(&self) -> &str {
        match self {
            AgentStatus::Unknown => "\x1b[90m",              // dim gray
            AgentStatus::Running => "\x1b[32m",              // green
            AgentStatus::WaitingForInput => "\x1b[1;33m",    // bold yellow
            AgentStatus::PermissionRequired => "\x1b[1;31m", // bold red
            AgentStatus::Stopped => "\x1b[2m",               // dim
        }
    }

    /// Human-readable label
    pub fn label(&self) -> &str {
        match self {
            AgentStatus::Unknown => "-",
            AgentStatus::Running => "Running",
            AgentStatus::WaitingForInput => "INPUT",
            AgentStatus::PermissionRequired => "PERMISSION",
            AgentStatus::Stopped => "Stopped",
        }
    }
}

/// Status message received from agent hooks via zellij pipe or file.
///
/// Trimmed in LINCE-118: hooks now only carry the bare minimum needed to drive
/// the 5-state status machine. Rich telemetry (tokens, tool name, model, etc.)
/// was removed along with the dashboard fields that consumed it.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct StatusMessage {
    pub agent_id: String,
    pub event: String,
    #[serde(default)]
    #[allow(dead_code)] // deserialized from hook JSON, reserved for elapsed time display
    pub timestamp: Option<String>,
    #[serde(default)]
    pub error: Option<String>,
    #[serde(default)]
    #[allow(dead_code)] // deserialized from hook JSON, reserved for future session tracking
    pub session_id: Option<String>,
    #[serde(default)]
    pub transcript_path: Option<String>,
}

/// Map a canonical status string to AgentStatus.
///
/// Used for event_map values and as the first pass for raw event matching.
/// LINCE-118: closed set of exactly 5 lowercase strings; all legacy aliases
/// (`start`, `idle`, `waiting_for_input`, `permission_required`) are gone.
/// Agent-specific event names (e.g. Claude's `PreToolUse`) must be translated
/// via per-agent `event_map` config entries instead.
pub(crate) fn canonical_status(s: &str) -> Option<AgentStatus> {
    match s {
        "unknown" => Some(AgentStatus::Unknown),
        "running" => Some(AgentStatus::Running),
        "input" => Some(AgentStatus::WaitingForInput),
        "permission" => Some(AgentStatus::PermissionRequired),
        "stopped" => Some(AgentStatus::Stopped),
        _ => None,
    }
}

impl StatusMessage {
    /// Map the event string to an AgentStatus.
    ///
    /// Resolution order (LINCE-118):
    /// 1. Per-agent `event_map` translates the raw event to a canonical string.
    /// 2. The raw event is itself a canonical string.
    /// 3. Fallback: `AgentStatus::Unknown` (a warning is emitted to stderr so
    ///    misconfigured event maps are visible during development).
    pub fn to_agent_status(&self, event_map: Option<&std::collections::HashMap<String, String>>) -> AgentStatus {
        // 1. Custom event_map lookup — translate raw event → canonical → status.
        if let Some(map) = event_map {
            if let Some(mapped) = map.get(&self.event) {
                if let Some(status) = canonical_status(mapped) {
                    return status;
                }
            }
        }
        // 2. Raw event already matches a canonical name.
        if let Some(status) = canonical_status(&self.event) {
            return status;
        }
        // 3. Unknown event → log and fall back to Unknown.
        eprintln!(
            "warning: unknown agent event '{}' from {}, mapping to Unknown",
            self.event, self.agent_id
        );
        AgentStatus::Unknown
    }
}

/// State for the inline name/rename prompt.
#[derive(Debug, Clone)]
pub struct NamePromptState {
    pub input: String,
    pub default_name: String,
    /// Label shown before the input (e.g. "Name" or "Rename").
    pub label: &'static str,
}

/// Phases of the inter-agent message relay state machine.
///
/// Flow: MessagePrompt → Extracting → DeliveryPending → (deliver or cancel).
/// Triggered by `s` (relay last message) or `S` (prompt for count).
#[derive(Debug, Clone)]
pub enum RelayPhase {
    /// User pressed S, entering message count (1-9).
    MessagePrompt { input: String },
    /// Async extraction from transcript in progress.
    Extracting {
        source_agent_id: String,
        source_agent_name: String,
        message_count: usize,
    },
    /// Extracted messages ready for delivery to target.
    DeliveryPending {
        source_agent_name: String,
        captured_text: String,
        message_count: usize,
    },
}

#[derive(Debug, Clone)]
pub struct RelayState {
    pub phase: RelayPhase,
    pub source_index: usize,
}

/// Which step the wizard is currently on.
///
/// Note: `Provider` selects an env-var bundle (Anthropic vs Vertex vs Z.ai
/// vs ...) — distinct from `SandboxLevel`, which selects the isolation
/// posture (paranoid/normal/permissive). The two axes are independent;
/// users can run e.g. `paranoid + zai`. See gh#81.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WizardStep {
    AgentType,
    SandboxBackend,
    SandboxLevel,
    /// Selected before `Name` (#167) so the directory basename can seed the
    /// default agent name (e.g. `myPrj-1`).
    ProjectDir,
    Name,
    /// Pick the provider env-var bundle (was `Profile` pre-#81).
    Provider,
    Confirm,
}

/// Sub-UI mode for the ProjectDir wizard step (#127).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProjectDirMode {
    /// Navigable list of recent project dirs with filter-as-you-type.
    List,
    /// Free-text path input (legacy behavior; reached via `i`, or used
    /// automatically when there are no recents yet).
    Input,
}

/// Case-insensitive match used by the project-dir picker filter: a hit is
/// either a substring match or an in-order subsequence match (so `snptc`
/// matches `synoptic`). Both `haystack` and `needle` must be lowercased by
/// the caller.
pub fn project_dir_filter_matches(haystack: &str, needle: &str) -> bool {
    if needle.is_empty() {
        return true;
    }
    if haystack.contains(needle) {
        return true;
    }
    // Fuzzy fallback: every needle char appears in order in the haystack —
    // e.g. "sntp" matches "synoptic". Advancing a single shared iterator keeps
    // the match strictly in-order.
    let mut chars = haystack.chars();
    needle.chars().all(|nc| chars.any(|hc| hc == nc))
}

/// State for the multi-step "New Agent" wizard.
#[derive(Debug, Clone)]
pub struct WizardState {
    pub step: WizardStep,
    /// Available *base* agent names (deduplicated by `agent_type_base_name`),
    /// e.g. `[("claude", "Claude Code"), ("codex", "OpenAI Codex")]`. Sandbox
    /// variant suffixes (`-unsandboxed`, `-paranoid`, ...) are folded out — the
    /// wizard's SandboxBackend / SandboxLevel steps recover that information.
    pub available_agent_types: Vec<(String, String)>,
    /// Currently selected base agent index.
    pub agent_type_index: usize,
    /// Available sandbox backends for the selected agent type. Includes
    /// `SandboxBackend::None` when an `<base>-unsandboxed` entry exists.
    pub available_sandbox_backends: Vec<crate::sandbox_backend::SandboxBackend>,
    /// Currently selected sandbox backend index in `available_sandbox_backends`.
    pub sandbox_backend_index: usize,
    /// Available sandbox levels for the selected agent type (e.g. ["paranoid","normal","permissive"]).
    /// May include custom levels discovered from the filesystem (e.g. "strict").
    /// Empty for unsandboxed agents or legacy entries with no sandbox_level field.
    pub available_sandbox_levels: Vec<String>,
    /// Currently selected sandbox level index in `available_sandbox_levels`.
    pub sandbox_level_index: usize,
    pub name: String,
    /// Auto-generated default name shown when the user leaves name empty (e.g. "claude-3").
    pub default_name: String,
    /// Available providers (env-var bundles) discovered from sandbox config.
    /// Was `available_profiles` pre-#81.
    pub available_providers: Vec<String>,
    /// Currently selected provider index in `available_providers`.
    /// Was `profile_index` pre-#81.
    pub provider_index: usize,
    pub project_dir: String,
    /// Tab-completion suggestions for the project directory.
    pub completions: Vec<String>,
    /// Currently highlighted completion index (if any).
    pub completion_index: Option<usize>,
    /// Validation error for the Project dir step. Set when Enter is
    /// pressed on ProjectDir with an invalid value (empty, tilde-prefixed,
    /// or not absolute); rendered as a red line below the input by
    /// `render_wizard`. Cleared as soon as the user edits the field or
    /// the value becomes valid.
    pub project_dir_error: Option<String>,
    /// True while `project_dir` holds an un-edited pre-fill from the selected
    /// agent (#168). The first Backspace clears the field instead of navigating
    /// to the previous step; any keystroke or completion clears the flag.
    /// Only meaningful in Input mode (#127).
    pub project_dir_suggested: bool,
    /// Recent project dirs (most-recently-used first) offered by the picker.
    /// Seeded from the global recents store when the wizard opens (#127).
    pub available_project_dirs: Vec<String>,
    /// Highlighted index into the *filtered* recents list (List mode).
    pub project_dir_index: usize,
    /// Filter text typed in List mode (substring / subsequence, case-insensitive).
    pub project_dir_filter: String,
    /// Whether the ProjectDir step shows the recents list or the free-text input.
    pub project_dir_mode: ProjectDirMode,
}

impl WizardState {
    /// Whether there are multiple base agent types to choose from.
    pub fn has_agent_types(&self) -> bool {
        self.available_agent_types.len() > 1
    }

    /// Return the selected *base* agent name (e.g. "claude"). Combine with
    /// `selected_sandbox_backend()` to derive the effective agent_type.
    pub fn selected_base_agent(&self) -> &str {
        self.available_agent_types
            .get(self.agent_type_index)
            .map(|(key, _)| key.as_str())
            .unwrap_or(crate::config::DEFAULT_AGENT_TYPE)
    }

    /// Resolve the effective `agent_type` config key for spawn:
    /// - `<base>-unsandboxed` when backend is `None`
    /// - `<base>` otherwise (canonical sandboxed entry)
    pub fn effective_agent_type(&self) -> String {
        let base = self.selected_base_agent();
        if matches!(
            self.selected_sandbox_backend(),
            Some(crate::sandbox_backend::SandboxBackend::None)
        ) {
            format!("{}-unsandboxed", base)
        } else {
            base.to_string()
        }
    }

    /// Whether there are multiple sandbox backends to choose from.
    pub fn has_sandbox_backends(&self) -> bool {
        self.available_sandbox_backends.len() > 1
    }

    /// Return the currently selected sandbox backend, or None if no backends available.
    pub fn selected_sandbox_backend(&self) -> Option<crate::sandbox_backend::SandboxBackend> {
        self.available_sandbox_backends.get(self.sandbox_backend_index).cloned()
    }

    /// Whether there are sandbox levels to choose from in the wizard.
    /// A single-option list is treated as "no choice" so the step is skipped —
    /// the lone level still applies, just without a useless one-row picker
    /// (see gh#91 shells, which pin `sandbox_levels = ["normal"]`).
    pub fn has_sandbox_levels(&self) -> bool {
        self.available_sandbox_levels.len() > 1
    }

    /// Return the currently selected sandbox level, or None if no levels available.
    pub fn selected_sandbox_level(&self) -> Option<&str> {
        self.available_sandbox_levels.get(self.sandbox_level_index).map(|s| s.as_str())
    }

    /// Recent project dirs matching the current List-mode filter, preserving
    /// most-recently-used order. Empty filter → all recents (#127).
    pub fn filtered_project_dirs(&self) -> Vec<&str> {
        let needle = self.project_dir_filter.trim().to_lowercase();
        self.available_project_dirs
            .iter()
            .filter(|d| project_dir_filter_matches(&d.to_lowercase(), &needle))
            .map(|s| s.as_str())
            .collect()
    }

    /// Build the ordered list of active wizard steps, applying skip rules.
    /// Used by the renderer for the step counter and by key handlers for
    /// computing prev/next steps without nested `if` arithmetic.
    pub fn active_steps(&self) -> Vec<WizardStep> {
        let mut steps = Vec::with_capacity(7);
        if self.has_agent_types() {
            steps.push(WizardStep::AgentType);
        }
        if self.has_sandbox_backends() {
            steps.push(WizardStep::SandboxBackend);
        }
        if self.has_sandbox_levels() && !self.is_unsandboxed_choice() {
            steps.push(WizardStep::SandboxLevel);
        }
        // #167: ProjectDir precedes Name so the directory basename can seed the
        // default name shown on the Name step.
        steps.push(WizardStep::ProjectDir);
        steps.push(WizardStep::Name);
        if self.has_providers() {
            steps.push(WizardStep::Provider);
        }
        steps.push(WizardStep::Confirm);
        steps
    }

    /// Whether the user has currently selected the "no sandbox" backend.
    pub fn is_unsandboxed_choice(&self) -> bool {
        matches!(
            self.selected_sandbox_backend(),
            Some(crate::sandbox_backend::SandboxBackend::None)
        )
    }

    /// Step that should follow the current one (or `None` if at end).
    pub fn next_step(&self) -> Option<WizardStep> {
        let steps = self.active_steps();
        let idx = steps.iter().position(|s| s == &self.step)?;
        steps.get(idx + 1).cloned()
    }

    /// Step that precedes the current one (or `None` if at start).
    pub fn prev_step(&self) -> Option<WizardStep> {
        let steps = self.active_steps();
        let idx = steps.iter().position(|s| s == &self.step)?;
        if idx == 0 {
            None
        } else {
            steps.get(idx - 1).cloned()
        }
    }

    /// Whether there are selectable providers (env-var bundles).
    pub fn has_providers(&self) -> bool {
        !self.available_providers.is_empty()
    }

    /// Clear any pending tab-completion state.
    pub fn clear_completions(&mut self) {
        self.completions.clear();
        self.completion_index = None;
    }

    /// Return the selected provider name, or None if no providers are available.
    /// Was `selected_profile()` pre-#81.
    pub fn selected_provider(&self) -> Option<&str> {
        self.available_providers.get(self.provider_index).map(|s| s.as_str())
    }
}

/// Enforced-boundary summary from the per-launch effective-policy record
/// (#221, design config-v2 §4.3.1): `lince config resolve --json` is the
/// REQUESTED view; this is the ENFORCED view, parsed from the
/// `<id>.policy.json` agent-sandbox writes next to the `.state` files.
#[derive(Debug, Clone, PartialEq, serde::Deserialize)]
pub struct EnforcedPolicy {
    #[serde(default)]
    pub backend: String,
    #[serde(default)]
    pub fs_enforced: bool,
    #[serde(default)]
    pub net_enforced: bool,
    #[serde(default)]
    pub net_limitation: Option<String>,
    #[serde(default)]
    pub degraded_reason: Option<String>,
    /// True when an [experimental] hatch (raw_bwrap_args / seatbelt_extra) is
    /// active for this launch (#210): the boundary may be widened in ways the
    /// mechanism layer can't attest, so fs/net ticks must NOT be trusted as a
    /// clean "fully enforced" result.
    #[serde(default)]
    pub policy_overridden: bool,
    #[serde(default)]
    pub experimental: Vec<String>,
}

impl EnforcedPolicy {
    /// Fully enforced ONLY when both axes hold AND no experimental override is
    /// in force (an override voids the validated-policy guarantee, §2.5).
    pub fn fully_enforced(&self) -> bool {
        self.fs_enforced && self.net_enforced && !self.policy_overridden
    }

    /// Compact badge: which boundary the kernel actually enforced. An active
    /// [experimental] override appends a custom-policy marker (#210) so a
    /// widened boundary never reads as a clean fs✓ net✓.
    pub fn badge(&self) -> String {
        let tick = |ok: bool| if ok { "\u{2713}" } else { "\u{2717}" };
        let base = format!("fs{} net{}", tick(self.fs_enforced), tick(self.net_enforced));
        if self.policy_overridden {
            format!("{} \u{26a0}custom", base)
        } else {
            base
        }
    }
}

#[derive(Debug, Clone)]
pub struct AgentInfo {
    pub id: String,
    pub name: String,
    pub agent_type: String,
    /// Provider env-var bundle name selected at spawn time (was `profile`
    /// pre-#81). Distinct from `sandbox_level`, which is the isolation posture.
    pub provider: Option<String>,
    pub project_dir: String,
    pub status: AgentStatus,
    pub pane_id: Option<u32>,
    pub started_at: Option<u64>,
    pub last_error: Option<String>,
    pub exit_code: Option<i32>,
    pub group: Option<String>,
    /// Last event string read by poll_status_files(), used for change detection.
    pub last_polled_event: Option<String>,
    /// Runtime-selected sandbox isolation level (wizard choice or saved state).
    /// None for unsandboxed agents or legacy agents spawned without the wizard.
    pub sandbox_level: Option<String>,
    /// Runtime-selected sandbox backend (wizard choice or saved state).
    /// None means use the agent type's TOML-pinned `sandbox_backend`.
    pub sandbox_backend: Option<crate::sandbox_backend::SandboxBackend>,
    pub transcript_path: Option<String>,
    /// Per-instance marker glyph (#166), claimed first-free from
    /// `[dashboard].instance_icons` at spawn (a distinctive emoji by default).
    /// Shown in the pane title and the dashboard list. Empty when the pool is
    /// empty. Runtime-only — not persisted to the state file (the spawn path
    /// re-derives it on restore).
    pub icon: String,
    /// Effective-policy record for this launch (#221). None until the
    /// `.policy.json` written by agent-sandbox is polled. Runtime-only —
    /// re-read from disk after a restore.
    pub enforced: Option<EnforcedPolicy>,
}

impl AgentInfo {
    /// Status label with exit code annotation for stopped agents.
    pub fn status_display(&self) -> String {
        if self.status == AgentStatus::Stopped {
            match self.exit_code {
                Some(code) => format!("Stopped ({code})"),
                None => "Stopped".to_string(),
            }
        } else {
            self.status.label().to_string()
        }
    }
}

// ── Save/Restore Types ───────────────────────────────────────────────

/// Persistable subset of AgentInfo for save-and-quit.
///
/// LINCE-119: `tokens_in`/`tokens_out` removed alongside the rich telemetry
/// fields in `AgentInfo`. Old `.lince-dashboard` files that still emit those
/// keys load fine — serde silently ignores unknown fields by default — and
/// every remaining field is `#[serde(default)]` so missing keys never panic.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SavedAgentInfo {
    #[serde(default)]
    pub name: String,
    /// Agent type key referencing AgentTypeConfig in config. Defaults to DEFAULT_AGENT_TYPE for v1 compat.
    #[serde(default = "default_agent_type")]
    pub agent_type: String,
    /// Provider env-var bundle name. `serde(alias = "profile")` keeps
    /// pre-#81 `.lince-dashboard` files loadable.
    #[serde(default, alias = "profile")]
    pub provider: Option<String>,
    #[serde(default)]
    pub project_dir: String,
    #[serde(default)]
    pub group: Option<String>,
    /// Runtime sandbox level selected at spawn time. None for older state files (backward compat).
    #[serde(default)]
    pub sandbox_level: Option<String>,
    /// Runtime sandbox backend selected at spawn time. None for older state files (backward compat).
    #[serde(default)]
    pub sandbox_backend: Option<crate::sandbox_backend::SandboxBackend>,
}

fn default_agent_type() -> String {
    crate::config::DEFAULT_AGENT_TYPE.to_string()
}

impl From<&AgentInfo> for SavedAgentInfo {
    fn from(a: &AgentInfo) -> Self {
        Self {
            name: a.name.clone(),
            agent_type: a.agent_type.clone(),
            provider: a.provider.clone(),
            project_dir: a.project_dir.clone(),
            group: a.group.clone(),
            sandbox_level: a.sandbox_level.clone(),
            sandbox_backend: a.sandbox_backend.clone(),
        }
    }
}

/// Per-project session defaults captured by the `N` wizard's `!` confirm
/// shortcut (gh#62). Persisted in `.lince-dashboard` alongside open agents
/// and reapplied to the `n` quick-spawn shortcut. `None` means: fall back to
/// `[dashboard].default_agent_type` / `default_provider` / `default_project_dir`.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SessionDefaults {
    /// Effective agent type key (e.g. `"claude"` or `"claude-unsandboxed"`).
    pub agent_type: String,
    pub provider: Option<String>,
    pub project_dir: String,
    pub sandbox_level: Option<String>,
    pub sandbox_backend: Option<crate::sandbox_backend::SandboxBackend>,
}

/// Persisted presentation, independent of the initial CLI preset.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StatusBarMode {
    Hidden,
    Summary,
    #[default]
    Full,
}
impl StatusBarMode {
    pub fn next(self) -> Self {
        match self { Self::Hidden => Self::Summary, Self::Summary => Self::Full, Self::Full => Self::Hidden }
    }
    pub fn visible(self) -> bool { self != Self::Hidden }
}
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SavedView {
    pub sidebar_visible: bool,
    pub statusbar_mode: StatusBarMode,
}

/// Top-level saved state written to `.lince-dashboard`.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SavedState {
    #[serde(default)]
    pub view: Option<SavedView>,
    pub version: u32,
    pub agents: Vec<SavedAgentInfo>,
    pub next_agent_id: u32,
    /// Per-project `n` quick-spawn defaults captured via wizard `!` (gh#62).
    /// Optional + serde-default so v2 state files load transparently.
    #[serde(default)]
    pub session_defaults: Option<SessionDefaults>,
}

// ── Tests ───────────────────────────────────────────────────────────
//
// LINCE-118: cover the simplified status machine. These tests exercise the
// pure functions in this module (no zellij host needed), so they run under
// the native target — `cargo test --target wasm32-wasip1` can't link the
// test harness inside the plugin sandbox.
#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn msg(event: &str) -> StatusMessage {
        StatusMessage {
            agent_id: "agent-1".to_string(),
            event: event.to_string(),
            timestamp: None,
            error: None,
            session_id: None,
            transcript_path: None,
        }
    }

    #[test]
    fn canonical_status_accepts_all_five_canonical_strings() {
        assert_eq!(canonical_status("unknown"), Some(AgentStatus::Unknown));
        assert_eq!(canonical_status("running"), Some(AgentStatus::Running));
        assert_eq!(canonical_status("input"), Some(AgentStatus::WaitingForInput));
        assert_eq!(canonical_status("permission"), Some(AgentStatus::PermissionRequired));
        assert_eq!(canonical_status("stopped"), Some(AgentStatus::Stopped));
    }

    #[test]
    fn canonical_status_rejects_legacy_aliases_and_garbage() {
        // Aliases dropped in LINCE-118 — must NOT resolve any more.
        assert_eq!(canonical_status("start"), None);
        assert_eq!(canonical_status("idle"), None);
        assert_eq!(canonical_status("waiting_for_input"), None);
        assert_eq!(canonical_status("permission_required"), None);
        // Unrelated junk.
        assert_eq!(canonical_status(""), None);
        assert_eq!(canonical_status("Running"), None); // case-sensitive
        assert_eq!(canonical_status("nonsense"), None);
    }

    #[test]
    fn to_agent_status_unknown_event_with_no_map_falls_back_to_unknown() {
        let m = msg("PreToolUse");
        assert_eq!(m.to_agent_status(None), AgentStatus::Unknown);
    }

    #[test]
    fn to_agent_status_empty_event_map_still_falls_back_to_unknown() {
        let m = msg("PreToolUse");
        let empty: HashMap<String, String> = HashMap::new();
        assert_eq!(m.to_agent_status(Some(&empty)), AgentStatus::Unknown);
    }

    #[test]
    fn to_agent_status_event_map_translates_to_canonical() {
        let mut map = HashMap::new();
        map.insert("PreToolUse".to_string(), "running".to_string());
        map.insert("Stop".to_string(), "stopped".to_string());
        map.insert("idle_prompt".to_string(), "input".to_string());
        map.insert("permission_prompt".to_string(), "permission".to_string());

        assert_eq!(msg("PreToolUse").to_agent_status(Some(&map)), AgentStatus::Running);
        assert_eq!(msg("Stop").to_agent_status(Some(&map)), AgentStatus::Stopped);
        assert_eq!(msg("idle_prompt").to_agent_status(Some(&map)), AgentStatus::WaitingForInput);
        assert_eq!(
            msg("permission_prompt").to_agent_status(Some(&map)),
            AgentStatus::PermissionRequired
        );
    }

    #[test]
    fn to_agent_status_event_map_with_bogus_canonical_falls_back_to_unknown() {
        // A misconfigured event_map pointing at a non-canonical value must NOT
        // silently coerce to Running (the old behaviour) — it has to surface
        // as Unknown so the operator sees the misconfig.
        let mut map = HashMap::new();
        map.insert("PreToolUse".to_string(), "kinda_running".to_string());
        assert_eq!(msg("PreToolUse").to_agent_status(Some(&map)), AgentStatus::Unknown);
    }

    #[test]
    fn to_agent_status_raw_canonical_event_resolves_without_map() {
        // If a hook already emits a canonical string verbatim (e.g. wrapper
        // writing "stopped" into the .state file), no event_map is required.
        assert_eq!(msg("running").to_agent_status(None), AgentStatus::Running);
        assert_eq!(msg("stopped").to_agent_status(None), AgentStatus::Stopped);
        assert_eq!(msg("input").to_agent_status(None), AgentStatus::WaitingForInput);
        assert_eq!(
            msg("permission").to_agent_status(None),
            AgentStatus::PermissionRequired
        );
        assert_eq!(msg("unknown").to_agent_status(None), AgentStatus::Unknown);
    }

    #[test]
    fn label_and_color_cover_all_five_variants() {
        // Smoke test: every variant has non-empty label + color, and Unknown
        // uses the spec'd "-" label / dim-gray color.
        for st in [
            AgentStatus::Unknown,
            AgentStatus::Running,
            AgentStatus::WaitingForInput,
            AgentStatus::PermissionRequired,
            AgentStatus::Stopped,
        ] {
            assert!(!st.label().is_empty());
            assert!(st.color().starts_with("\x1b["));
        }
        assert_eq!(AgentStatus::Unknown.label(), "-");
        assert_eq!(AgentStatus::Unknown.color(), "\x1b[90m");
    }

    // LINCE-123: extra coverage for rendering, status_display, and round-trip.

    #[test]
    fn status_labels_match_5_state_contract() {
        // Lock in the exact label strings the dashboard renders so a rename in
        // AgentStatus::label() would fail loudly. These strings are part of the
        // user-visible contract — changing them affects the UI and any docs
        // referencing them.
        assert_eq!(AgentStatus::Unknown.label(), "-");
        assert_eq!(AgentStatus::Running.label(), "Running");
        assert_eq!(AgentStatus::WaitingForInput.label(), "INPUT");
        assert_eq!(AgentStatus::PermissionRequired.label(), "PERMISSION");
        assert_eq!(AgentStatus::Stopped.label(), "Stopped");
    }

    #[test]
    fn status_colors_match_visual_contract() {
        // Lock in the ANSI escape sequences so visual styling stays stable.
        // Unknown=dim gray, Running=green, INPUT=bold yellow, PERMISSION=bold red, Stopped=dim.
        assert_eq!(AgentStatus::Unknown.color(), "\x1b[90m");
        assert_eq!(AgentStatus::Running.color(), "\x1b[32m");
        assert_eq!(AgentStatus::WaitingForInput.color(), "\x1b[1;33m");
        assert_eq!(AgentStatus::PermissionRequired.color(), "\x1b[1;31m");
        assert_eq!(AgentStatus::Stopped.color(), "\x1b[2m");
    }

    /// Effective-policy records (#221) arrive as single-line JSON written by
    /// agent-sandbox; unknown fields must be ignored, badge must reflect the
    /// enforced boundaries.
    #[test]
    fn enforced_policy_parses_record_json() {
        let json = r#"{"schema":1,"agent":"claude","agent_id":"claude-1",
            "backend":"bwrap","requested":{"level":"paranoid"},
            "landlock_abi":7,"fs_enforced":true,"net_enforced":true,
            "net_limitation":null,"bwrap_args_digest":"abc",
            "degraded_reason":null,"written_at":"2026-06-10T10:00:00+02:00"}"#;
        let p: EnforcedPolicy = serde_json::from_str(json).unwrap();
        assert!(p.fully_enforced());
        assert_eq!(p.backend, "bwrap");
        assert_eq!(p.badge(), "fs\u{2713} net\u{2713}");
    }

    #[test]
    fn enforced_policy_degraded_badge() {
        let json = r#"{"backend":"nono","fs_enforced":false,"net_enforced":false,
            "net_limitation":"unavailable","degraded_reason":"delegated to nono"}"#;
        let p: EnforcedPolicy = serde_json::from_str(json).unwrap();
        assert!(!p.fully_enforced());
        assert_eq!(p.badge(), "fs\u{2717} net\u{2717}");
        assert_eq!(p.degraded_reason.as_deref(), Some("delegated to nono"));
    }

    /// An [experimental] override (#210) voids the clean fully_enforced result
    /// even when both axes tick, and the badge shows a custom-policy marker.
    #[test]
    fn enforced_policy_experimental_override_voids_clean_result() {
        let json = r#"{"backend":"bwrap","fs_enforced":true,"net_enforced":true,
            "policy_overridden":true,"experimental":["raw_bwrap_args"]}"#;
        let p: EnforcedPolicy = serde_json::from_str(json).unwrap();
        assert!(!p.fully_enforced());
        assert!(p.badge().contains("custom"));
        assert_eq!(p.experimental, vec!["raw_bwrap_args".to_string()]);
    }

    fn make_agent(status: AgentStatus, exit_code: Option<i32>) -> AgentInfo {
        AgentInfo {
            id: "agent-1".to_string(),
            name: "test".to_string(),
            agent_type: "claude".to_string(),
            provider: None,
            project_dir: "/tmp".to_string(),
            status,
            pane_id: None,
            started_at: None,
            last_error: None,
            exit_code,
            group: None,
            last_polled_event: None,
            sandbox_level: None,
            sandbox_backend: None,
            transcript_path: None,
            enforced: None,
            icon: String::new(),
        }
    }

    #[test]
    fn status_display_stopped_with_exit_code() {
        // Stopped with explicit exit code: render "Stopped (N)".
        let a = make_agent(AgentStatus::Stopped, Some(0));
        assert_eq!(a.status_display(), "Stopped (0)");
        let b = make_agent(AgentStatus::Stopped, Some(137));
        assert_eq!(b.status_display(), "Stopped (137)");
        // Negative exit codes are valid (signals encoded as -N on some platforms).
        let c = make_agent(AgentStatus::Stopped, Some(-1));
        assert_eq!(c.status_display(), "Stopped (-1)");
    }

    #[test]
    fn status_display_stopped_without_exit_code() {
        // Stopped without exit code: bare "Stopped", no parens.
        let a = make_agent(AgentStatus::Stopped, None);
        assert_eq!(a.status_display(), "Stopped");
    }

    #[test]
    fn status_display_non_stopped_ignores_exit_code() {
        // Non-Stopped variants must use the plain label even if exit_code is set
        // (which shouldn't happen normally but mustn't break rendering).
        for st in [
            AgentStatus::Unknown,
            AgentStatus::Running,
            AgentStatus::WaitingForInput,
            AgentStatus::PermissionRequired,
        ] {
            let a = make_agent(st.clone(), Some(42));
            assert_eq!(a.status_display(), st.label().to_string());
        }
    }

    #[test]
    fn saved_agent_info_roundtrip_preserves_all_fields() {
        // Round-trip AgentInfo → SavedAgentInfo → JSON → SavedAgentInfo to
        // catch accidental field drops in From<&AgentInfo> or serde wiring.
        // The persistable subset is: name, agent_type, provider, project_dir,
        // group, sandbox_level, sandbox_backend.
        let agent = AgentInfo {
            id: "agent-7".to_string(), // not persisted
            name: "my-claude".to_string(),
            agent_type: "claude".to_string(),
            provider: Some("anthropic".to_string()),
            project_dir: "/home/me/project".to_string(),
            status: AgentStatus::Running, // not persisted (regenerated on restore)
            pane_id: Some(42),            // not persisted
            started_at: Some(123),        // not persisted
            last_error: None,
            exit_code: None,
            group: Some("eng".to_string()),
            last_polled_event: None,
            sandbox_level: Some("paranoid".to_string()),
            sandbox_backend: Some(crate::sandbox_backend::SandboxBackend::Nono),
            transcript_path: None,
            enforced: None,
            icon: String::new(), // not persisted
        };

        let saved: SavedAgentInfo = (&agent).into();
        assert_eq!(saved.name, "my-claude");
        assert_eq!(saved.agent_type, "claude");
        assert_eq!(saved.provider.as_deref(), Some("anthropic"));
        assert_eq!(saved.project_dir, "/home/me/project");
        assert_eq!(saved.group.as_deref(), Some("eng"));
        assert_eq!(saved.sandbox_level.as_deref(), Some("paranoid"));
        assert_eq!(saved.sandbox_backend, Some(crate::sandbox_backend::SandboxBackend::Nono));

        // Verify JSON round-trip is lossless for the persisted subset.
        let json = serde_json::to_string(&saved).expect("serialize");
        let back: SavedAgentInfo = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back.name, saved.name);
        assert_eq!(back.agent_type, saved.agent_type);
        assert_eq!(back.provider, saved.provider);
        assert_eq!(back.project_dir, saved.project_dir);
        assert_eq!(back.group, saved.group);
        assert_eq!(back.sandbox_level, saved.sandbox_level);
        assert_eq!(back.sandbox_backend, saved.sandbox_backend);
    }

    #[test]
    fn saved_agent_info_accepts_legacy_profile_alias() {
        // Pre-#81 state files used `profile` instead of `provider`. The
        // serde(alias = "profile") on `provider` must keep them loadable.
        let legacy = r#"{
            "name": "old-claude",
            "agent_type": "claude",
            "profile": "anthropic",
            "project_dir": "/x"
        }"#;
        let saved: SavedAgentInfo = serde_json::from_str(legacy).expect("legacy load");
        assert_eq!(saved.provider.as_deref(), Some("anthropic"));
        assert_eq!(saved.name, "old-claude");
    }

    #[test]
    fn saved_agent_info_tolerates_legacy_rich_fields() {
        // LINCE-119 dropped tokens_in/tokens_out from the schema. Old state
        // files that still carry those keys must load cleanly — serde silently
        // drops unknown fields by default, so this test pins that behaviour.
        let legacy_rich = r#"{
            "name": "rich-claude",
            "agent_type": "claude",
            "project_dir": "/x",
            "tokens_in": 1234,
            "tokens_out": 5678,
            "tool_name": "Edit"
        }"#;
        let saved: SavedAgentInfo = serde_json::from_str(legacy_rich).expect("rich load");
        assert_eq!(saved.name, "rich-claude");
        assert_eq!(saved.agent_type, "claude");
    }
}
