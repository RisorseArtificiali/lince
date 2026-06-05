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
    /// Path to sandbox config for provider auto-discovery.
    /// Defaults to `~/.agent-sandbox/config.toml`.
    #[serde(default)]
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
    #[serde(default)]
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
    /// Populated asynchronously by `discover_sandbox_levels_async()` reading
    /// profile files matching `~/.config/nono/profiles/lince-<base>-*.json` and
    /// `~/.agent-sandbox/profiles/<base>-*.toml`. Combined with the shipped
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
/// Command type for async provider discovery via `run_command` (was
/// `CMD_DISCOVER_PROFILES` pre-#81).
pub const CMD_DISCOVER_PROVIDERS: &str = "discover_providers";
/// Command type for async loading of agent type defaults via `run_command`.
pub const CMD_LOAD_AGENT_DEFAULTS: &str = "load_agent_defaults";

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
    let script = format!(
        "for f in '{}'/*.state; do [ -f \"$f\" ] || continue; \
         printf '%s\\t%s\\n' \"$(basename \"$f\" .state)\" \
         \"$(tr -d '\\n' < \"$f\" 2>/dev/null)\"; done",
        dir
    );
    run_typed_command(&["sh", "-c", &script], CMD_POLL_STATUS);
}

/// Command type for async discovery of custom sandbox-level profiles.
/// Output format: lines of `<backend>:<base>:<level>` (or `<backend>:<base>:` for the
/// suffix-less "normal" profile). See `discover_sandbox_levels_async()`.
pub const CMD_DISCOVER_SANDBOX_LEVELS: &str = "discover_sandbox_levels";

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

/// Extract provider details from a TOML table (the value side of a
/// `[*.providers.<name>]` / `[*.profiles.<name>]` entry).
fn parse_provider_details(table: &toml::Table) -> ProviderDetails {
    let mut pd = ProviderDetails::default();
    // Parse env vars to set
    if let Some(env_table) = table.get("env").and_then(|v| v.as_table()) {
        for (k, v) in env_table {
            if let Some(s) = v.as_str() {
                pd.env.insert(k.clone(), s.to_string());
            }
        }
    }
    // Parse env vars to unset
    if let Some(unset_arr) = table.get("env_unset").and_then(|v| v.as_array()) {
        for v in unset_arr {
            if let Some(s) = v.as_str() {
                pd.env_unset.push(s.to_string());
            }
        }
    }
    pd
}

/// Parse providers (env-var bundles) from sandbox config TOML content,
/// returning per-agent-type maps.
///
/// Recognises four formats — canonical first, legacy second:
///   - `[providers.<name>]`              → attributed to agent base "claude"
///   - `[<agent>.providers.<name>]`      → attributed to `<agent>`
///   - Legacy `[profiles.<name>]`        → attributed to "claude"
///   - Legacy `[<agent>.profiles.<name>]` → attributed to `<agent>`
///
/// When both forms exist for the same agent + name, the canonical entry wins.
/// Returns `(providers_by_agent, details_by_agent)`.
pub fn parse_providers_from_toml(
    content: &str,
) -> (HashMap<String, Vec<String>>, HashMap<String, HashMap<String, ProviderDetails>>) {
    let table: toml::Table = match toml::from_str(content) {
        Ok(t) => t,
        Err(_) => return (HashMap::new(), HashMap::new()),
    };

    let mut by_agent: HashMap<String, Vec<String>> = HashMap::new();
    let mut details_by_agent: HashMap<String, HashMap<String, ProviderDetails>> = HashMap::new();

    fn push_one(
        agent: &str,
        name: &str,
        detail_table: Option<&toml::Table>,
        by_agent: &mut HashMap<String, Vec<String>>,
        details_by_agent: &mut HashMap<String, HashMap<String, ProviderDetails>>,
    ) {
        let names = by_agent.entry(agent.to_string()).or_default();
        if !names.iter().any(|n| n == name) {
            names.push(name.to_string());
        }
        // Last-wins semantics: a later (higher-precedence) call OVERWRITES the
        // previous detail for the same agent + name. Match the Python reader's
        // dict.update() behaviour so the same config produces the same env-var
        // bundle on both sides — see the precedence comment below.
        if let Some(t) = detail_table {
            details_by_agent
                .entry(agent.to_string())
                .or_default()
                .insert(name.to_string(), parse_provider_details(t));
        }
    }

    // Process from LOWEST to HIGHEST precedence so the last write wins
    // (matches `resolve_providers` in sandbox/agent-sandbox: legacy top →
    // legacy ns → canonical top → canonical ns, with later layers replacing
    // earlier ones for any colliding agent + name pair).
    //
    // 1) Legacy top-level [profiles.*]      → "claude"
    // 2) Canonical top-level [providers.*]  → "claude"
    for top_key in ["profiles", "providers"] {
        if let Some(top) = table.get(top_key).and_then(|v| v.as_table()) {
            for (name, value) in top {
                push_one("claude", name, value.as_table(), &mut by_agent, &mut details_by_agent);
            }
        }
    }
    // 3) Legacy namespaced [<agent>.profiles.*]
    // 4) Canonical namespaced [<agent>.providers.*] — highest precedence
    for (agent_key, agent_value) in &table {
        if agent_key == "providers" || agent_key == "profiles" {
            continue;
        }
        let Some(agent_section) = agent_value.as_table() else { continue };
        for sub_key in ["profiles", "providers"] {
            if let Some(provs) = agent_section.get(sub_key).and_then(|v| v.as_table()) {
                for (name, val) in provs {
                    push_one(agent_key, name, val.as_table(), &mut by_agent, &mut details_by_agent);
                }
            }
        }
    }

    // Sort each agent's provider names
    for names in by_agent.values_mut() {
        names.sort();
    }

    (by_agent, details_by_agent)
}

/// Escape a string for use inside single quotes in a shell command.
pub fn shell_escape(s: &str) -> String {
    s.replace('\'', "'\\''")
}

/// Kick off async discovery of providers (env-var bundles) by reading sandbox
/// config files via `run_command`. Results arrive in `Event::RunCommandResult`
/// with context `type=discover_providers`. Was `discover_profiles_async`
/// pre-#81 — see issue for naming rationale.
///
/// Reads the global config and optionally a project-local config. Each file
/// is cat'd separately and their outputs are joined by a NUL byte so the
/// handler can parse them independently (avoiding invalid TOML from
/// concatenating files with duplicate `[providers]` headers).
pub fn discover_providers_async(sandbox_config_path: Option<&str>, launch_dir: Option<&str>) {
    // Build the global config path for the shell script.
    // IMPORTANT: We must NOT quote paths that start with `~` because the shell
    // only performs tilde expansion on unquoted tildes.  `expand_tilde()` uses
    // `std::env::var("HOME")` which is unavailable inside the WASI sandbox, so
    // the tilde would be passed through literally.  Instead we let the shell
    // handle `~` expansion by using `$HOME` in the script.
    let raw_path = sandbox_config_path.unwrap_or("~/.agent-sandbox/config.toml");
    let global_expr = shell_path_expr(raw_path);

    // Output each file separated by NUL so the handler can split and parse independently.
    let mut script = format!("cat {} 2>/dev/null", global_expr);

    if let Some(dir) = launch_dir {
        let local_path = format!(
            "{}/.agent-sandbox/config.toml",
            dir.trim_end_matches('/')
        );
        script = format!(
            "{} ; printf '\\0' ; cat '{}' 2>/dev/null",
            script,
            shell_escape(&local_path)
        );
    }

    run_typed_command(&["sh", "-c", &script], CMD_DISCOVER_PROVIDERS);
}

/// Kick off async discovery of custom sandbox-level profile files.
///
/// Globs:
/// - `~/.config/nono/profiles/lince-<base>-*.json` (nono: per-agent only)
/// - `~/.agent-sandbox/profiles/<base>-<level>.toml` (agent-sandbox: per-agent)
/// - `~/.agent-sandbox/profiles/<level>.toml` (agent-sandbox: agent-agnostic,
///   matches agent-sandbox's own resolution order — see its source for the
///   comment "tried as <agent>-<level>.toml then <level>.toml"). Agent-agnostic
///   levels are emitted once per known base so the cache is populated uniformly.
///
/// Filenames are emitted as `<backend>:<base>:<level>` lines on stdout.
/// Result arrives in `Event::RunCommandResult` with context
/// `type=discover_sandbox_levels`; the handler parses and populates
/// `DashboardConfig.discovered_sandbox_levels`.
pub fn discover_sandbox_levels_async(bases: &[String]) {
    if bases.is_empty() {
        return;
    }
    let mut script = String::new();
    // Per-base globs: nono (always per-agent) + agent-sandbox <base>-<level>.toml.
    for base in bases {
        let b = shell_escape(base);
        script.push_str(&format!(
            "find \"$HOME/.config/nono/profiles\" -maxdepth 1 -type f \
                -name 'lince-{base}-*.json' 2>/dev/null \
                | sed -n 's|.*/lince-{base}-\\(.*\\)\\.json$|nono:{base}:\\1|p';\n",
            base = b,
        ));
        script.push_str(&format!(
            "find \"$HOME/.agent-sandbox/profiles\" -maxdepth 1 -type f \
                -name '{base}-*.toml' 2>/dev/null \
                | sed -n 's|.*/{base}-\\(.*\\)\\.toml$|agent-sandbox:{base}:\\1|p';\n",
            base = b,
        ));
    }
    // Agent-agnostic agent-sandbox profiles: any *.toml whose stem doesn't start
    // with `<known-base>-`. Each such level applies to ALL bases, so we emit one
    // line per base. Skip-patterns are quoted shell `case` patterns built from
    // the same base list to avoid double-counting per-base files.
    let bases_quoted: Vec<String> = bases.iter().map(|b| format!("'{}'", shell_escape(b))).collect();
    let skip_patterns: Vec<String> = bases.iter().map(|b| format!("{}-*", shell_escape(b))).collect();
    script.push_str(&format!(
        "find \"$HOME/.agent-sandbox/profiles\" -maxdepth 1 -type f -name '*.toml' 2>/dev/null \
         | while IFS= read -r f; do \
             name=$(basename \"$f\" .toml); \
             case \"$name\" in {skip}) continue;; esac; \
             for base in {bases}; do \
                 printf 'agent-sandbox:%s:%s\\n' \"$base\" \"$name\"; \
             done; \
         done\n",
        skip = skip_patterns.join("|"),
        bases = bases_quoted.join(" "),
    ));
    run_typed_command(&["sh", "-c", &script], CMD_DISCOVER_SANDBOX_LEVELS);
}

/// Parse the stdout of `discover_sandbox_levels_async()` into a
/// `<backend>:<base> -> [level, ...]` map. Empty / malformed lines are skipped.
pub fn parse_discovered_sandbox_levels(stdout: &[u8]) -> HashMap<String, Vec<String>> {
    let output = String::from_utf8_lossy(stdout);
    let mut out: HashMap<String, Vec<String>> = HashMap::new();
    for line in output.lines() {
        // Format: backend:base:level — parse from the right so base names with
        // `-` (none today, future-proofing) survive.
        let mut parts = line.splitn(3, ':');
        let backend = match parts.next() { Some(s) if !s.is_empty() => s, _ => continue };
        let base = match parts.next() { Some(s) if !s.is_empty() => s, _ => continue };
        let level = match parts.next() { Some(s) if !s.is_empty() => s, _ => continue };
        let key = format!("{}:{}", backend, base);
        let bucket = out.entry(key).or_default();
        if !bucket.iter().any(|l| l == level) {
            bucket.push(level.to_string());
        }
    }
    out
}

/// Kick off async loading of agent type defaults from
/// `~/.config/lince-dashboard/agents-defaults.toml` via `run_command`.
/// Results arrive in `Event::RunCommandResult` with context
/// `type=load_agent_defaults`.
///
/// The shell reads the defaults file first, then (separated by NUL) any
/// `[agents.*]` sections from the user's dashboard config.toml so they can
/// be merged.  User entries override defaults (full replacement per key).
pub fn load_agent_defaults_async(_sandbox_config_path: Option<&str>) {
    let defaults_path = "\"$HOME/.config/lince-dashboard/agents-defaults.toml\"";
    let user_cfg_path = "\"$HOME/.config/lince-dashboard/config.toml\"";

    // Output defaults first, then NUL, then user dashboard config (which may
    // contain [agents.*]).
    let script = format!(
        "cat {} 2>/dev/null ; printf '\\0' ; cat {} 2>/dev/null",
        defaults_path, user_cfg_path
    );

    run_typed_command(&["sh", "-c", &script], CMD_LOAD_AGENT_DEFAULTS);
}

/// TOML wrapper for user config.toml `[agents.<name>]` sections.
#[derive(Deserialize, Default)]
struct UserAgentsSection {
    #[serde(default)]
    agents: HashMap<String, AgentTypeConfig>,
}

/// Parse agent type defaults from the stdout of `load_agent_defaults_async`.
///
/// The output consists of two NUL-separated chunks:
///   1. Contents of `agents-defaults.toml` (`[agents.<name>]` tables)
///   2. Contents of user `config.toml` (may contain `[agents.<name>]` tables)
///
/// User entries override defaults (full replacement per agent type key).
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
    /// Provider auto-discovery happens asynchronously via `discover_providers_async()`
    /// after the plugin has permissions and knows the launch directory.
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


    /// Merge discovered per-agent-type providers, deduplicating.
    pub fn merge_providers(
        &mut self,
        by_agent: &HashMap<String, Vec<String>>,
        details_by_agent: &HashMap<String, HashMap<String, ProviderDetails>>,
    ) {
        for (agent, names) in by_agent {
            let existing = self.providers_by_agent.entry(agent.clone()).or_default();
            for name in names {
                if !existing.contains(name) {
                    existing.push(name.clone());
                }
            }
            existing.sort();
        }
        for (agent, details) in details_by_agent {
            let existing = self.provider_details_by_agent.entry(agent.clone()).or_default();
            for (name, detail) in details {
                existing.entry(name.clone()).or_insert_with(|| detail.clone());
            }
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
    /// custom levels discovered from the filesystem (see
    /// `discover_sandbox_levels_async()`). The standard order is preserved;
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
            // Cache key MUST match the prefix that `discover_sandbox_levels_async`
            // emits ("agent-sandbox:" / "nono:") — NOT `display_name()`, which
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
    pub fn event_map_for(&self, agent_type: &str) -> Option<&HashMap<String, String>> {
        self.agent_types
            .get(agent_type)
            .map(|c| &c.event_map)
            .filter(|m| !m.is_empty())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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

    /// Sandbox config dual-read: namespaced canonical `[<agent>.providers.X]`
    /// must beat top-level legacy `[profiles.X]` for the same name. Matches
    /// the precedence implemented by `resolve_providers` in
    /// `sandbox/agent-sandbox` (legacy → canonical, last wins).
    #[test]
    fn namespaced_canonical_overrides_top_level_legacy() {
        let toml_text = r#"
            [profiles.zai]
            description = "from-legacy-top"
            [profiles.zai.env]
            ANTHROPIC_BASE_URL = "https://legacy.example.com"

            [claude.providers.zai]
            description = "from-canonical-ns"
            [claude.providers.zai.env]
            ANTHROPIC_BASE_URL = "https://canonical.example.com"
        "#;
        let (_names, details) = parse_providers_from_toml(toml_text);
        let claude = details.get("claude").expect("claude bucket");
        let zai = claude.get("zai").expect("zai entry");
        assert_eq!(
            zai.env.get("ANTHROPIC_BASE_URL").map(String::as_str),
            Some("https://canonical.example.com"),
            "namespaced canonical must replace top-level legacy",
        );
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

    /// Both forms in the same file must each contribute their distinct
    /// providers without dropping anything. Uses an explicit name list assert
    /// so a regression in iteration order would still surface a missing entry.
    #[test]
    fn legacy_and_canonical_coexist() {
        let toml_text = r#"
            [profiles.legacyOnly]
            [profiles.legacyOnly.env]
            X = "1"

            [claude.providers.canonicalOnly]
            [claude.providers.canonicalOnly.env]
            Y = "2"
        "#;
        let (names, _details) = parse_providers_from_toml(toml_text);
        let mut claude = names.get("claude").cloned().unwrap_or_default();
        claude.sort();
        assert_eq!(claude, vec!["canonicalOnly", "legacyOnly"]);
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
}
