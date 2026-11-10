'use client'

import { use } from 'react'
import LearningShell, {
  type LearningCourse,
  type LearningShellState,
} from '@components/Learning/LearningShell'
import Kursuebersicht from '@components/Learning/Kursuebersicht'
import { useCourses } from '@/hooks/queries/useCourses'

interface LearningPageProps {
  params: Promise<{ orgslug: string }>
  searchParams: Promise<Record<string, string | string[] | undefined>>
}

/**
 * Entry of the learning area is the course overview (own Lern-Hülle per course, and the
 * management area for admins and course leaders). `?bereich=browser` keeps the in-browser
 * practice workspace reachable.
 */
export default function LearningPage(_props: LearningPageProps) {
  const { orgslug } = use(_props.params)
  const { bereich } = use(_props.searchParams)

  if (bereich === 'browser') return <BrowserLearning orgslug={orgslug} />
  return <Kursuebersicht bereich={bereich === 'verwaltung' ? 'verwaltung' : 'kurse'} orgslug={orgslug} />
}

function BrowserLearning({ orgslug }: { orgslug: string }) {
  const query = useCourses(orgslug)
  const courses = normalizeCourses(query.data)
  let state: LearningShellState = 'ready'

  if (query.isLoading) state = 'loading'
  else if (query.isError) state = 'error'
  else if (courses === null) state = 'degraded'
  else if (courses.length === 0) state = 'empty'

  return <LearningShell orgslug={orgslug} courses={courses ?? []} state={state} />
}

function normalizeCourses(value: unknown): LearningCourse[] | null {
  if (!Array.isArray(value)) return value === undefined ? [] : null

  const courses: LearningCourse[] = []
  for (const candidate of value) {
    if (!isRecord(candidate)) return null
    if (typeof candidate.course_uuid !== 'string' || typeof candidate.name !== 'string') {
      return null
    }

    courses.push({
      id: candidate.course_uuid,
      name: candidate.name,
      ...(typeof candidate.description === 'string' && candidate.description
        ? { description: candidate.description }
        : {}),
    })
  }
  return courses
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}
