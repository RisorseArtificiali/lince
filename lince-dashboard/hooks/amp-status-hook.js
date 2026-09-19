// Amp system plugin. Observe actual thread state, not agent.end (which can continue).
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { spawn } from 'node:child_process';

export default function (amp) {
    const id = process.env.LINCE_AGENT_ID || '';
    if (!/^[A-Za-z0-9_-]+$/.test(id)) return;
    let subscription;
    let generation = 0;
    const report = (state) => {
        const event = `amp.${state}`;
        try {
            const dir = process.env.LINCE_STATUS_DIR || '/tmp/lince-dashboard';
            mkdirSync(dir, { recursive: true });
            writeFileSync(join(dir, `${id}.state`), event);
        } catch { /* observational only */ }
        if (process.env.ZELLIJ) {
            const child = spawn('zellij', ['pipe', '--name', 'lince-status'],
                { stdio: ['pipe', 'ignore', 'ignore'], timeout: 1000 });
            child.on('error', () => {});
            child.stdin.on('error', () => {});
            child.stdin.end(JSON.stringify({ agent_id: id, event }));
        }
    };
    report('unknown');
    amp.on('session.start', async (_event, ctx) => {
        const current = ++generation;
        subscription?.unsubscribe();
        report('unknown');
        let revision = 0;
        const observe = (state) => {
            if (current !== generation) return;
            revision++;
            report(['idle', 'running', 'awaiting-approval', 'error'].includes(state) ? state : 'unknown');
        };
        try {
            subscription = ctx.thread.state.subscribe({next: observe, error: () => observe('unknown'),
                complete: () => observe('unknown')});
            const before = revision;
            const state = await ctx.thread.state.get();
            if (revision === before) observe(state);
        } catch { observe('unknown'); }
    });
    amp.onDispose(() => {
        generation++;
        subscription?.unsubscribe();
        report('stopped');
    });
}
