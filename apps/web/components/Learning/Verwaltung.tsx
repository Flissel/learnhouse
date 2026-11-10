'use client'

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Check, Copy } from 'lucide-react'
import {
  aktiveLinks,
  gruppeAnlegen,
  gruppeSchliessen,
  kursleiterLinkErzeugen,
  linkZurueckziehen,
  meldungAus,
  personEntfernen,
  personenLaden,
  verwaltbareAnbieter,
  type AktiverLink,
  type AnbieterRolle,
  type Kurs,
  type LinkErzeugt,
  type Person,
  type Rolle,
} from '@/services/learning/verwaltung'

interface VerwaltungProps {
  kurse: Kurs[]
  rollen: AnbieterRolle[]
  accessToken?: string
}

const ROLLEN_LABEL: Record<Rolle, string> = {
  root: 'Root',
  admin: 'Admin',
  kursleiter: 'Kursleiter',
  teilnehmend: 'Teilnehmend',
}

const sectionClass = 'flex flex-col gap-3 rounded-2xl border border-zinc-200 bg-white p-5 sm:p-6'
const headingClass = 'text-lg font-bold tracking-tight'
const primaryButton =
  'min-h-11 rounded-xl bg-[#0E6B5C] px-5 font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0E6B5C]/40 disabled:opacity-50'
const secondaryButton =
  'min-h-11 rounded-xl border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-800 hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0E6B5C]/40 disabled:opacity-50'
const fieldClass =
  'min-h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-[15px] focus:border-[#0E6B5C] focus:outline-none focus:ring-2 focus:ring-[#0E6B5C]/30'
const alertClass = 'rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900'

const datum = (iso: string | null): string => {
  if (!iso) return ''
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

function Hinweis({ text }: { text: string | null | undefined }) {
  return text ? <div className={alertClass} role="alert">{text}</div> : null
}

/** A freshly created link: shown once, copied by hand or with the button, kept nowhere. */
export function LinkAnzeige({ url, laeuftAb }: { url: string; laeuftAb?: string | null }) {
  const [kopiert, setKopiert] = useState<'nein' | 'ja' | 'fehler'>('nein')

  async function kopieren() {
    try {
      await navigator.clipboard.writeText(url)
      setKopiert('ja')
    } catch {
      setKopiert('fehler')
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-xl bg-[#E8F2EF] p-3">
      <label className="text-xs font-bold uppercase tracking-wide text-[#0E6B5C]">
        Einladungslink
        <input
          className={`${fieldClass} mt-1 font-mono text-sm normal-case tracking-normal text-zinc-900`}
          onFocus={(event) => event.currentTarget.select()}
          readOnly
          type="text"
          value={url}
        />
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <button className={secondaryButton} onClick={() => { void kopieren() }} type="button">
          <span className="inline-flex items-center gap-2">
            {kopiert === 'ja' ? <Check aria-hidden="true" size={16} /> : <Copy aria-hidden="true" size={16} />}
            {kopiert === 'ja' ? 'Kopiert' : 'Kopieren'}
          </span>
        </button>
        {laeuftAb ? <span className="text-sm text-zinc-600">Gültig bis {datum(laeuftAb)}</span> : null}
        <span aria-live="polite" className="text-sm text-amber-800">
          {kopiert === 'fehler' ? 'Kopieren hat nicht geklappt. Bitte markieren und von Hand kopieren.' : ''}
        </span>
      </div>
    </div>
  )
}

export function PersonenListe({ personen, fehler, onEntfernen, beschaeftigt }: {
  personen: Person[]
  fehler: Record<number, string>
  onEntfernen: (person: Person) => void
  beschaeftigt?: number | null
}) {
  if (personen.length === 0) return <p className="text-sm text-zinc-600">Noch keine Personen bei diesem Anbieter.</p>
  return (
    <ul className="flex flex-col divide-y divide-zinc-100">
      {personen.map((person) => (
        <li className="flex flex-col gap-2 py-3" key={person.user_id}>
          <div className="flex flex-wrap items-center gap-3">
            <div className="min-w-0 flex-1">
              <div className="break-words font-semibold">{person.anzeigename}</div>
              <div className="text-sm text-zinc-600">
                {ROLLEN_LABEL[person.rolle]}
                {person.gruppen.length ? ` · ${person.gruppen.join(', ')}` : ''}
              </div>
            </div>
            <button
              className={secondaryButton}
              disabled={beschaeftigt === person.user_id}
              onClick={() => onEntfernen(person)}
              type="button"
            >
              Entfernen
            </button>
          </div>
          <Hinweis text={fehler[person.user_id]} />
        </li>
      ))}
    </ul>
  )
}

function linkBeschreibung(link: AktiverLink): string {
  if (link.gruppe_id !== null) return `Gruppe „${link.gruppe ?? ''}“`
  if (link.art === 'kursleiter') return 'Kursleiter-Link'
  if (link.art === 'admin') return 'Admin-Link'
  return 'Einladungslink'
}

/** Management for admins, course leaders and root: groups, course-leader links, people. */
export default function Verwaltung({ kurse, rollen, accessToken }: VerwaltungProps) {
  const anbieter = verwaltbareAnbieter(rollen)
  const [orgId, setOrgId] = useState<number | null>(anbieter[0]?.org_id ?? null)

  const [personen, setPersonen] = useState<Person[] | null>(null)
  const [links, setLinks] = useState<AktiverLink[] | null>(null)
  const [ladeFehler, setLadeFehler] = useState<string | null>(null)

  const [kursUuid, setKursUuid] = useState(kurse[0]?.course_uuid ?? '')
  const [gruppenName, setGruppenName] = useState('')
  const [neueGruppe, setNeueGruppe] = useState<{ gruppe_id: number; url: string } | null>(null)
  const [gruppeFehler, setGruppeFehler] = useState<string | null>(null)

  const [neuerLink, setNeuerLink] = useState<LinkErzeugt | null>(null)
  const [linkFehler, setLinkFehler] = useState<string | null>(null)

  const [entfernenFehler, setEntfernenFehler] = useState<Record<number, string>>({})
  const [beschaeftigt, setBeschaeftigt] = useState<string | null>(null)

  const neuLaden = useCallback(async (org: number) => {
    try {
      const [personenListe, linkListe] = await Promise.all([
        personenLaden(org, accessToken),
        aktiveLinks(org, accessToken),
      ])
      setPersonen(personenListe)
      setLinks(linkListe)
      setLadeFehler(null)
    } catch (fehler) {
      setLadeFehler(meldungAus(fehler))
    }
  }, [accessToken])

  useEffect(() => {
    if (orgId !== null) void neuLaden(orgId)
  }, [orgId, neuLaden])

  function anbieterWechseln(org: number) {
    setPersonen(null)
    setLinks(null)
    setNeueGruppe(null)
    setNeuerLink(null)
    setEntfernenFehler({})
    setGruppeFehler(null)
    setLinkFehler(null)
    setOrgId(org)
  }

  async function ausfuehren(schluessel: string, arbeit: () => Promise<void>) {
    setBeschaeftigt(schluessel)
    try {
      await arbeit()
    } finally {
      setBeschaeftigt(null)
    }
  }

  function gruppeErzeugen(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (orgId === null || !kursUuid || !gruppenName.trim()) return
    void ausfuehren('gruppe', async () => {
      try {
        const gruppe = await gruppeAnlegen(orgId, kursUuid, gruppenName.trim(), accessToken)
        setNeueGruppe(gruppe)
        setGruppenName('')
        setGruppeFehler(null)
        await neuLaden(orgId)
      } catch (fehler) {
        setGruppeFehler(meldungAus(fehler))
      }
    })
  }

  function schliessen(gruppeId: number) {
    if (orgId === null) return
    void ausfuehren(`schliessen-${gruppeId}`, async () => {
      try {
        await gruppeSchliessen(gruppeId, accessToken)
        if (neueGruppe?.gruppe_id === gruppeId) setNeueGruppe(null)
        setGruppeFehler(null)
        await neuLaden(orgId)
      } catch (fehler) {
        setGruppeFehler(meldungAus(fehler))
      }
    })
  }

  function kursleiterLink() {
    if (orgId === null) return
    void ausfuehren('link', async () => {
      try {
        setNeuerLink(await kursleiterLinkErzeugen(orgId, accessToken))
        setLinkFehler(null)
        await neuLaden(orgId)
      } catch (fehler) {
        setLinkFehler(meldungAus(fehler))
      }
    })
  }

  function zurueckziehen(linkId: number) {
    if (orgId === null) return
    void ausfuehren(`zurueckziehen-${linkId}`, async () => {
      try {
        await linkZurueckziehen(linkId, accessToken)
        if (neuerLink?.link_id === linkId) setNeuerLink(null)
        setLinkFehler(null)
        await neuLaden(orgId)
      } catch (fehler) {
        setLinkFehler(meldungAus(fehler))
      }
    })
  }

  function entfernen(person: Person) {
    if (orgId === null) return
    if (!window.confirm(`${person.anzeigename} aus diesem Anbieter entfernen? Lernstand und Mappen bleiben erhalten.`)) return
    void ausfuehren(`person-${person.user_id}`, async () => {
      try {
        await personEntfernen(person.user_id, orgId, accessToken)
        setEntfernenFehler((alt) => {
          const neu = { ...alt }
          delete neu[person.user_id]
          return neu
        })
        await neuLaden(orgId)
      } catch (fehler) {
        setEntfernenFehler((alt) => ({ ...alt, [person.user_id]: meldungAus(fehler) }))
      }
    })
  }

  const offeneGruppen = (links ?? []).filter((link) => link.gruppe_id !== null)
  const personenLinks = (links ?? []).filter((link) => link.gruppe_id === null)
  const beschaeftigtePerson = beschaeftigt?.startsWith('person-') ? Number(beschaeftigt.slice('person-'.length)) : null

  return (
    <div className="flex flex-col gap-4" data-testid="verwaltung">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Verwaltung</h1>
          <p className="text-sm text-zinc-600">Gruppen, Einladungslinks und Personen Ihres Anbieters.</p>
        </div>
        {anbieter.length > 1 ? (
          <label className="flex flex-col text-sm font-semibold text-zinc-700">
            Anbieter
            <select
              className={`${fieldClass} mt-1`}
              onChange={(event) => anbieterWechseln(Number(event.target.value))}
              value={orgId ?? ''}
            >
              {anbieter.map((eintrag) => (
                <option key={eintrag.org_id} value={eintrag.org_id}>{eintrag.org_name}</option>
              ))}
            </select>
          </label>
        ) : anbieter[0] ? (
          <div className="text-sm font-semibold text-zinc-700">{anbieter[0].org_name}</div>
        ) : null}
      </header>

      <Hinweis text={ladeFehler} />

      <section aria-labelledby="gruppe-anlegen" className={sectionClass}>
        <h2 className={headingClass} id="gruppe-anlegen">Gruppe anlegen</h2>
        <form className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end" onSubmit={gruppeErzeugen}>
          <label className="flex flex-col text-sm font-semibold text-zinc-700">
            Kurs
            <select className={`${fieldClass} mt-1`} onChange={(event) => setKursUuid(event.target.value)} value={kursUuid}>
              {kurse.map((kurs) => (
                <option key={kurs.course_uuid} value={kurs.course_uuid}>{kurs.titel}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col text-sm font-semibold text-zinc-700">
            Name der Gruppe
            <input
              className={`${fieldClass} mt-1`}
              maxLength={200}
              onChange={(event) => setGruppenName(event.target.value)}
              type="text"
              value={gruppenName}
            />
          </label>
          <button
            className={primaryButton}
            disabled={beschaeftigt !== null || orgId === null || !kursUuid || !gruppenName.trim()}
            type="submit"
          >
            Gruppe anlegen
          </button>
        </form>
        <Hinweis text={gruppeFehler} />
        {neueGruppe ? <LinkAnzeige url={neueGruppe.url} /> : null}
        {offeneGruppen.length ? (
          <ul className="flex flex-col divide-y divide-zinc-100">
            {offeneGruppen.map((link) => (
              <li className="flex flex-wrap items-center gap-3 py-2" key={link.link_id}>
                <span className="min-w-0 flex-1 break-words text-sm font-semibold">{linkBeschreibung(link)}</span>
                <span className="text-xs text-zinc-500">seit {datum(link.erstellt_am)}</span>
                <button
                  className={secondaryButton}
                  disabled={beschaeftigt !== null}
                  onClick={() => { if (link.gruppe_id !== null) schliessen(link.gruppe_id) }}
                  type="button"
                >
                  Gruppe schließen
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section aria-labelledby="kursleiter-link" className={sectionClass}>
        <h2 className={headingClass} id="kursleiter-link">Kursleiter einladen</h2>
        <p className="text-sm text-zinc-600">Ein Kursleiter-Link gilt sieben Tage und lässt sich jederzeit zurückziehen.</p>
        <div>
          <button className={primaryButton} disabled={beschaeftigt !== null || orgId === null} onClick={kursleiterLink} type="button">
            Kursleiter-Link erzeugen
          </button>
        </div>
        <Hinweis text={linkFehler} />
        {neuerLink ? <LinkAnzeige laeuftAb={neuerLink.laeuft_ab} url={neuerLink.url} /> : null}
        {personenLinks.length ? (
          <ul className="flex flex-col divide-y divide-zinc-100">
            {personenLinks.map((link) => (
              <li className="flex flex-wrap items-center gap-3 py-2" key={link.link_id}>
                <span className="min-w-0 flex-1 text-sm font-semibold">{linkBeschreibung(link)}</span>
                <span className="text-xs text-zinc-500">
                  {link.laeuft_ab ? `gültig bis ${datum(link.laeuft_ab)}` : `seit ${datum(link.erstellt_am)}`}
                </span>
                <button
                  className={secondaryButton}
                  disabled={beschaeftigt !== null}
                  onClick={() => zurueckziehen(link.link_id)}
                  type="button"
                >
                  Zurückziehen
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section aria-labelledby="personen" className={sectionClass}>
        <h2 className={headingClass} id="personen">Personen</h2>
        {personen === null ? (
          ladeFehler ? null : <p className="text-sm text-zinc-600">Personen werden geladen …</p>
        ) : (
          <PersonenListe
            beschaeftigt={beschaeftigtePerson}
            fehler={entfernenFehler}
            onEntfernen={entfernen}
            personen={personen}
          />
        )}
      </section>
    </div>
  )
}
