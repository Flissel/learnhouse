import { BarChart3, BookOpenCheck, Library } from 'lucide-react'

interface SpaceRailProps {
  coursesHref: string
  learningHref: string
}

const railLink =
  'group flex h-14 w-14 flex-col items-center justify-center gap-1 rounded-md text-[10px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2'

export default function SpaceRail({ coursesHref, learningHref }: SpaceRailProps) {
  return (
    <nav
      aria-label="VibeMind Spaces"
      className="hidden w-[4.5rem] shrink-0 flex-col items-center border-e border-zinc-200 bg-zinc-950 py-4 text-zinc-300 lg:flex"
      data-testid="space-rail"
    >
      <a
        aria-current="page"
        className={`${railLink} bg-emerald-500 text-zinc-950`}
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
      <div className="mt-auto flex h-14 w-14 flex-col items-center justify-center gap-1 text-[10px] text-zinc-500">
        <BarChart3 aria-hidden="true" size={18} />
        <span>Fortschritt</span>
      </div>
    </nav>
  )
}
