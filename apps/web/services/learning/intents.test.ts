// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'

import {
  LearningIntentProjector,
  consumeLearningIntentStream,
  decodeLearningIntent,
  focusTargetForIntent,
  reconstructLearningProjection,
  runLearningIntentReconnectLoop,
  type LearningIntent,
} from './intents'

const courseId = '00000000-0000-0000-0000-000000000101'

function openCourse(revision: number): LearningIntent {
  return {
    version: '1',
    kind: 'open_course',
    aggregate_id: 'course-101',
    aggregate_revision: revision,
    course_id: courseId,
  }
}

describe('decodeLearningIntent', () => {
  test('strictly decodes the frozen variants and rejects extra fields', () => {
    expect(decodeLearningIntent(openCourse(4))).toEqual(openCourse(4))
    expect(
      decodeLearningIntent({
        version: '1',
        kind: 'focus_answer',
        aggregate_id: 'session-1',
        aggregate_revision: 3,
        field_id: 'answer',
      }),
    ).toEqual({
      version: '1',
      kind: 'focus_answer',
      aggregate_id: 'session-1',
      aggregate_revision: 3,
      field_id: 'answer',
    })
    expect(decodeLearningIntent({ ...openCourse(4), unexpected: true })).toBeNull()
  })

  test('records only a sanitized reason for unknown or malformed intents', () => {
    const records: Array<{ code: string; kind?: string }> = []
    const decoded = decodeLearningIntent(
      { kind: 'run_shell', secret: 'must-not-be-recorded' },
      { recordUnknown: (record) => records.push(record) },
    )

    expect(decoded).toBeNull()
    expect(records).toEqual([{ code: 'unknown_kind', kind: 'run_shell' }])
    expect(JSON.stringify(records)).not.toContain('must-not-be-recorded')
  })
})

describe('LearningIntentProjector', () => {
  test('rejects stale revisions and duplicate event ids', () => {
    const projector = new LearningIntentProjector({ 'course:course-101': 4 })

    expect(projector.apply({ eventId: 'evt-stale', intent: openCourse(3) }).status).toBe('stale')
    expect(projector.apply({ eventId: 'evt-current', intent: openCourse(4) }).status).toBe('applied')
    expect(projector.apply({ eventId: 'evt-current', intent: openCourse(5) }).status).toBe('duplicate')
    expect(projector.apply({ eventId: 'evt-new', intent: openCourse(5) }).status).toBe('applied')
  })

  test('reconstructs revisions from APIs before applying stream events', async () => {
    const order: string[] = []
    const projector = await reconstructLearningProjection(async () => {
      order.push('api')
      return { 'course:course-101': 7 }
    })
    order.push('stream')

    expect(order).toEqual(['api', 'stream'])
    expect(projector.apply({ eventId: 'evt-6', intent: openCourse(6) }).status).toBe('stale')
  })

  test('fails closed when the API revision snapshot is malformed', async () => {
    await expect(
      reconstructLearningProjection(async () => ({ 'course:course-101': -1 })),
    ).rejects.toThrow('malformed API revision snapshot')
    await expect(
      reconstructLearningProjection(async () => ({ 'unknown:course-101': 4 })),
    ).rejects.toThrow('malformed API revision snapshot')
  })
})

describe('authenticated local SSE transport', () => {
  test('sends the bearer token in a header and decodes event ids', async () => {
    const received: Array<{ eventId: string; intent: LearningIntent }> = []
    const states: string[] = []
    const fetcher: typeof fetch = async (_input, init) => {
      const headers = new Headers(init?.headers)
      expect(headers.get('Authorization')).toBe('Bearer runtime-token-with-at-least-32-chars')
      expect(headers.get('Accept')).toBe('text/event-stream')
      return new Response(
        `id: evt-1\ndata: ${JSON.stringify(openCourse(4))}\n\n`,
        { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
      )
    }

    await consumeLearningIntentStream({
      endpoint: 'http://127.0.0.1:5151/ui/events',
      token: 'runtime-token-with-at-least-32-chars',
      fetcher,
      signal: new AbortController().signal,
      onOpen: () => states.push('open'),
      onEvent: (event) => received.push(event),
    })

    expect(received).toEqual([{ eventId: 'evt-1', intent: openCourse(4) }])
    expect(states).toEqual(['open'])
  })

  test('rejects non-loopback endpoints and short tokens before fetch', async () => {
    let calls = 0
    const fetcher: typeof fetch = async () => {
      calls += 1
      return new Response(null, { status: 204 })
    }

    await expect(
      consumeLearningIntentStream({
        endpoint: 'https://renderer.example.invalid/ui/events',
        token: 'runtime-token-with-at-least-32-chars',
        fetcher,
        signal: new AbortController().signal,
        onEvent: () => undefined,
      }),
    ).rejects.toThrow('loopback')
    await expect(
      consumeLearningIntentStream({
        endpoint: 'http://127.0.0.1:5151/ui/events',
        token: 'short',
        fetcher,
        signal: new AbortController().signal,
        onEvent: () => undefined,
      }),
    ).rejects.toThrow('token')
    expect(calls).toBe(0)
  })

  test('reconnects with bounded backoff after transport failure', async () => {
    const controller = new AbortController()
    const delays: number[] = []
    const states: string[] = []
    let attempts = 0

    await runLearningIntentReconnectLoop({
      signal: controller.signal,
      connect: async () => {
        attempts += 1
        if (attempts === 1) throw new Error('offline')
        controller.abort()
      },
      sleep: async (milliseconds) => {
        delays.push(milliseconds)
      },
      onState: (state) => states.push(state),
    })

    expect(attempts).toBe(2)
    expect(delays).toEqual([500])
    expect(states).toEqual(['connecting', 'reconnecting'])
  })
})

test('focus intents expose only their validated focus target', () => {
  expect(
    focusTargetForIntent({
      version: '1',
      kind: 'focus_answer',
      aggregate_id: 'session-1',
      aggregate_revision: 2,
      field_id: 'answer',
    }),
  ).toBe('answer')
  expect(focusTargetForIntent(openCourse(2))).toBeNull()
})
