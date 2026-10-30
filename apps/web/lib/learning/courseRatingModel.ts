export type Smiley = 'gut' | 'mittel' | 'schlecht'

export const MAX_KEYWORDS = 3
export const MAX_KEYWORD_LENGTH = 40

export interface RatingPayload {
  smiley: Smiley
  stichworte: string[]
}

export type KeywordResult = { ok: true; stichworte: string[] } | { ok: false; fehler: 'zu_lang' }

/** Trim, drop empty entries, keep at most three; a keyword over 40 characters is refused. */
export function cleanKeywords(input: string[]): KeywordResult {
  const stichworte = input.map((entry) => entry.trim()).filter((entry) => entry.length > 0)
  if (stichworte.some((entry) => entry.length > MAX_KEYWORD_LENGTH)) return { ok: false, fehler: 'zu_lang' }
  return { ok: true, stichworte: stichworte.slice(0, MAX_KEYWORDS) }
}

export const allesSuper = (): RatingPayload => ({ smiley: 'gut', stichworte: [] })

export interface StoredRating {
  smiley: Smiley
  stichworte: string[]
  aktualisiert?: string
}

/** What the proxy answers on GET: the rating wrapped, or null when there is none yet. */
export interface RatingReply {
  bewertung: StoredRating | null
}

/** Form values for an existing own rating; null when nothing is stored. */
export function prefillFrom(reply: RatingReply | null | undefined): { smiley: Smiley; words: string[] } | null {
  const own = reply?.bewertung
  if (!own || !own.smiley) return null
  return { smiley: own.smiley, words: [...(own.stichworte ?? []), '', '', ''].slice(0, MAX_KEYWORDS) }
}

/** A stored rating may fill the form only while the learner has not touched it. */
export const shouldPrefill = (touched: boolean): boolean => !touched
