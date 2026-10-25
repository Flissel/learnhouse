import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const webRoot = resolve(import.meta.dir, "..");
const learningRoot = resolve(webRoot, "components", "Learning");

const expectedFiles = [
  resolve(webRoot, "app", "orgs", "[orgslug]", "(withmenu)", "learning", "page.tsx"),
  resolve(learningRoot, "LearningShell.tsx"),
  resolve(learningRoot, "SpaceRail.tsx"),
  resolve(learningRoot, "CourseOutline.tsx"),
  resolve(learningRoot, "LearningWorkspace.tsx"),
  resolve(learningRoot, "AgentPanel.tsx"),
  resolve(learningRoot, "StatusStrip.tsx"),
  resolve(learningRoot, "LearningShell.test.tsx"),
];

describe("VibeMind learning workspace module boundary", () => {
  test("keeps the approved shell in explicit, maintainable modules", () => {
    for (const file of expectedFiles) {
      expect(existsSync(file), `missing ${file}`).toBe(true);
    }
  });

  test("exposes the workspace from the organization learning route", () => {
    const route = readFileSync(expectedFiles[0], "utf8");

    expect(route).toContain("LearningShell");
    expect(route).toContain("useCourses");
  });

  test("keeps the permanent status strip clear of outer footer chrome", () => {
    const layout = readFileSync(
      resolve(webRoot, "app", "orgs", "[orgslug]", "(withmenu)", "layout.tsx"),
      "utf8",
    );

    expect(layout).toContain("const noFooterPaths = ['copilot', 'learning']");
  });
});
