'use client'

import { useEffect, useState } from 'react'
import { ArrowRight, BookOpenCheck, Users } from 'lucide-react'
import { useLHSession } from '@components/Contexts/LHSessionContext'
import { getUriWithOrg } from '@services/config/config'
import {
  aufDerFlaecheLernen,
  darfVerwalten,
  GRUPPE_SPAETER,
  KNOPF_FLAECHE,
  kursuebersichtLaden,
  meldungAus,
  UEBERSICHT_WEG,
  type Kurs,
  type Kursuebersicht as KursuebersichtDaten,
} from '@/services/learning/verwaltung'

import SpaceRail from './SpaceRail'
import Verwaltung from './Verwaltung'

export type KursuebersichtBereich = 'kurse' | 'verwaltung'

export type UebersichtZustand =
  | { art: 'laden' }
  | { art: 'abgemeldet' }
  | { art: 'fehler'; text: string }
  | { art: 'bereit'; daten: KursuebersichtDaten }

export interface KartenZustand {
  beschaeftigt?: boolean
  fehler?: string
}

const primaryButton =
  'inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-[#0E6B5C] px-5 font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0E6B5C]/40 disabled:opacity-50'
const textLink = 'inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-[#0E6B5C] hover:underline'

/** One course: title, groups and the one-click hand-over to the own Lern-Hülle. */
export function KursKarte({ kurs, onOeffnen, zustand }: {
  kurs: Kurs
  onOeffnen: (courseId: string) => void
  zustand?: KartenZustand
}) {
  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-2xl border border-zinc-200 bg-white p-5" data-course-id={kurs.course_id}>
      <div className="flex items-start gap-3">
        <BookOpenCheck aria-hidden="true" className="mt-1 shrink-0 text-[#0E6B5C]" size={20} />
        <h2 className="min-w-0 break-words text-lg font-bold leading-snug">{kurs.titel}</h2>
      </div>
      {kurs.gruppen.length ? (
        <div className="flex flex-col gap-2">
          <p className="flex items-center gap-2 text-sm text-zinc-700">
            <Users aria-hidden="true" size={16} />
            <span className="break-words">{kurs.gruppen.join(', ')}</span>
          </p>
          <p className="rounded-xl bg-[#E8F2EF] px-3 py-2 text-sm text-[#0E6B5C]">{GRUPPE_SPAETER}</p>
        </div>
      ) : null}
      <div className="mt-auto">
        <button
          className={primaryButton}
          disabled={zustand?.beschaeftigt === true}
          onClick={() => onOeffnen(kurs.course_id)}
          type="button"
        >
          {KNOPF_FLAECHE}
          <ArrowRight aria-hidden="true" size={16} />
        </button>
      </div>
      {zustand?.fehler ? (
        <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="alert">
          {zustand.fehler}
        </div>
      ) : null}
    </article>
  )
}

export interface KursuebersichtAnsichtProps {
  orgslug: string
  bereich: KursuebersichtBereich
  zustand: UebersichtZustand
  oeffnen: Record<string, KartenZustand>
  onOeffnen: (courseId: string) => void
  accessToken?: string
}

export function KursuebersichtAnsicht({ orgslug, bereich, zustand, oeffnen, onOeffnen, accessToken }: KursuebersichtAnsichtProps) {
  const daten = zustand.art === 'bereit' ? zustand.daten : null
  const verwalten = daten !== null && darfVerwalten(daten.rollen)
  const zeigeVerwaltung = verwalten && bereich === 'verwaltung'

  const learningHref = getUriWithOrg(orgslug, '/learning')
  const verwaltungHref = verwalten ? getUriWithOrg(orgslug, '/learning?bereich=verwaltung') : undefined

  return (
    <div className="flex min-h-[calc(100vh-4rem)] w-full min-w-0 bg-[#F6F5F1] text-[#17191C]">
      <SpaceRail
        active={zeigeVerwaltung ? 'verwaltung' : 'learning'}
        coursesHref={getUriWithOrg(orgslug, '/courses')}
        learningHref={learningHref}
        notesHref={getUriWithOrg(orgslug, '/learning/notizen')}
        verwaltungHref={verwaltungHref}
      />
      <main className="mx-auto flex w-full min-w-0 max-w-6xl flex-col gap-4 px-4 py-6 sm:px-6">
        {zeigeVerwaltung && daten ? (
          <>
            <a className={textLink} href={learningHref}>Zur Kursübersicht</a>
            <Verwaltung accessToken={accessToken} kurse={daten.kurse} rollen={daten.rollen} />
          </>
        ) : (
          <>
            <header className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h1 className="text-2xl font-extrabold tracking-tight">Meine Kurse</h1>
                <p className="text-sm text-zinc-600">Wählen Sie einen Kurs und lernen Sie auf Ihrer eigenen Fläche.</p>
              </div>
              <nav aria-label="Weitere Bereiche" className="flex flex-wrap gap-4">
                {verwaltungHref ? <a className={`${textLink} lg:hidden`} href={verwaltungHref}>Verwaltung</a> : null}
                <a className={textLink} href={getUriWithOrg(orgslug, '/learning?bereich=browser')}>Im Browser üben</a>
              </nav>
            </header>

            {zustand.art === 'laden' ? <p className="text-sm text-zinc-600">Kurse werden geladen …</p> : null}
            {zustand.art === 'abgemeldet' ? (
              <div className="rounded-2xl border border-zinc-200 bg-white px-6 py-8 text-center">
                <p className="font-semibold">Bitte melden Sie sich an, um Ihre Kurse zu sehen.</p>
                <a className={`${textLink} mt-2`} href={`/login?next=${encodeURIComponent('/learning')}`}>Zur Anmeldung</a>
              </div>
            ) : null}
            {zustand.art === 'fehler' ? (
              <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="alert">
                {zustand.text}
              </div>
            ) : null}
            {daten && daten.kurse.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-zinc-300 bg-white px-6 py-10 text-center">
                <p className="font-semibold">Ihnen ist noch kein Kurs zugeordnet.</p>
              </div>
            ) : null}
            {daten && daten.kurse.length ? (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {daten.kurse.map((kurs) => (
                  <KursKarte key={kurs.course_id} kurs={kurs} onOeffnen={onOeffnen} zustand={oeffnen[kurs.course_id]} />
                ))}
              </div>
            ) : null}
          </>
        )}
      </main>
    </div>
  )
}

/** Entry of the learning area: the person's courses, and management for those allowed. */
export default function Kursuebersicht({ orgslug, bereich }: { orgslug: string; bereich: KursuebersichtBereich }) {
  const session = useLHSession()
  const accessToken = session?.data?.tokens?.access_token
  const status = session?.status ?? 'loading'
  const [zustand, setZustand] = useState<UebersichtZustand>({ art: 'laden' })
  const [oeffnen, setOeffnen] = useState<Record<string, KartenZustand>>({})

  useEffect(() => {
    if (status !== 'authenticated') return
    let aktiv = true
    kursuebersichtLaden(accessToken)
      .then((daten) => { if (aktiv) setZustand({ art: 'bereit', daten }) })
      .catch(() => { if (aktiv) setZustand({ art: 'fehler', text: UEBERSICHT_WEG }) })
    return () => { aktiv = false }
    // Only a sign-in change reloads; a refreshed access token is the same person.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, Boolean(accessToken)])

  function oeffneKurs(courseId: string) {
    setOeffnen((alt) => ({ ...alt, [courseId]: { beschaeftigt: true } }))
    aufDerFlaecheLernen(courseId, accessToken).catch((fehler: unknown) => {
      setOeffnen((alt) => ({ ...alt, [courseId]: { fehler: meldungAus(fehler) } }))
    })
  }

  return (
    <KursuebersichtAnsicht
      accessToken={accessToken}
      bereich={bereich}
      oeffnen={oeffnen}
      onOeffnen={oeffneKurs}
      orgslug={orgslug}
      zustand={status === 'unauthenticated' ? { art: 'abgemeldet' } : zustand}
    />
  )
}
