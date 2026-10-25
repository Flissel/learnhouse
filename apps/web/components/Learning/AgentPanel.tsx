import { Bot, CircleCheck, Database, WifiOff } from 'lucide-react'

import type { LearningCourse, LearningShellState } from './LearningShell'

interface AgentPanelProps {
  course: LearningCourse | null
  state: LearningShellState
  visibleOnCompact: boolean
}

export default function AgentPanel({ course, state, visibleOnCompact }: AgentPanelProps) {
  const available = state === 'ready'

  return (
    <aside
      aria-label="Learning Agent"
      className={`${visibleOnCompact ? 'flex' : 'hidden'} min-h-0 min-w-0 flex-col border-s border-zinc-200 bg-zinc-50 lg:flex`}
      data-testid="agent-panel"
      id="agent-panel"
      tabIndex={-1}
    >
      <div className="border-b border-zinc-200 px-4 py-4">
        <div className="flex items-center gap-2">
          <Bot aria-hidden="true" className="text-emerald-700" size={18} />
          <h2 className="text-sm font-semibold text-zinc-950">Learning Agent</h2>
        </div>
        <div className="mt-2 flex items-center gap-2 text-xs text-zinc-600">
          {available ? (
            <CircleCheck aria-hidden="true" className="text-emerald-600" size={14} />
          ) : (
            <WifiOff aria-hidden="true" className="text-amber-600" size={14} />
          )}
          <span>{available ? 'Kontext geladen' : 'Begrenzter Kontext'}</span>
        </div>
      </div>

      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto px-4 py-5">
        <section aria-labelledby="agent-context-title" className="min-w-0 border-b border-zinc-200 pb-5">
          <p className="text-xs font-semibold uppercase text-zinc-500" id="agent-context-title">
            Kurskontext
          </p>
          <p className="mt-2 min-w-0 break-words text-sm font-medium leading-6 text-zinc-900">
            {course?.name ?? 'Kein Kurs ausgewählt'}
          </p>
        </section>
        <section aria-labelledby="agent-sources-title" className="min-w-0 py-5">
          <div className="flex items-center gap-2">
            <Database aria-hidden="true" className="text-teal-700" size={15} />
            <p className="text-xs font-semibold uppercase text-zinc-500" id="agent-sources-title">
              Quellen
            </p>
          </div>
          <p className="mt-2 text-sm text-zinc-600">{available ? 'Kursmaterial' : 'Nicht verfügbar'}</p>
        </section>
      </div>
    </aside>
  )
}
