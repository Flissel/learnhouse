export type LearningIntentKind =
  | 'navigate'
  | 'open_course'
  | 'open_chapter'
  | 'open_task'
  | 'focus_answer'
  | 'open_canvas'
  | 'show_result'
  | 'show_progress'
  | 'show_error'

interface LearningIntentBase {
  version: '1'
  kind: LearningIntentKind
  aggregate_id: string
  aggregate_revision: number
}

export interface NavigateIntent extends LearningIntentBase {
  kind: 'navigate'
  route: string
}

export interface OpenCourseIntent extends LearningIntentBase {
  kind: 'open_course'
  course_id: string
}

export interface OpenChapterIntent extends LearningIntentBase {
  kind: 'open_chapter'
  course_id: string
  chapter_id: string
}

export interface OpenTaskIntent extends LearningIntentBase {
  kind: 'open_task'
  session_id: string
  task_id: string
}

export interface FocusAnswerIntent extends LearningIntentBase {
  kind: 'focus_answer'
  field_id: string
}

export interface OpenCanvasIntent extends LearningIntentBase {
  kind: 'open_canvas'
  activity_id: string
  canvas_revision: number
}

export interface ShowResultIntent extends LearningIntentBase {
  kind: 'show_result'
  result_id: string
}

export interface ShowProgressIntent extends LearningIntentBase {
  kind: 'show_progress'
  course_id: string
}

export interface ShowErrorIntent extends LearningIntentBase {
  kind: 'show_error'
  error_code: string
}

export type LearningIntent =
  | NavigateIntent
  | OpenCourseIntent
  | OpenChapterIntent
  | OpenTaskIntent
  | FocusAnswerIntent
  | OpenCanvasIntent
  | ShowResultIntent
  | ShowProgressIntent
  | ShowErrorIntent

export interface LearningIntentEvent {
  eventId: string
  intent: LearningIntent
}

export interface UnknownIntentRecord {
  code: 'malformed_intent' | 'unknown_kind' | 'malformed_event'
  kind?: string
}

interface DecodeOptions {
  recordUnknown?: (_record: UnknownIntentRecord) => void
}

export type LearningRevisionSnapshot = Readonly<Record<string, number>>
export type ProjectionStatus = 'applied' | 'stale' | 'duplicate'

export interface ProjectionResult {
  status: ProjectionStatus
  intent?: LearningIntent
}

const intentKinds: ReadonlySet<string> = new Set<LearningIntentKind>([
  'navigate',
  'open_course',
  'open_chapter',
  'open_task',
  'focus_answer',
  'open_canvas',
  'show_result',
  'show_progress',
  'show_error',
])

const safeToken = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const maximumRememberedEvents = 512

const variantKeys: Record<LearningIntentKind, ReadonlySet<string>> = {
  navigate: new Set(['version', 'kind', 'aggregate_id', 'aggregate_revision', 'route']),
  open_course: new Set(['version', 'kind', 'aggregate_id', 'aggregate_revision', 'course_id']),
  open_chapter: new Set([
    'version',
    'kind',
    'aggregate_id',
    'aggregate_revision',
    'course_id',
    'chapter_id',
  ]),
  open_task: new Set([
    'version',
    'kind',
    'aggregate_id',
    'aggregate_revision',
    'session_id',
    'task_id',
  ]),
  focus_answer: new Set(['version', 'kind', 'aggregate_id', 'aggregate_revision', 'field_id']),
  open_canvas: new Set([
    'version',
    'kind',
    'aggregate_id',
    'aggregate_revision',
    'activity_id',
    'canvas_revision',
  ]),
  show_result: new Set(['version', 'kind', 'aggregate_id', 'aggregate_revision', 'result_id']),
  show_progress: new Set(['version', 'kind', 'aggregate_id', 'aggregate_revision', 'course_id']),
  show_error: new Set(['version', 'kind', 'aggregate_id', 'aggregate_revision', 'error_code']),
}

export function decodeLearningIntent(
  value: unknown,
  options: DecodeOptions = {},
): LearningIntent | null {
  if (!isRecord(value)) {
    options.recordUnknown?.({ code: 'malformed_intent' })
    return null
  }

  const rawKind = value.kind
  const recordedKind = typeof rawKind === 'string' && /^[a-z_]{1,64}$/.test(rawKind)
    ? rawKind
    : undefined
  if (typeof rawKind !== 'string' || !intentKinds.has(rawKind)) {
    options.recordUnknown?.({ code: 'unknown_kind', ...(recordedKind ? { kind: recordedKind } : {}) })
    return null
  }
  const kind = rawKind as LearningIntentKind

  if (
    !hasExactKeys(value, variantKeys[kind])
    || value.version !== '1'
    || !isSafeToken(value.aggregate_id)
    || !isRevision(value.aggregate_revision)
    || !variantPayloadIsValid(kind, value)
  ) {
    options.recordUnknown?.({ code: 'malformed_intent', kind })
    return null
  }

  return value as unknown as LearningIntent
}

export class LearningIntentProjector {
  private readonly revisions = new Map<string, number>()
  private readonly eventIds = new Set<string>()
  private readonly eventOrder: string[] = []

  constructor(snapshot: LearningRevisionSnapshot) {
    for (const [key, revision] of Object.entries(snapshot)) {
      if (!key || !isRevision(revision)) throw new Error('malformed API revision snapshot')
      this.revisions.set(key, revision)
    }
  }

  apply(event: LearningIntentEvent): ProjectionResult {
    if (this.eventIds.has(event.eventId)) return { status: 'duplicate' }

    this.rememberEvent(event.eventId)
    const key = aggregateKey(event.intent)
    const renderedRevision = this.revisions.get(key) ?? -1
    if (event.intent.aggregate_revision < renderedRevision) return { status: 'stale' }

    this.revisions.set(key, event.intent.aggregate_revision)
    return { status: 'applied', intent: event.intent }
  }

  snapshot(): LearningRevisionSnapshot {
    return Object.fromEntries(this.revisions)
  }

  private rememberEvent(eventId: string) {
    if (!isSafeToken(eventId)) throw new Error('malformed UI event id')
    this.eventIds.add(eventId)
    this.eventOrder.push(eventId)
    if (this.eventOrder.length <= maximumRememberedEvents) return
    const oldest = this.eventOrder.shift()
    if (oldest) this.eventIds.delete(oldest)
  }
}

export async function reconstructLearningProjection(
  loadSnapshot: () => Promise<unknown>,
): Promise<LearningIntentProjector> {
  return new LearningIntentProjector(decodeLearningRevisionSnapshot(await loadSnapshot()))
}

export function decodeLearningRevisionSnapshot(value: unknown): LearningRevisionSnapshot {
  if (!isRecord(value)) throw new Error('malformed API revision snapshot')

  const snapshot: Record<string, number> = {}
  for (const [key, revision] of Object.entries(value)) {
    if (!safeAggregateKey(key) || !isRevision(revision)) {
      throw new Error('malformed API revision snapshot')
    }
    snapshot[key] = revision
  }
  return snapshot
}

interface ConsumeIntentStreamOptions {
  endpoint: string
  token: string
  signal: AbortSignal
  onEvent: (_event: LearningIntentEvent) => void
  onOpen?: () => void
  fetcher?: typeof fetch
  lastEventId?: string
  recordUnknown?: (_record: UnknownIntentRecord) => void
}

export async function consumeLearningIntentStream({
  endpoint,
  token,
  signal,
  onEvent,
  onOpen,
  fetcher = fetch,
  lastEventId,
  recordUnknown,
}: ConsumeIntentStreamOptions): Promise<void> {
  validateLoopbackEndpoint(endpoint)
  validateRuntimeToken(token)
  if (lastEventId !== undefined && !isSafeToken(lastEventId)) {
    throw new Error('malformed last UI event id')
  }

  const response = await fetcher(endpoint, {
    method: 'GET',
    headers: {
      Accept: 'text/event-stream',
      Authorization: `Bearer ${token}`,
      ...(lastEventId ? { 'Last-Event-ID': lastEventId } : {}),
    },
    cache: 'no-store',
    credentials: 'omit',
    redirect: 'error',
    signal,
  })
  if (!response.ok || !response.body) throw new Error('UI intent stream unavailable')
  if (!response.headers.get('Content-Type')?.toLowerCase().startsWith('text/event-stream')) {
    throw new Error('UI intent stream returned an invalid content type')
  }
  onOpen?.()

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (!signal.aborted) {
    const chunk = await reader.read()
    if (chunk.done) break
    buffer += decoder.decode(chunk.value, { stream: true }).replace(/\r\n/g, '\n')
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      parseSseBlock(block, onEvent, recordUnknown)
      boundary = buffer.indexOf('\n\n')
    }
  }
}

interface ReconnectLoopOptions {
  signal: AbortSignal
  connect: () => Promise<void>
  sleep?: (_milliseconds: number, _signal: AbortSignal) => Promise<void>
  onState?: (_state: 'connecting' | 'reconnecting') => void
}

export async function runLearningIntentReconnectLoop({
  signal,
  connect,
  sleep = abortableSleep,
  onState,
}: ReconnectLoopOptions): Promise<void> {
  let failures = 0
  onState?.('connecting')
  while (!signal.aborted) {
    try {
      await connect()
    } catch {
      if (signal.aborted) return
    }
    if (signal.aborted) return

    onState?.('reconnecting')
    const delay = Math.min(500 * (2 ** failures), 5_000)
    failures = Math.min(failures + 1, 4)
    try {
      await sleep(delay, signal)
    } catch {
      if (signal.aborted) return
      throw new Error('UI intent reconnect delay failed')
    }
  }
}

export function focusTargetForIntent(intent: LearningIntent): string | null {
  return intent.kind === 'focus_answer' ? intent.field_id : null
}

function parseSseBlock(
  block: string,
  onEvent: (_event: LearningIntentEvent) => void,
  recordUnknown?: (_record: UnknownIntentRecord) => void,
) {
  let eventId: string | null = null
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('id:')) eventId = line.slice(3).trim()
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  if (!eventId || !isSafeToken(eventId) || data.length === 0) {
    recordUnknown?.({ code: 'malformed_event' })
    return
  }

  let value: unknown
  try {
    value = JSON.parse(data.join('\n'))
  } catch {
    recordUnknown?.({ code: 'malformed_event' })
    return
  }
  const intent = decodeLearningIntent(value, { recordUnknown })
  if (intent) onEvent({ eventId, intent })
}

function variantPayloadIsValid(kind: LearningIntentKind, value: Record<string, unknown>): boolean {
  switch (kind) {
    case 'navigate':
      return typeof value.route === 'string'
        && value.route.length <= 512
        && /^\/learning(?:\/.*)?$/.test(value.route)
    case 'open_course':
      return isUuid(value.course_id)
    case 'open_chapter':
      return isUuid(value.course_id) && isUuid(value.chapter_id)
    case 'open_task':
      return isUuid(value.session_id) && isUuid(value.task_id)
    case 'focus_answer':
      return isSafeToken(value.field_id)
    case 'open_canvas':
      return isUuid(value.activity_id) && isRevision(value.canvas_revision)
    case 'show_result':
      return isUuid(value.result_id)
    case 'show_progress':
      return isUuid(value.course_id)
    case 'show_error':
      return isSafeToken(value.error_code)
  }
}

function aggregateKey(intent: LearningIntent): string {
  const prefix: Record<LearningIntentKind, string> = {
    navigate: 'navigation',
    open_course: 'course',
    open_chapter: 'chapter',
    open_task: 'task',
    focus_answer: 'session',
    open_canvas: 'activity',
    show_result: 'result',
    show_progress: 'progress',
    show_error: 'error',
  }
  return `${prefix[intent.kind]}:${intent.aggregate_id}`
}

function validateLoopbackEndpoint(value: string) {
  let endpoint: URL
  try {
    endpoint = new URL(value)
  } catch {
    throw new Error('UI intent endpoint must be a loopback URL')
  }
  const loopbackHosts = new Set(['127.0.0.1', 'localhost', '[::1]'])
  if (endpoint.protocol !== 'http:' || !loopbackHosts.has(endpoint.hostname)) {
    throw new Error('UI intent endpoint must be an http loopback URL')
  }
}

function validateRuntimeToken(value: string) {
  if (value.length < 32 || value.length > 512 || value.trim() !== value) {
    throw new Error('UI intent runtime token is invalid')
  }
}

function abortableSleep(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, milliseconds)
    signal.addEventListener('abort', () => {
      window.clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    }, { once: true })
  })
}

function hasExactKeys(value: Record<string, unknown>, expected: ReadonlySet<string>): boolean {
  const keys = Object.keys(value)
  return keys.length === expected.size && keys.every((key) => expected.has(key))
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isRevision(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

function isSafeToken(value: unknown): value is string {
  return typeof value === 'string' && safeToken.test(value)
}

function safeAggregateKey(value: string): boolean {
  return /^(navigation|course|chapter|task|session|activity|result|progress|error):[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value)
}

function isUuid(value: unknown): value is string {
  return typeof value === 'string' && uuid.test(value)
}
