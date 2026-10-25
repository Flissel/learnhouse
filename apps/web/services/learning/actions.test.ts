// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'

import { invokeLearningAction, type LearningHostBridge } from './actions'

const courseId = '00000000-0000-0000-0000-000000000101'

describe('VibeMind learning action bridge', () => {
  test('passes only frozen semantic actions to the host and strictly decodes its receipt', async () => {
    const calls: unknown[] = []
    const bridge: LearningHostBridge = {
      invoke: async (request) => {
        calls.push(request)
        return {
          version: '1',
          state: 'completed',
          correlation_id: '00000000-0000-0000-0000-000000000201',
          aggregate_revision: 4,
        }
      },
    }
    const action = {
      version: '1' as const,
      operation: 'material_import' as const,
      course_id: courseId,
      title: 'KI-Richtlinie',
      source_url: 'https://intranet.example.invalid/ki-richtlinie',
    }

    expect(await invokeLearningAction(bridge, action)).toEqual({
      version: '1',
      state: 'completed',
      correlation_id: '00000000-0000-0000-0000-000000000201',
      aggregate_revision: 4,
    })
    expect(calls).toEqual([action])
  })

  test('fails closed for host paths and malformed or overbroad receipts', async () => {
    const bridge: LearningHostBridge = {
      invoke: async () => ({
        version: '1',
        state: 'completed',
        correlation_id: '00000000-0000-0000-0000-000000000201',
        aggregate_revision: 4,
        secret: 'must-not-enter-renderer-state',
      }),
    }

    await expect(
      invokeLearningAction(bridge, {
        version: '1',
        operation: 'material_import',
        course_id: courseId,
        title: 'Lokale Datei',
        source_url: 'file:///C:/secret.pdf',
      }),
    ).rejects.toThrow('source URL')
    await expect(
      invokeLearningAction(bridge, {
        version: '1',
        operation: 'course_publish',
        course_id: courseId,
        confirmed: true,
      }),
    ).rejects.toThrow('malformed host receipt')

    await expect(
      invokeLearningAction(bridge, {
        version: '1',
        operation: 'course_generate',
        course_id: courseId,
        extra: 'not-frozen',
      } as unknown as Parameters<typeof invokeLearningAction>[1]),
    ).rejects.toThrow('malformed learning action')
  })
})
