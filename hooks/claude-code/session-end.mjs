#!/usr/bin/env node
/**
 * Lyra Claude Code SessionEnd hook.
 *
 * On each session end, runs `lyra compile` to promote any pending raw pages.
 * Falls back silently if lyra is not installed or the vault is not initialised
 * — the hook must never block a session from ending.
 *
 * Claude Code hook contract:
 *   - stdin:  JSON payload { session_id, cwd, ... }
 *   - stdout: not used by Claude Code for SessionEnd
 *   - exit 0: success (or graceful no-op)
 */

import { execFileSync } from "node:child_process";
import { readFileSync, mkdirSync, appendFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

function log(message) {
  try {
    const logDir = join(homedir(), "lyra", "logs");
    mkdirSync(logDir, { recursive: true });
    const ts = new Date().toISOString();
    appendFileSync(join(logDir, "session-end.log"), `${ts} ${message}\n`, "utf8");
  } catch {
    // log failure is non-fatal
  }
}

function main() {
  let payload = {};
  try {
    const raw = readFileSync("/dev/stdin", "utf8");
    payload = JSON.parse(raw);
  } catch {
    // Non-fatal: proceed with empty payload
  }

  // Skip subagent contexts to avoid recursive compile
  if (payload?.entrypoint === "sdk-ts") return;

  log("session-end: running lyra compile");
  try {
    execFileSync("lyra", ["compile"], {
      timeout: 60_000,
      encoding: "utf8",
      stdio: ["ignore", "ignore", "ignore"],
    });
    log("session-end: compile complete");
  } catch {
    log("session-end: compile skipped (lyra not installed, not initialised, or timed out)");
    // lyra not installed, not initialised, or timed out — silent no-op
  }
}

main();
