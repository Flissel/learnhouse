// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'
import { chapterStatus, nextActivity, shortTitle, type ChapterLike, type TrailLike } from './courseStart'

const COURSE = 'course_b189a3ec'
const chapters: ChapterLike[] = [
  { chapter_uuid: 'ch1', name: 'Einführung', activities: [{ id: 1, activity_uuid: 'activity_1', name: 'Einführung: Überblick' }] },
  { chapter_uuid: 'ch2', name: 'Schritt 2', activities: [
    { id: 2, activity_uuid: 'activity_2', name: 'Schritt 2: Installieren in Windows PowerShell' },
    { id: 3, activity_uuid: 'activity_3', name: 'Schritt 2: Installieren in CMD' },
  ] },
]
const trail = (done: number[]): TrailLike => ({
  runs: [{ course: { course_uuid: COURSE }, steps: done.map((id) => ({ activity_id: id, complete: true })) }],
})

describe('shortTitle', () => {
  test('cuts at the first colon or bracket and caps the length', () => {
    expect(shortTitle('Voraussetzung 1: Konto bei Anthropic (Plan-Preise und Nutzungsgrenzen)')).toBe('Voraussetzung 1')
    expect(shortTitle('Andere Installationswege (Homebrew, WinGet)')).toBe('Andere Installationswege')
    expect(shortTitle('x'.repeat(80))).toBe('x'.repeat(59) + '…')
    expect(shortTitle('  Kurz  ')).toBe('Kurz')
  })
})

describe('nextActivity', () => {
  test('is the first activity not yet completed, in course order', () => {
    expect(nextActivity(trail([]), chapters, COURSE)?.id).toBe(1)
    expect(nextActivity(trail([1]), chapters, COURSE)?.id).toBe(2)
    expect(nextActivity(trail([1, 3]), chapters, COURSE)?.id).toBe(2)
    expect(nextActivity(trail([1, 2, 3]), chapters, COURSE)).toBeNull()
  })

  test('without a trail or run the course starts at the beginning', () => {
    expect(nextActivity(undefined, chapters, COURSE)?.id).toBe(1)
    expect(nextActivity({ runs: [{ course: { course_uuid: 'course_other' }, steps: [{ activity_id: 1, complete: true }] }] }, chapters, COURSE)?.id).toBe(1)
    expect(nextActivity(trail([]), [], COURSE)).toBeNull()
  })
})

describe('chapterStatus', () => {
  test('done when every activity is complete, current where the next one sits, open otherwise', () => {
    expect(chapterStatus(trail([1]), chapters[0], chapters, COURSE)).toBe('done')
    expect(chapterStatus(trail([1]), chapters[1], chapters, COURSE)).toBe('current')
    expect(chapterStatus(trail([]), chapters[1], chapters, COURSE)).toBe('open')
    expect(chapterStatus(trail([]), chapters[0], chapters, COURSE)).toBe('current')
  })
})
