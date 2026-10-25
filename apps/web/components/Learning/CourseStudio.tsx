import { type FormEvent } from 'react'
import { ArrowUpRight, CheckCircle2, CircleAlert, FilePlus2, Play, Upload } from 'lucide-react'

import GenerationReview, { type GenerationState } from './GenerationReview'
import type { LearningCourse } from './LearningShell'

export type CourseDifficulty = 'foundation' | 'intermediate' | 'advanced' | 'expert'
export type CourseReviewStatus = 'pending' | 'approved' | 'rejected'

export interface CourseStudioSource {
  id: string
  title: string
  state: 'queued' | 'processing' | 'ready' | 'failed'
  revision?: number
  errorCode?: string
}

export interface CourseStudioModel {
  audience: string
  outcome: string
  prerequisites: string
  difficulty: CourseDifficulty
  sources: CourseStudioSource[]
  generation: GenerationState
  reviewStatus: CourseReviewStatus
}

interface CourseStudioProps {
  course: LearningCourse
  model: CourseStudioModel
  editorHref?: string | null
  onImportSource?: (_input: { title: string; sourceUrl: string }) => void
  onStartGeneration?: () => void
  onRegenerate?: () => void
  onApprove?: () => void
  onPublish?: () => void
}

const difficultyLabels: Record<CourseDifficulty, string> = {
  foundation: 'Grundlagen',
  intermediate: 'Mittelstufe',
  advanced: 'Fortgeschritten',
  expert: 'Expertenniveau',
}

export function emptyCourseStudioModel(): CourseStudioModel {
  return {
    audience: '',
    outcome: '',
    prerequisites: '',
    difficulty: 'intermediate',
    sources: [],
    generation: {
      stage: 'idle',
      progress: 0,
      unsupportedClaims: [],
      sourceCoverage: 0,
      regenerationAttempts: 0,
      maximumRegenerationAttempts: 3,
    },
    reviewStatus: 'pending',
  }
}

export default function CourseStudio({
  course,
  model,
  editorHref,
  onImportSource,
  onStartGeneration,
  onRegenerate,
  onApprove,
  onPublish,
}: CourseStudioProps) {
  const approved = model.reviewStatus === 'approved'

  function importSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    onImportSource?.({
      title: String(form.get('sourceTitle') ?? ''),
      sourceUrl: String(form.get('sourceUrl') ?? ''),
    })
  }

  return (
    <div className="mx-auto w-full max-w-4xl min-w-0 px-5 py-6 sm:px-8 lg:px-10">
      <header className="flex min-w-0 flex-wrap items-start justify-between gap-4 border-b border-zinc-200 pb-5">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase text-emerald-700">Course Studio</p>
          <h2 className="mt-1 break-words text-xl font-semibold text-zinc-950">{course.name}</h2>
        </div>
        {editorHref ? (
          <a className="inline-flex h-9 items-center gap-2 rounded-md border border-zinc-300 px-3 text-sm font-semibold text-zinc-800 hover:bg-zinc-50" href={editorHref}>
            Nativen Editor öffnen <ArrowUpRight aria-hidden="true" size={15} />
          </a>
        ) : null}
      </header>

      <section aria-labelledby="course-definition-title" className="py-6">
        <h3 className="text-sm font-semibold text-zinc-950" id="course-definition-title">Kursdefinition</h3>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          {[
            ['Zielgruppe', model.audience || 'Noch nicht festgelegt'],
            ['Lernziel', model.outcome || 'Noch nicht festgelegt'],
            ['Voraussetzungen', model.prerequisites || 'Noch nicht festgelegt'],
            ['Zielschwierigkeit', difficultyLabels[model.difficulty]],
          ].map(([label, value]) => (
            <div className="min-w-0 border-s-4 border-zinc-300 bg-zinc-50 px-4 py-3" key={label}>
              <dt className="text-xs font-semibold uppercase text-zinc-500">{label}</dt>
              <dd className="mt-1 break-words text-sm text-zinc-900">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="course-sources-title" className="border-t border-zinc-200 py-6">
        <div>
          <div>
            <p className="text-xs font-semibold uppercase text-zinc-500">Material</p>
            <h3 className="mt-1 text-sm font-semibold text-zinc-950" id="course-sources-title">Quellen und Versionen</h3>
          </div>
        </div>
        <form className="mt-4 grid min-w-0 gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto]" onSubmit={importSource}>
          <label className="min-w-0 text-xs font-semibold text-zinc-600">
            Titel
            <input className="mt-1 h-10 w-full min-w-0 rounded-md border border-zinc-300 px-3 text-sm font-normal text-zinc-950" maxLength={200} name="sourceTitle" required />
          </label>
          <label className="min-w-0 text-xs font-semibold text-zinc-600">
            Quellen-URL
            <input className="mt-1 h-10 w-full min-w-0 rounded-md border border-zinc-300 px-3 text-sm font-normal text-zinc-950" name="sourceUrl" placeholder="https://" required type="url" />
          </label>
          <button
            className="mt-auto inline-flex h-10 items-center justify-center gap-2 rounded-md border border-zinc-300 px-3 text-sm font-semibold text-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!onImportSource}
            type="submit"
          >
            <FilePlus2 aria-hidden="true" size={15} /> Hinzufügen
          </button>
        </form>
        {model.sources.length > 0 ? (
          <ul className="mt-4 space-y-2">
            {model.sources.map((source) => (
              <li className="flex min-w-0 items-start gap-3 rounded-md border border-zinc-200 px-4 py-3" key={source.id}>
                {source.state === 'failed' ? (
                  <CircleAlert aria-hidden="true" className="mt-0.5 shrink-0 text-rose-700" size={16} />
                ) : (
                  <CheckCircle2 aria-hidden="true" className="mt-0.5 shrink-0 text-teal-700" size={16} />
                )}
                <div className="min-w-0">
                  <p className="break-words text-sm font-medium text-zinc-900">{source.title}</p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {source.state === 'failed'
                      ? 'Verarbeitung fehlgeschlagen'
                      : source.revision
                        ? `Version ${source.revision}`
                        : 'Verarbeitung ausstehend'}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="mt-4 border-s-4 border-zinc-300 bg-zinc-50 px-4 py-4 text-sm text-zinc-600">
            <Upload aria-hidden="true" className="mb-2" size={18} />
            Noch kein Schulungsmaterial importiert.
          </div>
        )}
      </section>

      <button
        className="mb-6 inline-flex h-10 items-center gap-2 rounded-md bg-zinc-950 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
        disabled={!onStartGeneration || model.sources.length === 0}
        onClick={onStartGeneration}
        type="button"
      >
        <Play aria-hidden="true" size={16} /> AI-Kursgenerierung starten
      </button>

      <GenerationReview generation={model.generation} onRegenerate={onRegenerate} />

      <section aria-labelledby="publication-title" className="mt-6 border-t border-zinc-200 pt-6">
        <h3 className="text-sm font-semibold text-zinc-950" id="publication-title">Freigabe und Veröffentlichung</h3>
        <p className={`mt-2 text-sm ${approved ? 'text-teal-800' : 'text-zinc-600'}`}>
          {approved ? 'Freigabe erteilt' : 'Veröffentlichung wartet auf eine ausdrückliche Freigabe.'}
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <button
            className="h-10 rounded-md border border-zinc-300 px-4 text-sm font-semibold text-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!onApprove || approved}
            onClick={onApprove}
            type="button"
          >
            Review freigeben
          </button>
          <button
            className="h-10 rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!approved || !onPublish}
            onClick={onPublish}
            type="button"
          >
            Kurs ausdrücklich veröffentlichen
          </button>
        </div>
      </section>
    </div>
  )
}
