// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { afterEach, describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import {
  einladungAnnehmen,
  einladungLesen,
  kontoAnlegen,
  kontoAnlegenUndAnmelden,
  zielNachEinloesung,
} from '@/services/learning/verwaltung'
import { EinladungAnsicht, kontoAusFormular, type EinladungAnsichtProps } from './Einladung'

const originalFetch = globalThis.fetch
afterEach(() => {
  globalThis.fetch = originalFetch
})

function antwortet(status: number, body: unknown, headers?: Record<string, string>): string[] {
  const urls: string[] = []
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    urls.push(String(input))
    return new Response(JSON.stringify(body), { status, headers })
  }) as typeof fetch
  return urls
}

const info = { art: 'gruppe', anbieter: 'Anbieter A', kurs: 'Bruchrechnen' }

function render(props: Partial<EinladungAnsichtProps>) {
  return renderToStaticMarkup(
    <EinladungAnsicht
      angemeldet={false}
      loginHref="/login?next=%2Feinladung%2Ftok"
      onAnnehmen={() => undefined}
      onKontoAnlegen={() => undefined}
      zustand={{ art: 'bereit', info }}
      {...props}
    />,
  )
}

describe('Einladungsseite', () => {
  test('bei 410 steht der Text aus detail', async () => {
    antwortet(410, { detail: 'Dieser Einladungslink wurde zurückgezogen.', grund: 'zurueckgezogen' })

    const zustand = await einladungLesen('tok')
    expect(zustand).toEqual({ art: 'ungueltig', text: 'Dieser Einladungslink wurde zurückgezogen.' })

    const html = render({ zustand })
    expect(html).toContain('Dieser Einladungslink wurde zurückgezogen.')
    expect(html).not.toContain('Konto anlegen')
    expect(html).not.toContain('Einladung annehmen')
  })

  test('angemeldet: Knopf "Einladung annehmen" statt Formular', () => {
    const html = render({ angemeldet: true })

    expect(html).toContain('Anbieter A')
    expect(html).toContain('Bruchrechnen')
    expect(html).toContain('Einladung annehmen')
    expect(html).not.toContain('Konto anlegen')
  })

  test('nicht angemeldet: Formular "Konto anlegen" und Link zum Login mit Rücksprung', () => {
    const html = render({ angemeldet: false })

    expect(html).toContain('Konto anlegen')
    expect(html).toContain('type="email"')
    expect(html).toContain('type="password"')
    expect(html).toContain('Ich habe schon ein Konto')
    expect(html).toContain('href="/login?next=%2Feinladung%2Ftok"')
    expect(html).not.toContain('Einladung annehmen')
  })

  test('Formular fragt Vor- und Nachnamen vor dem Benutzernamen ab, mit Hinweis', () => {
    const html = render({ angemeldet: false })

    expect(html).toContain('Vorname')
    expect(html).toContain('Nachname')
    expect(html).toContain('name="vorname"')
    expect(html).toContain('name="nachname"')
    expect(html).toContain('Ihr Name wird den anderen in der Gruppe angezeigt.')
    expect(html.indexOf('name="vorname"')).toBeLessThan(html.indexOf('name="nachname"'))
    expect(html.indexOf('name="nachname"')).toBeLessThan(html.indexOf('name="username"'))
    // Optional: kein Pflichtfeld.
    expect(html).not.toMatch(/name="vorname"[^>]*required/)
    expect(html).not.toMatch(/name="nachname"[^>]*required/)
  })

  test('das Formular reicht Vor- und Nachnamen an onKontoAnlegen weiter', () => {
    const form = new FormData()
    form.set('vorname', ' Vor ')
    form.set('nachname', 'Nach ')
    form.set('email', ' person-a@example.org ')
    form.set('username', 'person-a ')
    form.set('password', ' geheim-genug ')

    expect(kontoAusFormular(form)).toEqual({
      email: 'person-a@example.org', username: 'person-a', password: ' geheim-genug ',
      vorname: 'Vor', nachname: 'Nach',
    })

    const ohneNamen = new FormData()
    ohneNamen.set('email', 'person-b@example.org')
    ohneNamen.set('username', 'person-b')
    ohneNamen.set('password', 'geheim-genug')
    expect(kontoAusFormular(ohneNamen)).toEqual({
      email: 'person-b@example.org', username: 'person-b', password: 'geheim-genug', vorname: '', nachname: '',
    })
  })

  test('Vor- und Nachname gehen bis in den API-Aufruf; leere Namen werden nicht gesendet', async () => {
    const gesendet: unknown[] = []
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      gesendet.push(JSON.parse(String(init?.body)))
      return new Response(JSON.stringify({
        org_id: 1, rolle: 'teilnehmend', gruppe_id: 3, course_id: 'kurs-a', uebergabe_url: null,
      }), { status: 200 })
    }) as typeof fetch
    const anmelden = async () => ({ ok: true })

    await kontoAnlegenUndAnmelden('tok', {
      email: 'person-a@example.org', username: 'person-a', password: 'geheim-genug',
      vorname: 'Vor', nachname: 'Nach',
    }, anmelden)
    await kontoAnlegenUndAnmelden('tok', {
      email: 'person-b@example.org', username: 'person-b', password: 'geheim-genug',
      vorname: '  ', nachname: '',
    }, anmelden)

    expect(gesendet).toEqual([
      { email: 'person-a@example.org', username: 'person-a', password: 'geheim-genug', vorname: 'Vor', nachname: 'Nach' },
      { email: 'person-b@example.org', username: 'person-b', password: 'geheim-genug' },
    ])
  })

  test('annehmen ruft die Route; weiter zur Übergabe oder, ohne sie, zur Kursübersicht', async () => {
    const urls = antwortet(200, {
      org_id: 1, rolle: 'teilnehmend', gruppe_id: 3, course_id: 'kurs-a',
      uebergabe_url: 'https://huelle.example/lernen/uebergabe/x',
    })

    const einloesung = await einladungAnnehmen('tok', 'zugang')
    expect(urls[0].endsWith('learning/einladung/tok/annehmen')).toBe(true)
    expect(zielNachEinloesung(einloesung)).toBe('https://huelle.example/lernen/uebergabe/x')
    expect(zielNachEinloesung({ ...einloesung, uebergabe_url: null })).toBe('/learning')
  })

  test('Drossel und abgeschaltetes Passwort bekommen eigene deutsche Texte', async () => {
    const konto = { email: 'person-a@example.org', username: 'person-a', password: 'geheim-genug' }

    antwortet(429, { detail: 'Too many invite attempts. Please try again in about 5 minutes.' }, { 'Retry-After': '300' })
    await expect(kontoAnlegen('tok', konto)).rejects.toThrow(
      'Zu viele Versuche. Bitte versuchen Sie es in einigen Minuten erneut.',
    )

    antwortet(403, { detail: { code: 'AUTH_METHOD_NOT_ALLOWED', message: 'This organization requires …', allowed_methods: ['google'] } })
    await expect(kontoAnlegen('tok', konto)).rejects.toThrow(
      'Für diesen Anbieter ist die Anmeldung mit Passwort abgeschaltet.',
    )

    antwortet(410, { detail: 'Dieser Einladungslink ist abgelaufen.', grund: 'abgelaufen' })
    await expect(kontoAnlegen('tok', konto)).rejects.toThrow('Dieser Einladungslink ist abgelaufen.')
  })

  test('neues Konto meldet danach über die Anmeldung des Webs an (die API setzt ihre Cookies außerhalb von https mit Secure)', async () => {
    const konto = { email: 'person-a@example.org', username: 'person-a', password: 'geheim-genug' }
    const einloesung = {
      org_id: 1, rolle: 'teilnehmend', gruppe_id: 3, course_id: 'kurs-a',
      uebergabe_url: 'https://huelle.example/lernen/uebergabe/x',
    }
    const anmeldungen: unknown[][] = []
    const anmelden = async (...args: unknown[]) => { anmeldungen.push(args); return { ok: true } }

    const urls = antwortet(200, einloesung)
    expect(await kontoAnlegenUndAnmelden('tok', konto, anmelden)).toEqual(einloesung)
    expect(urls[0].endsWith('learning/einladung/tok/konto')).toBe(true)
    expect(anmeldungen).toEqual([
      ['credentials', { redirect: false, email: 'person-a@example.org', password: 'geheim-genug' }],
    ])

    // Scheitert die Anmeldung, steht das Konto trotzdem: weiter wie bisher, die Anmeldeseite bleibt.
    antwortet(200, einloesung)
    const scheitert = async () => { throw new Error('netz') }
    expect(await kontoAnlegenUndAnmelden('tok', konto, scheitert)).toEqual(einloesung)

    // Lehnt die API ab, wird gar nicht erst angemeldet.
    anmeldungen.length = 0
    antwortet(410, { detail: 'Dieser Einladungslink ist abgelaufen.', grund: 'abgelaufen' })
    await expect(kontoAnlegenUndAnmelden('tok', konto, anmelden)).rejects.toThrow('Dieser Einladungslink ist abgelaufen.')
    expect(anmeldungen).toEqual([])
  })

  test('andere Fehler zeigen einen deutschen Allgemeintext, keine Rohdaten', async () => {
    antwortet(400, { detail: 'Email already exists' })
    const konto = { email: 'person-a@example.org', username: 'person-a', password: 'geheim-genug' }

    let text = ''
    try {
      await kontoAnlegen('tok', konto)
    } catch (fehler) {
      text = fehler instanceof Error ? fehler.message : ''
    }
    expect(text).not.toContain('Email')
    expect(text).toContain('Bitte versuchen Sie es')
  })
})
