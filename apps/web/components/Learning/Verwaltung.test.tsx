// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { afterEach, describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import {
  gruppeAnlegen,
  kursleiterLinkErzeugen,
  personEntfernen,
  type AnbieterRolle,
  type Kurs,
} from '@/services/learning/verwaltung'
import Verwaltung, { LinkAnzeige, PersonenListe } from './Verwaltung'

const kurse: Kurs[] = [{ course_id: 'kurs-a', course_uuid: 'course_kurs-a', titel: 'Bruchrechnen', gruppen: [] }]
const rollen: AnbieterRolle[] = [{ org_id: 1, org_name: 'Anbieter A', rolle: 'kursleiter' }]

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
