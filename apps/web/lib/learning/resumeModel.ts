import type { PracticeReply, PracticeTurn } from '@/services/learning/practice'

/** The session to continue on open: only an active training session; otherwise nothing. */
export function resumedTurn(reply: PracticeReply): PracticeTurn | null {
  const session = reply.result?.session
  if (!session || session.state !== 'active' || session.mode !== 'training') return null
  return session
}
