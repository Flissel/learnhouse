import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const webRoot = resolve(import.meta.dir, "..");
const service = resolve(webRoot, "services", "learning", "actions.ts");
const hook = resolve(webRoot, "hooks", "useLearningActions.ts");

describe("VibeMind learning action ownership", () => {
  test("keeps strict host invocation separate from React lifecycle", () => {
    expect(existsSync(service)).toBe(true);
    expect(existsSync(hook)).toBe(true);
  });

  test("uses an injected host bridge without browser persistence or direct MCP fetch", () => {
    const source = `${readFileSync(service, "utf8")}\n${readFileSync(hook, "utf8")}`;

    expect(source).toContain("vibemindLearningActions");
    expect(source).not.toContain("localStorage");
    expect(source).not.toContain("sessionStorage");
    expect(source).not.toContain("/mcp");
    expect(source).not.toContain("OPENAI_API_KEY");
  });
});
