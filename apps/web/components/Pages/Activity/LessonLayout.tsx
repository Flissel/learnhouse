'use client'

import { lazy, Suspense } from 'react'
import { splitLessonContent } from '@/lib/learning/lessonLayout'

const Canva = lazy(() => import('@components/Objects/Activities/DynamicCanva/DynamicCanva'))

interface LessonLayoutProps {
  content: any
  activity: any
  courseUuid?: string
  orgUuid?: string
}

/** A lesson with sequence players: the players first, full width; the text to read below,
 * folded away until wanted. A lesson without players renders as before. */
export default function LessonLayout({ content, activity, courseUuid, orgUuid }: LessonLayoutProps) {
  const { embeds, text } = splitLessonContent(content)
  if (!embeds.length) {
    return (
      <Suspense fallback={null}>
        <Canva content={content} activity={activity} courseUuid={courseUuid} orgUuid={orgUuid} />
      </Suspense>
    )
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-2xl bg-white p-2 nice-shadow sm:p-3">
        <Suspense fallback={<div className="h-[600px] animate-pulse rounded-xl bg-zinc-100" />}>
          <Canva content={{ ...content, content: embeds }} activity={activity} hideTableOfContents courseUuid={courseUuid} orgUuid={orgUuid} />
        </Suspense>
      </div>
      {text.length ? (
        <details className="group rounded-2xl bg-white nice-shadow">
          <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between px-5 py-3 text-base font-semibold text-[#17191C]">
            <span>Zum Nachlesen</span>
            <span className="text-sm font-normal text-zinc-500 group-open:hidden">aufklappen</span>
          </summary>
          <div className="px-3 pb-3 sm:px-5">
            <Suspense fallback={null}>
              <Canva content={{ ...content, content: text }} activity={activity} courseUuid={courseUuid} orgUuid={orgUuid} />
            </Suspense>
          </div>
        </details>
      ) : null}
    </div>
  )
}
