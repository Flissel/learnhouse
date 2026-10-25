import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const webRoot = resolve(import.meta.dir, "..");
const learningRoot = resolve(webRoot, "components", "Learning");
const files = [
  "CourseStudio.tsx",
  "GenerationReview.tsx",
  "LearningPlayer.tsx",
  "TaskRenderer.tsx",
  "SourceEvidence.tsx",
].map((name) => resolve(learningRoot, name));

describe("Course Studio and Learning Player module boundary", () => {
  test("keeps the product states in explicit modules", () => {
    for (const file of files) expect(existsSync(file), `missing ${file}`).toBe(true);
  });

  test("integrates both states into the approved learning shell", () => {
    const shell = readFileSync(resolve(learningRoot, "LearningShell.tsx"), "utf8");

    expect(shell).toContain("CourseStudio");
    expect(shell).toContain("LearningPlayer");
    expect(shell).toContain("studio");
    expect(shell).toContain("player");
  });
});
