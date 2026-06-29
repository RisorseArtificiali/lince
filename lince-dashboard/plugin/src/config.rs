use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use crate::sandbox_backend::{BackendConfig, SandboxBackend};

/// Default agent type key used when no explicit type is specified.
pub const DEFAULT_AGENT_TYPE: &str = "claude";

/// Default sandbox command / pane title pattern fallback.
pub const DEFAULT_SANDBOX_COMMAND: &str = "agent-sandbox";

/// Configuration for a single agent type (e.g. "claude", "codex", "gemini").
///
/// Agent types are defined in `agents-defaults.toml` and can be overridden
/// by `[agents.<name>]` sections in the user's `config.toml`.
/// String keys only — no enum, fully data-driven.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentTypeConfig {
    /// Command template. Supports `{agent_id}`, `{project_dir}`, and the
    /// equivalent provider placeholders `{provider}` (canonical) /
    /// `{profile}` (legacy alias) — both expand to the selected provider name.
    pub command: Vec<String>,
    /// Pattern to match pane titles for reconciliation (e.g. "agent-sandbox").
    pub pane_title_pattern: String,
    /// Pipe name for receiving status messages (e.g. "claude-status").
    pub status_pipe_name: String,
    /// Full display name for the UI (e.g. "Claude Code").
    pub display_name: String,
    /// 3-char label for the table column header (e.g. "CLA").
    pub short_label: String,
    /// ANSI color name (e.g. "blue", "red", "cyan").
    pub color: String,
    /// Whether the agent runs inside the bwrap sandbox.
    pub sandboxed: bool,
    /// Environment variables to pass through to the agent process.
    #[serde(default)]
    pub env_vars: HashMap<String, String>,
    /// If true, agent has its own status hooks; if false, needs a wrapper.
    #[serde(default)]
    pub has_native_hooks: bool,
    /// Read-only bind mounts from $HOME (e.g. ["~/.claude/"]).
    #[serde(default)]
    pub home_ro_dirs: Vec<String>,
    /// Read-write bind mounts from $HOME (e.g. ["~/.local/share/codex/"]).
    #[serde(default)]
    pub home_rw_dirs: Vec<String>,
    /// Agent uses bwrap internally, conflicts with outer sandbox bwrap.
    #[serde(default)]
    pub bwrap_conflict: bool,
    /// Arguments to disable agent's own sandbox (e.g. ["--sandbox", "none"]).
    #[serde(default)]
    pub disable_inner_sandbox_args: Vec<String>,
    /// Custom mapping from agent event names to lince status strings.
    #[serde(default)]
    pub event_map: HashMap<String, String>,
    /// Providers (env-var bundles) applicable to this agent type.
    /// - `["__discover__"]` means use all auto-discovered providers (default
    ///   for sandboxed agents via agent-sandbox).
    /// - Empty or omitted means no providers (skip the wizard's Provider step).
    /// - An explicit list restricts the wizard to those provider names.
    ///
    /// Was `profiles` pre-#81 — the legacy spelling is still accepted via
    /// `serde(alias)` so existing user `agents-defaults.toml` files keep working.
    #[serde(default, alias = "profiles")]
    pub providers: Vec<String>,
    /// Sandbox backend used by this agent type.
    /// Overrides the global `[dashboard].sandbox_backend` setting.
    /// Defaults to `AgentSandbox` for backward compatibility.
    #[serde(default)]
    pub sandbox_backend: SandboxBackend,
    /// Sandbox isolation level for this agent type.
    ///
    /// Free-form profile suffix, **not a closed enum**: `paranoid` / `normal`
    /// / `permissive` are the shipped defaults; any other value resolves to a
    /// user-supplied profile (`lince-<agent>-<value>.json` for nono,
    /// `<agent>-<value>.toml` for agent-sandbox). See
    /// `docs/documentation/dashboard/sandbox-levels.md`.
    ///
    /// When `None`, the legacy static `command` template is used as-is.
    /// When `Some`, the plugin synthesizes the command from
    /// `(agent_type, sandbox_backend, sandbox_level)`.
    #[serde(default)]
    pub sandbox_level: Option<String>,
    /// Restrict the wizard's SandboxLevel picker to a fixed set instead of the
    /// shipped default trio (paranoid/normal/permissive). Empty = use defaults.
    /// Set to `["normal"]` for agents that have only one meaningful level
    /// (e.g. shells, gh#91); the SandboxLevel step is auto-skipped when only
    /// one option remains so the user never sees a single-choice picker.
    #[serde(default)]
    pub sandbox_levels: Vec<String>,
    /// Home directory sub-path used by the paranoid nono wrapper to rsync agent
    /// state into a scratch directory (e.g. ".claude", ".codex").
    /// Only relevant when `sandbox_backend = "nono"` and `sandbox_level = "paranoid"`.
    /// When empty/missing, paranoid mode skips the rsync step (agent starts with
    /// clean HOME — appropriate for stateless agents like shells).
    #[serde(default)]
    pub sandbox_home_subdir: Option<String>,
}

/// Agent pane layout mode.
///
/// - `Floating` (default): agents open as floating overlay panes.
/// - `Tiled`: agents open as tiled panes in the Zellij layout grid.
///   Use with `layouts/dashboard-tiled.kdl` for a fixed split.
#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum AgentLayout {
    Floating,
    Tiled,
}

impl Default for AgentLayout {
    fn default() -> Self {
        AgentLayout::Tiled
    }
}

impl AgentLayout {
    pub fn is_tiled(&self) -> bool {
        matches!(self, AgentLayout::Tiled)
    }
}

/// How to show the focused agent pane.
#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum FocusMode {
    Replace,
    Floating,
}

impl Default for FocusMode {
    fn default() -> Self {
        FocusMode::Floating
    }
}

/// How the plugin detects agent status changes.
#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum StatusMethod {
    Pipe,
    File,
}

impl Default for StatusMethod {
    fn default() -> Self {
        StatusMethod::Pipe
    }
}

fn default_sandbox_command() -> String {
    DEFAULT_SANDBOX_COMMAND.to_string()
}

fn default_paranoid_color() -> String {
    "green".to_string()
}
fn default_normal_color() -> String {
    "blue".to_string()
}
fn default_permissive_color() -> String {
    "yellow".to_string()
}
fn default_sandbox_default_color() -> String {
    "white".to_string()
}

/// Color mapping for sandbox isolation levels.
///
/// Drives both the per-pane title indicator and the wizard's profile-selection
/// step. ANSI color names (e.g. `"green"`, `"blue"`, `"magenta"`). Sandbox
/// levels other than the three built-ins fall back to `default`.
#[derive(Debug, Clone, Deserialize)]
pub struct SandboxColors {
    #[serde(default = "default_paranoid_color")]
    pub paranoid: String,
    #[serde(default = "default_normal_color")]
    pub normal: String,
    #[serde(default = "default_permissive_color")]
    pub permissive: String,
    #[serde(default = "default_sandbox_default_color")]
    pub default: String,
}

impl Default for SandboxColors {
    fn default() -> Self {
        Self {
            paranoid: default_paranoid_color(),
            normal: default_normal_color(),
            permissive: default_permissive_color(),
            default: default_sandbox_default_color(),
        }
    }
}

impl SandboxColors {
    /// Resolve the color name for a sandbox level. Custom levels return `default`.
    pub fn for_level(&self, level: &str) -> &str {
        match level {
            "paranoid" => &self.paranoid,
            "normal" => &self.normal,
            "permissive" => &self.permissive,
            _ => &self.default,
        }
    }
}

fn default_project_search_max_depth() -> usize {
    3
}

/// Default pool of distinct per-instance marker glyphs (#166).
///
/// Each spawned agent claims the first marker not already in use by a live
/// agent, giving instant visual disambiguation between panes — two `claude`
/// instances open at once get different markers. The SAME glyph is shown in the
/// pane title and in the dashboard list, so the list entry and the pane share
/// one identity.
///
/// Distinctive, easy-to-tell-apart emoji (a plugin cannot recolor a pane's
/// border/title — that color is theme-driven and global — so varied glyphs beat
/// near-identical colored squares for at-a-glance recognition). Avoids the
/// sandbox-level circles (🟢🔵🟡). Overridable via `[dashboard] instance_icons`;
/// an empty list disables instance markers.
fn default_instance_icons() -> Vec<String> {
    [
        "⭐", "⚡", "🔥", "🌙", "🍀", "🎯", "🌸", "🐢", "🦊", "🐙", "🌵", "🍁", "🎲", "🦋", "🌊",
        "🍄",
    ]
    .iter()
    .map(|s| s.to_string())
    .collect()
}


fn default_status_file_dir() -> String {
    "/tmp/lince-dashboard".to_string()
}

fn default_max_agents() -> usize {
    9
}

/// Parsed provider details from sandbox config (env vars to set/unset).
///
/// Each provider corresponds to a `[providers.<name>]` (canonical) or
/// legacy `[profiles.<name>]` table in `~/.agent-sandbox/config.toml`. See
/// gh#81 for the rename rationale.
#[derive(Debug, Clone, Default)]
pub struct ProviderDetails {
    /// Environment variables to set (from `[<...>.<name>.env]`).
    pub env: HashMap<String, String>,
    /// Environment variables to unset (from `[<...>.<name>.env_unset]`).
    pub env_unset: Vec<String>,
}

/// Main dashboard configuration, deserialized from the `[dashboard]` TOML table.
#[derive(Debug, Clone, Deserialize)]
pub struct DashboardConfig {
    /// Default provider (env-var bundle) name. Was `default_profile` pre-#81;
    /// the legacy spelling is still accepted as a serde alias.
    #[serde(default, alias = "default_profile")]
    pub default_provider: Option<String>,
    /// Per-agent-type provider names, keyed by agent base name (e.g. "claude",
    /// "codex"). Populated from `[providers.*]` / `[<agent>.providers.*]`
    /// (canonical) and the legacy `[profiles.*]` / `[<agent>.profiles.*]`
    /// sections in the sandbox config.
    #[serde(skip)]
    pub providers_by_agent: HashMap<String, Vec<String>>,
    /// Per-agent-type provider details (env vars), keyed by agent base name
    /// then provider name.
    #[serde(skip)]
    pub provider_details_by_agent: HashMap<String, HashMap<String, ProviderDetails>>,
    /// Path to the sandbox config. Since #202 provider discovery happens in
    /// `lince-config resolve` (which reads the canonical locations itself);
    /// the key is kept so existing configs keep validating.
    #[serde(default)]
    #[allow(dead_code)]
    pub sandbox_config_path: Option<String>,
    #[serde(default)]
    pub default_project_dir: Option<String>,
    /// Default agent type for the `n` shortcut and the `N` wizard's initial
    /// selection. Must match a key in `agent_types` (loaded from
    /// `agents-defaults.toml` + user overrides). Unknown values silently fall
    /// back to `DEFAULT_AGENT_TYPE` then to the first registered type.
    #[serde(default)]
    pub default_agent_type: Option<String>,
    #[serde(default = "default_sandbox_command")]
    pub sandbox_command: String,
    #[serde(default)]
    pub agent_layout: AgentLayout,
    #[serde(default)]
    pub focus_mode: FocusMode,
    // Retained for config back-compat (existing configs may set
    // `status_method = "file"`), but no longer drives behavior: the dashboard
    // always polls the .state files now (the pipe is a best-effort fast-path
    // that can't cross the agent sandbox boundary). See the Timer handler.
    #[serde(default)]
    #[allow(dead_code)]
    pub status_method: StatusMethod,
    #[serde(default = "default_status_file_dir")]
    pub status_file_dir: String,
    #[serde(default = "default_max_agents")]
    pub max_agents: usize,
    /// Agent type configurations keyed by type name (e.g. "claude", "codex").
    /// Loaded asynchronously from `agents-defaults.toml`, then merged with
    /// any `[agents.<name>]` sections from the user's `config.toml`.
    #[serde(default)]
    pub agent_types: HashMap<String, AgentTypeConfig>,
    /// Global sandbox backend preference (parsed from config, not yet wired to resolution).
    #[allow(dead_code)]
    #[serde(default)]
    pub sandbox_backend: BackendConfig,
    /// Color mapping for sandbox isolation levels (`paranoid` / `normal` /
    /// `permissive` / fallback). Configurable via `[dashboard.sandbox_colors]`
    /// in `~/.config/lince-dashboard/config.toml`.
    #[serde(default)]
    pub sandbox_colors: SandboxColors,
    /// Root directories scanned recursively when the wizard's Project dir
    /// Tab-completion receives a bare name (no `/` or `~/` prefix). Enables
    /// zoxide-like UX: `syn` + Tab finds `<root>/Personal/synoptic` anywhere
    /// inside any configured root. Empty list = legacy glob in launch_dir.
    #[serde(default)]
    pub project_search_roots: Vec<String>,
    /// Maximum depth (passed to `find -maxdepth`) when scanning
    /// `project_search_roots`. Default 3 covers typical category-level
    /// nesting (e.g. `Projects/Personal/<proj>`, `Projects/Work/<client>/<repo>`).
    #[serde(default = "default_project_search_max_depth")]
    pub project_search_max_depth: usize,
    /// Pool of distinct per-instance marker glyphs (first-free) for visual pane
    /// identification (#166). Each live agent claims one (a distinctive emoji by
    /// default); it appears in the pane title and as the matching marker in the
    /// dashboard list. Overridable via `[dashboard] instance_icons`; empty
    /// disables instance markers.
    #[serde(default = "default_instance_icons")]
    pub instance_icons: Vec<String>,
    /// Custom sandbox levels discovered from the filesystem, keyed by
    /// `<backend>:<base>` (e.g. `"nono:claude"` or `"agent-sandbox:claude"`).
    /// Populated from the `levels_by_backend` field of `lince-config
    /// resolve --json` (#202; the resolver does the filesystem discovery
    /// the plugin's shell globs used to do). Combined with the shipped
    /// `paranoid`/`normal`/`permissive` defaults by `supported_sandbox_levels()`.
    #[serde(skip)]
    pub discovered_sandbox_levels: HashMap<String, Vec<String>>,
}

impl Default for DashboardConfig {
    fn default() -> Self {
        DashboardConfig {
            default_provider: None,
            providers_by_agent: HashMap::new(),
            provider_details_by_agent: HashMap::new(),
            sandbox_config_path: None,
            default_project_dir: None,
            default_agent_type: None,
            sandbox_command: default_sandbox_command(),
            agent_layout: AgentLayout::default(),
            focus_mode: FocusMode::default(),
            status_method: StatusMethod::default(),
            status_file_dir: default_status_file_dir(),
            max_agents: default_max_agents(),
            agent_types: HashMap::new(),
            sandbox_backend: BackendConfig::default(),
            sandbox_colors: SandboxColors::default(),
            project_search_roots: Vec::new(),
            project_search_max_depth: default_project_search_max_depth(),
            instance_icons: default_instance_icons(),
            discovered_sandbox_levels: HashMap::new(),
        }
    }
}

/// Wrapper matching the TOML file structure with a `[dashboard]` section.
#[derive(Deserialize)]
struct DashboardConfigFile {
    #[serde(default)]
    dashboard: DashboardConfig,
}

/// Current Unix timestamp in seconds, or 0 if unavailable (e.g. WASM).
pub fn now_secs() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// Expand leading `~` to the value of `$HOME`.
pub fn expand_tilde(path: &str) -> String {
    if let Some(rest) = path.strip_prefix('~') {
        if let Ok(home) = std::env::var("HOME") {
            return format!("{}{}", home, rest);
        }
    }
    path.to_string()
}

/// Collapse `$HOME` prefix back to `~` (inverse of `expand_tilde`).
pub fn collapse_tilde(path: &str) -> String {
    if let Ok(home) = std::env::var("HOME") {
        if !home.is_empty() && path.starts_with(&home) {
            return format!("~{}", &path[home.len()..]);
        }
    }
    path.to_string()
}

/// Convert a path that may start with `~` into a shell expression using `$HOME`.
/// Used for `run_command` scripts since the WASI sandbox lacks `$HOME` in its env.
pub fn shell_path_expr(path: &str) -> String {
    if let Some(rest) = path.strip_prefix('~') {
        format!("\"$HOME{}\"", shell_escape(rest))
    } else {
        format!("'{}'", shell_escape(path))
    }
}

/// Resolve a path-completer match against the launch directory.
///
/// The legacy glob completer (used when no project roots are configured) runs
/// in the plugin host's launch CWD and emits bare relative names like
/// `synoptic`; the multi-root `find` emits absolute paths. Written to
/// `project_dir` verbatim, a relative match is rejected by the absolute-path
/// validation at the ProjectDir step — see #125. Prefix relative matches with
/// `launch_dir` so every candidate is absolute; already-absolute and
/// `~`-prefixed matches are location-independent and pass through unchanged.
/// With no known launch dir there is nothing to resolve against, so the match
/// is returned as-is.
pub fn absolutize_under(launch_dir: Option<&str>, path: &str) -> String {
    if path.starts_with('/') || path.starts_with('~') {
        return path.to_string();
    }
    match launch_dir {
        Some(base) if !base.is_empty() => format!("{}/{}", base.trim_end_matches('/'), path),
        _ => path.to_string(),
    }
}

/// Find the longest common prefix among a list of strings.
/// Returns an empty string if the list is empty.
/// Handles multi-byte UTF-8 correctly by snapping to char boundaries.
pub fn common_prefix(items: &[String]) -> String {
    if items.is_empty() {
        return String::new();
    }
    let first = items[0].as_bytes();
    let mut prefix_len = first.len();
    for item in &items[1..] {
        let bytes = item.as_bytes();
        prefix_len = prefix_len.min(bytes.len());
        for i in 0..prefix_len {
            if first[i] != bytes[i] {
                prefix_len = i;
                break;
            }
        }
    }
    // Snap back to a valid UTF-8 char boundary.
    while prefix_len > 0 && !items[0].is_char_boundary(prefix_len) {
        prefix_len -= 1;
    }
    items[0][..prefix_len].to_string()
}

/// Context key for identifying RunCommandResult callbacks (shared with state_file).
pub const CMD_TYPE_KEY: &str = "type";
/// Command type for the async `lince-config resolve --json` call (#202) —
/// the single source for agent types, providers, and sandbox levels.
/// Replaces the former `discover_providers` / `load_agent_defaults` /
/// `discover_sandbox_levels` TOML-parsing pipeline.
pub const CMD_RESOLVE_CONFIG: &str = "resolve_config";

/// Run a command with a typed context map. Wraps the common
/// BTreeMap + `run_command` boilerplate used across modules.
pub fn run_typed_command(args: &[&str], cmd_type: &str) {
    run_typed_command_with(args, cmd_type, &[]);
}

/// Run a command with a typed context map plus extra key-value pairs.
pub fn run_typed_command_with(args: &[&str], cmd_type: &str, extra: &[(&str, &str)]) {
    use std::collections::BTreeMap;
    use zellij_tile::prelude::run_command;

    let mut ctx = BTreeMap::new();
    ctx.insert(CMD_TYPE_KEY.to_string(), cmd_type.to_string());
    for &(k, v) in extra {
        ctx.insert(k.to_string(), v.to_string());
    }
    run_command(args, ctx);
}

/// Command type for async path tab-completion via `run_command`.
pub const CMD_PATH_COMPLETE: &str = "path_complete";

/// Command type for async polling of per-agent `.state` status files.
pub const CMD_POLL_STATUS: &str = "poll_status";

/// Kick off async polling of the per-agent `.state` files.
///
/// WASI plugins have a virtualized filesystem — `std::fs` cannot see the
/// host's `/tmp`, so the old `poll_status_files()` using `std::fs::read_to_string`
/// silently read nothing. Read the files through a host `cat` via
/// `run_command`, the same channel every other host-filesystem access in
/// this plugin uses. Output is one `<basename>\t<event>` line per `.state`
/// file (basename without the `.state` suffix); results arrive in
/// `Event::RunCommandResult` with context `type=poll_status`.
pub fn poll_status_files_async(status_dir: &str) {
    let dir = shell_escape(status_dir);
    // Two line shapes share one poll (one fork per tick, not two):
    //   `<basename>\t<event>`            — agent status from .state files
    //   `POLICY\t<id>\t<json>`           — effective-policy record (#221)
    //                                      from <id>.policy.json
    let script = format!(
        "for f in '{dir}'/*.state; do [ -f \"$f\" ] || continue; \
         printf '%s\\t%s\\n' \"$(basename \"$f\" .state)\" \
         \"$(tr -d '\\n' < \"$f\" 2>/dev/null)\"; done; \
         for f in '{dir}'/*.policy.json; do [ -f \"$f\" ] || continue; \
         printf 'POLICY\\t%s\\t%s\\n' \"$(basename \"$f\" .policy.json)\" \
         \"$(tr -d '\\n' < \"$f\" 2>/dev/null)\"; done",
        dir = dir
    );
    run_typed_command(&["sh", "-c", &script], CMD_POLL_STATUS);
}

/// Command type for async transcript extraction for the relay feature.
pub const CMD_EXTRACT_TRANSCRIPT: &str = "extract_transcript";

/// Kick off async extraction of the last N conversation messages from a
/// Claude Code JSONL transcript file. Results arrive in
/// `Event::RunCommandResult` with context `type=extract_transcript`.
///
/// Uses python3 (guaranteed present — Claude Code requires it) because
/// JSONL with nested content arrays is awkward in jq but trivial in Python.
pub fn extract_transcript_async(
    source_agent_id: &str,
    transcript_path: &str,
    message_count: usize,
) {
    let path = shell_escape(transcript_path);
    let count = message_count;
    let script = format!(
        r#"python3 -c "
import json, sys
msgs = []
for line in open('{path}'):
    line = line.strip()
    if not line: continue
    try: d = json.loads(line)
    except: continue
    t = d.get('type','')
    if t not in ('user','assistant'): continue
    content = d.get('message',{{}}).get('content',[])
    texts = [c['text'].strip() for c in content if isinstance(c,dict) and c.get('type')=='text' and c.get('text','').strip()]
    if texts:
        role = 'User' if t == 'user' else 'Assistant'
        msgs.append('[' + role + ']: ' + ' '.join(texts))
for m in msgs[-{count}:]:
    print(m)
    print()
" 2>/dev/null || echo '[error] python3 extraction failed'"#,
        path = path,
        count = count,
    );
    run_typed_command_with(
        &["sh", "-c", &script],
        CMD_EXTRACT_TRANSCRIPT,
        &[
            ("source_agent_id", source_agent_id),
            ("message_count", &message_count.to_string()),
        ],
    );
}

/// Escape a string for use inside single quotes in a shell command.
pub fn shell_escape(s: &str) -> String {
    s.replace('\'', "'\\''")
}

/// Kick off the async `lince-config resolve --json` call (#202).
///
/// The resolver is the single resolution point (design config-v2 §4.3): it
/// merges registry.d, the legacy sandbox/dashboard user configs (dual-read
/// window) or `~/.config/lince/lince.toml`, the project overlay, and the
/// filesystem-discovered custom sandbox levels — so this plugin no longer
/// parses any sandbox-owned TOML. Result arrives in
/// `Event::RunCommandResult` with context `type=resolve_config` and is
/// applied by `apply_resolved_view`.
pub fn resolve_config_async(launch_dir: Option<&str>) {
    // PATH inside the Zellij host shell may not include ~/.local/bin —
    // prefer the PATH lookup, fall back to the canonical install location.
    let mut script = String::from(
        "LC=\"$(command -v lince-config || echo \"$HOME/.local/bin/lince-config\")\"; \
         \"$LC\" resolve --json",
    );
    if let Some(dir) = launch_dir {
        script.push_str(&format!(" --project '{}'", shell_escape(dir)));
    }
    run_typed_command(&["sh", "-c", &script], CMD_RESOLVE_CONFIG);
}

/// The resolve --json contract (design config-v2 §4.3), reduced to the fields
/// this plugin consumes. Unknown fields are ignored (forward compat); every
/// field is defaulted so partial output degrades instead of failing.
#[derive(Deserialize)]
pub struct ResolvedView {
    /// "default-deny", or "void:<key>" when an [experimental] hatch is
    /// active (I5). Not yet rendered — the #221 effective-policy badge
    /// consumes it.
    #[serde(default)]
    #[allow(dead_code)]
    pub guarantee: String,
    #[serde(default)]
    pub providers: HashMap<String, ResolvedProvider>,
    #[serde(default)]
    pub agents: HashMap<String, ResolvedAgent>,
    #[serde(default)]
    pub warnings: Vec<String>,
}

/// Provider entry: env-var NAMES (secret values are redacted to `$NAME`
/// self-references by the resolver — I4; the spawn path skips those and the
/// value is inherited from the host environment).
#[derive(Deserialize, Default)]
pub struct ResolvedProvider {
    #[serde(default)]
    pub env: HashMap<String, String>,
    #[serde(default)]
    pub env_unset: Vec<String>,
    /// Whether any of the provider's env names is set in the host env.
    /// Informational for now (wizard filtering is a follow-up).
    #[serde(default)]
    #[allow(dead_code)]
    pub available: bool,
}

#[derive(Deserialize, Default)]
pub struct ResolvedAgentDashboard {
    #[serde(default)]
    pub pane_title_pattern: String,
    #[serde(default)]
    pub status_pipe_name: String,
    #[serde(default)]
    pub has_native_hooks: bool,
}

#[derive(Deserialize, Default)]
pub struct ResolvedVariant {
    #[serde(default)]
    pub command: Vec<String>,
    #[serde(default)]
    pub pane_title_pattern: String,
    #[serde(default)]
    pub status_pipe_name: String,
    #[serde(default)]
    pub display_name: String,
    #[serde(default)]
    pub short_label: String,
    #[serde(default)]
    pub color: String,
    #[serde(default)]
    pub has_native_hooks: bool,
    #[serde(default)]
    pub providers: Vec<String>,
    #[serde(default)]
    pub env: HashMap<String, String>,
    #[serde(default)]
    pub event_map: HashMap<String, String>,
    #[serde(default)]
    pub bwrap_conflict: bool,
}

#[derive(Deserialize)]
pub struct ResolvedAgent {
    #[serde(default)]
    pub display_name: String,
    #[serde(default)]
    pub short_label: String,
    #[serde(default)]
    pub color: String,
    #[serde(default)]
    pub backend: String,
    #[serde(default)]
    pub level: Option<String>,
    #[serde(default)]
    pub levels_by_backend: HashMap<String, Vec<String>>,
    #[serde(default)]
    pub allowed_levels: Vec<String>,
    #[serde(default)]
    pub providers: Vec<String>,
    #[serde(default)]
    pub providers_available: Vec<String>,
    #[serde(default)]
    pub command: Vec<String>,
    #[serde(default)]
    pub env: HashMap<String, String>,
    #[serde(default)]
    pub event_map: HashMap<String, String>,
    #[serde(default)]
    pub bwrap_conflict: bool,
    #[serde(default)]
    pub disable_inner_sandbox_args: Vec<String>,
    #[serde(default)]
    pub home_subdir: String,
    #[serde(default)]
    pub dashboard: ResolvedAgentDashboard,
    #[serde(default)]
    pub variants: HashMap<String, ResolvedVariant>,
}

fn backend_from_str(s: &str) -> SandboxBackend {
    match s {
        "seatbelt" | "sandbox-exec" => SandboxBackend::Seatbelt,
        "nono" => SandboxBackend::Nono,
        // "bwrap" / "agent-sandbox" / "auto" / anything unknown
        _ => SandboxBackend::AgentSandbox,
    }
}

const SHIPPED_LEVELS: [&str; 3] = ["paranoid", "normal", "permissive"];

/// Apply a `lince-config resolve --json` payload to the dashboard config:
/// agent types (base + derived variants), per-agent providers + details,
/// and the per-backend custom sandbox-level cache. Returns the resolver
/// warnings on success.
pub fn apply_resolved_view(
    config: &mut DashboardConfig,
    json_text: &str,
) -> Result<Vec<String>, String> {
    let view: ResolvedView = serde_json::from_str(json_text.trim())
        .map_err(|e| format!("resolve JSON parse error: {}", e))?;
    if view.agents.is_empty() {
        return Err("resolve returned no agents".to_string());
    }

    let mut agent_types: HashMap<String, AgentTypeConfig> = HashMap::new();
    let mut providers_by_agent: HashMap<String, Vec<String>> = HashMap::new();
    let mut details_by_agent: HashMap<String, HashMap<String, ProviderDetails>> = HashMap::new();
    let mut discovered: HashMap<String, Vec<String>> = HashMap::new();

    for (name, agent) in &view.agents {
        agent_types.insert(
            name.clone(),
            AgentTypeConfig {
                command: agent.command.clone(),
                pane_title_pattern: if agent.dashboard.pane_title_pattern.is_empty() {
                    DEFAULT_SANDBOX_COMMAND.to_string()
                } else {
                    agent.dashboard.pane_title_pattern.clone()
                },
                status_pipe_name: agent.dashboard.status_pipe_name.clone(),
                display_name: agent.display_name.clone(),
                short_label: agent.short_label.clone(),
                color: agent.color.clone(),
                sandboxed: true,
                env_vars: agent.env.clone(),
                has_native_hooks: agent.dashboard.has_native_hooks,
                home_ro_dirs: Vec::new(),
                home_rw_dirs: Vec::new(),
                bwrap_conflict: agent.bwrap_conflict,
                disable_inner_sandbox_args: agent.disable_inner_sandbox_args.clone(),
                event_map: agent.event_map.clone(),
                providers: agent.providers.clone(),
                sandbox_backend: backend_from_str(&agent.backend),
                sandbox_level: agent.level.clone(),
                sandbox_levels: agent.allowed_levels.clone(),
                sandbox_home_subdir: if agent.home_subdir.is_empty() {
                    None
                } else {
                    Some(agent.home_subdir.clone())
                },
            },
        );
        for (variant, v) in &agent.variants {
            agent_types.insert(
                format!("{}-{}", name, variant),
                AgentTypeConfig {
                    command: v.command.clone(),
                    pane_title_pattern: v.pane_title_pattern.clone(),
                    status_pipe_name: v.status_pipe_name.clone(),
                    display_name: v.display_name.clone(),
                    short_label: v.short_label.clone(),
                    color: v.color.clone(),
                    sandboxed: false,
                    env_vars: v.env.clone(),
                    has_native_hooks: v.has_native_hooks,
                    home_ro_dirs: Vec::new(),
                    home_rw_dirs: Vec::new(),
                    bwrap_conflict: v.bwrap_conflict,
                    disable_inner_sandbox_args: Vec::new(),
                    event_map: v.event_map.clone(),
                    providers: v.providers.clone(),
                    sandbox_backend: SandboxBackend::None,
                    sandbox_level: None,
                    sandbox_levels: Vec::new(),
                    sandbox_home_subdir: None,
                },
            );
        }
        if !agent.providers_available.is_empty() {
            providers_by_agent.insert(name.clone(), agent.providers_available.clone());
            let details = details_by_agent.entry(name.clone()).or_default();
            for pname in &agent.providers_available {
                if let Some(p) = view.providers.get(pname) {
                    details.insert(
                        pname.clone(),
                        ProviderDetails {
                            env: p.env.clone(),
                            env_unset: p.env_unset.clone(),
                        },
                    );
                }
            }
        }
        // Per-backend custom levels (extras beyond the shipped trio) feed the
        // same cache the filesystem globs used to populate.
        for (backend_key, levels) in &agent.levels_by_backend {
            let extras: Vec<String> = levels
                .iter()
                .filter(|l| !SHIPPED_LEVELS.contains(&l.as_str()))
                .cloned()
                .collect();
            if !extras.is_empty() {
                discovered.insert(format!("{}:{}", backend_key, name), extras);
            }
        }
    }

    config.agent_types = agent_types;
    config.providers_by_agent = providers_by_agent;
    config.provider_details_by_agent = details_by_agent;
    config.discovered_sandbox_levels = discovered;
    Ok(view.warnings)
}

/// TOML wrapper for user config.toml `[agents.<name>]` sections.
#[derive(Deserialize, Default)]
struct UserAgentsSection {
    #[serde(default)]
    agents: HashMap<String, AgentTypeConfig>,
}

/// Parse agent type definitions from `[agents.<name>]` TOML content.
///
/// Since #202 the live agent types come from `lince-config resolve --json`
/// (`apply_resolved_view`); this parser remains only for the compiled-in
/// shipped defaults (`embedded_agent_types` / `embedded_event_maps` fallback,
/// #198) and tests. Input is up to two NUL-separated chunks; entries in the
/// second chunk fully replace same-named entries from the first.
pub fn parse_agent_defaults(stdout: &[u8]) -> HashMap<String, AgentTypeConfig> {
    let chunks: Vec<&[u8]> = stdout.split(|&b| b == 0).collect();

    // Parse defaults file (chunk 0) — uses [agents.<name>] structure.
    let mut agent_types: HashMap<String, AgentTypeConfig> = if let Some(chunk) = chunks.first() {
        let content = String::from_utf8_lossy(chunk);
        match toml::from_str::<UserAgentsSection>(content.trim()) {
            Ok(s) => s.agents,
            Err(_) => HashMap::new(),
        }
    } else {
        HashMap::new()
    };

    // Parse user overrides from config.toml (chunk 1) — also [agents.<name>].
    if let Some(chunk) = chunks.get(1) {
        let content = String::from_utf8_lossy(chunk);
        if let Ok(user) = toml::from_str::<UserAgentsSection>(content.trim()) {
            for (key, val) in user.agents {
                agent_types.insert(key, val);
            }
        }
    }

    agent_types
}

/// Kick off async path tab-completion for the wizard project directory.
///
/// Lists directories matching `partial*` (with tilde expansion). Results
/// arrive in `Event::RunCommandResult` with context `type=path_complete`.
///
/// - If `partial` ends with `/`, lists subdirectories inside that directory.
/// - Otherwise, lists directories whose names start with `partial`.
/// Maximum number of completion results returned by the shell.
const MAX_COMPLETIONS: usize = 50;

pub fn complete_path_async(partial: &str, roots: &[String], max_depth: usize) {
    let trimmed = partial.trim();

    // Dispatch by input shape:
    //  - Absolute or tilde-prefixed → legacy glob at that exact prefix
    //    (power users typing a specific path keep the familiar behavior).
    //  - Bare name + configured roots → recursive find across roots
    //    (zoxide-like: `syn` finds `<root>/.../synoptic` anywhere).
    //  - Bare name + no roots → fallback to legacy glob in launch_dir CWD.
    //  - Empty → no-op (avoids unbounded scan on accidental Tab).
    let script = if trimmed.is_empty() {
        // Empty stdout → handler will treat as "no matches", state unchanged.
        "true".to_string()
    } else if trimmed.starts_with('/') || trimmed.starts_with('~') {
        let prefix_expr = shell_path_expr(trimmed);
        format!(
            "for d in {}*/; do [ -d \"$d\" ] && echo \"$d\"; done 2>/dev/null | head -n {}",
            prefix_expr,
            MAX_COMPLETIONS
        )
    } else if roots.is_empty() {
        // Legacy: glob in the shell's CWD (= plugin host's launch_dir).
        let prefix_expr = shell_path_expr(trimmed);
        format!(
            "for d in {}*/; do [ -d \"$d\" ] && echo \"$d\"; done 2>/dev/null | head -n {}",
            prefix_expr,
            MAX_COMPLETIONS
        )
    } else {
        // Recursive multi-root scan. Build one `find` per root; output is
        // a list of absolute paths (since roots are absolute). Common noisy
        // subtrees are pruned to keep latency low on large homes.
        let depth = max_depth.max(1);
        let pattern = shell_escape(&format!("{}*", trimmed));
        let mut cmd = String::from("{\n");
        for root in roots {
            // Each root is wrapped in single quotes; shell_escape handles any
            // internal apostrophe. Tilde inside roots is expanded via $HOME
            // (consistent with shell_path_expr).
            let root_expr = shell_path_expr(root);
            cmd.push_str(&format!(
                "    find {root} -maxdepth {depth} -mindepth 1 -type d \\
        -name '{pattern}' \\
        -not -path '*/node_modules/*' \\
        -not -path '*/.git/*' \\
        -not -path '*/.cache/*' \\
        -not -path '*/target/*' 2>/dev/null\n",
                root = root_expr,
                depth = depth,
                pattern = pattern,
            ));
        }
        cmd.push_str(&format!("}} | sort -u | head -n {}\n", MAX_COMPLETIONS));
        cmd
    };

    // Store the request prefix so the handler can detect stale results.
    run_typed_command_with(
        &["sh", "-c", &script],
        CMD_PATH_COMPLETE,
        &[("prefix", partial)],
    );
}

impl DashboardConfig {
    /// Load configuration from a TOML file at `path`.
    ///
    /// Returns `(config, error)` where `error` is `Some(msg)` if reading or
    /// parsing failed (in which case `config` holds all defaults).
    ///
    /// Agent types and providers arrive asynchronously via
    /// `resolve_config_async()` (#202) after the plugin has permissions and
    /// knows the launch directory.
    ///
    /// # Manual testing
    ///
    /// 1. Place a valid `config.toml` next to the plugin WASM and pass
    ///    `config_path "/path/to/config.toml"` in the Zellij layout KDL.
    /// 2. Verify the plugin loads without warnings in the status bar.
    /// 3. Introduce a syntax error in the TOML and reload — a yellow
    ///    warning line should appear in the dashboard render output.
    /// 4. Remove the file entirely — plugin should start with defaults.
    /// Parse config from TOML string content. Used by async config loading
    /// (run_command cat) since std::fs is unavailable in WASI sandbox.
    pub fn parse_toml(content: &str) -> (Self, Option<String>) {
        match toml::from_str::<DashboardConfigFile>(content.trim()) {
            Ok(file) => (file.dashboard, None),
            Err(e) => (
                DashboardConfig::default(),
                Some(format!("Config parse error: {}", e)),
            ),
        }
    }


    /// Resolve the effective provider list for a given agent type.
    ///
    /// - If the agent type has `providers = ["__discover__"]`, returns
    ///   discovered providers for the agent's base name (e.g. "claude", "codex").
    /// - If the agent type has an explicit list, returns the intersection with
    ///   discovered providers (so unknown names are silently filtered).
    /// - If the agent type has no providers (empty), returns an empty list.
    pub fn providers_for_agent_type(&self, agent_type: &str) -> Vec<String> {
        let cfg = match self.agent_types.get(agent_type) {
            Some(c) => c,
            None => return Vec::new(),
        };
        if cfg.providers.is_empty() {
            return Vec::new();
        }
        let base = crate::agent::agent_type_base_name(agent_type);
        let discovered = self.providers_by_agent.get(base);
        if cfg.providers.len() == 1 && cfg.providers[0] == "__discover__" {
            return discovered.cloned().unwrap_or_default();
        }
        // Explicit list: intersect with discovered providers for validation
        let disc = discovered.cloned().unwrap_or_default();
        cfg.providers
            .iter()
            .filter(|p| disc.contains(p))
            .cloned()
            .collect()
    }

    /// Return the supported sandbox levels for a given agent type and backend.
    ///
    /// Combines the shipped defaults (`paranoid`, `normal`, `permissive`) with
    /// custom levels discovered by the resolver (see
    /// `resolve_config_async()` / `apply_resolved_view()`). The standard order is preserved;
    /// custom levels are appended in alphabetical order. Duplicates are
    /// removed.
    ///
    /// Returns an empty vec for unsandboxed agents or when the agent type has
    /// no `sandbox_level` field — the wizard uses that as the skip signal.
    /// `backend == None` returns just the standard defaults (no per-backend
    /// custom merge), used when the backend hasn't been picked yet.
    pub fn supported_sandbox_levels(
        &self,
        agent_type: &str,
        backend: Option<&crate::sandbox_backend::SandboxBackend>,
    ) -> Vec<String> {
        let cfg = match self.agent_types.get(agent_type) {
            Some(c) => c,
            None => return Vec::new(),
        };
        if !cfg.sandboxed || cfg.sandbox_level.is_none() {
            return Vec::new();
        }
        // Per-agent override: a non-empty `sandbox_levels` replaces the shipped
        // trio. Custom-level discovery is intentionally skipped here — agents
        // that opt in (e.g. shells, gh#91) want a fixed set, not surprise
        // additions from `~/.agent-sandbox/profiles/`.
        if !cfg.sandbox_levels.is_empty() {
            return cfg.sandbox_levels.clone();
        }
        let mut levels: Vec<String> = vec![
            "paranoid".to_string(),
            "normal".to_string(),
            "permissive".to_string(),
        ];
        if let Some(b) = backend {
            // Cache key MUST match the backend key that `apply_resolved_view`
            // stores ("agent-sandbox:" / "nono:") — NOT `display_name()`, which
            // returns "bwrap" for AgentSandbox and would silently miss the cache.
            // `None` has no custom-profile concept (no fs lookup), so skip.
            use crate::sandbox_backend::SandboxBackend;
            let backend_key = match b {
                SandboxBackend::AgentSandbox => "agent-sandbox",
                SandboxBackend::Seatbelt => return levels,
                SandboxBackend::Nono => "nono",
                SandboxBackend::None => return levels,
            };
            let base = crate::agent::agent_type_base_name(agent_type);
            let key = format!("{}:{}", backend_key, base);
            if let Some(custom) = self.discovered_sandbox_levels.get(&key) {
                let mut extras: Vec<String> = custom
                    .iter()
                    .filter(|l| !levels.iter().any(|s| s == *l))
                    .cloned()
                    .collect();
                extras.sort();
                levels.extend(extras);
            }
        }
        levels
    }

    /// Enumerate unique *base* agent names with display names, sorted alphabetically.
    /// Variants like `<base>-unsandboxed` / `<base>-paranoid` collapse into one
    /// entry per base — the wizard recovers backend / level via subsequent steps.
    ///
    /// Display name preference: canonical sandboxed entry's `display_name` first,
    /// then fall back to the unsandboxed variant with `" (unsandboxed)"` stripped,
    /// finally to the bare base name.
    pub fn base_agents(&self) -> Vec<(String, String)> {
        use std::collections::BTreeSet;
        let mut bases: BTreeSet<String> = BTreeSet::new();
        for key in self.agent_types.keys() {
            bases.insert(crate::agent::agent_type_base_name(key).to_string());
        }
        bases
            .into_iter()
            .map(|base| {
                let display = if let Some(cfg) = self.agent_types.get(&base) {
                    cfg.display_name.clone()
                } else if let Some(cfg) = self.agent_types.get(&format!("{}-unsandboxed", base)) {
                    cfg.display_name.replace(" (unsandboxed)", "")
                } else {
                    base.clone()
                };
                (base, display)
            })
            .collect()
    }

    /// Return the available sandbox backends for a base agent on this host.
    ///
    /// - When detection has completed: include only backends actually installed.
    /// - When detection is pending (`detected = None`): fall back to the agent's
    ///   TOML-pinned `sandbox_backend` only, so the wizard never offers a
    ///   non-existent backend during the boot race. The wizard refreshes its
    ///   list when `CMD_DETECT_BACKEND` resolves (see `main.rs` event handler).
    /// - `None` is included whenever a `<base>-unsandboxed` entry exists,
    ///   independent of detection state (no host check needed for "no sandbox").
    pub fn available_backends_for_base(
        &self,
        base: &str,
        detected: Option<&crate::sandbox_backend::DetectedBackends>,
    ) -> Vec<crate::sandbox_backend::SandboxBackend> {
        use crate::sandbox_backend::SandboxBackend;
        let mut out = Vec::with_capacity(3);
        let has_sandboxed = self.agent_types.get(base).map_or(false, |c| c.sandboxed);
        let has_unsandboxed = self
            .agent_types
            .get(&format!("{}-unsandboxed", base))
            .map_or(false, |c| !c.sandboxed);
        if has_sandboxed {
            match detected {
                Some(d) => {
                    if d.has_agent_sandbox {
                        out.push(SandboxBackend::AgentSandbox);
                    }
                    if d.has_nono {
                        out.push(SandboxBackend::Nono);
                    }
                    if d.has_seatbelt {
                        out.push(SandboxBackend::Seatbelt);
                    }
                }
                None => {
                    if let Some(cfg) = self.agent_types.get(base) {
                        out.push(cfg.sandbox_backend.clone());
                    }
                }
            }
        }
        if has_unsandboxed {
            out.push(SandboxBackend::None);
        }
        out
    }

    /// Resolve the index of the preferred default backend for a base agent.
    /// Preference order: TOML-pinned `sandbox_backend` on the canonical entry,
    /// then first available (which is OS-aware via detection).
    pub fn default_backend_index_for_base(
        &self,
        base: &str,
        available: &[crate::sandbox_backend::SandboxBackend],
    ) -> usize {
        if let Some(cfg) = self.agent_types.get(base) {
            if let Some(idx) = available.iter().position(|b| b == &cfg.sandbox_backend) {
                return idx;
            }
        }
        0
    }

    /// Look up provider details for a given agent type and provider name.
    pub fn provider_details_for(&self, agent_type: &str, provider_name: &str) -> Option<&ProviderDetails> {
        let base = crate::agent::agent_type_base_name(agent_type);
        self.provider_details_by_agent
            .get(base)
            .and_then(|m| m.get(provider_name))
    }

    /// Return the event_map for a given agent type, or None if empty/missing.
    ///
    /// Resolution order:
    /// 1. The on-disk config's map for this exact agent type (when non-empty).
    /// 2. The binary-embedded shipped defaults (exact agent type, then base
    ///    name).
    ///
    /// The embedded fallback exists because `agents-defaults.toml` is shipped
    /// defaults, but `update.sh` *preserves* a pre-existing on-disk copy (it
    /// never overwrites it once present). Users who first installed before
    /// LINCE-122 added `event_map` therefore keep an event_map-less file across
    /// updates, which left every native hook event mapping to `Unknown` and
    /// froze the Status column at "-". Falling back to the compiled-in defaults
    /// keeps status working for the built-in agents no matter how stale the
    /// on-disk file is, while still letting a non-empty on-disk map override.
    pub fn event_map_for(&self, agent_type: &str) -> Option<&HashMap<String, String>> {
        if let Some(m) = self
            .agent_types
            .get(agent_type)
            .map(|c| &c.event_map)
            .filter(|m| !m.is_empty())
        {
            return Some(m);
        }

        let embedded = embedded_event_maps();
        if let Some(m) = embedded.get(agent_type).filter(|m| !m.is_empty()) {
            return Some(m);
        }
        let base = crate::agent::agent_type_base_name(agent_type);
        embedded.get(base).filter(|m| !m.is_empty())
    }
}

/// Full agent-type definitions for the built-in agents, parsed once from the
/// shipped `agents-defaults.toml` baked into the binary at compile time.
/// Last-resort fallback (#198 precedent) when `lince-config resolve --json`
/// is unavailable or fails — the dashboard stays usable with shipped
/// defaults instead of an empty agent picker.
pub fn embedded_agent_types() -> &'static HashMap<String, AgentTypeConfig> {
    static TYPES: std::sync::OnceLock<HashMap<String, AgentTypeConfig>> =
        std::sync::OnceLock::new();
    TYPES.get_or_init(|| {
        const SHIPPED: &str = include_str!("../../agents-defaults.toml");
        parse_agent_defaults(SHIPPED.as_bytes())
    })
}

/// Event maps for the built-in agents, parsed once from the shipped
/// `agents-defaults.toml` baked into the binary at compile time. Used as a
/// fallback by `event_map_for` so a stale or partial on-disk config can't
/// break the status column for built-in agents. See `event_map_for`.
fn embedded_event_maps() -> &'static HashMap<String, HashMap<String, String>> {
    static MAPS: std::sync::OnceLock<HashMap<String, HashMap<String, String>>> =
        std::sync::OnceLock::new();
    MAPS.get_or_init(|| {
        const SHIPPED: &str = include_str!("../../agents-defaults.toml");
        match toml::from_str::<UserAgentsSection>(SHIPPED) {
            Ok(s) => s
                .agents
                .into_iter()
                .map(|(k, v)| (k, v.event_map))
                .collect(),
            Err(_) => HashMap::new(),
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// #125: the legacy glob completer emits bare relative names; they must be
    /// resolved against the launch dir before reaching `project_dir`.
    #[test]
    fn absolutize_under_prefixes_relative_matches() {
        assert_eq!(
            absolutize_under(Some("/home/u/work"), "synoptic"),
            "/home/u/work/synoptic"
        );
        // A trailing slash on the base must not double up.
        assert_eq!(
            absolutize_under(Some("/home/u/work/"), "synoptic"),
            "/home/u/work/synoptic"
        );
    }

    /// Absolute (multi-root `find`) and `~`-prefixed matches are already
    /// location-independent and must pass through untouched — in particular
    /// `~/api` must not become `<launch>/~/api`.
    #[test]
    fn absolutize_under_passes_through_absolute_and_tilde() {
        assert_eq!(
            absolutize_under(Some("/home/u/work"), "/srv/projects/api"),
            "/srv/projects/api"
        );
        assert_eq!(absolutize_under(Some("/home/u/work"), "~/api"), "~/api");
    }

    /// With no usable launch dir there is nothing to resolve against, so the
    /// match is returned unchanged rather than guessed at.
    #[test]
    fn absolutize_under_without_launch_dir_is_noop() {
        assert_eq!(absolutize_under(None, "synoptic"), "synoptic");
        assert_eq!(absolutize_under(Some(""), "synoptic"), "synoptic");
    }

    /// Pre-#81 `agents-defaults.toml` files used `profiles = [...]`. The
    /// rename added `#[serde(alias = "profiles")]` on `AgentTypeConfig.providers`
    /// so legacy files keep working without the user editing them.
    #[test]
    fn legacy_profiles_field_in_agent_defaults_loads() {
        let toml_text = r#"
            [agents.claude]
            command = ["claude"]
            pane_title_pattern = "claude"
            status_pipe_name = "claude-status"
            display_name = "Claude"
            short_label = "CLA"
            color = "blue"
            sandboxed = true
            profiles = ["__discover__"]
        "#;
        let parsed = parse_agent_defaults(toml_text.as_bytes());
        let claude = parsed.get("claude").expect("claude should parse");
        assert_eq!(claude.providers, vec!["__discover__"]);
    }

    /// A full resolve --json payload maps onto the plugin structures: base +
    /// variant agent types, per-agent providers with details, and the
    /// per-backend custom-level cache. (Provider precedence itself is the
    /// Python resolver's job now — covered by scripts/tests/test_resolve.py.)
    #[test]
    fn apply_resolved_view_populates_config() {
        let json = r#"{
            "guarantee": "default-deny",
            "providers": {
                "zai": {
                    "env": {"ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
                             "ANTHROPIC_API_KEY": "$ANTHROPIC_API_KEY"},
                    "env_unset": ["CLAUDE_CODE_OAUTH_TOKEN"],
                    "available": true
                }
            },
            "agents": {
                "claude": {
                    "display_name": "Claude Code",
                    "short_label": "CLA",
                    "color": "blue",
                    "backend": "bwrap",
                    "level": "paranoid",
                    "levels_by_backend": {
                        "agent-sandbox": ["paranoid", "normal", "permissive", "strict"],
                        "nono": ["paranoid", "normal", "permissive"]
                    },
                    "allowed_levels": [],
                    "providers": ["__discover__"],
                    "providers_available": ["zai"],
                    "command": ["agent-sandbox", "run", "-p", "{project_dir}",
                                 "--id", "{agent_id}", "--agent", "claude"],
                    "env": {},
                    "event_map": {"Stop": "input"},
                    "bwrap_conflict": false,
                    "disable_inner_sandbox_args": [],
                    "home_subdir": ".claude",
                    "dashboard": {"pane_title_pattern": "agent-sandbox",
                                   "status_pipe_name": "claude-status",
                                   "has_native_hooks": true},
                    "variants": {
                        "unsandboxed": {
                            "command": ["claude"],
                            "pane_title_pattern": "claude",
                            "status_pipe_name": "claude-status",
                            "display_name": "Claude Code (unsandboxed)",
                            "short_label": "CLU",
                            "color": "red",
                            "has_native_hooks": true,
                            "providers": ["__discover__"],
                            "env": {},
                            "event_map": {"Stop": "input"},
                            "bwrap_conflict": false
                        }
                    }
                }
            },
            "warnings": []
        }"#;
        let mut cfg = DashboardConfig::parse_toml("[dashboard]\n").0;
        let warnings = apply_resolved_view(&mut cfg, json).expect("apply should succeed");
        assert!(warnings.is_empty());
        let claude = cfg.agent_types.get("claude").expect("claude type");
        assert!(claude.sandboxed);
        assert_eq!(claude.sandbox_level.as_deref(), Some("paranoid"));
        assert_eq!(claude.status_pipe_name, "claude-status");
        assert_eq!(claude.sandbox_home_subdir.as_deref(), Some(".claude"));
        assert!(matches!(claude.sandbox_backend, SandboxBackend::AgentSandbox));
        let clu = cfg.agent_types.get("claude-unsandboxed").expect("variant type");
        assert!(!clu.sandboxed);
        assert_eq!(clu.command, vec!["claude"]);
        assert_eq!(clu.short_label, "CLU");
        // provider plumbing
        assert_eq!(cfg.providers_by_agent.get("claude").unwrap(), &vec!["zai".to_string()]);
        let details = cfg.provider_details_by_agent.get("claude").unwrap();
        assert_eq!(details.get("zai").unwrap().env_unset, vec!["CLAUDE_CODE_OAUTH_TOKEN"]);
        // secrets arrive as $NAME self-refs only (I4) — spawn path skips them
        assert_eq!(
            details.get("zai").unwrap().env.get("ANTHROPIC_API_KEY").map(String::as_str),
            Some("$ANTHROPIC_API_KEY"),
        );
        // custom-level cache: only the extras beyond the shipped trio
        assert_eq!(
            cfg.discovered_sandbox_levels.get("agent-sandbox:claude").unwrap(),
            &vec!["strict".to_string()],
        );
        assert!(cfg.discovered_sandbox_levels.get("nono:claude").is_none());
    }

    /// An empty / malformed resolve payload must fail loudly so the caller
    /// can fall back to the embedded shipped defaults.
    #[test]
    fn apply_resolved_view_rejects_empty_and_malformed() {
        let mut cfg = DashboardConfig::parse_toml("[dashboard]\n").0;
        assert!(apply_resolved_view(&mut cfg, "{}").is_err());
        assert!(apply_resolved_view(&mut cfg, "not json").is_err());
    }

    /// The compiled-in fallback parses to a non-empty agent set with event
    /// maps (the dashboard must stay usable without lince-config installed).
    #[test]
    fn embedded_agent_types_nonempty() {
        let types = embedded_agent_types();
        assert!(types.contains_key("claude"));
        assert!(types.contains_key("claude-unsandboxed"));
        assert!(!types.get("claude").unwrap().event_map.is_empty());
    }

    /// `default_agent_type` (gh#62) round-trips through TOML so the `n`
    /// shortcut + `N` wizard can pick it up from the user's config.
    #[test]
    fn dashboard_config_parses_default_agent_type() {
        let toml_text = r#"
            [dashboard]
            default_agent_type = "codex"
        "#;
        let (cfg, err) = DashboardConfig::parse_toml(toml_text);
        assert!(err.is_none(), "parse error: {err:?}");
        assert_eq!(cfg.default_agent_type.as_deref(), Some("codex"));
    }

    /// Absent `default_agent_type` must deserialize to `None`, preserving the
    /// pre-#62 behaviour for users who never touched the field.
    #[test]
    fn dashboard_config_default_agent_type_absent_is_none() {
        let (cfg, err) = DashboardConfig::parse_toml("[dashboard]\n");
        assert!(err.is_none(), "parse error: {err:?}");
        assert!(cfg.default_agent_type.is_none());
    }

    /// Verify that an unknown agent type (e.g. "zai") parses with
    /// sandbox_home_subdir and that the config-driven fallback works.
    #[test]
    fn unknown_agent_type_with_sandbox_home_subdir_parses() {
        let toml_text = r#"
[agents.custom-agent]
command = ["custom-agent", "--flag"]
pane_title_pattern = "custom-agent"
status_pipe_name = "custom-status"
display_name = "Custom Agent"
short_label = "CST"
color = "green"
sandboxed = true
has_native_hooks = true
providers = ["__discover__"]
sandbox_level = "normal"
sandbox_backend = "nono"
sandbox_home_subdir = ".custom-agent"
"#;
        let parsed: UserAgentsSection = toml::from_str(toml_text).unwrap();
        let cfg = parsed.agents.get("custom-agent").unwrap();
        assert_eq!(cfg.command, vec!["custom-agent", "--flag"]);
        assert_eq!(cfg.sandbox_level.as_deref(), Some("normal"));
        assert_eq!(cfg.sandbox_home_subdir.as_deref(), Some(".custom-agent"));
        assert!(matches!(cfg.sandbox_backend, SandboxBackend::Nono));
    }

    /// Verify that sandbox_home_subdir defaults to None when omitted.
    #[test]
    fn sandbox_home_subdir_defaults_to_none() {
        let toml_text = r#"
[agents.claude]
command = ["claude"]
pane_title_pattern = "claude"
status_pipe_name = "claude-status"
display_name = "Claude Code"
short_label = "CLA"
color = "blue"
sandboxed = true
"#;
        let parsed: UserAgentsSection = toml::from_str(toml_text).unwrap();
        let cfg = parsed.agents.get("claude").unwrap();
        assert!(cfg.sandbox_home_subdir.is_none());
    }

    /// Verify that parse_agent_defaults gracefully handles malformed TOML
    /// (the unwrap→match fix) instead of silently returning an empty map.
    #[test]
    fn parse_agent_defaults_malformed_toml_returns_empty() {
        let malformed = b"this is not valid toml [[[";
        let result = parse_agent_defaults(malformed);
        assert!(result.is_empty());
    }

    /// The binary-embedded shipped defaults must carry event maps for the
    /// built-in agents so `event_map_for` can fall back to them.
    #[test]
    fn embedded_event_maps_cover_builtin_agents() {
        let maps = embedded_event_maps();
        for agent in ["claude", "codex", "pi", "opencode"] {
            assert!(
                maps.get(agent).map(|m| !m.is_empty()).unwrap_or(false),
                "embedded event_map missing for built-in agent {agent}"
            );
        }
        // Claude's full native→canonical mapping must be present.
        let claude = &maps["claude"];
        assert_eq!(claude.get("PreToolUse").map(String::as_str), Some("running"));
        assert_eq!(claude.get("Stop").map(String::as_str), Some("input"));
        assert_eq!(
            claude.get("permission_prompt").map(String::as_str),
            Some("permission")
        );
    }

    /// A stale on-disk config (claude entry with an empty event_map) must still
    /// resolve via the embedded fallback — this is the Status-column fix.
    #[test]
    fn event_map_for_falls_back_to_embedded_when_config_empty() {
        let mut cfg = DashboardConfig::default();
        cfg.agent_types = parse_agent_defaults(
            br#"
            [agents.claude]
            command = ["claude"]
            pane_title_pattern = "claude"
            status_pipe_name = "claude-status"
            display_name = "Claude"
            short_label = "CLA"
            color = "blue"
            sandboxed = true
            "#,
        );
        // The stale entry has no event_map...
        assert!(cfg.agent_types["claude"].event_map.is_empty());
        // ...but event_map_for resolves it from the embedded defaults.
        let resolved = cfg.event_map_for("claude").expect("fallback map");
        assert_eq!(resolved.get("PreToolUse").map(String::as_str), Some("running"));

        // A sandbox variant (suffix stripped by agent_type_base_name) with no
        // embedded entry of its own resolves to the base agent's map.
        let resolved_variant = cfg.event_map_for("claude-paranoid").expect("base fallback");
        assert_eq!(resolved_variant.get("Stop").map(String::as_str), Some("input"));
    }

    /// A non-empty on-disk map still wins over the embedded fallback.
    #[test]
    fn event_map_for_prefers_config_over_embedded() {
        let mut cfg = DashboardConfig::default();
        cfg.agent_types = parse_agent_defaults(
            br#"
            [agents.claude]
            command = ["claude"]
            pane_title_pattern = "claude"
            status_pipe_name = "claude-status"
            display_name = "Claude"
            short_label = "CLA"
            color = "blue"
            sandboxed = true
            [agents.claude.event_map]
            PreToolUse = "stopped"
            "#,
        );
        let resolved = cfg.event_map_for("claude").expect("config map");
        assert_eq!(resolved.get("PreToolUse").map(String::as_str), Some("stopped"));
    }
}
