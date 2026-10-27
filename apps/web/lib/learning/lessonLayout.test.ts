// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'
import { splitLessonContent } from './lessonLayout'

const player = (url: string) => ({ type: 'blockEmbed', attrs: { embedType: 'url', embedUrl: url, embedHeight: 900 } })
const paragraph = (text: string) => ({ type: 'paragraph', content: [{ type: 'text', text }] })

describe('splitLessonContent', () => {
  test('sequence players come first, in their order; everything else stays text in order', () => {
    const content = {
      type: 'doc',
      content: [
        paragraph('Einleitung'),
        { type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: 'Erklärvideo zum Kurs' }] },
        player('http://h:8090/lernsequenz/video-1?k=a'),
        paragraph('Dazwischen'),
        player('http://h:8090/lernsequenz/praes-1?k=b'),
        { type: 'blockEmbed', attrs: { embedType: 'url', embedUrl: 'https://www.youtube.com/watch?v=x' } },
        paragraph('Schluss'),
      ],
    }
    const split = splitLessonContent(content)
    expect(split.embeds.map((b) => (b.attrs as any).embedUrl)).toEqual([
      'http://h:8090/lernsequenz/video-1?k=a',
      'http://h:8090/lernsequenz/praes-1?k=b',
    ])
    expect(split.text.map((b) => b.type)).toEqual(['paragraph', 'heading', 'paragraph', 'blockEmbed', 'paragraph'])
  })

  test('a lesson without a player is all text', () => {
    expect(splitLessonContent({ type: 'doc', content: [paragraph('Nur Text')] })).toEqual({
      embeds: [],
      text: [paragraph('Nur Text')],
    })
    expect(splitLessonContent(null)).toEqual({ embeds: [], text: [] })
    expect(splitLessonContent({ type: 'doc' })).toEqual({ embeds: [], text: [] })
  })
})
