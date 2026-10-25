'use client'

import { useEffect, useRef, useState } from 'react'
import { captureError } from '@/lib/errors/report'
import {
  consumeLearningIntentStream,
  reconstructLearningProjection,
  runLearningIntentReconnectLoop,
  type LearningIntent,
  type UnknownIntentRecord,
} from '@/services/learning/intents'

export type LearningIntentConnectionState =
  | 'disabled'
  | 'reconstructing'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'error'

interface LearningIntentRuntime {
  endpoint: string
  token: string
  loadRevisionSnapshot: () => Promise<unknown>
}

interface UseLearningIntentsOptions {
  onIntent: (_intent: LearningIntent) => void
}

declare global {
  interface Window {
    vibemindLearningIntents?: unknown
  }
}

export function useLearningIntents({ onIntent }: UseLearningIntentsOptions) {
  const [connectionState, setConnectionState] = useState<LearningIntentConnectionState>('disabled')
  const onIntentRef = useRef(onIntent)

  useEffect(() => {
    onIntentRef.current = onIntent
  }, [onIntent])

  useEffect(() => {
    const runtime = decodeRuntime(window.vibemindLearningIntents)
    if (!runtime) return
    const activeRuntime: LearningIntentRuntime = runtime

    const controller = new AbortController()
    let lastEventId: string | undefined

    async function start() {
      setConnectionState('reconstructing')
      try {
        const projector = await reconstructLearningProjection(activeRuntime.loadRevisionSnapshot)
        if (controller.signal.aborted) return

        await runLearningIntentReconnectLoop({
          signal: controller.signal,
          onState: setConnectionState,
          connect: () => consumeLearningIntentStream({
            endpoint: activeRuntime.endpoint,
            token: activeRuntime.token,
            signal: controller.signal,
            lastEventId,
            onOpen: () => setConnectionState('connected'),
            recordUnknown,
            onEvent: (event) => {
              lastEventId = event.eventId
              const result = projector.apply(event)
              if (result.status === 'applied' && result.intent) {
                onIntentRef.current(result.intent)
              }
            },
          }),
        })
      } catch {
        if (controller.signal.aborted) return
        setConnectionState('error')
        captureError(new Error('Learning UI intent boundary failed'), {
          boundary: 'learning-ui-intents',
        })
      }
    }

    void start()
    return () => controller.abort()
  }, [])

  return connectionState
}

function decodeRuntime(value: unknown): LearningIntentRuntime | null {
  if (!isRecord(value)) return null
  const keys = Object.keys(value)
  if (
    keys.length !== 3
    || !keys.includes('endpoint')
    || !keys.includes('token')
    || !keys.includes('loadRevisionSnapshot')
    || typeof value.endpoint !== 'string'
    || typeof value.token !== 'string'
    || typeof value.loadRevisionSnapshot !== 'function'
    || !isLoopbackEndpoint(value.endpoint)
    || !isRuntimeToken(value.token)
  ) {
    return null
  }
  return {
    endpoint: value.endpoint,
    token: value.token,
    loadRevisionSnapshot: value.loadRevisionSnapshot as () => Promise<unknown>,
  }
}

function isLoopbackEndpoint(value: string): boolean {
  try {
    const endpoint = new URL(value)
    return endpoint.protocol === 'http:'
      && ['127.0.0.1', 'localhost', '[::1]'].includes(endpoint.hostname)
  } catch {
    return false
  }
}

function isRuntimeToken(value: string): boolean {
  return value.length >= 32
    && value.length <= 512
    && value.trim() === value
    && /^[\x21-\x7e]+$/.test(value)
}

function recordUnknown(record: UnknownIntentRecord) {
  captureError(new Error('Learning UI intent rejected'), {
    boundary: 'learning-ui-intents',
    code: record.code,
    ...(record.kind ? { kind: record.kind } : {}),
  })
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
