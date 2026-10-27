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
}

export interface PracticeFeedback {
  state: 'correct' | 'incorrect' | 'partial' | 'needs_review'
  score: number
  mastery_applied?: boolean
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

export type PracticeAnswer = { choice_id: string } | { choice_ids: string[] } | { text: string }

async function call<T = PracticeReply>(path: string, method: 'GET' | 'POST', token: string | undefined, body?: unknown): Promise<T> {
  const response = await secureFetch(
    `${getAPIUrl()}learning/practice/${path}`,
    RequestBodyWithAuthHeader(method, body ?? null, null, token),
  )
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : 'Die Übung ist gerade nicht erreichbar.'
    throw new Error(detail)
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
export const playerToken = (token?: string) => call<{ token: string }>('player-token', 'GET', token)

// One person token per page: every sequence player embedded on a lesson page shares it;
// when the backend refuses, the players are embedded without one (answers then count for
// the shared learner, as before).
let personTokenRequest: Promise<string> | null = null
let personTokenFor: string | undefined
export function playerTokenOnce(token?: string): Promise<string> {
  if (!personTokenRequest || personTokenFor !== token) {
    personTokenFor = token
    personTokenRequest = playerToken(token)
      .then((reply) => reply.token)
      .catch(() => {
        personTokenRequest = null
        return ''
      })
  }
  return personTokenRequest
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

/** Source refs are JSON with heading and text; the title is the heading. */
export function evidenceTitle(ref: string): { title: string; locator?: string } {
  try {
    const parsed = JSON.parse(ref)
    const heading = parsed?.locator?.heading ?? parsed?.locator?.section
    const content = typeof parsed?.content === 'string' ? parsed.content : undefined
    return { title: typeof heading === 'string' ? heading : 'Kursmaterial', locator: content?.slice(0, 160) }
  } catch {
    return { title: 'Kursmaterial' }
  }
}
