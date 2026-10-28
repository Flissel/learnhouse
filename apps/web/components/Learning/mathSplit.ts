export type MathPart = { kind: 'text' | 'inline' | 'block'; value: string }

// $$…$$ (may span lines) or $…$ on one line; no space right after the opening or
// before the closing $, so "5 $ und 6 $" stays text. An unclosed $ never matches.
const MATH = /\$\$([\s\S]+?)\$\$|\$(?!\s)([^$\n]*[^$\s])\$/g

/** Splits text into plain text, inline formulas ($…$) and block formulas ($$…$$). */
export function splitMath(text: string): MathPart[] {
  const parts: MathPart[] = []
  let last = 0
  for (const match of text.matchAll(MATH)) {
    const index = match.index ?? 0
    if (index > last) parts.push({ kind: 'text', value: text.slice(last, index) })
    if (match[1] !== undefined) parts.push({ kind: 'block', value: match[1].trim() })
    else parts.push({ kind: 'inline', value: match[2] })
    last = index + match[0].length
  }
  if (last < text.length) parts.push({ kind: 'text', value: text.slice(last) })
  return parts
}
