import { MicOff, Plug, ShieldCheck } from 'lucide-react'

import type { LearningShellState } from './LearningShell'
import type { LearningIntentConnectionState } from '@/hooks/useLearningIntents'

interface StatusStripProps {
  state: LearningShellState
  connectionState: LearningIntentConnectionState
}

const connectionLabels: Record<LearningIntentConnectionState, string> = {
  disabled: 'MCP nicht geprüft',
  reconstructing: 'MCP wird geprüft',
  connecting: 'MCP verbindet',
  connected: 'MCP verbunden',
  reconnecting: 'MCP verbindet erneut',
  error: 'MCP nicht verfügbar',
}

export default function StatusStrip({ state, connectionState }: StatusStripProps) {
  const courseDataLimited = state === 'error' || state === 'degraded'

  return (
    <footer
      aria-label="Systemstatus"
      className="flex min-h-10 shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-t border-zinc-200 bg-white px-3 py-2 text-xs text-zinc-600 sm:px-4"
      data-testid="status-strip"
    >
      <span className="flex items-center gap-1.5">
        <MicOff aria-hidden="true" size={14} />
        Sprache inaktiv
      </span>
      <span className="flex items-center gap-1.5">
        <Plug
          aria-hidden="true"
          className={connectionState === 'connected' ? 'text-teal-700' : 'text-zinc-500'}
          size={14}
        />
        {connectionLabels[connectionState]}
      </span>
      <span className="ms-auto flex items-center gap-1.5">
        <ShieldCheck
          aria-hidden="true"
          className={courseDataLimited ? 'text-amber-600' : 'text-teal-700'}
          size={14}
        />
        Kursdaten {courseDataLimited ? 'begrenzt' : 'bereit'}
      </span>
    </footer>
  )
}
