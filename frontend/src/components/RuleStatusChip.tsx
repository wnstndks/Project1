import { chipTone } from '../lib/rules'

/**
 * Short status of the user's own rule check (매도 검토 / 추매 검토 / 관망) for list rows and
 * tables. Text carries the meaning; the tone (sell blue, buy red, hold gray) only echoes it.
 * No price or probability belongs here: those live on the detail card.
 */
export function RuleStatusChip({ status, label, className = '' }: {
  status: string
  label: string
  className?: string
}) {
  const tone = chipTone(status)
  return (
    <span
      className={`whitespace-nowrap rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${tone.className} ${className}`}
      title="내가 정한 규칙의 점검 결과예요. 예측이 아닙니다."
    >
      {label}
    </span>
  )
}
