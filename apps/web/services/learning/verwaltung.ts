import { getAPIUrl } from '@services/config/config'
import { RequestBodyWithAuthHeader, secureFetch } from '@services/utils/ts/requests'

/**
 * Lernfläche Teil B: course overview, invitation links, groups and people.
 *
 * Every call goes to the LearnHouse backend (`/learning/...`); it holds all rights and
 * protection rules. Invitation URLs come back only once, to their creator: they are shown
 * and copied, never stored or logged here.
 */

export const KNOPF_GRUPPENFLAECHE = 'Gruppenfläche öffnen'
export const KNOPF_FLAECHE = 'Auf der Fläche lernen'
export const UEBERSICHT_WEG = 'Die Kursübersicht ist gerade nicht erreichbar. Bitte versuchen Sie es gleich noch einmal.'
export const ALLGEMEINER_FEHLER = 'Das hat gerade nicht geklappt. Bitte versuchen Sie es noch einmal.'
export const ZU_VIELE_VERSUCHE = 'Zu viele Versuche. Bitte versuchen Sie es in einigen Minuten erneut.'
export const PASSWORT_ABGESCHALTET = 'Für diesen Anbieter ist die Anmeldung mit Passwort abgeschaltet.'

/** Where a person lands when there is no hand-over to the Lern-Hülle. */
export const KURSUEBERSICHT_PFAD = '/learning'

export type Rolle = 'root' | 'admin' | 'kursleiter' | 'teilnehmend'

export interface KursGruppe {
  id: number
  name: string
}

export interface Kurs {
  course_id: string
  course_uuid: string
  titel: string
  gruppen: KursGruppe[]
  /** The provider the course belongs to (groups are created per provider). */
  org_id: number
}

export interface AnbieterRolle {
  org_id: number
  org_name: string
  rolle: Rolle
}

export interface Kursuebersicht {
  kurse: Kurs[]
  rollen: AnbieterRolle[]
}

export interface LinkErzeugt {
  link_id: number
  url: string
  laeuft_ab: string | null
}

export interface AktiverLink {
  link_id: number
  art: string
  gruppe_id: number | null
  gruppe: string | null
  erstellt_am: string
  laeuft_ab: string | null
  /** Group links only: members now; null (or missing) for other links. */
  mitglieder?: number | null
  /** Group links only: how many people the group surface of the course holds; null when unknown. */
  kapazitaet?: number | null
}

export interface GruppeErzeugt {
  gruppe_id: number
  url: string
}

export interface Person {
  user_id: number
  anzeigename: string
  rolle: Rolle
  gruppen: string[]
}

export interface EinladungInfo {
  art: string
  anbieter: string
  kurs: string | null
}

export interface Einloesung {
  org_id: number
  rolle: Rolle
  gruppe_id: number | null
  course_id: string | null
  uebergabe_url: string | null
}

export interface KontoDaten {
  email: string
  username: string
  password: string
  /** Optional; shown to the group instead of the username. Empty means not set. */
  vorname?: string
  nachname?: string
}

export type EinladungZustand =
  | { art: 'bereit'; info: EinladungInfo }
  | { art: 'ungueltig'; text: string }
  | { art: 'fehler'; text: string }

/** An API refusal carrying the text a person may read. */
export class LernFehler extends Error {
  readonly status: number

  constructor(status: number, text: string) {
    super(text)
    this.name = 'LernFehler'
    this.status = status
  }
}

const VERWALTENDE: ReadonlySet<Rolle> = new Set<Rolle>(['root', 'admin', 'kursleiter'])

/** Admins, course leaders and root manage; participants never see the management area. */
export function darfVerwalten(rollen: readonly AnbieterRolle[]): boolean {
  return rollen.some((eintrag) => VERWALTENDE.has(eintrag.rolle))
}

export function verwaltbareAnbieter(rollen: readonly AnbieterRolle[]): AnbieterRolle[] {
  return rollen.filter((eintrag) => VERWALTENDE.has(eintrag.rolle))
}

/** After redeeming a link: straight to the own Lern-Hülle, or to the course overview. */
export function zielNachEinloesung(einloesung: Pick<Einloesung, 'uebergabe_url'>): string {
  return einloesung.uebergabe_url ?? KURSUEBERSICHT_PFAD
}

/** How full a group is: "n von höchstens N Personen", or "n Personen" while the limit is unknown. */
export function belegungText(link: Pick<AktiverLink, 'mitglieder' | 'kapazitaet'>): string | null {
  const n = link.mitglieder
  if (n === null || n === undefined) return null
  const hoechstens = link.kapazitaet
  if (hoechstens === null || hoechstens === undefined) return `${n} ${n === 1 ? 'Person' : 'Personen'}`
  return `${n} von höchstens ${hoechstens} ${hoechstens === 1 ? 'Person' : 'Personen'}`
}

/** The text to show for anything a call threw: only texts meant for people get through. */
export function meldungAus(fehler: unknown): string {
  return fehler instanceof LernFehler ? fehler.message : ALLGEMEINER_FEHLER
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * The text for a refused call. 403 and 410 carry a German `detail` written for people and
 * are shown as they are; throttling and a provider without password sign-in get their own
 * text; everything else a short general one (no raw server data).
 */
export function fehlerText(status: number, body: unknown): string {
  if (status === 429) return ZU_VIELE_VERSUCHE
  const detail = isRecord(body) ? body.detail : undefined
  if (status === 403 && isRecord(detail) && detail.code === 'AUTH_METHOD_NOT_ALLOWED') return PASSWORT_ABGESCHALTET
  if ((status === 403 || status === 410) && typeof detail === 'string' && detail.trim()) return detail
  return ALLGEMEINER_FEHLER
}

async function anfrage(
  pfad: string,
  method: 'GET' | 'POST' | 'DELETE',
  accessToken: string | undefined,
  body?: unknown,
): Promise<unknown> {
  let response: Response
  try {
    response = await secureFetch(
      `${getAPIUrl()}learning/${pfad}`,
      RequestBodyWithAuthHeader(method, body ?? null, null, accessToken),
    )
  } catch {
    throw new LernFehler(0, ALLGEMEINER_FEHLER)
  }
  if (response.status === 204) return null
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) throw new LernFehler(response.status, fehlerText(response.status, data))
  return data
}

function istString(value: unknown): value is string {
  return typeof value === 'string'
}

function istStringListe(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(istString)
}

function istRolle(value: unknown): value is Rolle {
  return value === 'root' || value === 'admin' || value === 'kursleiter' || value === 'teilnehmend'
}

function istZahl(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function istKursGruppe(value: unknown): value is KursGruppe {
  return isRecord(value) && istZahl(value.id) && istString(value.name)
}

function istKurs(value: unknown): value is Kurs {
  return isRecord(value) && istString(value.course_id) && istString(value.course_uuid)
    && istString(value.titel) && Array.isArray(value.gruppen) && value.gruppen.every(istKursGruppe) && istZahl(value.org_id)
}

function istAnbieterRolle(value: unknown): value is AnbieterRolle {
  return isRecord(value) && istZahl(value.org_id) && istString(value.org_name) && istRolle(value.rolle)
}

function istPerson(value: unknown): value is Person {
  return isRecord(value) && istZahl(value.user_id) && istString(value.anzeigename)
    && istRolle(value.rolle) && istStringListe(value.gruppen)
}

function istLeerOderZahl(value: unknown): boolean {
  return value === undefined || value === null || istZahl(value)
}

function istAktiverLink(value: unknown): value is AktiverLink {
  return isRecord(value) && istZahl(value.link_id) && istString(value.art)
    && (value.gruppe_id === null || istZahl(value.gruppe_id))
    && (value.gruppe === null || istString(value.gruppe))
    && istString(value.erstellt_am) && (value.laeuft_ab === null || istString(value.laeuft_ab))
    && istLeerOderZahl(value.mitglieder) && istLeerOderZahl(value.kapazitaet)
}

function erwarte<T>(data: unknown, pruefe: (value: unknown) => value is T): T {
  if (!pruefe(data)) throw new LernFehler(0, ALLGEMEINER_FEHLER)
  return data
}

function erwarteListe<T>(data: unknown, pruefe: (value: unknown) => value is T): T[] {
  if (!Array.isArray(data) || !data.every(pruefe)) throw new LernFehler(0, ALLGEMEINER_FEHLER)
  return data
}

function istUrlAntwort(value: unknown): value is { url: string } {
  return isRecord(value) && istString(value.url) && value.url.length > 0
}

function istLinkErzeugt(value: unknown): value is LinkErzeugt {
  return isRecord(value) && istZahl(value.link_id) && istString(value.url)
    && (value.laeuft_ab === null || istString(value.laeuft_ab))
}

function istGruppeErzeugt(value: unknown): value is GruppeErzeugt {
  return isRecord(value) && istZahl(value.gruppe_id) && istString(value.url)
}

function istEinladungInfo(value: unknown): value is EinladungInfo {
  return isRecord(value) && istString(value.art) && istString(value.anbieter)
    && (value.kurs === null || istString(value.kurs))
}

function istEinloesung(value: unknown): value is Einloesung {
  return isRecord(value) && istZahl(value.org_id) && istRolle(value.rolle)
    && (value.gruppe_id === null || istZahl(value.gruppe_id))
    && (value.course_id === null || istString(value.course_id))
    && (value.uebergabe_url === undefined || value.uebergabe_url === null || istString(value.uebergabe_url))
}

function alsEinloesung(data: unknown): Einloesung {
  const einloesung = erwarte(data, istEinloesung)
  return { ...einloesung, uebergabe_url: einloesung.uebergabe_url ?? null }
}

// --- Course overview and hand-over ------------------------------------------------------

export async function kursuebersichtLaden(accessToken?: string): Promise<Kursuebersicht> {
  const data = await anfrage('verwaltung/kursuebersicht', 'GET', accessToken)
  if (!isRecord(data)) throw new LernFehler(0, UEBERSICHT_WEG)
  return {
    kurse: erwarteListe(data.kurse, istKurs),
    rollen: erwarteListe(data.rollen, istAnbieterRolle),
  }
}

/**
 * Opens the course on the person's own Lern-Hülle: hand-over link, then navigate there.
 * With `gruppeId` the link leads to the shared group surface (the server checks membership).
 */
export async function aufDerFlaecheLernen(
  courseId: string,
  accessToken: string | undefined,
  navigieren: (url: string) => void = (url) => window.location.assign(url),
  gruppeId?: number,
): Promise<void> {
  const body = gruppeId === undefined ? { course_id: courseId } : { course_id: courseId, gruppe_id: gruppeId }
  const data = await anfrage('uebergabe', 'POST', accessToken, body)
  navigieren(erwarte(data, istUrlAntwort).url)
}

// --- Links and groups -----------------------------------------------------------------------

export async function kursleiterLinkErzeugen(orgId: number, accessToken?: string): Promise<LinkErzeugt> {
  return erwarte(await anfrage('verwaltung/links', 'POST', accessToken, { art: 'kursleiter', org_id: orgId }), istLinkErzeugt)
}

export async function linkZurueckziehen(linkId: number, accessToken?: string): Promise<void> {
  await anfrage(`verwaltung/links/${encodeURIComponent(String(linkId))}`, 'DELETE', accessToken)
}

export async function aktiveLinks(orgId: number, accessToken?: string): Promise<AktiverLink[]> {
  return erwarteListe(
    await anfrage(`verwaltung/links?org_id=${encodeURIComponent(String(orgId))}`, 'GET', accessToken),
    istAktiverLink,
  )
}

export async function gruppeAnlegen(
  orgId: number,
  courseUuid: string,
  name: string,
  accessToken?: string,
): Promise<GruppeErzeugt> {
  return erwarte(
    await anfrage('verwaltung/gruppen', 'POST', accessToken, { org_id: orgId, course_uuid: courseUuid, name }),
    istGruppeErzeugt,
  )
}

export async function gruppeSchliessen(gruppeId: number, accessToken?: string): Promise<void> {
  await anfrage(`verwaltung/gruppen/${encodeURIComponent(String(gruppeId))}/schliessen`, 'POST', accessToken)
}

// --- People ---------------------------------------------------------------------------------

export async function personenLaden(orgId: number, accessToken?: string): Promise<Person[]> {
  return erwarteListe(
    await anfrage(`verwaltung/personen?org_id=${encodeURIComponent(String(orgId))}`, 'GET', accessToken),
    istPerson,
  )
}

export async function personEntfernen(userId: number, orgId: number, accessToken?: string): Promise<void> {
  await anfrage(
    `verwaltung/personen/${encodeURIComponent(String(userId))}?org_id=${encodeURIComponent(String(orgId))}`,
    'DELETE',
    accessToken,
  )
}

// --- Invitations ----------------------------------------------------------------------------

const einladungPfad = (linkToken: string) => `einladung/${encodeURIComponent(linkToken)}`

/**
 * After a refused redemption. A 410 (withdrawn, expired, or the group is full) replaces the
 * page by its text, without form or button; anything else is a message above the form.
 */
export function nachAblehnung(fehler: unknown): { art: 'ungueltig'; text: string } | { art: 'meldung'; text: string } {
  if (fehler instanceof LernFehler && fehler.status === 410) return { art: 'ungueltig', text: fehler.message }
  return { art: 'meldung', text: meldungAus(fehler) }
}

/** What a link invites to (public). An invalid link is a state of the page, not an error. */
export async function einladungLesen(linkToken: string): Promise<EinladungZustand> {
  try {
    const data = await anfrage(einladungPfad(linkToken), 'GET', undefined)
    return { art: 'bereit', info: erwarte(data, istEinladungInfo) }
  } catch (fehler) {
    if (fehler instanceof LernFehler && fehler.status === 410) return { art: 'ungueltig', text: fehler.message }
    return { art: 'fehler', text: meldungAus(fehler) }
  }
}

export async function einladungAnnehmen(linkToken: string, accessToken?: string): Promise<Einloesung> {
  return alsEinloesung(await anfrage(`${einladungPfad(linkToken)}/annehmen`, 'POST', accessToken))
}

/** A new account through the link; the backend signs the person in with cookies. */
export async function kontoAnlegen(linkToken: string, konto: KontoDaten): Promise<Einloesung> {
  const { vorname, nachname, ...pflicht } = konto
  // Empty names are left out, so the body stays what the API accepted before the names.
  const body: Record<string, string> = { ...pflicht }
  if (vorname?.trim()) body.vorname = vorname.trim()
  if (nachname?.trim()) body.nachname = nachname.trim()
  return alsEinloesung(await anfrage(`${einladungPfad(linkToken)}/konto`, 'POST', undefined, body))
}

/** The sign-in of the web (`useAuth().signIn`), passed in so this module stays free of React. */
export type Anmelden = (
  provider: 'credentials',
  optionen: { redirect: false; email: string; password: string },
) => Promise<unknown>

/**
 * A new account through the link, then signed in through the web's own login route.
 * The API sets its cookies `Secure` outside https, so on a plain-http host (tailnet) only
 * the same-origin `/api/auth/login` session reaches the browser. If that sign-in fails,
 * the account and the redemption still stand; the login page remains the way in.
 */
export async function kontoAnlegenUndAnmelden(
  linkToken: string,
  konto: KontoDaten,
  anmelden: Anmelden,
): Promise<Einloesung> {
  const einloesung = await kontoAnlegen(linkToken, konto)
  try {
    await anmelden('credentials', { redirect: false, email: konto.email, password: konto.password })
  } catch {
    // The account exists; the person signs in on the login page instead.
  }
  return einloesung
}
