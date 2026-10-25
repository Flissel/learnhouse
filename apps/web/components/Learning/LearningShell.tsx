'use client'

import { useCallback, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Bot, BookOpen, PanelLeft } from 'lucide-react'
import { getUriWithOrg } from '@services/config/config'
import { useLearningIntents } from '@/hooks/useLearningIntents'
import { useLearningActions } from '@/hooks/useLearningActions'
import { usePracticeSession } from '@/hooks/usePracticeSession'
import { practiceModel } from '@/lib/learning/practiceModel'
import type { LearningIntent } from '@/services/learning/intents'

import AgentPanel from './AgentPanel'
import CourseStudio, { emptyCourseStudioModel } from './CourseStudio'
import CourseOutline from './CourseOutline'
import LearningPlayer, { emptyLearningPlayerModel } from './LearningPlayer'
import LearningWorkspace from './LearningWorkspace'
import SpaceRail from './SpaceRail'
import StatusStrip from './StatusStrip'

export type LearningShellState = 'ready' | 'loading' | 'empty' | 'error' | 'degraded'
export type CompactPanel = 'outline' | 'workspace' | 'agent'
export type WorkspaceMode = 'studio' | 'player'

export interface LearningCourse {
  id: string
  name: string
  description?: string
}

export interface LearningShellProps {
  orgslug: string
  courses: LearningCourse[]
  state: LearningShellState
}

export function nextPanelAfterKey(panel: CompactPanel, key: string): CompactPanel {
  return key === 'Escape' ? 'workspace' : panel
}

const panelControls: Array<{
  id: CompactPanel
  label: string
  target: string
  icon: typeof BookOpen
}> = [
  { id: 'outline', label: 'Kurse', target: 'course-outline', icon: PanelLeft },
  { id: 'workspace', label: 'Lernen', target: 'learning-workspace', icon: BookOpen },
  { id: 'agent', label: 'Agent', target: 'agent-panel', icon: Bot },
]

export default function LearningShell({ orgslug, courses, state }: LearningShellProps) {
  const [compactPanel, setCompactPanel] = useState<CompactPanel>('workspace')
  const [selectedCourseId, setSelectedCourseId] = useState<string | null>(courses[0]?.id ?? null)
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>('player')
  const [playerMode, setPlayerMode] = useState<'training' | 'exam'>('training')
  const workspaceRef = useRef<HTMLElement | null>(null)
  const shellRef = useRef<HTMLDivElement | null>(null)

  const projectIntent = useCallback((intent: LearningIntent) => {
    if (intent.kind === 'open_course' && courses.some((course) => course.id === intent.course_id)) {
      setSelectedCourseId(intent.course_id)
      setCompactPanel('workspace')
      return
    }
    if (intent.kind === 'show_progress' || intent.kind === 'open_task') {
      setWorkspaceMode('player')
    }
    if (intent.kind !== 'focus_answer') return

    requestAnimationFrame(() => {
      const target = document.getElementById(intent.field_id)
      if (target instanceof HTMLElement && shellRef.current?.contains(target)) target.focus()
    })
  }, [courses])

  const connectionState = useLearningIntents({ onIntent: projectIntent })
  const learningActions = useLearningActions()

  const selectedCourse = useMemo(
    () => courses.find((course) => course.id === selectedCourseId) ?? courses[0] ?? null,
    [courses, selectedCourseId],
  )
  // Without the VibeMind desktop host the player practises through the LearnHouse backend.
  const practice = usePracticeSession(selectedCourse?.id ?? null)
  const browserPractice = !learningActions.available

  const learningHref = getUriWithOrg(orgslug, '/learning')
  const coursesHref = getUriWithOrg(orgslug, '/courses')
  const courseHref = selectedCourse
    ? getUriWithOrg(orgslug, `/course/${selectedCourse.id.replace(/^course_/, '')}`)
    : null
  const editorHref = selectedCourse
    ? getUriWithOrg(orgslug, `/dash/courses/course/${selectedCourse.id.replace(/^course_/, '')}/general`)
    : null

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const nextPanel = nextPanelAfterKey(compactPanel, event.key)
    if (nextPanel === compactPanel) return

    event.preventDefault()
    setCompactPanel(nextPanel)
    requestAnimationFrame(() => {
      workspaceRef.current = document.getElementById('learning-workspace')
      workspaceRef.current?.focus()
    })
  }

  function selectCourse(courseId: string) {
    setSelectedCourseId(courseId)
    setCompactPanel('workspace')
  }

  return (
    <div
      ref={shellRef}
      className="flex h-[calc(100vh-4rem)] min-h-0 w-full min-w-0 flex-col overflow-hidden bg-white text-zinc-950"
      data-learning-state={state}
      onKeyDown={handleKeyDown}
    >
      <a
        className="sr-only z-50 bg-white px-3 py-2 text-sm font-semibold text-zinc-950 focus:not-sr-only focus:absolute focus:start-3 focus:top-3 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        href="#learning-workspace"
      >
        Zum Lernbereich
      </a>

      <div aria-label="Bereich auswählen" className="grid grid-cols-3 border-b border-zinc-200 bg-white p-2 lg:hidden">
        {panelControls.map((control) => (
          <button
            aria-controls={control.target}
            aria-pressed={compactPanel === control.id}
            className={`flex h-10 items-center justify-center gap-2 rounded-md px-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
              compactPanel === control.id ? 'bg-zinc-950 text-white' : 'text-zinc-600 hover:bg-zinc-100'
            }`}
            key={control.id}
            onClick={() => setCompactPanel(control.id)}
            type="button"
          >
            <control.icon aria-hidden="true" size={16} />
            <span>{control.label}</span>
          </button>
        ))}
      </div>

      <div className="grid min-h-0 min-w-0 flex-1 grid-cols-1 lg:grid-cols-[4.5rem_minmax(13rem,17rem)_minmax(0,1fr)_minmax(16rem,20rem)]">
        <SpaceRail coursesHref={coursesHref} learningHref={learningHref} />
        <CourseOutline
          courses={courses}
          onSelect={selectCourse}
          selectedCourseId={selectedCourse?.id ?? null}
          state={state}
          visibleOnCompact={compactPanel === 'outline'}
        />
        <LearningWorkspace
          course={selectedCourse}
          courseHref={courseHref}
          state={state}
          visibleOnCompact={compactPanel === 'workspace'}
          mode={workspaceMode}
          onModeChange={setWorkspaceMode}
        >
          {selectedCourse && workspaceMode === 'studio' ? (
            <CourseStudio
              course={selectedCourse}
              editorHref={editorHref}
              model={emptyCourseStudioModel()}
              onApprove={learningActions.available ? () => {
                void learningActions.invoke({
                  version: '1', operation: 'course_review', course_id: selectedCourse.id, decision: 'approved',
                }).catch(() => undefined)
              } : undefined}
              onImportSource={learningActions.available ? (input) => {
                void learningActions.invoke({
                  version: '1', operation: 'material_import', course_id: selectedCourse.id,
                  title: input.title, source_url: input.sourceUrl,
                }).catch(() => undefined)
              } : undefined}
              onPublish={learningActions.available ? () => {
                void learningActions.invoke({
                  version: '1', operation: 'course_publish', course_id: selectedCourse.id, confirmed: true,
                }).catch(() => undefined)
              } : undefined}
              onStartGeneration={learningActions.available ? () => {
                void learningActions.invoke({
                  version: '1', operation: 'course_generate', course_id: selectedCourse.id,
                }).catch(() => undefined)
              } : undefined}
            />
          ) : selectedCourse && browserPractice ? (
            <LearningPlayer
              course={selectedCourse}
              courseHref={courseHref}
              model={practiceModel(practice.state.turn, {
                mode: playerMode, hint: practice.state.hint, busy: practice.state.busy, error: practice.state.error,
              })}
              onModeChange={setPlayerMode}
              onStartSession={practice.signedIn ? () => { void practice.start(playerMode) } : undefined}
              onSubmit={(answer) => { void practice.submit(answer) }}
              onHint={() => { void practice.hint() }}
              onNext={() => { void practice.next() }}
            />
          ) : selectedCourse ? (
            <LearningPlayer
              course={selectedCourse}
              courseHref={courseHref}
              model={{ ...emptyLearningPlayerModel(), mode: playerMode }}
              onModeChange={setPlayerMode}
              onStartSession={() => {
                void learningActions.invoke({
                  version: '1', operation: 'session_start', course_id: selectedCourse.id, mode: playerMode,
                }).catch(() => undefined)
              }}
            />
          ) : null}
        </LearningWorkspace>
        <AgentPanel
          course={selectedCourse}
          state={state}
          visibleOnCompact={compactPanel === 'agent'}
          // While a feedback is shown the engine already holds the next task; the tutor would
          // answer about that one, so it returns with the next task.
          onAsk={browserPractice && practice.state.turn && !practice.state.pending
            ? (question) => { void practice.ask(question) } : undefined}
          tutor={practice.state.tutor}
          busy={practice.state.busy}
        />
      </div>
      <StatusStrip connectionState={connectionState} state={state} />
    </div>
  )
}
