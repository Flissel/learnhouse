import type { NoteRead } from '@/services/learning/practice'

export type { NoteRead }

export interface NotesByCourse {
  courseId: string
  title: string
  notes: NoteRead[]
}

export interface NotesModel {
  byCourse: NotesByCourse[]
  total: number
}

/** Notes grouped by course: the course with the newest note first, newest note first
 * inside it. `extra` stays exactly as stored — it is what the course did not say. */
export function notesModel(notes: NoteRead[], courseNames: Record<string, string>): NotesModel {
  const groups = new Map<string, NoteRead[]>()
  for (const note of [...notes].sort((a, b) => b.created_at.localeCompare(a.created_at))) {
    const list = groups.get(note.course_id)
    if (list) list.push(note)
    else groups.set(note.course_id, [note])
  }
  const byCourse = [...groups.entries()].map(([courseId, list]) => ({
    courseId,
    title: courseNames[courseId] ?? `Kurs ${courseId}`,
    notes: list,
  }))
  return { byCourse, total: notes.length }
}

/** Back into the course the note was taken in (the LearnHouse course id carries the prefix). */
export const courseHref = (note: NoteRead): string => `/course/course_${note.course_id}`
