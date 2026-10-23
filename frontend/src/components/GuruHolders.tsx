import { Link } from 'react-router-dom'

import { useGuruCompare } from '../api/hooks'
import { holdersOf, holdersSentence } from '../lib/gurus'

/**
 * One line under the asset header: which well-known investors hold this symbol and at what weight,
 * from the compare result (my holdings only). Renders nothing while loading or when no one holds it.
 */
export function GuruHolders({ symbol }: { symbol: string }) {
  const compare = useGuruCompare()
  if (!compare.data || !symbol) return null
  const holders = holdersOf(compare.data.gurus, symbol)
  if (holders.length === 0) return null
  return (
    <p className="mt-2 text-sm text-ink-2">
      이 종목을 들고 있는 유명 투자자:{' '}
      <Link to="/compare" className="num text-ink hover:underline">
        {holdersSentence(holders)}
      </Link>
    </p>
  )
}
