import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const webRoot = resolve(import.meta.dir, "..");
const serviceFile = resolve(webRoot, "services", "learning", "intents.ts");
const hookFile = resolve(webRoot, "hooks", "useLearningIntents.ts");
const shellFile = resolve(webRoot, "components", "Learning", "LearningShell.tsx");
const statusFile = resolve(webRoot, "components", "Learning", "StatusStrip.tsx");

describe("revisioned learning UI intent boundary", () => {
  test("keeps transport, projection, and React lifecycle in separate modules", () => {
    expect(existsSync(serviceFile)).toBe(true);
    expect(existsSync(hookFile)).toBe(true);
  });

  test("authenticates locally and reconstructs from the API before streaming", () => {
    const service = readFileSync(serviceFile, "utf8");
    const hook = readFileSync(hookFile, "utf8");

    expect(service).toContain("Authorization: `Bearer ${token}`");
    expect(service).toContain("validateLoopbackEndpoint");
    expect(hook).toContain("loadRevisionSnapshot");
    expect(hook).toContain("reconstructLearningProjection");
    expect(hook.indexOf("reconstructLearningProjection")).toBeLessThan(
      hook.indexOf("runLearningIntentReconnectLoop"),
    );
    expect(`${service}\n${hook}`).not.toContain("localStorage");
  });

  test("projects verified connection state into the existing shell", () => {
    const shell = readFileSync(shellFile, "utf8");
    const status = readFileSync(statusFile, "utf8");

    expect(shell).toContain("useLearningIntents");
    expect(shell).toContain("connectionState=");
    expect(status).toContain("MCP verbunden");
    expect(status).toContain("MCP nicht geprüft");
  });
});
