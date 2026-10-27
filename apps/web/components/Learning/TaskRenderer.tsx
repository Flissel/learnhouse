import { useState, type FormEvent } from 'react'

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

/** What the Learning engine scores: one option, several options, text, an order, or pairs. */
export type TaskAnswer =
  | { choice_id: string }
  | { choice_ids: string[] }
  | { text: string }
  | { order: string[] }
  | { pairs: Record<string, string> }

export interface OrderingTask extends TaskBase {
  type: 'ordering'
  // Already shuffled by the engine; the learner puts them in order.
  items: Array<{ id: string; label: string }>
}

export interface Picture {
  src: string
  width: number
  height: number
}

export interface Box {
  x: number
  y: number
  w: number
  h: number
}

export interface MatchingTask extends TaskBase {
  type: 'matching'
  left: Array<{ id: string; label: string; image?: Picture }>
  right: Array<{ id: string; label: string; image?: Picture }>
}

export interface FillInTask extends TaskBase {
  type: 'fill_in'
  // A command with one {{blank}}; the learner types what belongs there.
  template: string
  shell?: string
  // A drawn terminal window instead of the text line: the input sits on the empty box,
  // further boxes of the same blank mirror it.
  image?: Picture & { rect: Box; more: Box[] }
}

export interface OpenResponseTask extends TaskBase {
  type: 'open_response' | 'case' | 'code'
}

export interface CanvasTask extends TaskBase {
  type: 'canvas'
  canvasHref?: string
  // Learning's drawing page for this person, embedded once the task is opened.
  canvasUrl?: string
}

export type LearningTask = MultipleChoiceTask | OpenResponseTask | CanvasTask | OrderingTask | MatchingTask | FillInTask

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
  if (task.type === 'ordering') return { order: form.getAll('order').map(String) }
  if (task.type === 'matching') {
    return { pairs: Object.fromEntries(task.left.map((item) => [item.id, String(form.get(`pair:${item.id}`) ?? '')])) }
  }
  return { text: String(form.get('answer') ?? '') }
}

const SHELL_NAMES: Record<string, string> = { powershell: 'Windows PowerShell', cmd: 'Windows CMD', unix: 'macOS / Linux' }

/** The order as a list with up/down buttons; hidden inputs carry it in the form. */
function OrderingField({ items }: { items: Array<{ id: string; label: string }> }) {
  const [order, setOrder] = useState(items.map((item) => item.id))
  const labels = Object.fromEntries(items.map((item) => [item.id, item.label]))
  const move = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= order.length) return
    const next = [...order]
    ;[next[index], next[target]] = [next[target], next[index]]
    setOrder(next)
  }
  return (
    <ol aria-label="Reihenfolge" className="space-y-2">
      {order.map((id, index) => (
        <li className="flex items-center gap-3 rounded-md border border-zinc-200 px-3 py-2" key={id}>
          <input name="order" type="hidden" value={id} />
          <span className="w-6 text-sm font-semibold text-zinc-500">{index + 1}.</span>
          <span className="min-w-0 flex-1 break-words text-sm text-zinc-900">{labels[id]}</span>
          <button aria-label="Nach oben" className="h-11 w-11 rounded-md border border-zinc-300 text-base hover:bg-zinc-100 disabled:opacity-40" disabled={index === 0} onClick={() => move(index, -1)} type="button">↑</button>
          <button aria-label="Nach unten" className="h-11 w-11 rounded-md border border-zinc-300 text-base hover:bg-zinc-100 disabled:opacity-40" disabled={index === order.length - 1} onClick={() => move(index, 1)} type="button">↓</button>
        </li>
      ))}
    </ol>
  )
}

const percent = (r: Box, image: Picture) => ({
  left: `${(r.x / image.width) * 100}%`,
  top: `${(r.y / image.height) * 100}%`,
  width: `${(r.w / image.width) * 100}%`,
  height: `${(r.h / image.height) * 100}%`,
  // Grows with the picture: the box height in container-width units.
  fontSize: `clamp(9px, ${((r.h / image.width) * 100 * 0.72).toFixed(3)}cqw, 18px)`,
})

function ImageFillInField({ image, shell }: { image: Picture & { rect: Box; more: Box[] }; shell?: string }) {
  const [value, setValue] = useState('')
  const name = shell ? SHELL_NAMES[shell] ?? shell : 'Terminal'
  return (
    <div
      className="relative w-full max-w-[560px] overflow-hidden rounded-md border border-zinc-300"
      style={{ aspectRatio: `${image.width} / ${image.height}`, containerType: 'inline-size' }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- drawn window served by learning-api */}
      <img alt={`Fenster von ${name}`} className="absolute inset-0 h-full w-full" height={image.height} src={image.src} width={image.width} />
      <input
        aria-label={`Lücke im Fenster von ${name}`}
        autoComplete="off"
        className="absolute box-border rounded-sm border-2 border-amber-600 bg-amber-50 px-1 font-mono leading-none text-zinc-950 outline-none focus:border-blue-700"
        id="answer"
        name="answer"
        onInput={(event) => setValue(event.currentTarget.value)}
        required
        spellCheck={false}
        style={percent(image.rect, image)}
        type="text"
      />
      {image.more.map((r, index) => (
        <span
          aria-hidden="true"
          className="absolute box-border flex items-center overflow-hidden whitespace-nowrap rounded-sm border-2 border-dashed border-amber-600 bg-amber-50 px-1 font-mono leading-none text-zinc-600"
          key={index}
          style={percent(r, image)}
        >
          {value}
        </span>
      ))}
    </div>
  )
}

function FillInField({ template, shell }: { template: string; shell?: string }) {
  const parts = template.split(/(\{\{\w+\}\})/).filter(Boolean)
  let placed = false
  return (
    <div>
      {shell ? <p className="mb-2 text-xs text-zinc-500">Für {SHELL_NAMES[shell] ?? shell}</p> : null}
      <pre className="flex flex-wrap items-center gap-1 whitespace-pre-wrap rounded-md bg-zinc-950 px-4 py-3 font-mono text-sm text-zinc-100">
        {parts.map((part, index) => {
          if (/^\{\{\w+\}\}$/.test(part)) {
            if (placed) return <span className="rounded border border-dashed border-zinc-500 px-2 text-zinc-400" key={index}>…</span>
            placed = true
            return (
              <input
                aria-label="Lücke"
                autoComplete="off"
                className="h-9 min-w-[12ch] rounded border border-zinc-400 bg-white px-2 font-mono text-sm text-zinc-950"
                id="answer"
                key={index}
                name="answer"
                required
                spellCheck={false}
                type="text"
              />
            )
          }
          return <span key={index}>{part}</span>
        })}
      </pre>
    </div>
  )
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
        ) : task.type === 'ordering' ? (
          <OrderingField items={task.items} />
        ) : task.type === 'matching' ? (
          <div className="space-y-2">
            {task.left.map((item, index) => (
              <label className="flex flex-wrap items-center gap-3 rounded-md border border-zinc-200 px-3 py-2" key={item.id}>
                <span className="min-w-[140px] flex-1 break-words text-sm font-semibold text-zinc-900">{item.label}</span>
                {item.image ? (
                  // eslint-disable-next-line @next/next/no-img-element -- drawn window served by learning-api
                  <img alt={item.label} className="block h-auto w-full max-w-[560px] basis-full rounded-md border border-zinc-200" height={item.image.height} src={item.image.src} width={item.image.width} />
                ) : null}
                <select
                  className="h-11 min-w-[180px] rounded-md border border-zinc-300 bg-white px-2 text-sm"
                  defaultValue=""
                  id={index === 0 ? 'answer' : undefined}
                  name={`pair:${item.id}`}
                  required
                >
                  <option disabled value="">– bitte wählen –</option>
                  {task.right.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
                </select>
              </label>
            ))}
          </div>
        ) : task.type === 'fill_in' ? (
          task.image ? <ImageFillInField image={task.image} shell={task.shell} /> : <FillInField shell={task.shell} template={task.template} />
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

