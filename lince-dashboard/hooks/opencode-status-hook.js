#!/usr/bin/env node
/**
 * opencode-status-hook.js — OpenCode plugin that reports session lifecycle
 * status to the lince-dashboard Zellij plugin via pipe (primary) and file
 * (fallback).
 *
 * Emits a minimal JSON contract: {agent_id, event}. Native event names
 * (event.type, plus the busy/idle sub-state of session.status) are forwarded
 * verbatim — the dashboard's per-agent event_map (in agents-defaults.toml)
 * maps them to canonical status values. See LINCE-118 / LINCE-122.
 *
 * Forwarded native event names:
 *   - session.created
 *   - session.status.busy   (session.status with properties.status.type=busy)
 *   - session.status.idle   (session.status with properties.status.type=idle)
 *   - session.idle
 *   - session.deleted
 *
 * Environment:
 *   LINCE_AGENT_ID   — set by the dashboard when spawning the agent
 *   ZELLIJ           — set by Zellij when running inside a session
 *   LINCE_STATUS_DIR — override for status file directory (default: /tmp/lince-dashboard)
 */

import { execSync } from "child_process";
import { writeFileSync, mkdirSync } from "fs";
import { join } from "path";

const AGENT_ID = process.env.LINCE_AGENT_ID || "";
const STATUS_DIR = process.env.LINCE_STATUS_DIR || "/tmp/lince-dashboard";

function buildPayload(event) {
    return JSON.stringify({ agent_id: AGENT_ID, event });
}

function sendViaZellijPipe(payload) {
    if (!process.env.ZELLIJ) return false;
    try {
        execSync(
            `echo '${payload.replace(/'/g, "'\\''")}' | timeout 2 zellij pipe --name "lince-status"`,
            { timeout: 3000, encoding: "utf8" }
        );
        return true;
    } catch {
        return false;
    }
}

function writeStatusFile(event) {
    try {
        mkdirSync(STATUS_DIR, { recursive: true });
        writeFileSync(join(STATUS_DIR, `${AGENT_ID}.state`), event);
    } catch {
        // ignore
    }
}

function reportEvent(event) {
    if (!AGENT_ID) return;
    sendViaZellijPipe(buildPayload(event));
    writeStatusFile(event);
}

export default async ({ directory }) => {
    return {
        event: async ({ event }) => {
            switch (event.type) {
                case "session.created":
                    reportEvent("session.created");
                    break;

                case "session.status": {
                    const type = event.properties?.status?.type;
                    const sub = type === "busy" || type === "idle" ? type : "unknown";
                    reportEvent(`session.status.${sub}`);
                    break;
                }

                case "session.idle":
                    reportEvent("session.idle");
                    break;

                case "session.deleted":
                    reportEvent("session.deleted");
                    break;
            }
        },
    };
};
