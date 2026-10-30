'use client'

import { useEffect, useRef, useState } from 'react'
import { useLHSession } from '@components/Contexts/LHSessionContext'
import { getCourseRating, submitCourseRating } from '@/services/learning/practice'
import { allesSuper, cleanKeywords, MAX_KEYWORD_LENGTH, prefillFrom, shouldPrefill, type Smiley } from '@/lib/learning/courseRatingModel'

interface CourseRatingProps {
  courseUuid: string
}

const SMILEYS: { value: Smiley; icon: string }[] = [
  { value: 'schlecht', icon: '😕' },
  { value: 'mittel', icon: '🙂' },
  { value: 'gut', icon: '😃' },
]

/** Last page of a course: a smiley and up to three short keywords. */
export default function CourseRating({ courseUuid }: CourseRatingProps) {
  const session = useLHSession() as any
  const token = session?.data?.tokens?.access_token as string | undefined
  const courseId = courseUuid.replace(/^course_/, '')
  const [smiley, setSmiley] = useState<Smiley | null>(null)
  const [words, setWords] = useState<string[]>(['', '', ''])
  const touched = useRef(false)
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    getCourseRating(courseId, token)
      .then((reply) => {
        const own = prefillFrom(reply)
        if (!active || !own || !shouldPrefill(touched.current)) return
        setSmiley(own.smiley)
        setWords(own.words)
        setSaved(true)
      })
      .catch(() => undefined)
    return () => { active = false }
  }, [courseId, token])

  async function send(chosen: Smiley, keywords: string[]) {
    const cleaned = cleanKeywords(keywords)
    if (!cleaned.ok) {
      setError(`Ein Stichwort darf höchstens ${MAX_KEYWORD_LENGTH} Zeichen lang sein.`)
      return
    }
    setBusy(true)
    setError(null)
    try {
      await submitCourseRating(courseId, chosen, cleaned.stichworte, token)
      setSaved(true)
    } catch (reason) {
      const own = (reason as { userMessage?: unknown } | null)?.userMessage
      setError(typeof own === 'string' && own ? own : 'Die Bewertung konnte nicht gespeichert werden. Bitte versuchen Sie es noch einmal.')
    } finally {
      setBusy(false)
    }
  }

  function everythingFine() {
    const payload = allesSuper()
    touched.current = true
    setSmiley(payload.smiley)
    setWords(['', '', ''])
    void send(payload.smiley, payload.stichworte)
  }

  return (
    <section className="mx-auto flex w-full max-w-xl flex-col gap-5 px-4 py-8 text-[#17191C]">
      <h2 className="text-2xl font-semibold">Wie fanden Sie diesen Kurs?</h2>
      <div className="flex gap-3">
        {SMILEYS.map((item) => (
          <button
            key={item.value}
            type="button"
            aria-label={item.value}
            aria-pressed={smiley === item.value}
            onClick={() => { touched.current = true; setSmiley(item.value); setSaved(false) }}
            className={`flex-1 rounded-xl border-2 py-4 text-4xl transition ${smiley === item.value ? 'border-[#17191C] bg-white' : 'border-transparent bg-[#F6F5F1]'}`}
          >
            <span aria-hidden="true">{item.icon}</span>
          </button>
        ))}
      </div>
      <p className="text-base">Was würden Sie besser machen? Drei kurze Stichworte – oder keins, wenn alles gepasst hat.</p>
      <div className="flex flex-col gap-2">
        {words.map((word, index) => (
          <input
            key={index}
            type="text"
            value={word}
            maxLength={MAX_KEYWORD_LENGTH}
            onChange={(event) => { touched.current = true; setWords(words.map((w, i) => (i === index ? event.target.value : w))); setSaved(false) }}
            className="w-full rounded-lg border border-[#C9C6BC] bg-white px-3 py-2"
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          disabled={!smiley || busy}
          onClick={() => smiley && void send(smiley, words)}
          className="rounded-lg bg-[#17191C] px-5 py-2 text-white disabled:opacity-40"
        >
          Absenden
        </button>
        <button type="button" disabled={busy} onClick={everythingFine} className="rounded-lg border border-[#17191C] px-5 py-2 disabled:opacity-40">
          Alles super
        </button>
      </div>
      {error && <p role="alert" className="text-red-700">{error}</p>}
      {saved && (
        <div role="status">
          <p className="font-medium">Danke für Ihre Bewertung!</p>
          <p>Sie können sie jederzeit ändern.</p>
        </div>
      )}
    </section>
  )
}
