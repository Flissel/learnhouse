import type { FormEvent } from 'react'
import { Bot, CircleCheck, Database, WifiOff } from 'lucide-react'

import type { LearningCourse, LearningShellState } from './LearningShell'

interface AgentPanelProps {
  course: LearningCourse | null
  state: LearningShellState
  visibleOnCompact: boolean
  // Tutor for the open practice task; absent without a session.
  onAsk?: (_question: string) => void
  tutor?: { answer: string; nextStep: string }
  busy?: boolean
}

export default function AgentPanel({ course, state, visibleOnCompact, onAsk, tutor, busy }: AgentPanelProps) {
  const available = state === 'ready'

  function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const question = String(new FormData(form).get('question') ?? '').trim()
    if (question && onAsk) {
      onAsk(question)
      form.reset()
    }
  }

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
        <section aria-labelledby="agent-tutor-title" className="min-w-0 border-t border-zinc-200 py-5">
          <p className="text-xs font-semibold uppercase text-zinc-500" id="agent-tutor-title">
            Tutor zur Aufgabe
          </p>
          {onAsk ? (
            <form className="mt-2 flex flex-col gap-2" onSubmit={ask}>
              <label className="sr-only" htmlFor="tutor-question">Frage an den Tutor</label>
              <textarea
                className="min-h-20 w-full resize-y rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-200"
                id="tutor-question"
                maxLength={2000}
                name="question"
                placeholder="Was verstehst du nicht?"
              />
              <button
                className="inline-flex h-9 items-center justify-center rounded-md bg-zinc-950 px-3 text-sm font-semibold text-white disabled:opacity-50"
                disabled={busy}
                type="submit"
              >
                {busy ? 'Der Tutor denkt nach …' : 'Fragen'}
              </button>
            </form>
          ) : (
            <p className="mt-2 text-sm text-zinc-600">Starte eine Lernsitzung, dann hilft dir der Tutor bei der offenen Aufgabe.</p>
          )}
          {tutor ? (
            <div className="mt-3 rounded-md bg-emerald-50 px-3 py-3 text-sm leading-6 text-zinc-800">
              <p>{tutor.answer}</p>
              <p className="mt-2 text-xs text-zinc-600"><strong>Nächster Schritt:</strong> {tutor.nextStep}</p>
            </div>
          ) : null}
        </section>
      </div>
    </aside>
  )
}
