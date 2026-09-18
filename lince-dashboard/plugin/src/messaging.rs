//! Authoritative mailbox snapshots. No terminal inspection or synthetic input.
use serde::{Deserialize, Serialize};
use crate::{attention, config, types::AgentInfo};

pub const SNAPSHOT_COMMAND: &str = "messages_snapshot";

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
}
