/** Links to the sequence player (learning-api) carry the signed person token, so what the
 * person answers there counts for them. Course authors can embed any URL, so the token
 * goes only to the one trusted player origin, matched exactly, on a player path. */
export const isSequencePlayer = (url: string): boolean => url.includes('/lernsequenz/')

export function withPersonToken(url: string, token: string, origin: string | null | undefined): string {
  if (!token || !origin) return url
  try {
    const parsed = new URL(url)
    if (parsed.origin !== origin || !parsed.pathname.startsWith('/lernsequenz/')) return url
    parsed.searchParams.set('p', token)
    return parsed.toString()
  } catch {
    return url
  }
}
