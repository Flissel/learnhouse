// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { afterEach, describe, expect, test } from 'bun:test'
import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { aufDerFlaecheLernen, darfVerwalten, KNOPF_GRUPPENFLAECHE, type AnbieterRolle, type Kurs } from '@/services/learning/verwaltung'
import { beiRueckkehr, KursKarte, KursuebersichtAnsicht } from './Kursuebersicht'
import SpaceRail from './SpaceRail'

const kursAllein: Kurs = { course_id: 'kurs-a', course_uuid: 'course_kurs-a', titel: 'Bruchrechnen', gruppen: [], org_id: 1 }
const kursInGruppe: Kurs = { course_id: 'kurs-b', course_uuid: 'course_kurs-b', titel: 'Geometrie', gruppen: [{ id: 7, name: 'Gruppe Nord' }, { id: 9, name: 'Gruppe Süd' }], org_id: 1 }

const teilnehmend: AnbieterRolle[] = [{ org_id: 1, org_name: 'Anbieter A', rolle: 'teilnehmend' }]
const admin: AnbieterRolle[] = [{ org_id: 1, org_name: 'Anbieter A', rolle: 'admin' }]

type Props = { children?: ReactNode; onClick?: () => void; type?: string }

function buttons(node: ReactNode): ReactElement<Props>[] {
  if (Array.isArray(node)) return node.flatMap((child) => buttons(child as ReactNode))
  if (!isValidElement<Props>(node)) return []
  const own = node.type === 'button' ? [node] : []
  return [...own, ...buttons(node.props.children)]
}

const originalFetch = globalThis.fetch
afterEach(() => {
  globalThis.fetch = originalFetch
})

function ansicht(rollen: AnbieterRolle[], bereich: 'kurse' | 'verwaltung' = 'kurse') {
  return renderToStaticMarkup(
    <KursuebersichtAnsicht
      bereich={bereich}
      oeffnen={{}}
      onOeffnen={() => undefined}
      orgslug="anbieter-a"
      zustand={{ art: 'bereit', daten: { kurse: [kursAllein, kursInGruppe], rollen } }}
    />,
  )
}

describe('Kursübersicht', () => {
  test('jede Karte zeigt Titel und den Knopf "Auf der Fläche lernen"', () => {
    const html = renderToStaticMarkup(<KursKarte kurs={kursAllein} onOeffnen={() => undefined} />)

    expect(html).toContain('Bruchrechnen')
    expect(html).toContain('Auf der Fläche lernen')
    expect(html).not.toContain(KNOPF_GRUPPENFLAECHE)
  })

  test('ein Klick auf den Knopf öffnet genau diesen Kurs', () => {
    const geoeffnet: unknown[] = []
    const karte = KursKarte({ kurs: kursAllein, onOeffnen: (id, gruppe) => geoeffnet.push([id, gruppe]) })
    const knopf = buttons(karte).find((element) => renderToStaticMarkup(element).includes('Auf der Fläche lernen'))

    expect(knopf).toBeDefined()
    knopf?.props.onClick?.()
    expect(geoeffnet).toEqual([['kurs-a', undefined]])
  })

  test('das Öffnen ruft die Übergabe-Route und navigiert zur gelieferten Adresse', async () => {
    const aufrufe: Array<{ url: string; init?: RequestInit }> = []
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      aufrufe.push({ url: String(input), init })
      return new Response(JSON.stringify({ url: 'https://huelle.example/lernen/uebergabe/abc' }), { status: 200 })
    }) as typeof fetch
    const ziele: string[] = []

    await aufDerFlaecheLernen('kurs-a', 'zugang', (url) => ziele.push(url))

    expect(aufrufe).toHaveLength(1)
    expect(aufrufe[0].url.endsWith('learning/uebergabe')).toBe(true)
    expect(aufrufe[0].init?.method).toBe('POST')
    expect(JSON.parse(String(aufrufe[0].init?.body))).toEqual({ course_id: 'kurs-a' })
    expect(ziele).toEqual(['https://huelle.example/lernen/uebergabe/abc'])
  })

  test('ein verweigerter Kurs navigiert nicht und meldet den Text aus detail', async () => {
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ detail: 'Nicht erlaubt.' }), { status: 403 })) as typeof fetch
    const ziele: string[] = []

    await expect(aufDerFlaecheLernen('kurs-x', 'zugang', (url) => ziele.push(url))).rejects.toThrow('Nicht erlaubt.')
    expect(ziele).toEqual([])
  })

  test('Rückkehr per Zurück-Taste (bfcache) gibt gesperrte Knöpfe wieder frei', () => {
    const fenster = new EventTarget()
    let zurueckgesetzt = 0
    const abmelden = beiRueckkehr(
      fenster as unknown as Pick<Window, 'addEventListener' | 'removeEventListener'>,
      () => { zurueckgesetzt += 1 },
    )

    fenster.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: false }))
    expect(zurueckgesetzt).toBe(0)
    fenster.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }))
    expect(zurueckgesetzt).toBe(1)

    abmelden()
    fenster.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }))
    expect(zurueckgesetzt).toBe(1)
  })

  test('zeigt_knopf_gruppenflaeche_je_gruppe', () => {
    const html = renderToStaticMarkup(<KursKarte kurs={kursInGruppe} onOeffnen={() => undefined} />)

    expect(html).toContain('Gruppe: Gruppe Nord')
    expect(html).toContain('Gruppe: Gruppe Süd')
    expect(html.split('Gruppenfläche öffnen').length - 1).toBe(2)
    expect(KNOPF_GRUPPENFLAECHE).toBe('Gruppenfläche öffnen')
  })

  test('klick_gruppenflaeche_sendet_gruppe_id', async () => {
    const geoeffnet: unknown[] = []
    const karte = KursKarte({ kurs: kursInGruppe, onOeffnen: (id, gruppe) => geoeffnet.push([id, gruppe]) })
    const knoepfe = buttons(karte).filter((element) => renderToStaticMarkup(element).includes('Gruppenfläche öffnen'))

    expect(knoepfe).toHaveLength(2)
    knoepfe[1].props.onClick?.()
    expect(geoeffnet).toEqual([['kurs-b', 9]])

    const aufrufe: Array<{ init?: RequestInit }> = []
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      aufrufe.push({ init })
      return new Response(JSON.stringify({ url: 'https://huelle.example/x?gruppe=9' }), { status: 200 })
    }) as typeof fetch
    const ziele: string[] = []
    await aufDerFlaecheLernen('kurs-b', 'zugang', (url) => ziele.push(url), 9)
    expect(JSON.parse(String(aufrufe[0].init?.body))).toEqual({ course_id: 'kurs-b', gruppe_id: 9 })
    expect(ziele).toEqual(['https://huelle.example/x?gruppe=9'])
  })

  test('kein_gruppe_spaeter_text_mehr', () => {
    const html = renderToStaticMarkup(<KursKarte kurs={kursInGruppe} onOeffnen={() => undefined} />)

    expect(html).not.toContain('späteren Schritt')
    expect(html).not.toContain('kommt in einem')
  })

  test('Teilnehmende sehen keine Verwaltung, weder in der Leiste noch als Bereich', () => {
    expect(darfVerwalten(teilnehmend)).toBe(false)

    const html = ansicht(teilnehmend, 'verwaltung')
    expect(html).toContain('Bruchrechnen')
    expect(html).not.toContain('Verwaltung')
    expect(html).not.toContain('data-testid="verwaltung"')
  })

  test('Admins, Kursleiter und Root sehen den Eintrag und den Bereich', () => {
    expect(darfVerwalten(admin)).toBe(true)
    expect(darfVerwalten([{ org_id: 2, org_name: 'Anbieter B', rolle: 'kursleiter' }])).toBe(true)
    expect(darfVerwalten([{ org_id: 2, org_name: 'Anbieter B', rolle: 'root' }])).toBe(true)

    expect(ansicht(admin)).toContain('Verwaltung')
    expect(ansicht(admin, 'verwaltung')).toContain('data-testid="verwaltung"')
  })

  test('die Leiste zeigt "Verwaltung" nur mit eigener Adresse', () => {
    const ohne = renderToStaticMarkup(<SpaceRail coursesHref="/courses" learningHref="/learning" />)
    const mit = renderToStaticMarkup(
      <SpaceRail coursesHref="/courses" learningHref="/learning" verwaltungHref="/learning?bereich=verwaltung" />,
    )

    expect(ohne).not.toContain('Verwaltung')
    expect(mit).toContain('Verwaltung')
  })
})
