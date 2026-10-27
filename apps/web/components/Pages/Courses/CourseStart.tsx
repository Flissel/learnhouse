'use client'

import Link from 'next/link'
import { Check, ChevronRight, Play } from 'lucide-react'
import { getUriWithOrg } from '@services/config/config'
import {
  chapterStatus,
  completedIds,
  nextActivity,
  shortTitle,
  type ActivityLike,
  type ChapterLike,
  type TrailLike,
} from '@/lib/learning/courseStart'

interface CourseStartProps {
  course: { name: string; course_uuid: string; chapters?: ChapterLike[] }
  trail?: TrailLike | null
  orgslug: string
}

/** The course start as "Dein Weg": one clear next step, and the chapters as a short list
 * with their state. The course page keeps its details below. */
export default function CourseStart({ course, trail, orgslug }: CourseStartProps) {
  const chapters = course.chapters ?? []
  const courseId = course.course_uuid.replace(/^course_/, '')
  const next = nextActivity(trail, chapters, course.course_uuid)
  const done = completedIds(trail, course.course_uuid)
  const total = chapters.reduce((sum, chapter) => sum + (chapter.activities?.length ?? 0), 0)
  const finished = chapters.reduce(
    (sum, chapter) => sum + (chapter.activities ?? []).filter((activity) => activity.id !== undefined && done.has(activity.id)).length,
    0,
  )
  const href = (activity: ActivityLike) =>
    getUriWithOrg(orgslug, `/course/${courseId}/activity/${activity.activity_uuid.replace(/^activity_/, '')}`)

  return (
    <section aria-labelledby="course-start" className="rounded-2xl border border-[#E3E5E0] bg-[#F6F5F1] p-5 text-[#17191C] sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-xs font-bold uppercase tracking-[0.08em] text-[#0E6B5C]">Dein Weg</div>
          <h2 className="mt-1 text-2xl font-extrabold tracking-tight" id="course-start">{course.name}</h2>
          <p className="mt-1 text-sm text-zinc-600">
            {total > 0 ? `${finished} von ${total} Schritten geschafft` : 'Dieser Kurs hat noch keine Schritte.'}
          </p>
        </div>
        {next ? (
          <Link
            className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-[#0E6B5C] px-5 font-semibold text-white hover:bg-[#0B5649] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0E6B5C]/40"
            href={href(next)}
          >
            <Play aria-hidden="true" size={16} />
            <span>{finished > 0 ? 'Weiter mit' : 'Starten mit'}: {shortTitle(next.name)}</span>
          </Link>
        ) : total > 0 ? (
          <div className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-[#E8F2EF] px-5 font-semibold text-[#0E6B5C]">
            <Check aria-hidden="true" size={16} /> Alles geschafft
          </div>
        ) : null}
      </div>

      {chapters.length ? (
        <ol aria-label="Schritte" className="mt-5 grid gap-2 sm:grid-cols-2">
          {chapters.map((chapter, index) => {
            const status = chapterStatus(trail, chapter, chapters, course.course_uuid)
            const first = chapter.activities?.[0]
            const lead = shortTitle(chapter.name)
            const frame = status === 'done'
              ? 'border-[#0E6B5C]/30 bg-[#E8F2EF]'
              : status === 'current' ? 'border-[#0E6B5C] bg-white' : 'border-[#E3E5E0] bg-white'
            const badge = status === 'done'
              ? 'bg-[#0E6B5C] text-white'
              : status === 'current' ? 'border-2 border-[#0E6B5C] text-[#0E6B5C]' : 'bg-zinc-100 text-zinc-500'
            const inner = (
              <>
                <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${badge}`}>
                  {status === 'done' ? <Check aria-hidden="true" size={14} /> : index + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold">{lead}</span>
                  {lead !== chapter.name ? <span className="block truncate text-xs text-zinc-500">{chapter.name}</span> : null}
                </span>
                <ChevronRight aria-hidden="true" className="shrink-0 text-zinc-400" size={16} />
              </>
            )
            const className = `flex min-h-12 items-center gap-3 rounded-xl border px-3 py-2 ${frame}`
            return (
              <li key={chapter.chapter_uuid}>
                {first ? (
                  <Link aria-current={status === 'current' ? 'step' : undefined} className={className} href={href(first)}>{inner}</Link>
                ) : (
                  <div className={className}>{inner}</div>
                )}
              </li>
            )
          })}
        </ol>
      ) : null}
    </section>
  )
}
