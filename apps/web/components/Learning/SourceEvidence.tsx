import MathText from './MathText'
import { BookMarked, CircleAlert, ExternalLink } from 'lucide-react'

export interface SourceEvidenceItem {
  id: string
  title: string
  locator?: string
  href?: string
  supported: boolean
}

interface SourceEvidenceProps {
  items: SourceEvidenceItem[]
  math?: boolean
}

export default function SourceEvidence({ items, math }: SourceEvidenceProps) {
  if (items.length === 0) {
    return <p className="text-sm text-zinc-500">Keine Quellenbelege für diese Aufgabe verfügbar.</p>
  }

  return (
    <ul className="space-y-2" aria-label="Quellenbelege">
      {items.map((item) => (
        <li className="min-w-0 rounded-md border border-zinc-200 bg-white px-3 py-3" key={item.id}>
          <div className="flex min-w-0 items-start gap-2">
            {item.supported ? (
              <BookMarked aria-hidden="true" className="mt-0.5 shrink-0 text-teal-700" size={16} />
            ) : (
              <CircleAlert aria-hidden="true" className="mt-0.5 shrink-0 text-rose-700" size={16} />
            )}
            <div className="min-w-0 flex-1">
              <p className="break-words text-sm font-medium text-zinc-900">{item.title}</p>
              <p className="mt-1 break-words text-xs text-zinc-500">
                {item.supported ? (item.locator ? <MathText math={math} text={item.locator} /> : 'Fundstelle verfügbar') : 'Beleg nicht bestätigt'}
              </p>
            </div>
            {item.href ? (
              <a
                aria-label={`${item.title} öffnen`}
                className="shrink-0 rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                href={item.href}
              >
                <ExternalLink aria-hidden="true" size={15} />
              </a>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  )
}

