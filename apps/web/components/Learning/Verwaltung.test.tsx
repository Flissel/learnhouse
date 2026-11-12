// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { afterEach, describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import {
  aktiveLinks,
  belegungText,
  gruppeAnlegen,
  kursleiterLinkErzeugen,
  kursuebersichtLaden,
  personEntfernen,
  type AktiverLink,
  type AnbieterRolle,
  type Kurs,
} from '@/services/learning/verwaltung'
import Verwaltung, { GruppenListe, LinkAnzeige, PersonenListe } from './Verwaltung'

const kurse: Kurs[] = [{ course_id: 'kurs-a', course_uuid: 'course_kurs-a', titel: 'Bruchrechnen', gruppen: [], org_id: 1 }]
const rollen: AnbieterRolle[] = [{ org_id: 1, org_name: 'Anbieter A', rolle: 'kursleiter' }]
const kursAndererAnbieter: Kurs = {
  course_id: 'kurs-b', course_uuid: 'course_kurs-b', titel: 'Geometrie', gruppen: [], org_id: 2,
}

type Aufruf = { url: string; init?: RequestInit }

const originalFetch = globalThis.fetch
afterEach(() => {
  globalThis.fetch = originalFetch
})

function antwortet(status: number, body?: unknown): Aufruf[] {
  const aufrufe: Aufruf[] = []
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    aufrufe.push({ url: String(input), init })
    return new Response(body === undefined ? null : JSON.stringify(body), { status })
  }) as typeof fetch
  return aufrufe
}

describe('Verwaltung', () => {
  test('zeigt Gruppe anlegen, Kursleiter-Link und Personenliste', () => {
    const html = renderToStaticMarkup(<Verwaltung kurse={kurse} rollen={rollen} />)

    expect(html).toContain('data-testid="verwaltung"')
    expect(html).toContain('Gruppe anlegen')
    expect(html).toContain('Kursleiter-Link erzeugen')
    expect(html).toContain('Personen')
    expect(html).toContain('Bruchrechnen')
  })

  test('Gruppe anlegen bietet nur Kurse des gewählten Anbieters an', () => {
    const html = renderToStaticMarkup(<Verwaltung kurse={[...kurse, kursAndererAnbieter]} rollen={rollen} />)

    expect(html).toContain('value="course_kurs-a"')
    expect(html).not.toContain('Geometrie')
    expect(html).not.toContain('course_kurs-b')

    // Root with two providers starts on the first one: only its courses.
    const root = renderToStaticMarkup(
      <Verwaltung
        kurse={[kursAndererAnbieter, ...kurse]}
        rollen={[
          { org_id: 2, org_name: 'Anbieter B', rolle: 'root' },
          { org_id: 1, org_name: 'Anbieter A', rolle: 'root' },
        ]}
      />,
    )
    expect(root).toContain('value="course_kurs-b"')
    expect(root).not.toContain('value="course_kurs-a"')
  })

  test('mit Teilnehmerrolle rendert die Verwaltung nichts', () => {
    const html = renderToStaticMarkup(
      <Verwaltung kurse={kurse} rollen={[{ org_id: 1, org_name: 'Anbieter A', rolle: 'teilnehmend' }]} />,
    )

    expect(html).toBe('')
  })

  test('die Kursübersicht liest den Anbieter je Kurs und weist Antworten ohne ihn ab', async () => {
    antwortet(200, { kurse: [{ ...kurse[0] }], rollen })
    expect((await kursuebersichtLaden('zugang')).kurse[0].org_id).toBe(1)

    const { org_id: _ohne, ...ohneAnbieter } = kurse[0]
    antwortet(200, { kurse: [ohneAnbieter], rollen })
    await expect(kursuebersichtLaden('zugang')).rejects.toThrow()
  })

  test('ein neuer Link wird angezeigt und lässt sich kopieren', () => {
    const html = renderToStaticMarkup(<LinkAnzeige url="https://lernen.example/einladung/tok" />)

    expect(html).toContain('value="https://lernen.example/einladung/tok"')
    expect(html).toContain('Kopieren')
  })

  test('die Personenliste bietet "Entfernen" und zeigt Fehlertexte wörtlich', () => {
    const html = renderToStaticMarkup(
      <PersonenListe
        fehler={{ 7: 'Kursleiter können keine Admins entfernen.' }}
        onEntfernen={() => undefined}
        personen={[
          { user_id: 7, anzeigename: 'person-a', rolle: 'admin', gruppen: [] },
          { user_id: 8, anzeigename: 'person-b', rolle: 'teilnehmend', gruppen: ['Gruppe Nord'] },
        ]}
      />,
    )

    expect(html).toContain('person-a')
    expect(html).toContain('Gruppe Nord')
    expect(html).toContain('Entfernen')
    expect(html).toContain('Kursleiter können keine Admins entfernen.')
  })

  test('Entfernen ruft die Route und reicht den Text aus detail unverändert weiter', async () => {
    const aufrufe = antwortet(403, { detail: 'Der letzte Admin eines Anbieters kann nicht entfernt werden.' })

    await expect(personEntfernen(7, 1, 'zugang')).rejects.toThrow(
      'Der letzte Admin eines Anbieters kann nicht entfernt werden.',
    )
    expect(aufrufe[0].url.endsWith('learning/verwaltung/personen/7?org_id=1')).toBe(true)
    expect(aufrufe[0].init?.method).toBe('DELETE')
  })

  test('Gruppe anlegen und Kursleiter-Link schicken die erwarteten Felder', async () => {
    const gruppe = antwortet(200, { gruppe_id: 3, url: 'https://lernen.example/einladung/g' })
    expect(await gruppeAnlegen(1, 'course_kurs-a', 'Gruppe Nord', 'zugang')).toEqual({
      gruppe_id: 3, url: 'https://lernen.example/einladung/g',
    })
    expect(gruppe[0].url.endsWith('learning/verwaltung/gruppen')).toBe(true)
    expect(JSON.parse(String(gruppe[0].init?.body))).toEqual({ org_id: 1, course_uuid: 'course_kurs-a', name: 'Gruppe Nord' })

    const link = antwortet(200, { link_id: 5, url: 'https://lernen.example/einladung/k', laeuft_ab: null })
    expect((await kursleiterLinkErzeugen(1, 'zugang')).link_id).toBe(5)
    expect(JSON.parse(String(link[0].init?.body))).toEqual({ art: 'kursleiter', org_id: 1 })
  })
})

describe('Gruppenbelegung', () => {
  const gruppe = (link_id: number, name: string, mitglieder: number | null, kapazitaet: number | null): AktiverLink => ({
    link_id, art: 'gruppe', gruppe_id: link_id + 100, gruppe: name, erstellt_am: '2026-11-12T08:00:00Z',
    laeuft_ab: null, mitglieder, kapazitaet,
  })

  test('belegungText: mit Höchstzahl, ohne Höchstzahl, ohne Zahl', () => {
    expect(belegungText({ mitglieder: 3, kapazitaet: 10 })).toBe('3 von höchstens 10 Personen')
    expect(belegungText({ mitglieder: 0, kapazitaet: 1 })).toBe('0 von höchstens 1 Person')
    expect(belegungText({ mitglieder: 3, kapazitaet: null })).toBe('3 Personen')
    expect(belegungText({ mitglieder: 1 })).toBe('1 Person')
    expect(belegungText({ mitglieder: null, kapazitaet: 10 })).toBeNull()
    expect(belegungText({})).toBeNull()
  })

  test('die Gruppenliste zeigt je Gruppe "n von höchstens N Personen", unbekannt nur "n Personen"', () => {
    const html = renderToStaticMarkup(
      <GruppenListe
        gruppen={[gruppe(1, 'Montag', 3, 10), gruppe(2, 'Dienstag', 4, null)]}
        onSchliessen={() => undefined}
      />,
    )

    expect(html).toContain('Gruppe „Montag“')
    expect(html).toContain('3 von höchstens 10 Personen')
    expect(html).toContain('Gruppe „Dienstag“')
    expect(html).toContain('4 Personen')
    expect(html).not.toContain('höchstens null')
    expect(html).toContain('Gruppe schließen')
  })

  test('aktiveLinks nimmt mitglieder und kapazitaet an, auch ohne sie (ältere API)', async () => {
    antwortet(200, [
      { ...gruppe(1, 'Montag', 3, 10) },
      { link_id: 2, art: 'kursleiter', gruppe_id: null, gruppe: null, erstellt_am: '2026-11-12T08:00:00Z',
        laeuft_ab: '2026-11-19T08:00:00Z', mitglieder: null, kapazitaet: null },
      { link_id: 3, art: 'gruppe', gruppe_id: 103, gruppe: 'Alt', erstellt_am: '2026-11-12T08:00:00Z', laeuft_ab: null },
    ])
    const links = await aktiveLinks(1, 'zugang')
    expect(links.map(belegungText)).toEqual(['3 von höchstens 10 Personen', null, null])

    antwortet(200, [{ ...gruppe(1, 'Montag', 3, 10), kapazitaet: 'zehn' }])
    await expect(aktiveLinks(1, 'zugang')).rejects.toThrow('Bitte versuchen Sie es')
  })
})
