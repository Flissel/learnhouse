export type LearningAction =
  | {
      version: '1'
      operation: 'material_import'
      course_id: string
      title: string
      source_url: string
    }
  | { version: '1'; operation: 'course_generate'; course_id: string }
  | { version: '1'; operation: 'course_review'; course_id: string; decision: 'approved' | 'rejected' }
  | { version: '1'; operation: 'course_publish'; course_id: string; confirmed: true }
  | { version: '1'; operation: 'session_start'; course_id: string; mode: 'training' | 'exam' }
  | {
      version: '1'
      operation: 'task_answer'
      session_id: string
      task_id: string
      answer: string
    }
  | { version: '1'; operation: 'hint_request'; session_id: string; task_id: string }

export interface LearningHostBridge {
  invoke: (_request: LearningAction) => Promise<unknown>
}

export interface LearningActionReceipt {
  version: '1'
  state: 'completed' | 'rejected' | 'approval_required' | 'unavailable'
  correlation_id: string
  aggregate_revision?: number
  error_code?: string
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const safeCode = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/
const receiptKeys = new Set([
  'version',
  'state',
  'correlation_id',
  'aggregate_revision',
  'error_code',
])
const receiptStates = new Set(['completed', 'rejected', 'approval_required', 'unavailable'])
const actionKeys: Record<LearningAction['operation'], ReadonlySet<string>> = {
  material_import: new Set(['version', 'operation', 'course_id', 'title', 'source_url']),
  course_generate: new Set(['version', 'operation', 'course_id']),
  course_review: new Set(['version', 'operation', 'course_id', 'decision']),
  course_publish: new Set(['version', 'operation', 'course_id', 'confirmed']),
  session_start: new Set(['version', 'operation', 'course_id', 'mode']),
  task_answer: new Set(['version', 'operation', 'session_id', 'task_id', 'answer']),
  hint_request: new Set(['version', 'operation', 'session_id', 'task_id']),
}

export async function invokeLearningAction(
  bridge: LearningHostBridge,
  action: LearningAction,
): Promise<LearningActionReceipt> {
  validateAction(action)
  return decodeReceipt(await bridge.invoke(action))
}

export function decodeLearningHostBridge(value: unknown): LearningHostBridge | null {
  if (!isRecord(value) || Object.keys(value).length !== 1 || typeof value.invoke !== 'function') {
    return null
  }
  return { invoke: value.invoke as (_request: LearningAction) => Promise<unknown> }
}

function validateAction(action: LearningAction) {
  const expectedKeys = actionKeys[action.operation]
  if (
    action.version !== '1'
    || !expectedKeys
    || Object.keys(action).length !== expectedKeys.size
    || !Object.keys(action).every((key) => expectedKeys.has(key))
  ) {
    throw new Error('malformed learning action')
  }
  if ('course_id' in action && !uuid.test(action.course_id)) throw new Error('invalid course id')
  if ('session_id' in action && !uuid.test(action.session_id)) throw new Error('invalid session id')
  if ('task_id' in action && !uuid.test(action.task_id)) throw new Error('invalid task id')

  if (action.operation === 'material_import') {
    if (!action.title.trim() || action.title.length > 200) throw new Error('invalid source title')
    let source: URL
    try {
      source = new URL(action.source_url)
    } catch {
      throw new Error('invalid source URL')
    }
    if (!['http:', 'https:'].includes(source.protocol) || source.username || source.password) {
      throw new Error('invalid source URL')
    }
  }
  if (action.operation === 'task_answer' && (!action.answer.trim() || action.answer.length > 20_000)) {
    throw new Error('invalid task answer')
  }
}

function decodeReceipt(value: unknown): LearningActionReceipt {
  if (
    !isRecord(value)
    || !Object.keys(value).every((key) => receiptKeys.has(key))
    || value.version !== '1'
    || typeof value.state !== 'string'
    || !receiptStates.has(value.state)
    || typeof value.correlation_id !== 'string'
    || !uuid.test(value.correlation_id)
    || (value.aggregate_revision !== undefined && !isRevision(value.aggregate_revision))
    || (value.error_code !== undefined
      && (typeof value.error_code !== 'string' || !safeCode.test(value.error_code)))
    || (value.state === 'completed' && !isRevision(value.aggregate_revision))
  ) {
    throw new Error('malformed host receipt')
  }
  return value as unknown as LearningActionReceipt
}

function isRevision(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
