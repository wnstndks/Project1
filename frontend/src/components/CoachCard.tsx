import { Link } from 'react-router-dom'

import { useCoachDiagnosis } from '../api/hooks'
import { coachSummary } from '../lib/coach'

/**
 * Home strip for the portfolio coach (D-033): one sentence from the diagnosis (policy
 * violations, coin share, missing cash) or the nudge to write a policy, linking to the coach
 * page. Hidden while loading, on error and with nothing held. Not advice, and it says so.
 */
export function CoachCard() {
  const diagnosis = useCoachDiagnosis()
  const text = coachSummary(diagnosis.data)
  if (!text) return null
  return (
    <Link to="/coach" className="block rounded-lg border border-line bg-surface px-4 py-3 text-sm hover:bg-hover">
      <span className="font-medium">포트폴리오 코치</span>
      <span className="ml-2 text-ink-2">{text}</span>
      <span className="mt-1 block text-xs text-muted">내가 정한 정책 기준의 점검이에요. 투자 조언이 아닙니다.</span>
    </Link>
  )
}
