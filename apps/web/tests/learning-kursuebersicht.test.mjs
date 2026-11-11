import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const webRoot = resolve(import.meta.dir, "..");
const learningRoot = resolve(webRoot, "components", "Learning");

const service = resolve(webRoot, "services", "learning", "verwaltung.ts");
const kursuebersicht = resolve(learningRoot, "Kursuebersicht.tsx");
const verwaltung = resolve(learningRoot, "Verwaltung.tsx");
const einladung = resolve(learningRoot, "Einladung.tsx");
const einladungPage = resolve(webRoot, "app", "einladung", "[token]", "page.tsx");
const learningPage = resolve(webRoot, "app", "orgs", "[orgslug]", "(withmenu)", "learning", "page.tsx");
const spaceRail = resolve(learningRoot, "SpaceRail.tsx");

const neueDateien = [service, kursuebersicht, verwaltung, einladung, einladungPage];

describe("Lernfläche Teil B: Kursübersicht, Einladung, Verwaltung im Web", () => {
  test("legt die Bausteine als eigene Module an", () => {
    for (const file of neueDateien) {
      expect(existsSync(file), `missing ${file}`).toBe(true);
    }
  });

  test("die Lernseite steigt mit der Kursübersicht ein und behält den Browser-Arbeitsplatz", () => {
    const route = readFileSync(learningPage, "utf8");

    expect(route).toContain("Kursuebersicht");
    expect(route).toContain("LearningShell");
  });

  test("übernimmt die festgelegten Texte wörtlich", () => {
    const source = readFileSync(service, "utf8");

    expect(source).not.toContain("kommt in einem späteren Schritt");
    expect(source).toContain("Gruppenfläche öffnen");
    expect(source).toContain("Auf der Fläche lernen");
    expect(source).toContain("learning/${pfad}");
    expect(source).toContain("anfrage('uebergabe', 'POST'");
  });

  test("Einladungslinks /einladung/<token> erreichen die eigene Seite statt der Anbieter-Weiche", () => {
    const proxy = readFileSync(resolve(webRoot, "proxy.ts"), "utf8");

    expect(proxy).toContain("pathname.startsWith('/einladung/')");
  });

  test("der Verwaltungs-Eintrag der Leiste hängt an einer eigenen Adresse", () => {
    const rail = readFileSync(spaceRail, "utf8");

    expect(rail).toContain("verwaltungHref");
    expect(rail).toContain("Verwaltung");
  });

  test("Links und Fehler landen weder im Browser-Speicher noch im Log", () => {
    for (const file of neueDateien) {
      const source = readFileSync(file, "utf8");
      expect(source, file).not.toContain("localStorage");
      expect(source, file).not.toContain("sessionStorage");
      expect(source, file).not.toContain("console.");
    }
  });
});
