import type { LearnLevel } from '../api/client'
import { LEVEL_LABELS_KO, LEVEL_TONE } from '../lib/learn'

/**
 * Strength of evidence for one habit in my own records (D-034): `뚜렷함 · 급등 뒤 매수`. The
 * level is about the evidence, never the person, and the text always carries it; the tone only
 * echoes it. No gain/loss colour: a habit is not a result.
 */
export function SkillChip({ level, label, className = '' }: {
  level: LearnLevel
  label: string
  className?: string
}) {
  return (
    <span className={`whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-semibold ${LEVEL_TONE[level]} ${className}`}>
      {LEVEL_LABELS_KO[level]} · {label}
    </span>
  )
}
