'use client'

import { useCallback, useEffect, useState } from 'react'
import { captureError } from '@/lib/errors/report'
import {
  decodeLearningHostBridge,
  invokeLearningAction,
  type LearningAction,
  type LearningActionReceipt,
} from '@/services/learning/actions'

declare global {
  interface Window {
    vibemindLearningActions?: unknown
  }
}

export function useLearningActions() {
  const [available, setAvailable] = useState(false)

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setAvailable(Boolean(decodeLearningHostBridge(window.vibemindLearningActions)))
    })
    return () => window.cancelAnimationFrame(frame)
  }, [])

  const invoke = useCallback(async (action: LearningAction): Promise<LearningActionReceipt> => {
    const bridge = decodeLearningHostBridge(window.vibemindLearningActions)
    if (!bridge) throw new Error('VibeMind Learning Host is unavailable')
    try {
      return await invokeLearningAction(bridge, action)
    } catch {
      captureError(new Error('Learning host action failed'), {
        boundary: 'learning-host-actions',
        operation: action.operation,
      })
      throw new Error('Learning action was not accepted')
    }
  }, [])

  return { available, invoke }
}

