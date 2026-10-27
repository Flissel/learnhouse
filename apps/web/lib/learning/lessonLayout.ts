/** A lesson's content split for the lesson layout: the sequence players (video, presentation)
 * go first, full width; everything else is the text to read below. */

export interface Block {
  type: string
  attrs?: Record<string, unknown>
  content?: Block[]
  [key: string]: unknown
}

export interface LessonSplit {
  embeds: Block[]
  text: Block[]
}

const isPlayer = (block: Block): boolean =>
  block.type === 'blockEmbed' && typeof block.attrs?.embedUrl === 'string' && (block.attrs.embedUrl as string).includes('/lernsequenz/')

export function splitLessonContent(content: { type?: string; content?: Block[] } | null | undefined): LessonSplit {
  const blocks = Array.isArray(content?.content) ? content.content : []
  return { embeds: blocks.filter(isPlayer), text: blocks.filter((block) => !isPlayer(block)) }
}
