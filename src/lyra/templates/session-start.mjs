#!/usr/bin/env node
/**
 * Lyra Claude Code SessionStart hook.
 *
 * On each session start, runs `lyra brief` and prepends its output to the
 * session context. Falls back silently if lyra is not installed or the vault
 * is not initialised — the hook must never block a session from starting.
 *
 * Claude Code hook contract:
 *   - stdin:  JSON payload { session_id, cwd, ... }
 *   - stdout: text to inject into the session preamble
 *   - exit 0: success (or graceful no-op)
 */

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

function main() {
  let payload = {};
  try {
    const raw = readFileSync("/dev/stdin", "utf8");
    payload = JSON.parse(raw);
  } catch {
    // Non-fatal: proceed with empty payload
  }

  // Skip subagent contexts to avoid recursive brief injection
  if (payload?.entrypoint === "sdk-ts") return;

  try {
    const brief = execFileSync("lyra", ["brief"], {
      timeout: 10_000,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    });
    if (brief && brief.trim()) {
      process.stdout.write(brief.trimEnd() + "\n");
    }
  } catch {
    // lyra not installed, not initialised, or timed out — silent no-op
  }
}

main();
