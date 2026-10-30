/** Feedback is "new" when it appears or its content changes; only then the window scrolls to it. */
export function shouldScrollToFeedback<T extends object>(prev: T | null | undefined, next: T | null | undefined): boolean {
  if (!next) return false
  if (!prev) return true
  return JSON.stringify(prev) !== JSON.stringify(next)
}
