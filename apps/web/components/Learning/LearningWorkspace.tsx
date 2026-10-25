import { AlertTriangle, ArrowUpRight, BookOpenCheck, LoaderCircle, WifiOff } from 'lucide-react'

import type { LearningCourse, LearningShellState } from './LearningShell'
import type { ReactNode } from 'react'

interface LearningWorkspaceProps {
  course: LearningCourse | null
  courseHref: string | null
  state: LearningShellState
  visibleOnCompact: boolean
  mode?: 'studio' | 'player'
  onModeChange?: (_mode: 'studio' | 'player') => void
  children?: ReactNode
}

const workspaceState = {
  loading: {
    icon: LoaderCircle,
    title: 'Kurse werden geladen',
    detail: 'Der Lernraum wird vorbereitet.',
  },
  empty: {
    icon: BookOpenCheck,
    title: 'Noch keine Kurse',
    detail: 'Sobald ein Kurs bereitsteht, erscheint er hier.',
  },
  error: {
    icon: AlertTriangle,
    title: 'Kurse konnten nicht geladen werden',
    detail: 'Die Kursdaten sind momentan nicht erreichbar.',
  },
  degraded: {
    icon: WifiOff,
    title: 'Eingeschränkter Betrieb',
    detail: 'Der Lernraum ist verfügbar, aber Kursdaten fehlen teilweise.',
  },
} as const

export default function LearningWorkspace({
  course,
  courseHref,
  state,
  visibleOnCompact,
  mode,
  onModeChange,
  children,
}: LearningWorkspaceProps) {
  const fallback = state === 'ready' ? null : workspaceState[state]

  return (
    <main
      className={`${visibleOnCompact ? 'flex' : 'hidden'} min-h-0 min-w-0 flex-col overflow-y-auto bg-white lg:flex`}
      data-testid="learning-workspace"
      id="learning-workspace"
      tabIndex={-1}
    >
      {fallback ? (
        <div className="m-auto flex max-w-md flex-col items-center px-6 py-12 text-center" role="status">
          <fallback.icon
            aria-hidden="true"
            className={state === 'loading' ? 'animate-spin text-emerald-600' : 'text-zinc-500'}
            size={28}
          />
          <h2 className="mt-4 text-lg font-semibold text-zinc-950">{fallback.title}</h2>
          <p className="mt-2 text-sm leading-6 text-zinc-600">{fallback.detail}</p>
        </div>
      ) : course && children ? (
        <>
          <div aria-label="Arbeitsbereich" className="flex shrink-0 gap-1 border-b border-zinc-200 bg-white px-4 py-2">
            <button
              aria-pressed={mode === 'player'}
              className={`h-9 rounded-md px-3 text-sm font-semibold ${mode === 'player' ? 'bg-zinc-950 text-white' : 'text-zinc-600 hover:bg-zinc-100'}`}
              onClick={() => onModeChange?.('player')}
              type="button"
            >
              Lernen
            </button>
            <button
              aria-pressed={mode === 'studio'}
              className={`h-9 rounded-md px-3 text-sm font-semibold ${mode === 'studio' ? 'bg-zinc-950 text-white' : 'text-zinc-600 hover:bg-zinc-100'}`}
              onClick={() => onModeChange?.('studio')}
              type="button"
            >
              Course Studio
            </button>
          </div>
          {children}
        </>
      ) : course ? (
        <div className="mx-auto flex w-full max-w-4xl min-w-0 flex-1 flex-col px-5 py-7 sm:px-8 lg:px-10">
          <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs font-medium text-zinc-500">
            <span>Lernraum</span>
            <span aria-hidden="true">/</span>
            <span className="min-w-0 break-words text-emerald-700">Aktiver Kurs</span>
          </div>
          <div className="mt-5 min-w-0 border-b border-zinc-200 pb-7">
            <p className="text-xs font-semibold uppercase text-emerald-700">Kursübersicht</p>
            <h2 className="mt-2 min-w-0 break-words text-2xl font-semibold leading-8 text-zinc-950 sm:text-3xl">
              {course.name}
            </h2>
            {course.description ? (
              <p className="mt-3 max-w-2xl break-words text-sm leading-6 text-zinc-600">
                {course.description}
              </p>
            ) : null}
          </div>

          <section aria-labelledby="next-step-title" className="min-w-0 py-7">
            <p className="text-xs font-semibold uppercase text-zinc-500">Weiterlernen</p>
            <div className="mt-3 flex min-w-0 flex-col gap-4 border-s-4 border-emerald-500 bg-zinc-50 px-5 py-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <h3 className="break-words text-base font-semibold text-zinc-950" id="next-step-title">
                  {course.name}
                </h3>
                <p className="mt-1 text-sm text-zinc-600">Kursinhalt und Kapitel öffnen</p>
              </div>
              {courseHref ? (
                <a
                  className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md bg-zinc-950 px-4 text-sm font-semibold text-white transition-colors hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2"
                  href={courseHref}
                >
                  Kurs öffnen
                  <ArrowUpRight aria-hidden="true" size={16} />
                </a>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}
    </main>
  )
}
