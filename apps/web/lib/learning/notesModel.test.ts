import { describe, expect, test } from 'bun:test'
import { courseHref, notesModel, type NoteRead } from './notesModel'

const note = (changes: Partial<NoteRead>): NoteRead => ({
  id: 'n1',
  course_id: 'c-1',
  sequence_id: 'praes-c-1-kurs',
  anchor: { section_id: 'f1' },
  selection: '45.000 € im Jahr',
  explanation: 'Die jährlichen Kosten laut Folie 2.',
  extra: '',
  extra_sources: [],
  own_text: '',
  created_at: '2026-10-27T10:00:00+00:00',
  updated_at: '2026-10-27T10:00:00+00:00',
  ...changes,
})

describe('notesModel', () => {
  test('groups by course, newest course and newest note first, with the course name', () => {
    const notes = [
      note({ id: 'old', course_id: 'c-1', created_at: '2026-10-25T10:00:00+00:00' }),
      note({ id: 'b', course_id: 'c-2', created_at: '2026-10-26T10:00:00+00:00' }),
      note({ id: 'new', course_id: 'c-1', created_at: '2026-10-27T10:00:00+00:00' }),
    ]
    const model = notesModel(notes, { 'c-1': 'Claude Code im Terminal einrichten' })
    expect(model.byCourse.map((c) => c.courseId)).toEqual(['c-1', 'c-2'])
    expect(model.byCourse[0].title).toBe('Claude Code im Terminal einrichten')
    expect(model.byCourse[0].notes.map((n) => n.id)).toEqual(['new', 'old'])
    expect(model.byCourse[1].title).toBe('Kurs c-2')
    expect(model.total).toBe(3)
  })

  test('the outside-course marker survives and empty extras stay empty', () => {
    const marked = note({ extra: 'Allgemein gilt …' })
    const model = notesModel([marked, note({ id: 'n2' })], {})
    expect(model.byCourse[0].notes.find((n) => n.id === 'n1')?.extra).toBe('Allgemein gilt …')
    expect(model.byCourse[0].notes.find((n) => n.id === 'n2')?.extra).toBe('')
  })

  test('the course link leads back into the course', () => {
    expect(courseHref(note({ course_id: 'b189a3ec-a82a-4ae2-8cab-e71ab0d75055' }))).toBe(
      '/course/course_b189a3ec-a82a-4ae2-8cab-e71ab0d75055',
    )
  })

  test('nothing to show is an empty model', () => {
    expect(notesModel([], {})).toEqual({ byCourse: [], total: 0 })
  })
})
