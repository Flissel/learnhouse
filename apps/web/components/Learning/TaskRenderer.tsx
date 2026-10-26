import type { FormEvent } from 'react'

import SourceEvidence, { type SourceEvidenceItem } from './SourceEvidence'

interface TaskBase {
  id: string
  prompt: string
  evidence: SourceEvidenceItem[]
}

export interface MultipleChoiceTask extends TaskBase {
  type: 'multiple_choice'
  options: Array<{ id: string; label: string }>
  // Several options may be right: checkboxes instead of radio buttons.
  multiple?: boolean
}

/** What the Learning engine scores: one option, several options, or text. */
export type TaskAnswer = { choice_id: string } | { choice_ids: string[] } | { text: string }

export interface OpenResponseTask extends TaskBase {
  type: 'open_response' | 'case' | 'code'
}

export interface CanvasTask extends TaskBase {
  type: 'canvas'
  canvasHref?: string
  // Learning's drawing page for this person, embedded once the task is opened.
  canvasUrl?: string
}

export type LearningTask = MultipleChoiceTask | OpenResponseTask | CanvasTask

interface TaskRendererProps {
  task: LearningTask
  submitLabel: string
  onSubmit?: (_answer: TaskAnswer) => void
  onOpenCanvas?: () => void
  disabled?: boolean
}

export function answerFromForm(task: LearningTask, form: FormData): TaskAnswer {
  if (task.type === 'multiple_choice') {
    const chosen = form.getAll('answer').map(String)
    return task.multiple ? { choice_ids: chosen } : { choice_id: chosen[0] ?? '' }
  }
  return { text: String(form.get('answer') ?? '') }
}

export default function TaskRenderer({ task, submitLabel, onSubmit, onOpenCanvas, disabled }: TaskRendererProps) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit?.(answerFromForm(task, new FormData(event.currentTarget)))
  }

  return (
    <form className="min-w-0" onSubmit={submit}>
      <h3 className="break-words text-lg font-semibold leading-7 text-zinc-950">{task.prompt}</h3>

      <div className="mt-5">
        {task.type === 'multiple_choice' ? (
          <fieldset className="space-y-2">
            <legend className="sr-only">Antwort auswählen</legend>
            {task.options.map((option, index) => (
              <label className="flex min-w-0 cursor-pointer items-start gap-3 rounded-md border border-zinc-200 px-4 py-3 hover:border-emerald-400 hover:bg-emerald-50" key={option.id}>
                <input
                  className="mt-1 accent-emerald-700"
                  id={index === 0 ? 'answer' : undefined}
                  name="answer"
                  required={!task.multiple}
                  type={task.multiple ? 'checkbox' : 'radio'}
                  value={option.id}
                />
                <span className="min-w-0 break-words text-sm text-zinc-900">{option.label}</span>
              </label>
            ))}
          </fieldset>
        ) : task.type === 'canvas' && task.canvasUrl ? (
          <iframe
            className="h-[780px] w-full rounded-md border border-zinc-300 bg-white"
            id="answer"
            src={task.canvasUrl}
            title="Zeichenfläche"
          />
        ) : task.type === 'canvas' && onOpenCanvas ? (
          <div className="border-s-4 border-cyan-600 bg-cyan-50 px-4 py-4">
            <p className="text-sm text-zinc-700">Zeichne deine Lösung auf der Zeichenfläche; du gibst sie dort selbst ab.</p>
            <button
              className="mt-3 inline-flex h-10 items-center rounded-md bg-cyan-800 px-4 text-sm font-semibold text-white hover:bg-cyan-900 disabled:opacity-50"
              disabled={disabled}
              id="answer"
              onClick={onOpenCanvas}
              type="button"
            >
              Zeichenfläche öffnen
            </button>
          </div>
        ) : task.type === 'canvas' ? (
          <div className="border-s-4 border-cyan-600 bg-cyan-50 px-4 py-4">
            <p className="text-sm text-zinc-700">Diese Zeichenaufgabe öffnest du über den Lern-Agenten; dort zeichnest du und gibst selbst ab.</p>
            {task.canvasHref ? (
              <a className="mt-3 inline-flex text-sm font-semibold text-cyan-800 underline" href={task.canvasHref} id="answer">
                Canvas öffnen
              </a>
            ) : (
              <button className="mt-3 text-sm font-semibold text-zinc-500" disabled id="answer" type="button">
                Canvas nicht verfügbar
              </button>
            )}
          </div>
        ) : (
          <textarea
            className="min-h-40 w-full resize-y rounded-md border border-zinc-300 px-3 py-3 text-sm text-zinc-950 focus:border-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-200"
            id="answer"
            name="answer"
            placeholder={task.type === 'code' ? 'Lösung und Begründung eingeben' : 'Antwort ausarbeiten'}
            required
          />
        )}
      </div>

      {task.type === 'canvas' ? null : (
        <button
          className="mt-5 inline-flex h-10 items-center justify-center rounded-md bg-zinc-950 px-5 text-sm font-semibold text-white hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!onSubmit || disabled}
          type="submit"
        >
          {submitLabel}
        </button>
      )}

      <section aria-labelledby="task-evidence-title" className="mt-7 border-t border-zinc-200 pt-5">
        <h4 className="mb-3 text-xs font-semibold uppercase text-zinc-500" id="task-evidence-title">
          Quellenbelege
        </h4>
        <SourceEvidence items={task.evidence} />
      </section>
    </form>
  )
}

