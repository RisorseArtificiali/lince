//! Read-only terminal conversation log. No groups or task lifecycle.
use serde::{Deserialize, Serialize};
use crate::{attention, config, types::AgentInfo};

pub const SNAPSHOT_COMMAND: &str = "messages_snapshot";
pub const BROWSER_COMMAND: &str = "messages_browser";

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Instance {
    pub id: String,
    pub alias: String,
    pub agent: String,
    pub pane_ref: String,
    pub live: u8,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Message {
    pub id: String,
    pub conversation: String,
    pub sender: String,
    pub recipient: String,
    pub sender_name: String,
    pub recipient_name: String,
    pub text: String,
    pub status: String,
    pub detail: String,
    pub created: f64,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Snapshot {
    pub instances: Vec<Instance>,
    pub messages: Vec<Message>,
}

pub fn poll(agents: &[AgentInfo]) {
    let aliases: Vec<_> = agents.iter().filter_map(|a| a.pane_id.map(|pane|
        serde_json::json!({"pane_ref": pane.to_string(), "status_id": a.id, "alias": a.name}))).collect();
    let args = serde_json::json!({"aliases": aliases}).to_string();
    config::run_typed_command(&["lince-msg-host", "request", "snapshot", "--json", &args], SNAPSHOT_COMMAND);
}

impl Snapshot {
    pub fn instance_for(&self, agent: &AgentInfo) -> Option<&Instance> {
        let pane = agent.pane_id?.to_string();
        self.instances.iter().rev().find(|i| i.live == 1 && i.pane_ref == pane)
    }
    pub fn decorate(&self, bar: &mut attention::Snapshot, agents: &[AgentInfo], ascii: bool) {
        let pending = self.messages.iter().filter(|m| m.status == "pending").count();
        let errors = self.messages.iter().filter(|m| matches!(m.status.as_str(), "failed" | "uncertain")).count();
        bar.mailbox = if self.instances.iter().all(|i| i.live == 0) { "Chat off".into() }
            else { format!("Chat {} pending !{}", pending, errors) };
        bar.provenance = if ascii { "-" } else { "—" }.into();
        // Last submitted message is context, never a claim about current work.
        for (entry, agent) in bar.agents.iter_mut().zip(agents) {
            entry.provenance.clear();
            if !entry.focused { continue; }
            let Some(instance) = self.instance_for(agent) else { continue; };
            if let Some(message) = self.messages.iter().rev().find(|m| m.recipient == instance.id && m.status == "submitted") {
                bar.provenance = format!("{} {} #{}", if ascii { "<" } else { "←" },
                    crate::dashboard::clip_cells(&message.sender_name, 4), message.conversation);
            }
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum Action { None, Close, Navigate(String), Rpc(&'static str, serde_json::Value) }

#[derive(Default)]
pub struct Browser {
    pub open: bool,
    pub pending: bool,
    pub revision: u64,
    pub error: Option<String>,
    pub page: Snapshot,
    pub selected: Option<String>,
    pub detail: bool,
    pub scroll: usize,
}
impl Browser {
    pub fn refresh(&self) -> Action { Action::Rpc("snapshot", serde_json::json!({})) }
    pub fn refresh_visible(&self) -> Action {
        if self.open && !self.pending { self.refresh() } else { Action::None }
    }
    pub fn command(&mut self, op: &str, args: serde_json::Value) {
        self.pending = true;
        self.revision += 1;
        config::run_typed_command_with(&["lince-msg-host", "request", op, "--json", &args.to_string()],
            BROWSER_COMMAND, &[("revision", &self.revision.to_string())]);
    }
    pub fn response(&mut self, revision: u64, _operation: &str, success: bool, bytes: &[u8]) -> Action {
        if revision != self.revision || !self.open { return Action::None; }
        self.pending = false;
        match serde_json::from_slice::<Snapshot>(bytes) {
            Ok(page) if success => {
                if !page.messages.iter().any(|m| Some(&m.id) == self.selected.as_ref()) {
                    self.selected = page.messages.last().map(|m| m.id.clone());
                    self.detail = false;
                }
                self.page = page;
                self.error = None;
            },
            _ => self.error = Some("Communication unavailable; install the optional lince-converse skill.".into()),
        }
        Action::None
    }
    fn selected_message(&self) -> Option<&Message> {
        self.page.messages.iter().find(|m| Some(&m.id) == self.selected.as_ref())
    }
    pub fn key(&mut self, key: &zellij_tile::prelude::BareKey, _snapshot: Option<&Snapshot>) -> Action {
        use zellij_tile::prelude::BareKey;
        if *key == BareKey::Esc {
            if self.detail { self.detail = false; self.scroll = 0; return Action::None; }
            self.open = false; self.pending = false; self.revision += 1;
            return Action::Close;
        }
        match key {
            BareKey::Char('r') if !self.pending => return self.refresh(),
            BareKey::Enter => { self.detail = self.selected_message().is_some(); self.scroll = 0; },
            BareKey::Char('s') | BareKey::Char('f') => if let Some(m) = self.selected_message() {
                return Action::Navigate(if *key == BareKey::Char('s') { m.sender.clone() } else { m.recipient.clone() });
            },
            BareKey::PageDown => self.scroll += 8,
            BareKey::PageUp => self.scroll = self.scroll.saturating_sub(8),
            BareKey::Down | BareKey::Char('j') | BareKey::Up | BareKey::Char('k') if !self.detail => {
                let messages: Vec<_> = self.page.messages.iter().rev().collect();
                let index = messages.iter().position(|m| Some(&m.id) == self.selected.as_ref()).unwrap_or(0);
                let next = if matches!(key, BareKey::Up | BareKey::Char('k')) { index.saturating_sub(1) }
                           else { (index + 1).min(messages.len().saturating_sub(1)) };
                self.selected = messages.get(next).map(|m| m.id.clone());
            },
            _ => {},
        }
        Action::None
    }
    pub fn render(&self, _snapshot: Option<&Snapshot>, rows: usize, cols: usize) {
        let mut lines = vec!["Pane conversations — recent session exchanges".to_string()];
        if self.detail {
            if let Some(m) = self.selected_message() {
                lines.extend([format!("{} -> {} | #{} | {}", m.sender_name, m.recipient_name, m.conversation, m.status),
                    m.detail.clone(), "".into(), m.text.clone()]);
            }
        } else {
            if self.page.messages.is_empty() {
                lines.extend(["No messages. Enable the optional lince-converse skill for each agent.".into(),
                    "Agents use: lince-msg peers; lince-msg send NAME --text '...'".into()]);
            }
            for m in self.page.messages.iter().rev() {
                lines.push(format!("{} {} -> {} #{} [{}]", if Some(&m.id) == self.selected.as_ref() { ">" } else { " " },
                    m.sender_name, m.recipient_name, m.conversation, m.status));
                lines.push(format!("  {}", m.text.replace('\n', " ")));
            }
        }
        let lines: Vec<_> = lines.iter().flat_map(|l| wrap(l, cols)).collect();
        let available = rows.saturating_sub(3);
        let mut offset = self.scroll.min(lines.len().saturating_sub(available));
        if !self.detail {
            if let Some(position) = lines.iter().position(|l| l.starts_with('>')) {
                if position >= offset + available { offset = position.saturating_sub(available.saturating_sub(2)); }
                if position < offset { offset = position; }
            }
        }
        for row in 0..available {
            crate::render_output::write(format_args!("{}\n", crate::dashboard::clip_cells(
                lines.get(offset + row).map(String::as_str).unwrap_or(""), cols)));
        }
        for line in [self.error.as_deref().unwrap_or("Submitted = text + Enter sent, not work completed."),
                     "Enter message | j/k select | r refresh | Esc back",
                     "s sender pane | f recipient pane | PgUp/PgDn scroll"].iter().take(rows.min(3)) {
            crate::render_output::write(format_args!("{}\n", crate::dashboard::clip_cells(line, cols)));
        }
    }
}

fn wrap(text: &str, cols: usize) -> Vec<String> {
    use unicode_width::UnicodeWidthChar;
    if cols == 0 { return Vec::new(); }
    let mut result = Vec::new();
    for paragraph in text.split('\n') {
        let mut line = String::new();
        let mut used = 0;
        for c in paragraph.chars().filter(|c| !c.is_control()) {
            let width = c.width().unwrap_or(0);
            if width > cols { continue; }
            if used + width > cols { result.push(std::mem::take(&mut line)); used = 0; }
            line.push(c); used += width;
        }
        result.push(line);
    }
    result
}


#[cfg(test)]
mod tests {
    use super::*;
    use zellij_tile::prelude::BareKey;
    #[test]
    fn conversation_navigation_is_read_only_and_keeps_message_identity() {
        let mut browser = Browser { open: true, ..Browser::default() };
        browser.response(0, "snapshot", true, br#"{"instances":[],"messages":[{"id":"one","conversation":"12ab34cd","sender":"a","recipient":"b","sender_name":"A","recipient_name":"B","text":"hello","status":"submitted","detail":"sent","created":0.0}]}"#);
        assert_eq!(browser.key(&BareKey::Char('f'), None), Action::Navigate("b".into()));
        browser.key(&BareKey::Enter, None);
        assert!(browser.detail);
        browser.key(&BareKey::Esc, None);
        assert!(browser.open);
        assert_eq!(browser.key(&BareKey::Char('g'), None), Action::None);
        assert_eq!(browser.key(&BareKey::Esc, None), Action::Close);
        browser.response(0, "snapshot", false, b"bad");
        assert!(browser.error.is_none());
    }
    #[test]
    fn terminal_log_stays_in_popup_and_strips_controls() {
        let browser = Browser::default();
        let frame = crate::render_output::capture(|| browser.render(None, 18, 78));
        assert_eq!(frame.lines().count(), 18);
        assert!(frame.contains("No messages."));
        assert!(!frame.contains("groups"));
        assert_eq!(wrap("hello\x1b[2J", 80), vec!["hello[2J"]);
    }
}
