import { Link } from 'react-router-dom'

import { useRuleCheck } from '../api/hooks'
import { bannerTitle, countByStatus } from '../lib/rules'

/**
 * Home strip: how many holdings the user's own rules put under review, linking to the rules
 * page. Hidden while loading, on error, and when nothing is under review. The loss if every
 * stop were hit is the backend's `total_risk_pct_equity`, shown as is.
 */
export function RulesBanner() {
  const rules = useRuleCheck()
  if (!rules.data) return null
  const title = bannerTitle(countByStatus(rules.data.checks))
  if (!title) return null
  const total = rules.data.total_risk_pct_equity
  return (
    <Link
      to="/rules"
      className="block rounded-lg border border-line bg-surface px-4 py-3 text-sm hover:bg-hover"
    >
      <span className="font-medium">{title}</span>
      <span className="ml-2 text-ink-2">— 내가 정한 규칙의 점검 결과예요 →</span>
      {typeof total === 'number' && (
        <span className="num mt-1 block text-xs text-muted">
          모든 손절이 걸리면 총자산의 {total.toFixed(1)}%를 잃습니다
        </span>
      )}
    </Link>
  )
}
