'use client'

import { use } from 'react'
import LearningShell, {
  type LearningCourse,
  type LearningShellState,
} from '@components/Learning/LearningShell'
import { useCourses } from '@/hooks/queries/useCourses'

interface LearningPageProps {
  params: Promise<{ orgslug: string }>
}

export default function LearningPage(_props: LearningPageProps) {
  const { orgslug } = use(_props.params)
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
