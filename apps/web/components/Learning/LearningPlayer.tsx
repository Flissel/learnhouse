'use client'

import { useEffect, useRef } from 'react'
import { ArrowRight, ArrowUpRight, GraduationCap, Lightbulb, ShieldCheck, Trophy } from 'lucide-react'

import type { LearningCourse } from './LearningShell'
import { shouldScrollToFeedback } from '@/lib/learning/feedbackScroll'
import MathText from './MathText'
import TaskRenderer, { type LearningTask, type TaskAnswer } from './TaskRenderer'

export type LearningMode = 'training' | 'exam'

export interface LearningPlayerModel {
  mode: LearningMode
  sessionProgress: { completed: number; total: number }
  task: LearningTask | null
  feedback?: {
    state: 'correct' | 'incorrect' | 'needs_review' | 'submitted'
    message: string
    misconception?: string
    /** Criteria below 100 %, with the grader's text. */
    criteria?: Array<{ id: string; description: string; feedback: string }>
  }
  hint?: string
  // Set when the session is over: attempted, correct, overall score 0..1.
  summary?: { attempted: number; correct: number; score: number }
  busy?: boolean
  error?: string
}

interface LearningPlayerProps {
  course: LearningCourse
  model: LearningPlayerModel
  courseHref?: string | null
  onModeChange?: (_mode: LearningMode) => void
  onSubmit?: (_answer: TaskAnswer) => void
  onHint?: () => void
  onNext?: () => void
  onOpenCanvas?: () => void
  onStartSession?: () => void
  startHint?: string
}

export function emptyLearningPlayerModel(): LearningPlayerModel {
  return {
    mode: 'training',
    sessionProgress: { completed: 0, total: 0 },
    task: null,
  }
}

export default function LearningPlayer({
  course,
  model,
  courseHref,
  onModeChange,
  onSubmit,
  onHint,
  onNext,
  onOpenCanvas,
  onStartSession,
  startHint,
}: LearningPlayerProps) {
  const isTraining = model.mode === 'training'
  const answered = Boolean(model.feedback)
  const feedbackRef = useRef<HTMLElement | null>(null)
  const shownFeedback = useRef<LearningPlayerModel['feedback']>(undefined)
  const visibleFeedback = isTraining ? model.feedback : undefined
  useEffect(() => {
    if (shouldScrollToFeedback(shownFeedback.current, visibleFeedback)) {
      feedbackRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
      feedbackRef.current?.focus({ preventScroll: true })
    }
    shownFeedback.current = visibleFeedback
  }, [visibleFeedback])

  return (
    <div className="mx-auto w-full max-w-4xl min-w-0 px-5 py-6 sm:px-8 lg:px-10">
      <header className="flex min-w-0 flex-wrap items-start justify-between gap-4 border-b border-zinc-200 pb-5">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase text-emerald-700">Learning Player</p>
          <h2 className="mt-1 break-words text-xl font-semibold text-zinc-950">{course.name}</h2>
          <p className="mt-2 text-sm text-zinc-600">
            Fortschritt: {model.sessionProgress.completed} von {model.sessionProgress.total}
          </p>
          {model.sessionProgress.total > 0 ? (
            <div aria-hidden="true" className="mt-2 h-1.5 w-48 overflow-hidden rounded-full bg-zinc-200">
              <div
                className="h-1.5 rounded-full bg-emerald-600 transition-all"
                style={{ width: `${Math.min(100, (100 * model.sessionProgress.completed) / model.sessionProgress.total)}%` }}
              />
            </div>
          ) : null}
        </div>
        <div aria-label="Lernmodus" className="inline-flex rounded-md border border-zinc-300 p-1">
          <button
            aria-pressed={isTraining}
            className={`h-8 rounded px-3 text-xs font-semibold ${isTraining ? 'bg-zinc-950 text-white' : 'text-zinc-600'}`}
            onClick={() => onModeChange?.('training')}
            type="button"
          >
            Training
          </button>
          <button
            aria-pressed={!isTraining}
            className={`h-8 rounded px-3 text-xs font-semibold ${!isTraining ? 'bg-zinc-950 text-white' : 'text-zinc-600'}`}
            onClick={() => onModeChange?.('exam')}
            type="button"
          >
            Prüfung
          </button>
        </div>
      </header>

      {model.error ? (
        <p className="mt-4 border-s-4 border-amber-500 bg-amber-50 px-3 py-2 text-sm text-amber-950" role="alert">
          {model.error}
        </p>
      ) : null}

      {isTraining && model.feedback ? (
        <section ref={feedbackRef} tabIndex={-1} className="pt-6 outline-none" aria-labelledby="feedback-title">
          <div className="flex items-center gap-2">
            <ShieldCheck aria-hidden="true" className="text-teal-700" size={17} />
            <h3 className="text-sm font-semibold text-zinc-950" id="feedback-title">Quellengebundenes Feedback</h3>
          </div>
          <p className="mt-2 text-sm leading-6 text-zinc-700"><MathText math={model.task?.math} text={model.feedback.message} /></p>
          {model.feedback.misconception ? (
            <p className="mt-2 border-s-4 border-amber-500 bg-amber-50 px-3 py-2 text-sm text-amber-950">
              Fehlvorstellung: <MathText math={model.task?.math} text={model.feedback.misconception} />
            </p>
          ) : null}
          {model.feedback.criteria?.length ? (
            <ul aria-label="Kriterien" className="mt-3 space-y-2">
              {model.feedback.criteria.map((c) => (
                <li className="border-s-4 border-zinc-300 bg-zinc-50 px-3 py-2 text-sm text-zinc-800" key={c.id}>
                  <p className="font-medium"><MathText math={model.task?.math} text={c.description} /></p>
                  <p className="mt-1 leading-6 text-zinc-700"><MathText math={model.task?.math} text={c.feedback} /></p>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      <div className="py-6">
        {model.summary ? (
          <div className="border-s-4 border-emerald-500 bg-zinc-50 px-5 py-5">
            <div className="flex items-center gap-2">
              <Trophy aria-hidden="true" className="text-emerald-700" size={18} />
              <h3 className="text-base font-semibold text-zinc-950">Sitzung abgeschlossen</h3>
            </div>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              {model.summary.correct} von {model.summary.attempted} richtig ({Math.round(model.summary.score * 100)} %).
              Ihr Lernstand ist aktualisiert.
            </p>
            {onStartSession ? (
              <button className="mt-4 inline-flex h-10 items-center rounded-md bg-zinc-950 px-4 text-sm font-semibold text-white" onClick={onStartSession} type="button">
                Neue Sitzung starten
              </button>
            ) : null}
          </div>
        ) : model.task ? (
          <TaskRenderer
            disabled={model.busy || (isTraining && answered)}
            key={model.task.id}
            onOpenCanvas={onOpenCanvas}
            onSubmit={onSubmit}
            submitLabel={isTraining ? 'Antwort prüfen' : 'Antwort abgeben'}
            task={model.task}
          />
        ) : (
          <div className="border-s-4 border-emerald-500 bg-zinc-50 px-5 py-5">
            <div className="flex items-center gap-2">
              <GraduationCap aria-hidden="true" className="text-emerald-700" size={18} />
              <h3 className="text-base font-semibold text-zinc-950">Keine aktive Aufgabe</h3>
            </div>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              {startHint ?? 'Starten Sie eine Lernsitzung: Die Aufgaben werden für Ihren Lernstand ausgewählt.'}
            </p>
            <button
              className="mt-4 me-4 inline-flex h-10 items-center rounded-md bg-zinc-950 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!onStartSession || model.busy}
              onClick={onStartSession}
              type="button"
            >
              {onStartSession ? (model.busy ? 'Wird gestartet …' : 'Lernsitzung starten') : 'Bitte anmelden'}
            </button>
            {courseHref ? (
              <a className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-emerald-800" href={courseHref}>
                Kurs öffnen <ArrowUpRight aria-hidden="true" size={15} />
              </a>
            ) : null}
          </div>
        )}
      </div>

      {answered && onNext ? (
        <button
          className="mb-5 inline-flex h-10 items-center gap-2 rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
          disabled={model.busy}
          onClick={onNext}
          type="button"
        >
          Nächste Aufgabe <ArrowRight aria-hidden="true" size={16} />
        </button>
      ) : null}

      {isTraining && model.task && (model.hint || onHint) ? (
        <section className="border-t border-zinc-200 py-5">
          <button
            className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-300 px-4 text-sm font-semibold text-zinc-800 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!onHint || model.busy}
            onClick={onHint}
            type="button"
          >
            <Lightbulb aria-hidden="true" size={16} />
            Hinweis anzeigen
          </button>
          {model.hint ? <p className="mt-3 text-sm leading-6 text-zinc-600">{model.hint}</p> : null}
        </section>
      ) : null}
    </div>
  )
}
