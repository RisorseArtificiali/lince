//! Authoritative mailbox snapshots. No terminal inspection or synthetic input.
use serde::{Deserialize, Serialize};
use crate::{attention, config, types::AgentInfo};

pub const SNAPSHOT_COMMAND: &str = "messages_snapshot";
pub const BROWSER_COMMAND: &str = "messages_browser";

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Counts {
    pub unread: usize,
    pub waiting: usize,
    pub errors: usize,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Current {
    pub id: String,
    pub sender: String,
    pub requester: String,
    pub kind: String,
    pub work: String,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Instance {
    pub id: String,
    pub alias: String,
    pub agent: String,
    pub pane_ref: String,
    pub live: u8,
    pub provenance: String,
    pub readiness: String,
    pub capabilities: String,
    pub automatic: u8,
    pub current: Option<Current>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Group { pub id: String, pub name: String }
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Member { pub instance: String, pub group_id: String }
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Request {
    pub id: String,
    pub conversation: String,
    pub parent: Option<String>,
    pub sender: String,
    pub recipient: String,
    pub group_id: String,
    pub kind: String,
    pub text: String,
    pub delivery: String,
    pub work: String,
    pub cancel_ack: u8,
    pub created: f64,
    pub updated: f64,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Snapshot {
    pub session: String,
    pub summary: Counts,
    pub instances: Vec<Instance>,
    pub groups: Vec<Group>,
    pub members: Vec<Member>,
    pub requests: Vec<Request>,
}

pub fn request(op: &str, args: serde_json::Value, context: &str) {
    // Every value is an argv entry; peer text is never interpreted by a shell.
    config::run_typed_command(&["lince-msg-host", "request", op, "--json", &args.to_string()], context);
}

pub fn poll() { request("snapshot", serde_json::json!({}), SNAPSHOT_COMMAND); }

impl Snapshot {
    pub fn instance_for(&self, agent: &AgentInfo) -> Option<&Instance> {
        let pane = agent.pane_id?.to_string();
        self.instances.iter().rev().find(|instance| instance.live == 1 && instance.pane_ref == pane)
    }

    pub fn decorate(&self, bar: &mut attention::Snapshot, agents: &[AgentInfo], ascii: bool) {
        bar.mailbox = if self.groups.is_empty() { "Mailbox off".into() } else {
            format!("Mail {}  Work {}  !{}", self.summary.unread, self.summary.waiting, self.summary.errors)
        };
        bar.provenance = if ascii { "-" } else { "—" }.into();
        for (entry, agent) in bar.agents.iter_mut().zip(agents) {
            let Some(instance) = self.instance_for(agent) else { continue; };
            entry.provenance = match instance.provenance.as_str() {
                "human" => if ascii { "U" } else { "●" },
                "peer-question" | "peer-task" => if ascii { "<" } else { "←" },
                _ => "",
            }.into();
            if entry.focused {
                bar.provenance = if instance.provenance == "human" { "User request".into() }
                else if let Some(current) = instance.current.as_ref().filter(|r|
                    r.work == "active" && instance.provenance.starts_with("peer-")) {
                    format!("{} {} {} {} #{}", if ascii { "<" } else { "←" },
                        crate::dashboard::clip_cells(&current.requester, 9), if ascii { "." } else { "·" },
                        if current.kind == "question" { "ask" } else { "task" },
                        current.id.chars().take(8).collect::<String>())
                } else { if ascii { "-" } else { "—" }.into() };
            }
        }
    }
}

#[derive(Clone, Debug, Default, Deserialize)]
pub struct Page {
    pub requests: Vec<Request>,
    pub cursor: i64,
    pub more: bool,
}
#[derive(Clone, Debug, Default, Deserialize)]
pub struct Event {
    pub seq: u64,
    pub actor: String,
    #[serde(rename = "type")]
    pub kind: String,
    pub text: String,
    pub created: f64,
}
#[derive(Clone, Debug, Default, Deserialize)]
pub struct Thread {
    #[serde(flatten)]
    pub request: Request,
    pub events: Vec<Event>,
    pub cursor: u64,
    pub more: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Action {
    None,
    Close,
    Navigate(String),
    Rpc(&'static str, serde_json::Value),
}

#[derive(Default)]
pub struct Browser {
    pub open: bool,
    pub groups_open: bool,
    pub pending: bool,
    pub revision: u64,
    pub error: Option<String>,
    pub filter: usize,
    pub page: Page,
    pub page_before: Option<i64>,
    pub selected: Option<String>,
    pub thread: Option<Thread>,
    pub scroll: usize,
    pub group_index: usize,
    pub instance_index: usize,
}

const FILTERS: [&str; 6] = ["all", "unread", "waiting", "active", "errors", "completed"];

impl Browser {
    pub fn refresh(&self) -> Action {
        Action::Rpc("list", serde_json::json!({"filter": FILTERS[self.filter]}))
    }

    pub fn refresh_visible(&self) -> Action {
        if !self.open || self.pending || self.groups_open { return Action::None; }
        if let Some(thread) = &self.thread {
            Action::Rpc("get", serde_json::json!({"request": thread.request.id, "after": thread.cursor}))
        } else {
            let mut args = serde_json::json!({"filter": FILTERS[self.filter]});
            if let Some(before) = self.page_before { args["before"] = before.into(); }
            Action::Rpc("list", args)
        }
    }

    pub fn command(&mut self, op: &str, args: serde_json::Value) {
        if op == "list" { self.page_before = args.get("before").and_then(|v| v.as_i64()); }
        self.revision += 1;
        self.pending = true;
        self.error = None;
        config::run_typed_command_with(&["lince-msg-host", "request", op, "--json", &args.to_string()],
            BROWSER_COMMAND, &[("revision", &self.revision.to_string()), ("operation", op)]);
    }

    pub fn response(&mut self, revision: u64, operation: &str, success: bool, bytes: &[u8]) -> Action {
        if revision != self.revision || !self.open { return Action::None; }
        self.pending = false;
        if !success {
            self.error = Some(serde_json::from_slice::<serde_json::Value>(bytes).ok()
                .and_then(|v| v.get("message").and_then(|s| s.as_str()).map(str::to_owned))
                .unwrap_or_else(|| "Mailbox operation failed; refresh to reconcile before retrying".into()));
            return Action::None;
        }
        if operation == "list" {
            match serde_json::from_slice::<Page>(bytes) {
                Ok(page) => {
                    if !page.requests.iter().any(|r| Some(&r.id) == self.selected.as_ref()) {
                        self.selected = page.requests.first().map(|r| r.id.clone());
                    }
                    self.page = page;
                }
                Err(_) => self.error = Some("Invalid mailbox page".into()),
            }
        } else if operation == "get" {
            match serde_json::from_slice::<Thread>(bytes) {
                Ok(mut page) => {
                    if Some(&page.request.id) != self.selected.as_ref() { return Action::None; }
                    if let Some(old) = self.thread.take().filter(|t| t.request.id == page.request.id) {
                        let mut events = old.events;
                        events.extend(page.events.into_iter().filter(|e| e.seq > old.cursor));
                        page.events = events;
                    }
                    let next = if page.more && page.events.len() < 128 {
                        Action::Rpc("get", serde_json::json!({"request": page.request.id, "after": page.cursor}))
                    } else { Action::None };
                    self.thread = Some(page);
                    return next;
                }
                Err(_) => self.error = Some("Invalid mailbox thread".into()),
            }
        } else {
            // State mutation is followed by an authoritative refresh; don't infer
            // acceptance/cancellation from which key the human pressed.
            if let Some(thread) = self.thread.take() {
                return Action::Rpc("get", serde_json::json!({"request": thread.request.id}));
            }
            return self.refresh();
        }
        Action::None
    }

    pub fn key(&mut self, key: &zellij_tile::prelude::BareKey, snapshot: Option<&Snapshot>) -> Action {
        use zellij_tile::prelude::BareKey;
        if *key == BareKey::Esc {
            self.revision += 1;
            self.pending = false;
            self.error = None;
            if self.thread.take().is_some() { self.scroll = 0; return Action::None; }
            if self.groups_open { self.groups_open = false; return Action::None; }
            self.open = false;
            return Action::Close;
        }
        if self.pending { return Action::None; }
        if *key == BareKey::Char('g') {
            self.thread = None;
            self.groups_open = !self.groups_open;
            self.scroll = 0;
            return Action::None;
        }
        if self.groups_open {
            let Some(data) = snapshot else { return Action::None; };
            let live: Vec<_> = data.instances.iter().filter(|i| i.live == 1).collect();
            self.instance_index = self.instance_index.min(live.len().saturating_sub(1));
            self.group_index = self.group_index.min(data.groups.len().saturating_sub(1));
            match key {
                BareKey::Char('j') | BareKey::Down => self.instance_index = (self.instance_index + 1).min(live.len().saturating_sub(1)),
                BareKey::Char('k') | BareKey::Up => self.instance_index = self.instance_index.saturating_sub(1),
                BareKey::Char(']') => self.group_index = (self.group_index + 1) % data.groups.len().max(1),
                BareKey::Char('[') => self.group_index = (self.group_index + data.groups.len().max(1) - 1) % data.groups.len().max(1),
                BareKey::Char('n') => return Action::Rpc("group", serde_json::json!({"name": format!("Peers {}", data.groups.len() + 1), "members": []})),
                BareKey::Char(' ') => {
                    if let (Some(group), Some(instance)) = (data.groups.get(self.group_index), live.get(self.instance_index)) {
                        let mut members: Vec<_> = data.members.iter().filter(|m| m.group_id == group.id
                            && live.iter().any(|i| i.id == m.instance)).map(|m| m.instance.clone()).collect();
                        if members.contains(&instance.id) { members.retain(|id| id != &instance.id); }
                        else { members.push(instance.id.clone()); }
                        return Action::Rpc("group", serde_json::json!({"group": group.id, "name": group.name, "members": members}));
                    }
                }
                BareKey::Char('a') => if let Some(instance) = live.get(self.instance_index) {
                    return Action::Rpc("automatic", serde_json::json!({"instance": instance.id, "enabled": instance.automatic == 0}));
                },
                _ => {},
            }
            return Action::None;
        }
        if matches!(key, BareKey::PageDown | BareKey::PageUp) {
            self.scroll = if *key == BareKey::PageDown { self.scroll.saturating_add(8) } else { self.scroll.saturating_sub(8) };
            return Action::None;
        }
        if let BareKey::Char(c @ '1'..='6') = key {
            self.filter = (*c as u8 - b'1') as usize;
            self.thread = None;
            self.scroll = 0;
            return self.refresh();
        }
        if *key == BareKey::Char('r') {
            if let Some(thread) = self.thread.take() { return Action::Rpc("get", serde_json::json!({"request": thread.request.id})); }
            return self.refresh();
        }
        if *key == BareKey::Char('n') {
            if let Some(thread) = &self.thread {
                if thread.more { return Action::Rpc("get", serde_json::json!({"request": thread.request.id, "after": thread.cursor})); }
            } else if self.page.more {
                return Action::Rpc("list", serde_json::json!({"filter": FILTERS[self.filter], "before": self.page.cursor}));
            }
            return Action::None;
        }
        if *key == BareKey::Enter && self.thread.is_some() { return Action::None; }
        if self.thread.is_none() {
            let index = self.page.requests.iter().position(|r| Some(&r.id) == self.selected.as_ref()).unwrap_or(0);
            let next = match key { BareKey::Down | BareKey::Char('j') => Some(index + 1),
                BareKey::Up | BareKey::Char('k') => Some(index.saturating_sub(1)), _ => None };
            if let Some(next) = next {
                self.selected = self.page.requests.get(next.min(self.page.requests.len().saturating_sub(1))).map(|r| r.id.clone());
                return Action::None;
            }
        }
        let selected = self.thread.as_ref().map(|t| &t.request)
            .or_else(|| self.page.requests.iter().find(|r| Some(&r.id) == self.selected.as_ref()));
        if let Some(request) = selected {
            match key {
                BareKey::Enter => return Action::Rpc("get", serde_json::json!({"request": request.id})),
                BareKey::Char('c') => return Action::Rpc("cancel", serde_json::json!({"request": request.id})),
                BareKey::Char('p') => return Action::Rpc("pause", serde_json::json!({"request": request.id})),
                BareKey::Char('u') => return Action::Rpc("resume", serde_json::json!({"request": request.id})),
                BareKey::Char('t') => return Action::Rpc("reconcile", serde_json::json!({"request": request.id, "retry": true})),
                BareKey::Char('d') => return Action::Rpc("reconcile", serde_json::json!({"request": request.id, "retry": false})),
                BareKey::Char('s') => return Action::Navigate(request.sender.clone()),
                BareKey::Char('f') => return Action::Navigate(request.recipient.clone()),
                _ => {},
            }
        }
        if *key == BareKey::Char('D') { return Action::Rpc("prune", serde_json::json!({})); }
        Action::None
    }

    pub fn lines(&self, snapshot: Option<&Snapshot>) -> Vec<String> {
        let alias = |id: &str| snapshot.and_then(|s| s.instances.iter().find(|i| i.id == id))
            .map(|i| i.alias.clone()).unwrap_or_else(|| id.to_owned());
        if self.groups_open {
            let mut lines = vec!["Communication groups (explicit opt-in)".into(),
                "n new group | [/] choose group | j/k agent | Space membership | a automatic intake".into(),
                "Removing membership interrupts outstanding work in that group.".into()];
            if let Some(data) = snapshot {
                let group = data.groups.get(self.group_index);
                lines.push(group.map(|g| format!("Group: {} ({})", g.name, g.id)).unwrap_or_else(|| "No groups. Press n to create one.".into()));
                for (index, instance) in data.instances.iter().filter(|i| i.live == 1).enumerate() {
                    let member = group.is_some_and(|g| data.members.iter().any(|m| m.instance == instance.id && m.group_id == g.id));
                    lines.push(format!("{} [{}] {} ({}) | automatic {}", if index == self.instance_index { ">" } else { " " },
                        if member { "x" } else { " " }, instance.alias, instance.agent, if instance.automatic == 1 { "on" } else { "off" }));
                    if index == self.instance_index {
                        let reason = serde_json::from_str::<serde_json::Value>(&instance.capabilities).ok()
                            .and_then(|v| v.get("reason").and_then(|s| s.as_str()).map(str::to_owned));
                        if let Some(reason) = reason { lines.push(format!("  {reason}")); }
                    }
                }
            }
            return lines;
        }
        if let Some(thread) = &self.thread {
            let r = &thread.request;
            let mut lines = vec![format!("{} -> {} | {}", alias(&r.sender), alias(&r.recipient), r.kind),
                format!("Request {} | conversation {}", r.id, r.conversation),
                format!("Parent: {} | delivery {} | work {}", r.parent.as_deref().unwrap_or("none"), r.delivery, r.work),
                format!("Created {:.3} | updated {:.3} (Unix seconds)", r.created, r.updated),
                format!("Cancellation: {}", if r.work != "cancelled" { "not requested" } else if r.cancel_ack == 1 { "acknowledged" } else { "requested; recipient acknowledgement pending" }),
                "".into(), r.text.clone()];
            for event in &thread.events {
                lines.push(format!("\n{:.3} {} [{}]\n{}", event.created, alias(&event.actor), event.kind, event.text));
            }
            if thread.more { lines.push("More events available: n to load the next page.".into()); }
            if r.work == "interrupted" { lines.push("Recipient/session interrupted. Create a new assignment explicitly; this request cannot be retargeted.".into()); }
            return lines;
        }
        let mut lines = vec![format!("Messages and tasks — {}", FILTERS[self.filter]),
            "1 all | 2 unread | 3 waiting | 4 active/paused | 5 errors | 6 completed".into(),
            "Delivered = offered; accepted = owned; completed = explicit result.".into()];
        if self.page.requests.is_empty() { lines.push("No matching requests. g: enable a group; r: refresh.".into()); }
        for r in &self.page.requests {
            lines.push(format!("{} {} -> {} | {} | {} / {}", if Some(&r.id) == self.selected.as_ref() { ">" } else { " " },
                alias(&r.sender), alias(&r.recipient), r.kind, r.delivery, r.work));
            lines.push(format!("  #{}  {}", r.id, r.text.replace('\n', " ")));
        }
        if self.page.more { lines.push("n: older requests; r: return to latest".into()); }
        lines
    }

    pub fn render(&self, snapshot: Option<&Snapshot>, rows: usize, cols: usize) {
        let mut lines = Vec::new();
        for line in self.lines(snapshot) { lines.extend(wrap(&line, cols)); }
        let available = rows.saturating_sub(3);
        let mut offset = self.scroll.min(lines.len().saturating_sub(available));
        if self.thread.is_none() {
            if let Some(position) = lines.iter().position(|l| l.starts_with('>')) {
                if position >= offset + available { offset = position.saturating_sub(available.saturating_sub(2)); }
                if position < offset { offset = position; }
            }
        }
        for row in 0..available {
            let line = lines.get(offset + row).map(String::as_str).unwrap_or("");
            crate::render_output::write(format_args!("{}\n", crate::dashboard::clip_cells(line, cols)));
        }
        let status = self.error.as_deref().unwrap_or(if self.pending { "Loading…" } else { "Cancel does not undo edits. D: delete terminal history older than 30 days." });
        for line in [status,
            "Enter thread | c cancel | p pause | u resume | t retry uncertain | d mark delivered",
            "s sender pane | f recipient pane | PgUp/PgDn scroll | g groups | Esc back"].iter().take(rows.min(3)) {
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
    use crate::{dashboard, config::DashboardConfig, types::AgentStatus};
    #[test]
    fn focus_maps_to_live_instance_not_alias_or_old_occupant() {
        let mut agent = dashboard::preview_agent("renamed", AgentStatus::Running);
        agent.pane_id = Some(42);
        let mut data = Snapshot::default();
        data.instances.push(Instance { id: "old".into(), pane_ref: "42".into(), live: 0,
            provenance: "peer-task".into(), ..Instance::default() });
        assert!(data.instance_for(&agent).is_none());
        data.instances.push(Instance { id: "new".into(), pane_ref: "42".into(), live: 1,
            provenance: "human".into(), ..Instance::default() });
        let mut bar = attention::Snapshot::from_agents(&[agent.clone()], Some(&agent.id), &DashboardConfig::default(), None);
        data.decorate(&mut bar, &[agent], true);
        assert_eq!(bar.agents[0].provenance, "U");
        assert_eq!(bar.provenance, "User request");
    }
    #[test]
    fn queued_receipt_does_not_set_peer_provenance() {
        let mut agent = dashboard::preview_agent("peer", AgentStatus::WaitingForInput);
        agent.pane_id = Some(1);
        let mut data = Snapshot::default();
        data.instances.push(Instance { pane_ref: "1".into(), live: 1, provenance: "unknown".into(), ..Instance::default() });
        data.summary.unread = 2;
        data.groups.push(Group { id: "group".into(), name: "review".into() });
        let mut bar = attention::Snapshot::from_agents(&[agent.clone()], Some(&agent.id), &DashboardConfig::default(), None);
        data.decorate(&mut bar, &[agent], false);
        assert!(bar.agents[0].provenance.is_empty());
        assert_eq!(bar.mailbox, "Mail 2  Work 0  !0");
    }

    #[test]
    fn refresh_keeps_selection_and_stale_response_cannot_reopen_thread() {
        let mut browser = Browser { open: true, revision: 3, selected: Some("old".into()), ..Browser::default() };
        let page = serde_json::json!({"requests": [Request { id: "new".into(), ..Request::default() },
            Request { id: "old".into(), ..Request::default() }], "cursor": 1, "more": false});
        browser.response(3, "list", true, page.to_string().as_bytes());
        assert_eq!(browser.selected.as_deref(), Some("old"));
        assert_eq!(browser.key(&zellij_tile::prelude::BareKey::Esc, None), Action::Close);
        browser.response(3, "get", true, b"{}");
        assert!(!browser.open);
        assert!(browser.thread.is_none());
    }

    #[test]
    fn reading_and_cancelling_do_not_navigate_and_ids_stay_pinned() {
        use zellij_tile::prelude::BareKey;
        let mut browser = Browser { open: true, selected: Some("request".into()), ..Browser::default() };
        browser.page.requests.push(Request { id: "request".into(), sender: "sender-instance".into(),
            recipient: "recipient-instance".into(), ..Request::default() });
        assert_eq!(browser.key(&BareKey::Enter, None), Action::Rpc("get", serde_json::json!({"request":"request"})));
        assert_eq!(browser.key(&BareKey::Char('c'), None), Action::Rpc("cancel", serde_json::json!({"request":"request"})));
        assert_eq!(browser.key(&BareKey::Char('f'), None), Action::Navigate("recipient-instance".into()));
        assert_eq!(browser.key(&BareKey::Char('s'), None), Action::Navigate("sender-instance".into()));
    }

    #[test]
    fn membership_is_an_explicit_action_and_automatic_is_separate() {
        use zellij_tile::prelude::BareKey;
        let mut snapshot = Snapshot::default();
        snapshot.groups.push(Group { id: "g".into(), name: "review".into() });
        snapshot.instances.push(Instance { id: "b".into(), live: 1, ..Instance::default() });
        let mut browser = Browser { open: true, groups_open: true, ..Browser::default() };
        assert_eq!(browser.key(&BareKey::Char(' '), Some(&snapshot)), Action::Rpc("group",
            serde_json::json!({"group":"g", "name":"review", "members":["b"]})));
        assert_eq!(browser.key(&BareKey::Char('a'), Some(&snapshot)), Action::Rpc("automatic",
            serde_json::json!({"instance":"b", "enabled":true})));
        assert_eq!(snapshot.members.len(), 0);
    }

    #[test]
    fn thread_preserves_late_results_and_cancellation_acknowledgement() {
        let browser = Browser { thread: Some(Thread { request: Request { work: "cancelled".into(),
            cancel_ack: 0, parent: Some("parent".into()), ..Request::default() },
            events: vec![Event { kind: "late_complete".into(), text: "edits already made".into(), ..Event::default() }],
            ..Thread::default() }), ..Browser::default() };
        let text = browser.lines(None).join("\n");
        assert!(text.contains("acknowledgement pending"));
        assert!(text.contains("Parent: parent"));
        assert!(text.contains("late_complete"));
        assert!(text.contains("edits already made"));
    }

    #[test]
    fn mailbox_content_and_controls_stay_inside_bordered_popup() {
        let browser = Browser { page: Page { requests: vec![Request {
            id: "message-id".into(), sender: "sender".into(), recipient: "recipient".into(),
            text: "Visible full preview".into(), ..Request::default()
        }], ..Page::default() }, ..Browser::default() };
        let content = crate::render_output::capture(|| browser.render(None, 18, 78));
        assert_eq!(content.lines().count(), 18);
        assert!(!content.contains('\x1b'));
        let frame = crate::render_output::bordered(20, 80, "Messages", |rows, cols|
            browser.render(None, rows, cols));
        assert_eq!(frame.lines().count(), 20);
        assert!(frame.contains("Visible full preview"));
        assert!(frame.contains("s sender pane | f recipient pane"));
        assert!(frame.contains("No matching requests") == false);
    }

    #[test]
    fn unicode_long_messages_and_empty_views_render_without_control_injection() {
        use unicode_width::UnicodeWidthChar;
        let text = "界文字\nsecond line\x1b[2J";
        for width in 1..40 {
            for line in wrap(text, width) {
                assert!(!line.chars().any(char::is_control));
                assert!(line.chars().map(|c| c.width().unwrap_or(0)).sum::<usize>() <= width);
            }
        }
        let browser = Browser::default();
        assert!(browser.lines(None).join(" ").contains("No matching requests"));
        for rows in 0..6 { for cols in 0..8 {
            let _ = crate::render_output::capture(|| browser.render(None, rows, cols));
        }}
    }
}
