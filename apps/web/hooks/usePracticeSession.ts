'use client'

import { useCallback, useEffect, useState } from 'react'
import { useLHSession } from '@components/Contexts/LHSessionContext'
import {
  answerPractice,
  askPracticeTutor,
  currentPractice,
  CANVAS_SUBMITTED_MESSAGE,
  hintPractice,
  hintText,
  openPracticeCanvas,
  startPractice,
  type PracticeAnswer,
  type PracticeTurn,
} from '@/services/learning/practice'

export interface PracticeState {
  turn: PracticeTurn | null
  // The engine answers with the next task already chosen; it waits here until "next".
  pending?: PracticeTurn | null
  hint?: string
  tutor?: { answer: string; nextStep: string }
  // Drawing page of the current canvas task, and whether the drawing was submitted there.
  canvas?: { taskId: string; url: string; submitted: boolean }
  busy: boolean
  error?: string
}

/** Practice session of the signed-in person, through the LearnHouse backend. */
export function usePracticeSession(courseId: string | null) {
  const session = useLHSession() as any
  const token = session?.data?.tokens?.access_token as string | undefined
  const [state, setState] = useState<PracticeState>({ turn: null, busy: false })

  // Another course: its own session.
  useEffect(() => {
    setState({ turn: null, busy: false })
  }, [courseId])

  const run = useCallback(async (work: () => Promise<Partial<PracticeState>>) => {
    setState((s) => ({ ...s, busy: true, error: undefined }))
    try {
      const update = await work()
      setState((s) => ({ ...s, ...update, busy: false }))
    } catch (error) {
      setState((s) => ({ ...s, busy: false, error: error instanceof Error ? error.message : 'Fehler' }))
    }
  }, [])

  const start = useCallback((mode: 'training' | 'exam') => run(async () => {
    if (!courseId) throw new Error('Kein Kurs ausgewählt')
    const started = await startPractice(courseId, mode, token)
    const sessionId = started.result.session?.session_id
    if (!sessionId) throw new Error('Die Sitzung konnte nicht gestartet werden.')
    const next = await currentPractice(sessionId, token)
    return { turn: next.result.session ?? started.result.session ?? null, hint: undefined, tutor: undefined, canvas: undefined }
  }), [courseId, run, token])

  const submit = useCallback((answer: PracticeAnswer) => run(async () => {
    const turn = state.turn
    if (!turn) throw new Error('Keine aktive Sitzung')
    const reply = await answerPractice(turn.session_id, turn.session_revision, answer, token)
    const after = reply.result.session ?? turn
    // Keep the answered task on screen with its feedback; the next one waits.
    return { turn: { ...after, task: turn.task, state: after.state === 'active' ? 'active' : turn.state }, pending: after, hint: undefined }
  }), [run, state.turn, token])

  const next = useCallback(() => run(async () => {
    const turn = state.turn
    if (!turn) throw new Error('Keine aktive Sitzung')
    const fresh = state.pending ?? (await currentPractice(turn.session_id, token)).result.session ?? turn
    return { turn: { ...fresh, feedback: null }, pending: null, hint: undefined, tutor: undefined, canvas: undefined }
  }), [run, state.pending, state.turn, token])

  const openCanvas = useCallback(() => run(async () => {
    const turn = state.turn
    if (!turn?.task) throw new Error('Keine offene Aufgabe')
    const opened = await openPracticeCanvas(turn.session_id, turn.task.id, token)
    return { canvas: { taskId: turn.task.id, url: opened.page_url, submitted: false } }
  }), [run, state.turn, token])

  // The drawing page (another origin) reports the submission; only that page counts.
  useEffect(() => {
    const canvas = state.canvas
    if (!canvas || canvas.submitted) return
    const origin = new URL(canvas.url).origin
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== origin || event.data?.type !== CANVAS_SUBMITTED_MESSAGE) return
      setState((s) => (s.canvas ? { ...s, canvas: { ...s.canvas, submitted: true } } : s))
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [state.canvas])

  const hint = useCallback(() => run(async () => {
    const turn = state.turn
    if (!turn?.task) throw new Error('Keine offene Aufgabe')
    const reply = await hintPractice(turn.session_id, turn.task.id, token)
    return { hint: hintText(reply.result.hint) ?? 'Kein Hinweis verfügbar.' }
  }), [run, state.turn, token])

  const ask = useCallback((question: string) => run(async () => {
    const turn = state.turn
    if (!turn || !courseId) throw new Error('Starte zuerst eine Lernsitzung.')
    const reply = await askPracticeTutor(turn.session_id, courseId, question, token)
    const tutor = reply.result.tutor
    if (!tutor) throw new Error('Der Tutor hat nicht geantwortet.')
    // The tutor cites sources by internal keys (S1, S2); the learner sees the evidence instead.
    const plain = (text: string) => text.replace(/\s*\((?:S\d+(?:,\s*)?)+\)/g, '').replace(/\bS\d+\b/g, 'der Quelle')
    return { tutor: { answer: plain(tutor.answer), nextStep: plain(tutor.next_step) } }
  }), [courseId, run, state.turn, token])

  return { state, start, submit, next, hint, ask, openCanvas, signedIn: Boolean(token) }
}
