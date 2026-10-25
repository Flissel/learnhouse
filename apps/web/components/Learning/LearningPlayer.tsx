import { ArrowUpRight, GraduationCap, Lightbulb, ShieldCheck } from 'lucide-react'

import type { LearningCourse } from './LearningShell'
import TaskRenderer, { type LearningTask } from './TaskRenderer'

export type LearningMode = 'training' | 'exam'

export interface LearningPlayerModel {
  mode: LearningMode
  sessionProgress: { completed: number; total: number }
  task: LearningTask | null
  feedback?: {
    state: 'correct' | 'incorrect' | 'needs_review'
    message: string
    misconception?: string
  }
  hint?: string
}

interface LearningPlayerProps {
  course: LearningCourse
  model: LearningPlayerModel
  courseHref?: string | null
  onModeChange?: (_mode: LearningMode) => void
  onSubmit?: (_answer: string) => void
  onHint?: () => void
  onStartSession?: () => void
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
  onStartSession,
}: LearningPlayerProps) {
  const isTraining = model.mode === 'training'

  return (
    <div className="mx-auto w-full max-w-4xl min-w-0 px-5 py-6 sm:px-8 lg:px-10">
      <header className="flex min-w-0 flex-wrap items-start justify-between gap-4 border-b border-zinc-200 pb-5">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase text-emerald-700">Learning Player</p>
          <h2 className="mt-1 break-words text-xl font-semibold text-zinc-950">{course.name}</h2>
          <p className="mt-2 text-sm text-zinc-600">
            Fortschritt: {model.sessionProgress.completed} von {model.sessionProgress.total}
          </p>
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

      <div className="py-6">
        {model.task ? (
          <TaskRenderer
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
              Öffne den bestehenden Kurs oder starte eine Sitzung über den VibeMind Learning Agent.
            </p>
            <button
              className="mt-4 me-4 inline-flex h-10 items-center rounded-md bg-zinc-950 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!onStartSession}
              onClick={onStartSession}
              type="button"
            >
              {onStartSession ? 'Lernsitzung starten' : 'VibeMind Host erforderlich'}
            </button>
            {courseHref ? (
              <a className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-emerald-800" href={courseHref}>
                Kurs öffnen <ArrowUpRight aria-hidden="true" size={15} />
              </a>
            ) : null}
          </div>
        )}
      </div>

      {isTraining && model.feedback ? (
        <section className="border-t border-zinc-200 py-5" aria-labelledby="feedback-title">
          <div className="flex items-center gap-2">
            <ShieldCheck aria-hidden="true" className="text-teal-700" size={17} />
            <h3 className="text-sm font-semibold text-zinc-950" id="feedback-title">Quellengebundenes Feedback</h3>
          </div>
          <p className="mt-2 text-sm leading-6 text-zinc-700">{model.feedback.message}</p>
          {model.feedback.misconception ? (
            <p className="mt-2 border-s-4 border-amber-500 bg-amber-50 px-3 py-2 text-sm text-amber-950">
              Fehlvorstellung: {model.feedback.misconception}
            </p>
          ) : null}
        </section>
      ) : null}

      {isTraining && model.hint ? (
        <section className="border-t border-zinc-200 py-5">
          <button
            className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-300 px-4 text-sm font-semibold text-zinc-800 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!onHint}
            onClick={onHint}
            type="button"
          >
            <Lightbulb aria-hidden="true" size={16} />
            Hinweis anzeigen
          </button>
          <p className="mt-3 text-sm leading-6 text-zinc-600">{model.hint}</p>
        </section>
      ) : null}
    </div>
  )
}
