import { AlertCircle, BookOpen, CheckCircle2, LoaderCircle, WifiOff } from 'lucide-react'

import type { LearningCourse, LearningShellState } from './LearningShell'

interface CourseOutlineProps {
  courses: LearningCourse[]
  selectedCourseId: string | null
  state: LearningShellState
  visibleOnCompact: boolean
  onSelect: (_courseId: string) => void
}

const stateContent = {
  loading: { icon: LoaderCircle, label: 'Kurse werden geladen' },
  empty: { icon: BookOpen, label: 'Noch keine Kurse' },
  error: { icon: AlertCircle, label: 'Kurse konnten nicht geladen werden' },
  degraded: { icon: WifiOff, label: 'Eingeschränkter Betrieb' },
} as const

export default function CourseOutline({
  courses,
  selectedCourseId,
  state,
  visibleOnCompact,
  onSelect,
}: CourseOutlineProps) {
  const status = state === 'ready' ? null : stateContent[state]

  return (
    <nav
      aria-label="Kursnavigation"
      className={`${visibleOnCompact ? 'flex' : 'hidden'} min-h-0 min-w-0 flex-col border-e border-zinc-200 bg-zinc-50 lg:flex`}
      data-testid="course-outline"
      id="course-outline"
      tabIndex={-1}
    >
      <div className="border-b border-zinc-200 px-4 py-4">
        <p className="text-xs font-semibold uppercase text-zinc-500">Meine Kurse</p>
        <h1 className="mt-1 break-words text-base font-semibold text-zinc-950">
          Lernraum
        </h1>
      </div>

      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto p-2">
        {status ? (
          <div className="flex min-w-0 items-start gap-2 px-2 py-4 text-sm text-zinc-600" role="status">
            <status.icon
              aria-hidden="true"
              className={state === 'loading' ? 'mt-0.5 shrink-0 animate-spin' : 'mt-0.5 shrink-0'}
              size={16}
            />
            <span className="min-w-0 break-words">{status.label}</span>
          </div>
        ) : (
          <ul className="space-y-1">
            {courses.map((course) => {
              const selected = course.id === selectedCourseId
              return (
                <li key={course.id} className="min-w-0">
                  <button
                    aria-current={selected ? 'page' : undefined}
                    className={`flex w-full min-w-0 items-start gap-2 rounded-md px-3 py-3 text-start text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                      selected
                        ? 'bg-white font-semibold text-zinc-950 shadow-sm ring-1 ring-zinc-200'
                        : 'text-zinc-600 hover:bg-white hover:text-zinc-950'
                    }`}
                    onClick={() => onSelect(course.id)}
                    type="button"
                  >
                    {selected ? (
                      <CheckCircle2 aria-hidden="true" className="mt-0.5 shrink-0 text-emerald-600" size={16} />
                    ) : (
                      <BookOpen aria-hidden="true" className="mt-0.5 shrink-0 text-zinc-400" size={16} />
                    )}
                    <span className="min-w-0 break-words">{course.name}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </nav>
  )
}
