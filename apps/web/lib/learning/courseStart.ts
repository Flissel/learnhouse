/** What the course start needs from the trail and the chapters: where to continue, and
 * how far each chapter is. Pure, so it can be tested without React. */

export interface ActivityLike {
  id?: number
  activity_uuid: string
  name: string
}

export interface ChapterLike {
  chapter_uuid: string
  name: string
  activities: ActivityLike[]
}

export interface TrailLike {
  runs?: Array<{
    course?: { course_uuid?: string }
    steps?: Array<{ activity_id?: number; complete?: boolean }>
  }>
}

export type ChapterStatus = 'done' | 'current' | 'open'

const MAX_TITLE = 60

/** The title's lead: cut at the first colon or bracket, at most 60 characters. */
export function shortTitle(title: string): string {
  const lead = title.split(/[:(]/, 1)[0].trim()
  return lead.length > MAX_TITLE ? lead.slice(0, MAX_TITLE - 1).trimEnd() + '…' : lead
}

const bare = (uuid: string | undefined): string => (uuid ?? '').replace(/^course_/, '')

/** Ids of the activities the person completed in this course. */
export function completedIds(trail: TrailLike | null | undefined, courseUuid: string): Set<number> {
  const run = (trail?.runs ?? []).find((candidate) => bare(candidate.course?.course_uuid) === bare(courseUuid))
  const done = new Set<number>()
  for (const step of run?.steps ?? []) {
    if (step.complete === true && typeof step.activity_id === 'number') done.add(step.activity_id)
  }
  return done
}

/** The first activity not yet completed, in course order; null when there is none left. */
export function nextActivity(trail: TrailLike | null | undefined, chapters: ChapterLike[], courseUuid: string): ActivityLike | null {
  const done = completedIds(trail, courseUuid)
  for (const chapter of chapters) {
    for (const activity of chapter.activities ?? []) {
      if (activity.id === undefined || !done.has(activity.id)) return activity
    }
  }
  return null
}

export function chapterStatus(
  trail: TrailLike | null | undefined, chapter: ChapterLike, chapters: ChapterLike[], courseUuid: string,
): ChapterStatus {
  const activities = chapter.activities ?? []
  const done = completedIds(trail, courseUuid)
  if (activities.length > 0 && activities.every((activity) => activity.id !== undefined && done.has(activity.id))) return 'done'
  const next = nextActivity(trail, chapters, courseUuid)
  if (next && activities.some((activity) => activity.activity_uuid === next.activity_uuid)) return 'current'
  return 'open'
}
