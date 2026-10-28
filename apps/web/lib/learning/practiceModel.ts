import type { LearningPlayerModel } from '@components/Learning/LearningPlayer'
import type { Box, LearningTask, Picture } from '@components/Learning/TaskRenderer'
import { evidenceTitle, type PracticeTask, type PracticeTurn } from '@/services/learning/practice'

const FEEDBACK: Record<string, { state: 'correct' | 'incorrect' | 'needs_review'; message: string }> = {
  correct: { state: 'correct', message: 'Richtig – gut gemacht.' },
  partial: { state: 'incorrect', message: 'Teilweise richtig. Schau dir die Quellenbelege noch einmal an.' },
  incorrect: { state: 'incorrect', message: 'Noch nicht richtig. Die Quellenbelege unten zeigen, wo es steht.' },
  needs_review: { state: 'needs_review', message: 'Deine Antwort wird von einer Person geprüft; danach zählt sie für deinen Lernstand.' },
}

const CANVAS_SUBMITTED = {
  state: 'submitted' as const,
  message: 'Deine Zeichnung ist abgegeben. Das Ergebnis steht in der Zeichenfläche; ist die KI unsicher, prüft es noch eine Person.',
}

export function practiceTask(task: PracticeTask): LearningTask {
  const evidence = task.source_refs.map((ref, index) => {
    const { title, locator } = evidenceTitle(ref)
    return { id: `source-${index}`, title, locator, supported: true }
  })
  const base = { id: task.id, prompt: task.prompt, evidence, math: task.presentation?.math === true }
  if (task.type === 'single_choice' || task.type === 'multiple_choice') {
    return { ...base, type: 'multiple_choice', options: task.options, multiple: task.type === 'multiple_choice' }
  }
  if (task.type === 'penecho_canvas') return { ...base, type: 'canvas' }
  if (task.type === 'case' || task.type === 'code') return { ...base, type: task.type }
  if (task.type === 'ordering') return { ...base, type: 'ordering', items: task.options }
  if (task.type === 'matching') {
    return { ...base, type: 'matching', left: pairItems(task.presentation?.left), right: pairItems(task.presentation?.right) }
  }
  if (task.type === 'numeric') {
    const unit = typeof task.presentation?.unit === 'string' && task.presentation.unit ? task.presentation.unit : undefined
    return unit ? { ...base, type: 'numeric', unit } : { ...base, type: 'numeric' }
  }
  if (task.type === 'fill_in') {
    const template = typeof task.presentation?.template === 'string' ? task.presentation.template : '{{wert}}'
    const shell = typeof task.presentation?.shell === 'string' ? task.presentation.shell : undefined
    // A drawn terminal window: the input sits on its empty box.
    const pic = picture(task.presentation)
    const rect = box(task.presentation?.rect)
    if (pic && rect) {
      const more = Array.isArray(task.presentation?.more) ? task.presentation.more.map(box).filter((b): b is Box => !!b) : []
      return { ...base, type: 'fill_in', template, shell, image: { ...pic, rect, more } }
    }
    return { ...base, type: 'fill_in', template, shell }
  }
  return { ...base, type: 'open_response' }
}

/** A number as a learner types it: comma or point, spaces around, `1e3` allowed; otherwise null. */
export function parseNumber(input: string): number | null {
  const text = input.trim().replace(/\u2212/g, '-').replace(',', '.')
  if (!/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(text)) return null
  const value = Number(text)
  return Number.isFinite(value) ? value : null
}

/** Whether a fill_in shows the text line instead of a drawn window (no usable picture). */
export function imageFallback(task: { image?: unknown }): boolean {
  return !task.image
}

function pairItems(value: unknown): Array<{ id: string; label: string; image?: Picture }> {
  if (!Array.isArray(value)) return []
  return value
    .filter((item): item is { id: string; label: string } =>
      typeof item === 'object' && item !== null && typeof (item as any).id === 'string' && typeof (item as any).label === 'string')
    .map((item) => {
      const pic = picture(item)
      return pic ? { id: item.id, label: item.label, image: pic } : { id: item.id, label: item.label }
    })
}

const positive = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value > 0

/** A picture the engine sent (already absolute on learning-api's origin), with its size. */
function picture(value: unknown): Picture | undefined {
  if (typeof value !== 'object' || value === null) return undefined
  const { image, width, height } = value as Record<string, unknown>
  if (typeof image !== 'string' || !/^https?:\/\//.test(image) || !positive(width) || !positive(height)) return undefined
  return { src: image, width, height }
}

function box(value: unknown): Box | undefined {
  if (typeof value !== 'object' || value === null) return undefined
  const { x, y, w, h } = value as Record<string, unknown>
  const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n) && n >= 0
  return finite(x) && finite(y) && positive(w) && positive(h) ? { x, y, w, h } : undefined
}

/** The engine's turn as the Learning Player shows it. */
export function practiceModel(
  turn: PracticeTurn | null,
  extra: {
    mode: 'training' | 'exam'
    hint?: string
    busy?: boolean
    error?: string
    canvas?: { taskId: string; url: string; submitted: boolean }
  },
): LearningPlayerModel {
  if (!turn) {
    return { mode: extra.mode, sessionProgress: { completed: 0, total: 0 }, task: null, busy: extra.busy, error: extra.error }
  }
  const canvas = extra.canvas && turn.task?.id === extra.canvas.taskId ? extra.canvas : undefined
  const feedback = canvas?.submitted
    ? CANVAS_SUBMITTED
    : turn.feedback ? FEEDBACK[turn.feedback.state] : undefined
  const done = turn.state !== 'active' && turn.summary
  const task = turn.task ? practiceTask(turn.task) : null
  return {
    mode: turn.mode,
    sessionProgress: { completed: turn.progress.completed, total: turn.progress.total },
    task: task?.type === 'canvas' && canvas ? { ...task, canvasUrl: canvas.url } : task,
    feedback: feedback && turn.feedback?.mastery_applied && !canvas?.submitted
      ? { ...feedback, message: `${feedback.message} Dein Lernstand ist aktualisiert.` }
      : feedback,
    hint: extra.hint,
    summary: done ? { attempted: turn.summary!.attempted, correct: turn.summary!.correct, score: turn.summary!.score } : undefined,
    busy: extra.busy,
    error: extra.error,
  }
}
