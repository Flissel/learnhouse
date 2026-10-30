import type { RatingReply, StoredRating } from '@/lib/learning/courseRatingModel'
import { getAPIUrl } from '@services/config/config'
import { RequestBodyWithAuthHeader, secureFetch } from '@services/utils/ts/requests'

/**
 * Practice for the signed-in person in the browser (no VibeMind desktop host).
 * Every call goes through the LearnHouse backend, which forwards it to the Learning
 * engine with this person as learner; the browser never talks to the engine.
 */

export interface PracticeOption {
  id: string
  label: string
}

export interface PracticeTask {
  id: string
  type: string
  prompt: string
  options: PracticeOption[]
  source_refs: string[]
  /** Per-type extras the engine allows the learner to see (matching: left/right; fill_in: template). */
  presentation?: Record<string, unknown>
}

export interface PracticeCriterion {
  criterion_id: string
  description: string
  /** 0..1 */
  score: number
  feedback: string
}

export interface PracticeFeedback {
  state: 'correct' | 'incorrect' | 'partial' | 'needs_review'
  score: number
  mastery_applied?: boolean
  /** Per-criterion grader feedback; absent or empty for deterministic types. */
  criteria?: PracticeCriterion[]
}

export interface PracticeTurn {
  session_id: string
  session_revision: number
  state: 'active' | 'completed' | 'cancelled'
  mode: 'training' | 'exam'
  task: PracticeTask | null
  progress: { completed: number; total: number }
  feedback?: PracticeFeedback | null
  summary?: { attempted: number; correct: number; score: number } | null
}

export interface PracticeReply {
  state: string | null
  result: {
    session?: PracticeTurn
    hint?: unknown
    tutor?: { answer: string; next_step: string; source_refs?: string[] }
  }
}

export type PracticeAnswer =
  | { choice_id: string }
  | { choice_ids: string[] }
  | { text: string }
  | { order: string[] }
  | { pairs: Record<string, string> }
  | { value: number }

async function call<T = PracticeReply>(path: string, method: 'GET' | 'POST' | 'PATCH', token: string | undefined, body?: unknown): Promise<T> {
  const response = await secureFetch(
    `${getAPIUrl()}learning/practice/${path}`,
    RequestBodyWithAuthHeader(method, body ?? null, null, token),
  )
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const userMessage = typeof data?.detail?.message === 'string' ? (data.detail.message as string) : undefined
    const detail = typeof data?.detail === 'string' ? data.detail : userMessage ?? 'Die Übung ist gerade nicht erreichbar.'
    throw Object.assign(new Error(detail), { userMessage })
  }
  return data as T
}

export const startPractice = (courseId: string, mode: 'training' | 'exam', token?: string) =>
  call('sessions', 'POST', token, { course_id: courseId, mode })

export const currentPractice = (sessionId: string, token?: string) =>
  call(`sessions/${encodeURIComponent(sessionId)}`, 'GET', token)

export const answerPractice = (sessionId: string, revision: number, answer: PracticeAnswer, token?: string) =>
  call(`sessions/${encodeURIComponent(sessionId)}/answer`, 'POST', token, { revision, answer })

export const hintPractice = (sessionId: string, taskId: string, token?: string) =>
  call(`sessions/${encodeURIComponent(sessionId)}/hint`, 'POST', token, { task_id: taskId })

export const askPracticeTutor = (sessionId: string, courseId: string, question: string, token?: string) =>
  call(`sessions/${encodeURIComponent(sessionId)}/tutor?course_id=${encodeURIComponent(courseId)}`, 'POST', token, { question })

/** The signed drawing page of this person for a canvas task (served by Learning). */
export const openPracticeCanvas = (sessionId: string, activityId: string, token?: string) =>
  call<{ page_url: string }>(`sessions/${encodeURIComponent(sessionId)}/canvas`, 'POST', token, { activity_id: activityId })

/** The drawing page tells the player that the drawing was submitted. */
export interface NoteRead {
  id: string
  course_id: string
  sequence_id: string
  anchor: Record<string, unknown>
  selection: string
  explanation: string
  /** What the tutor added from outside the course; always shown as such. */
  extra: string
  extra_sources: string[]
  own_text: string
  created_at: string
  updated_at: string
}

export const listNotes = (token?: string) => call<{ notes: NoteRead[] }>('notes', 'GET', token)
export const setNoteText = (noteId: string, ownText: string, token?: string) =>
  call<NoteRead>(`notes/${encodeURIComponent(noteId)}`, 'PATCH', token, { own_text: ownText })

export type CourseRatingRead = StoredRating

export const submitCourseRating = (courseId: string, smiley: 'gut' | 'mittel' | 'schlecht', stichworte: string[], token?: string) =>
  call<unknown>('course-rating', 'POST', token, { course_id: courseId, smiley, stichworte })

export const getCourseRating = (courseId: string, token?: string) =>
  call<RatingReply>(`course-rating/${encodeURIComponent(courseId)}`, 'GET', token)

export interface PlayerPerson {
  token: string
  /** The only origin the token may be attached to (the learning-api player); null = attach nowhere. */
  origin: string | null
}

export const playerToken = (token?: string) => call<PlayerPerson>('player-token', 'GET', token)

// One person token per page: every sequence player embedded on a lesson page shares it;
// when the backend refuses, the players are embedded without one (answers then count for
// the shared learner, as before).
const NOBODY: PlayerPerson = { token: '', origin: null }
let personRequest: Promise<PlayerPerson> | null = null
let personRequestFor: string | undefined
export function playerTokenOnce(token?: string): Promise<PlayerPerson> {
  if (!personRequest || personRequestFor !== token) {
    personRequestFor = token
    personRequest = playerToken(token)
      .then((reply) => ({ token: reply.token, origin: reply.origin ?? null }))
      .catch(() => {
        personRequest = null
        return NOBODY
      })
  }
  return personRequest
}

export const CANVAS_SUBMITTED_MESSAGE = 'learning-zeichnung-abgegeben'

/** A hint arrives as text or as an object with a text field; show only text. */
export function hintText(value: unknown): string | undefined {
  if (typeof value === 'string') return value
  if (value && typeof value === 'object') {
    for (const key of ['text', 'hint', 'message']) {
      const field = (value as Record<string, unknown>)[key]
      if (typeof field === 'string') return field
    }
  }
  return undefined
}

/** A source excerpt cut at a safe place: never inside a $…$ formula, at whitespace, with an ellipsis. */
export function excerpt(content: string, max = 400): string {
  if (content.length <= max) return content
  let cut = content.slice(0, max)
  const dollars = [...cut.matchAll(/(?<!\\)\$/g)]
  if (dollars.length % 2 === 1) cut = cut.slice(0, dollars[dollars.length - 1].index)
  else {
    const space = cut.search(/\s\S*$/)
    if (space > 0) cut = cut.slice(0, space)
  }
  return `${cut.trimEnd()}…`
}

/** Source refs are JSON with heading and text; the title is the heading. */
export function evidenceTitle(ref: string): { title: string; locator?: string } {
  try {
    const parsed = JSON.parse(ref)
    const heading = parsed?.locator?.heading ?? parsed?.locator?.section
    const content = typeof parsed?.content === 'string' ? parsed.content : undefined
    return { title: typeof heading === 'string' ? heading : 'Kursmaterial', locator: content ? excerpt(content) : undefined }
  } catch {
    return { title: 'Kursmaterial' }
  }
}
