import { daysAgo } from './format'

export type RangeKey = '1M' | '3M' | '6M' | '1Y' | '3Y' | 'ALL'

const DAYS: Record<Exclude<RangeKey, 'ALL'>, number> = {
  '1M': 30,
  '3M': 91,
  '6M': 182,
  '1Y': 365,
  '3Y': 365 * 3,
}

export const RANGE_OPTIONS: { value: RangeKey; label: string }[] = [
  { value: '1M', label: '1개월' },
  { value: '3M', label: '3개월' },
  { value: '6M', label: '6개월' },
  { value: '1Y', label: '1년' },
  { value: '3Y', label: '3년' },
  { value: 'ALL', label: '전체' },
]

/** Start date for a range; undefined means "from the beginning". */
export function rangeStart(range: RangeKey): string | undefined {
  return range === 'ALL' ? undefined : daysAgo(DAYS[range])
}
