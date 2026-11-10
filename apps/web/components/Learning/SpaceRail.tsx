import { BarChart3, BookOpenCheck, Library, StickyNote, UsersRound } from 'lucide-react'

interface SpaceRailProps {
  coursesHref: string
  learningHref: string
  notesHref?: string
  /** Only for admins, course leaders and root; participants get no entry. */
  verwaltungHref?: string
  active?: 'learning' | 'verwaltung'
}

const railLink =
  'group flex h-14 w-14 flex-col items-center justify-center gap-1 rounded-md text-[10px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2'
const railActive = 'bg-emerald-500 text-zinc-950'
const railIdle = 'text-zinc-400 hover:bg-zinc-800 hover:text-white'

export default function SpaceRail({ coursesHref, learningHref, notesHref, verwaltungHref, active = 'learning' }: SpaceRailProps) {
  const verwaltungActive = active === 'verwaltung' && Boolean(verwaltungHref)
  return (
    <nav
      aria-label="VibeMind Spaces"
      className="hidden w-[4.5rem] shrink-0 flex-col items-center border-e border-zinc-200 bg-zinc-950 py-4 text-zinc-300 lg:flex"
      data-testid="space-rail"
    >
      <a
        aria-current={verwaltungActive ? undefined : 'page'}
        className={`${railLink} ${verwaltungActive ? railIdle : railActive}`}
        href={learningHref}
        title="Lernen"
      >
        <BookOpenCheck aria-hidden="true" size={19} strokeWidth={2} />
        <span>Lernen</span>
      </a>
      <a
        className={`${railLink} mt-2 text-zinc-400 hover:bg-zinc-800 hover:text-white`}
        href={coursesHref}
        title="Kurse"
      >
        <Library aria-hidden="true" size={19} strokeWidth={2} />
        <span>Kurse</span>
      </a>
      {notesHref ? (
        <a
          className={`${railLink} mt-2 text-zinc-400 hover:bg-zinc-800 hover:text-white`}
          href={notesHref}
          title="Notizen"
        >
          <StickyNote aria-hidden="true" size={19} strokeWidth={2} />
          <span>Notizen</span>
        </a>
      ) : null}
      {verwaltungHref ? (
        <a
          aria-current={verwaltungActive ? 'page' : undefined}
          className={`${railLink} mt-2 ${verwaltungActive ? railActive : railIdle}`}
          href={verwaltungHref}
          title="Verwaltung"
        >
          <UsersRound aria-hidden="true" size={19} strokeWidth={2} />
          <span>Verwaltung</span>
        </a>
      ) : null}
      <div className="mt-auto flex h-14 w-14 flex-col items-center justify-center gap-1 text-[10px] text-zinc-500">
        <BarChart3 aria-hidden="true" size={18} />
        <span>Fortschritt</span>
      </div>
    </nav>
  )
}
