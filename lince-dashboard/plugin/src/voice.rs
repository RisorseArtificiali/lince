//! VoxCode configuration and passive popup. Audio remains in the host adapter.
use serde::{Deserialize, Serialize};
use zellij_tile::prelude::*;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(default)]
pub struct Settings {
    pub configured: bool,
    pub mode: String,
    pub microphone: String,
    pub language: String,
    pub model: String,
    pub device: String,
    pub auto_send: bool,
}
impl Default for Settings {
    fn default() -> Self {
        Self { configured: false, mode: "ptt".into(), microphone: "default".into(),
            language: "auto".into(), model: "small".into(), device: "cpu".into(), auto_send: false }
    }
}
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Microphone { pub id: String, pub name: String }
#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
#[serde(default)]
pub struct TextEvent {
    pub sequence: u64,
    pub text: String,
    pub pinned: bool,
    pub target: Option<u32>,
    pub submit: bool,
}
#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
#[serde(default)]
pub struct Snapshot {
    pub installed: bool,
    pub settings: Settings,
    pub status: String,
    pub level: usize,
    pub error: String,
    pub buffer: String,
    pub devices: Vec<Microphone>,
    pub events: Vec<TextEvent>,
}
impl Snapshot {
    pub fn active(&self) -> bool { matches!(self.status.as_str(), "loading" | "listening" | "recording" | "transcribing" | "muted") }
    pub fn indicator(&self) -> String {
        if !self.error.is_empty() { return "V-ERR     ".into(); }
        if !self.settings.configured { return "V-??????  ".into(); }
        let prefix = if self.settings.mode == "ptt" { "VP" } else { "VA" };
        let suffix = match self.status.as_str() {
            "muted" => "MUTE  ".into(),
            "loading" => "LOAD  ".into(),
            "transcribing" => "...   ".into(),
            "stopped" | "" => "STOP  ".into(),
            _ => format!("{}{}", "#".repeat(self.level.min(6)), "·".repeat(6 - self.level.min(6))),
        };
        format!("{prefix}-{suffix} ")
    }
}
/// Build the paste-safe payload and submit byte for a voice delivery (#379).
///
/// Trailing CR/LF are stripped (a leaked newline is a literal Ctrl+J in
/// multiline composers), the text is wrapped in a bracketed paste so internal
/// newlines stay prompt text — the same mechanism the agent messaging
/// transport uses — and the submit is a real Enter (CR, byte 13) sent after
/// the paste-end sequence. Returns `None` when there is nothing to deliver.
pub fn voice_delivery(text: &str, submit: bool) -> Option<(String, Option<Vec<u8>>)> {
    let cleaned = text.trim_end_matches(['\r', '\n']);
    if cleaned.trim().is_empty() {
        return None;
    }
    let payload = format!("\x1b[200~{cleaned}\x1b[201~");
    let enter = if submit { Some(vec![b'\r']) } else { None };
    Some((payload, enter))
}

#[derive(Default)]
pub struct Voice {
    pub open: bool,
    pub tab: Option<usize>,
    pub snapshot: Snapshot,
    pub draft: Settings,
    pub dirty: bool,
    pub field: usize,
    pub editing: bool,
    pub pending: bool,
    pub poll_armed: bool,
    pub queue: std::collections::VecDeque<serde_json::Value>,
    pub ack: u64,
    pub target: Option<u32>,
    pub restore_target: Option<u32>,
    pub error_seen: String,
}
impl Voice {
    pub fn render(&self, rows: usize, cols: usize, enabled: bool) {
        let settings = &self.draft;
        let mut lines = vec!["VoxCode — voice input to the last active agent or shell".into(),
            format!("State: {}   {}", self.snapshot.status, self.snapshot.indicator()),
            if !enabled { "Integration disabled: set [dashboard] voxcode_enabled=true".into() } else if self.snapshot.installed { "".into() } else { "VoxCode not installed: https://github.com/RisorseArtificiali/voxcode".into() }];
        for (i, (name, value)) in [("Mode", settings.mode.clone()), ("Microphone", settings.microphone.clone()),
            ("Language", settings.language.clone()), ("Whisper model", settings.model.clone()),
            ("Compute device", settings.device.clone()), ("Auto-insert", settings.auto_send.to_string())].iter().enumerate() {
            lines.push(format!("{} {name}: {value}{}", if self.field == i { ">" } else { " " },
                if self.field == i && self.editing { "_" } else { "" }));
        }
        lines.push("".into());
        lines.push(format!("Buffer: {}", self.snapshot.buffer));
        if !self.snapshot.error.is_empty() { lines.push(format!("Error: {}", self.snapshot.error)); }
        lines.push("Tab/↑/↓ field · ←/→ change · Enter edit/finish".into());
        lines.push("[s] Save [a] Start [m] Mute/unmute [x] Stop".into());
        lines.push("[i] Insert buffer [c] Clear [r] Refresh microphones [Esc] Close".into());
        lines.push("Alt+m: mute/unmute · PTT stop: Ctrl+Space inserts + Enter; Alt+t inserts only.".into());
        lines.push("Stop before editing. Settings persist; listening never auto-starts.".into());
        for line in lines.iter().take(rows) {
            crate::render_output::write(format_args!("{}\n", crate::dashboard::clip_cells(line, cols)));
        }
    }
    pub fn edit_key(&mut self, key: &KeyWithModifier) -> bool {
        if self.editing {
            let value = match self.field { 1 => &mut self.draft.microphone, 2 => &mut self.draft.language, _ => &mut self.draft.model };
            match key.bare_key {
                BareKey::Enter | BareKey::Esc => self.editing = false,
                BareKey::Backspace => { value.pop(); self.dirty = true; },
                BareKey::Char(c) if key.key_modifiers.is_empty() && !c.is_control() => { value.push(c); self.dirty = true; },
                _ => (),
            }
            return true;
        }
        match key.bare_key {
            BareKey::Tab | BareKey::Down => self.field = (self.field + 1) % 6,
            BareKey::Up => self.field = (self.field + 5) % 6,
            BareKey::Left | BareKey::Right | BareKey::Enter if !self.snapshot.active() => {
                match self.field {
                    0 => self.draft.mode = if self.draft.mode == "ptt" { "vad" } else { "ptt" }.into(),
                    1 if key.bare_key != BareKey::Enter => {
                        let mut names = vec!["default".to_owned()];
                        names.extend(self.snapshot.devices.iter().map(|d| d.name.clone()));
                        let index = names.iter().position(|n| n == &self.draft.microphone).unwrap_or(0);
                        let next = if key.bare_key == BareKey::Left { (index + names.len() - 1) % names.len() } else { (index + 1) % names.len() };
                        self.draft.microphone = names[next].clone();
                    }
                    1..=3 => self.editing = true,
                    4 => self.draft.device = if self.draft.device == "cpu" { "cuda" } else { "cpu" }.into(),
                    5 => self.draft.auto_send = !self.draft.auto_send,
                    _ => (),
                }
                self.dirty = true;
            }
            _ => return false,
        }
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn indicators_reserve_fixed_width_and_distinguish_muted_stopped_and_loading() {
        let mut snapshot = Snapshot::default();
        assert_eq!(snapshot.indicator().trim(), "V-??????");
        snapshot.settings.configured = true;
        for mode in ["ptt", "vad"] {
            snapshot.settings.mode = mode.into();
            for state in ["stopped", "loading", "muted", "listening", "recording", "transcribing"] {
                snapshot.status = state.into();
                snapshot.level = 99;
                assert_eq!(snapshot.indicator().chars().count(), 10);
            }
        }
        snapshot.status = "muted".into();
        assert!(snapshot.indicator().contains("MUTE"));
        snapshot.status = "stopped".into();
        assert!(!snapshot.active());
    }
    #[test]
    fn configuration_editing_is_blocked_during_listening_and_mute() {
        let mut voice = Voice::default();
        for status in ["listening", "muted", "loading"] {
            voice.snapshot.status = status.into();
            let original = voice.draft.clone();
            voice.edit_key(&KeyWithModifier::new(BareKey::Right));
            assert_eq!(voice.draft, original);
        }
        voice.snapshot.status = "stopped".into();
        voice.edit_key(&KeyWithModifier::new(BareKey::Right));
        assert_eq!(voice.draft.mode, "vad");
        assert!(voice.dirty);
    }
    #[test]
    fn voice_delivery_strips_trailing_newlines_and_submits_cr() {
        let (payload, enter) = voice_delivery("fix the bug\n", true).unwrap();
        assert_eq!(payload, "\x1b[200~fix the bug\x1b[201~");
        assert_eq!(enter, Some(vec![b'\r']));
    }
    #[test]
    fn voice_delivery_keeps_internal_newlines_inside_the_paste() {
        let (payload, enter) = voice_delivery("line one\nline two\r\n", true).unwrap();
        assert_eq!(payload, "\x1b[200~line one\nline two\x1b[201~");
        assert_eq!(enter, Some(vec![b'\r']));
    }
    #[test]
    fn voice_delivery_insert_only_sends_no_enter() {
        let (_, enter) = voice_delivery("note to self", false).unwrap();
        assert_eq!(enter, None);
    }
    #[test]
    fn voice_delivery_empty_or_whitespace_delivers_nothing() {
        assert!(voice_delivery(" \n \r ", true).is_none());
        assert!(voice_delivery("", true).is_none());
    }
}
