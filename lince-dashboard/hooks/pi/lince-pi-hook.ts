// lince-pi-hook.ts — Pi extension that emits agent-status events to the
// lince-dashboard via the shared "lince-status" Zellij pipe.
//
// Installed by install-pi-hooks.sh into ~/.pi/agent/extensions/, where Pi
// auto-discovers it on startup. JSON payload schema is the minimal contract
// shared by all hook scripts: {agent_id, event}. Native event names are
// forwarded verbatim — the dashboard's per-agent event_map (in
// agents-defaults.toml) maps them to canonical status values. See
// LINCE-118 / LINCE-122.

import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export default function (pi: { on: (ev: string, h: (e: any, ctx: { isIdle: () => boolean }) => void) => void }) {
  const agentId = process.env.LINCE_AGENT_ID;
  const session = process.env.ZELLIJ_SESSION_NAME;
  if (!agentId) return;
  const statusDir = process.env.LINCE_STATUS_DIR || "/tmp/lince-dashboard";

  const send = (event: string) => {
    try {
      mkdirSync(statusDir, { recursive: true });
      writeFileSync(join(statusDir, `${agentId}.state`), event);
    } catch {}
    if (!session) return;
    const payload = JSON.stringify({ agent_id: agentId, event });
    try {
      const child = spawn(
        "zellij",
        ["--session", session, "pipe", "--name", "lince-status"],
        { stdio: ["pipe", "ignore", "ignore"] },
      );
      child.on("error", () => {});
      child.stdin.on("error", () => {});
      child.stdin.end(payload);
    } catch {}
  };

  let idleTimer: ReturnType<typeof setTimeout> | undefined;
  const cancelIdle = () => { if (idleTimer) clearTimeout(idleTimer); idleTimer = undefined; };
  const active = (event: string) => { cancelIdle(); send(event); };
  const settled = (event: string, ctx: { isIdle: () => boolean }) => {
    cancelIdle();
    let remaining = 100;
    const check = () => {
      idleTimer = undefined;
      if (ctx.isIdle()) send(event);
      else if (--remaining > 0) idleTimer = setTimeout(check, 50);
    };
    // Pi 0.79 clears isStreaming only after agent_end handlers return.
    // Never await idle inside that callback: it would block settlement itself.
    idleTimer = setTimeout(check, 50);
  };
  pi.on("session_start", () => active("session_start"));
  pi.on("agent_start", () => active("turn_start"));
  pi.on("turn_start", () => active("turn_start"));
  pi.on("tool_call", () => active("tool_call"));
  // turn_end is also emitted between tool iterations, not just at the prompt.
  pi.on("turn_end", () => active("turn_end"));
  pi.on("agent_end", (_event, ctx) => settled("agent_end", ctx));
  pi.on("agent_settled", (_event, ctx) => settled("agent_settled", ctx));
  pi.on("session_shutdown", () => active("session_shutdown"));
}
