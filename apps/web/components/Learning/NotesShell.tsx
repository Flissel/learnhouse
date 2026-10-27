'use client'

import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, StickyNote } from 'lucide-react'
import { useLHSession } from '@components/Contexts/LHSessionContext'
import { getUriWithOrg } from '@services/config/config'
import { listNotes, setNoteText, type NoteRead } from '@/services/learning/practice'
import { courseHref, notesModel } from '@/lib/learning/notesModel'
import { useCourses } from '@/hooks/queries/useCourses'

interface NotesShellProps {
  orgslug: string
}

const dateLabel = (iso: string): string => {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

/** The person's notes: list by course on the left, the chosen note on the right. */
export default function NotesShell({ orgslug }: NotesShellProps) {
  const session = useLHSession() as any
  const token = session?.data?.tokens?.access_token as string | undefined
  const courses = useCourses(orgslug)
  const [notes, setNotes] = useState<NoteRead[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    listNotes(token)
      .then((reply) => { if (active) { setNotes(reply.notes); setError(null) } })
      .catch((reason: Error) => { if (active) { setNotes([]); setError(reason.message) } })
    return () => { active = false }
  }, [token])

  const courseNames = useMemo(() => {
    const names: Record<string, string> = {}
    for (const course of Array.isArray(courses.data) ? courses.data : []) {
      if (typeof course?.course_uuid === 'string' && typeof course?.name === 'string') {
        names[course.course_uuid.replace(/^course_/, '')] = course.name
      }
    }
    return names
  }, [courses.data])

  const model = useMemo(() => notesModel(notes ?? [], courseNames), [notes, courseNames])
  const selected = useMemo(
    () => (notes ?? []).find((note) => note.id === selectedId) ?? model.byCourse[0]?.notes[0] ?? null,
    [notes, selectedId, model],
  )

  function replace(changed: NoteRead) {
    setNotes((current) => (current ?? []).map((note) => (note.id === changed.id ? changed : note)))
  }

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-[#F6F5F1] text-[#17191C]">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-6 sm:px-6">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <a
              className="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-[#0E6B5C] hover:underline"
              href={getUriWithOrg(orgslug, '/learning')}
            >
              <ArrowLeft aria-hidden="true" size={16} /> Lernen
            </a>
            <h1 className="mt-1 text-2xl font-extrabold tracking-tight">Meine Notizen</h1>
            <p className="text-sm text-zinc-600">
              Was Sie im Kurs markiert haben – mit der Erklärung aus dem Kurs und Ihren eigenen Worten.
            </p>
          </div>
          <div className="text-sm text-zinc-600">{model.total} {model.total === 1 ? 'Notiz' : 'Notizen'}</div>
        </header>

        {error ? (
          <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="alert">
            Die Notizen sind gerade nicht erreichbar: {error}
          </div>
        ) : null}

        {notes !== null && model.total === 0 && !error ? (
          <div className="rounded-2xl border border-dashed border-zinc-300 bg-white px-6 py-10 text-center">
            <StickyNote aria-hidden="true" className="mx-auto text-[#0E6B5C]" size={28} />
            <p className="mt-3 font-semibold">Noch keine Notizen.</p>
            <p className="mt-1 text-sm text-zinc-600">
              Im Kurs „Stelle markieren“ wählen, einen Rahmen ziehen und „Notiz anlegen“ drücken.
            </p>
          </div>
        ) : null}

        {model.total > 0 ? (
          <div className="grid gap-4 lg:grid-cols-[minmax(260px,340px)_1fr]">
            <nav aria-label="Notizen nach Kurs" className="flex flex-col gap-4">
              {model.byCourse.map((course) => (
                <section key={course.courseId} className="rounded-2xl border border-zinc-200 bg-white p-3">
                  <h2 className="px-2 pb-2 text-xs font-bold uppercase tracking-wide text-zinc-500">{course.title}</h2>
                  <ul className="flex flex-col gap-1">
                    {course.notes.map((note) => (
                      <li key={note.id}>
                        <button
                          aria-current={selected?.id === note.id ? 'true' : undefined}
                          className={`flex min-h-11 w-full flex-col items-start rounded-xl px-3 py-2 text-left transition-colors ${
                            selected?.id === note.id ? 'bg-[#E8F2EF] text-[#0E6B5C]' : 'hover:bg-zinc-100'
                          }`}
                          onClick={() => setSelectedId(note.id)}
                          type="button"
                        >
                          <span className="line-clamp-2 text-sm font-semibold">„{note.selection}“</span>
                          <span className="text-xs text-zinc-500">{dateLabel(note.created_at)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </nav>

            {selected ? <NoteDetail key={selected.id} note={selected} orgslug={orgslug} token={token} onSaved={replace} /> : null}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function NoteDetail({ note, orgslug, token, onSaved }: {
  note: NoteRead
  orgslug: string
  token?: string
  onSaved: (note: NoteRead) => void
}) {
  const [text, setText] = useState(note.own_text)
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [message, setMessage] = useState('')

  async function save() {
    setState('saving')
    try {
      onSaved(await setNoteText(note.id, text, token))
      setState('saved')
      setMessage('Gespeichert.')
    } catch (reason) {
      setState('error')
      setMessage(reason instanceof Error ? reason.message : 'Speichern hat nicht geklappt.')
    }
  }

  return (
    <article aria-labelledby="note-title" className="flex flex-col gap-4 rounded-2xl border border-zinc-200 bg-white p-5 sm:p-6">
      <div>
        <div className="text-xs font-bold uppercase tracking-wide text-[#0E6B5C]">Markierte Stelle</div>
        <blockquote id="note-title" className="mt-1 border-l-4 border-[#0E6B5C] pl-3 text-lg font-semibold leading-snug">
          {note.selection}
        </blockquote>
        <div className="mt-1 text-xs text-zinc-500">{dateLabel(note.created_at)}</div>
      </div>

      <section>
        <h3 className="text-xs font-bold uppercase tracking-wide text-zinc-500">Erklärung aus dem Kurs</h3>
        <p className="mt-1 whitespace-pre-wrap text-[15px] leading-relaxed">{note.explanation}</p>
      </section>

      {note.extra ? (
        <section className="rounded-xl border-l-4 border-amber-500 bg-amber-50 px-4 py-3">
          <h3 className="text-xs font-bold uppercase tracking-wide text-amber-800">Mehr dazu – nicht aus dem Kurs</h3>
          <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-amber-950">{note.extra}</p>
          {note.extra_sources.length ? (
            <ul className="mt-2 text-xs text-amber-800">
              {note.extra_sources.map((source) => <li key={source}>{source}</li>)}
            </ul>
          ) : null}
        </section>
      ) : null}

      <section>
        <label className="text-xs font-bold uppercase tracking-wide text-zinc-500" htmlFor="own-text">Eigene Worte</label>
        <textarea
          className="mt-1 min-h-28 w-full rounded-xl border border-zinc-300 px-3 py-2 text-[15px] leading-relaxed focus:border-[#0E6B5C] focus:outline-none focus:ring-2 focus:ring-[#0E6B5C]/30"
          id="own-text"
          maxLength={10000}
          onChange={(event) => { setText(event.target.value); setState('idle') }}
          placeholder="Was nehmen Sie daraus mit?"
          value={text}
        />
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <button
            className="min-h-11 rounded-xl bg-[#0E6B5C] px-5 font-semibold text-white disabled:opacity-50"
            disabled={state === 'saving' || text === note.own_text}
            onClick={save}
            type="button"
          >
            Speichern
          </button>
          <span aria-live="polite" className={`text-sm ${state === 'error' ? 'text-amber-800' : 'text-zinc-600'}`}>{message}</span>
          <a className="ml-auto min-h-11 inline-flex items-center text-sm font-semibold text-[#0E6B5C] hover:underline" href={getUriWithOrg(orgslug, courseHref(note))}>
            Zur Stelle im Kurs →
          </a>
        </div>
      </section>
    </article>
  )
}
