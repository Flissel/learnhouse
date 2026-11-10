'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { LogIn, Mail } from 'lucide-react'
import { useLHSession } from '@components/Contexts/LHSessionContext'
import {
  einladungAnnehmen,
  einladungLesen,
  kontoAnlegen,
  LernFehler,
  meldungAus,
  zielNachEinloesung,
  type EinladungInfo,
  type EinladungZustand,
  type Einloesung,
  type KontoDaten,
} from '@/services/learning/verwaltung'

export interface EinladungAnsichtProps {
  zustand: EinladungZustand | { art: 'laden' }
  /** 'laden' while the session is still being checked. */
  angemeldet: boolean | 'laden'
  loginHref: string
  onAnnehmen: () => void
  onKontoAnlegen: (konto: KontoDaten) => void
  beschaeftigt?: boolean
  meldung?: string | null
}

const primaryButton =
  'inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-[#0E6B5C] px-5 font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0E6B5C]/40 disabled:opacity-50'
const fieldClass =
  'mt-1 min-h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-[15px] focus:border-[#0E6B5C] focus:outline-none focus:ring-2 focus:ring-[#0E6B5C]/30'
const alertClass = 'rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900'

function einladungsText(info: EinladungInfo): string {
  const anbieter = info.anbieter || 'diesen Anbieter'
  if (info.art === 'admin') return `Sie sind als Admin für ${anbieter} eingeladen.`
  if (info.art === 'kursleiter') return `Sie sind als Kursleiter für ${anbieter} eingeladen.`
  if (info.kurs) return `Sie sind zum Kurs „${info.kurs}“ bei ${anbieter} eingeladen.`
  return `Sie sind zu ${anbieter} eingeladen.`
}

function feld(form: FormData, name: string): string {
  const value = form.get(name)
  return typeof value === 'string' ? value : ''
}

export function EinladungAnsicht({
  zustand, angemeldet, loginHref, onAnnehmen, onKontoAnlegen, beschaeftigt = false, meldung,
}: EinladungAnsichtProps) {
  function absenden(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    onKontoAnlegen({ email: feld(form, 'email').trim(), username: feld(form, 'username').trim(), password: feld(form, 'password') })
  }

  return (
    <div className="min-h-screen bg-[#F6F5F1] px-4 py-10 text-[#17191C]">
      <div className="mx-auto flex max-w-md flex-col gap-4 rounded-2xl border border-zinc-200 bg-white p-6 sm:p-8">
        <div className="flex items-center gap-2 text-[#0E6B5C]">
          <Mail aria-hidden="true" size={20} />
          <h1 className="text-2xl font-extrabold tracking-tight text-[#17191C]">Einladung</h1>
        </div>

        {zustand.art === 'laden' ? <p className="text-sm text-zinc-600">Die Einladung wird geprüft …</p> : null}
        {zustand.art === 'ungueltig' || zustand.art === 'fehler' ? (
          <div className={alertClass} role="alert">{zustand.text}</div>
        ) : null}

        {zustand.art === 'bereit' ? (
          <>
            <p className="text-[15px] leading-relaxed">{einladungsText(zustand.info)}</p>
            {meldung ? <div className={alertClass} role="alert">{meldung}</div> : null}

            {angemeldet === 'laden' ? <p className="text-sm text-zinc-600">Anmeldung wird geprüft …</p> : null}

            {angemeldet === true ? (
              <div>
                <button className={primaryButton} disabled={beschaeftigt} onClick={onAnnehmen} type="button">
                  Einladung annehmen
                </button>
              </div>
            ) : null}

            {angemeldet === false ? (
              <>
                <form className="flex flex-col gap-3" onSubmit={absenden}>
                  <h2 className="text-lg font-bold">Konto anlegen</h2>
                  <label className="text-sm font-semibold text-zinc-700">
                    E-Mail
                    <input autoComplete="email" className={fieldClass} name="email" required type="email" />
                  </label>
                  <label className="text-sm font-semibold text-zinc-700">
                    Benutzername
                    <input autoComplete="username" className={fieldClass} maxLength={100} name="username" required type="text" />
                  </label>
                  <label className="text-sm font-semibold text-zinc-700">
                    Passwort
                    <input autoComplete="new-password" className={fieldClass} maxLength={256} name="password" required type="password" />
                  </label>
                  <button className={primaryButton} disabled={beschaeftigt} type="submit">Konto anlegen</button>
                </form>
                <a className="inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-[#0E6B5C] hover:underline" href={loginHref}>
                  <LogIn aria-hidden="true" size={16} /> Ich habe schon ein Konto
                </a>
              </>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  )
}

/** /einladung/[token]: redeem an invitation, signed in or with a new account. */
export default function Einladung({ token }: { token: string }) {
  const session = useLHSession()
  const status = session?.status ?? 'loading'
  const accessToken = session?.data?.tokens?.access_token
  const [zustand, setZustand] = useState<EinladungAnsichtProps['zustand']>({ art: 'laden' })
  const [beschaeftigt, setBeschaeftigt] = useState(false)
  const [meldung, setMeldung] = useState<string | null>(null)

  useEffect(() => {
    let aktiv = true
    einladungLesen(token).then((gelesen) => { if (aktiv) setZustand(gelesen) })
    return () => { aktiv = false }
  }, [token])

  async function einloesen(arbeit: () => Promise<Einloesung>) {
    setBeschaeftigt(true)
    setMeldung(null)
    try {
      window.location.assign(zielNachEinloesung(await arbeit()))
    } catch (fehler) {
      if (fehler instanceof LernFehler && fehler.status === 410) setZustand({ art: 'ungueltig', text: fehler.message })
      else setMeldung(meldungAus(fehler))
      setBeschaeftigt(false)
    }
  }

  return (
    <EinladungAnsicht
      angemeldet={status === 'loading' ? 'laden' : status === 'authenticated'}
      beschaeftigt={beschaeftigt}
      loginHref={`/login?next=${encodeURIComponent(`/einladung/${encodeURIComponent(token)}`)}`}
      meldung={meldung}
      onAnnehmen={() => { void einloesen(() => einladungAnnehmen(token, accessToken)) }}
      onKontoAnlegen={(konto) => { void einloesen(() => kontoAnlegen(token, konto)) }}
      zustand={zustand}
    />
  )
}
