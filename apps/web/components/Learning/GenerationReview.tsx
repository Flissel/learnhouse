import { AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react'

export type GenerationStage =
  | 'idle'
  | 'queued'
  | 'ingesting'
  | 'structuring'
  | 'authoring'
  | 'assessing'
  | 'verifying'
  | 'quality_gate'
  | 'review_ready'
  | 'failed'

export interface UnsupportedClaim {
  id: string
  text: string
}

export interface GenerationState {
  stage: GenerationStage
  progress: number
  unsupportedClaims: UnsupportedClaim[]
  sourceCoverage: number
  regenerationAttempts: number
  maximumRegenerationAttempts: number
}

interface GenerationReviewProps {
  generation: GenerationState
  onRegenerate?: () => void
}

const stageLabels: Record<GenerationStage, string> = {
  idle: 'Noch nicht gestartet',
  queued: 'Eingereiht',
  ingesting: 'Material wird verarbeitet',
  structuring: 'Curriculum wird strukturiert',
  authoring: 'Lektionen werden erstellt',
  assessing: 'Aufgaben werden erstellt',
  verifying: 'Quellen werden geprüft',
  quality_gate: 'Qualitätsprüfung',
  review_ready: 'Zur Prüfung bereit',
  failed: 'Generierung fehlgeschlagen',
}

export default function GenerationReview({ generation, onRegenerate }: GenerationReviewProps) {
  const remaining = Math.max(
    generation.maximumRegenerationAttempts - generation.regenerationAttempts,
    0,
  )
  const canRegenerate = remaining > 0 && Boolean(onRegenerate)

  return (
    <section aria-labelledby="generation-review-title" className="border-t border-zinc-200 pt-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase text-zinc-500">AI Course Factory</p>
          <h3 className="mt-1 text-base font-semibold text-zinc-950" id="generation-review-title">
            {stageLabels[generation.stage]}
          </h3>
        </div>
        <span className="text-sm font-semibold text-emerald-700">{generation.progress}%</span>
      </div>
      <div
        aria-label={`Generierungsfortschritt ${generation.progress}%`}
        className="mt-3 h-2 overflow-hidden rounded-full bg-zinc-200"
        role="progressbar"
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={generation.progress}
      >
        <div className="h-full bg-emerald-600" style={{ width: `${generation.progress}%` }} />
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className="border-s-4 border-teal-600 bg-teal-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase text-teal-800">Quellenabdeckung</p>
          <p className="mt-1 text-xl font-semibold text-zinc-950">{generation.sourceCoverage}%</p>
        </div>
        <div className="border-s-4 border-zinc-400 bg-zinc-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase text-zinc-600">Regeneration</p>
          <p className="mt-1 text-sm font-medium text-zinc-900">
            {remaining} von {generation.maximumRegenerationAttempts} Versuchen verfügbar
          </p>
        </div>
      </div>

      {generation.unsupportedClaims.length > 0 ? (
        <div className="mt-5">
          <div className="flex items-center gap-2 text-rose-800">
            <AlertTriangle aria-hidden="true" size={16} />
            <p className="text-sm font-semibold">Nicht belegte Aussage</p>
          </div>
          <ul className="mt-2 space-y-2">
            {generation.unsupportedClaims.map((claim) => (
              <li className="break-words rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-950" key={claim.id}>
                {claim.text}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="mt-5 flex items-center gap-2 text-sm text-teal-800">
          <CheckCircle2 aria-hidden="true" size={16} />
          Keine unbelegten Aussagen erkannt
        </div>
      )}

      <button
        className="mt-5 inline-flex h-10 items-center gap-2 rounded-md border border-zinc-300 px-4 text-sm font-semibold text-zinc-800 hover:bg-zinc-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={!canRegenerate}
        onClick={onRegenerate}
        type="button"
      >
        <RefreshCw aria-hidden="true" size={16} />
        Markierten Abschnitt neu erzeugen
      </button>
    </section>
  )
}

