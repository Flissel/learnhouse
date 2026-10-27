/** Links to the sequence player (learning-api) carry the signed person token, so what the
 * person answers there counts for them. Any other embed is left alone. */
export const isSequencePlayer = (url: string): boolean => url.includes('/lernsequenz/')

export function withPersonToken(url: string, token: string): string {
  if (!token || !isSequencePlayer(url)) return url
  return url + (url.includes('?') ? '&' : '?') + 'p=' + encodeURIComponent(token)
}
