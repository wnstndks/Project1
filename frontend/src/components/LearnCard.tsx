import { Link } from 'react-router-dom'

import { useLearnSkills, useLearnWeek, useLessons } from '../api/hooks'
import { LEARN_CARD_NOTE_KO, learnSummary } from '../lib/learn'

/**
 * Home strip for the learn coach (D-034): how many things to check this week and the first
 * topic to read, from my own records, linking to the study page. Hidden while any of the
 * three responses is loading or failed. A reading order, not advice, and it says so.
 */
export function LearnCard() {
  const week = useLearnWeek()
  const skills = useLearnSkills()
  const lessons = useLessons()
  const text = learnSummary(week.data, skills.data, lessons.data)
  if (!text) return null
  return (
    <Link to="/learn" className="block rounded-lg border border-line bg-surface px-4 py-3 text-sm hover:bg-hover">
      <span className="font-medium">투자 공부</span>
      <span className="ml-2 text-ink-2">{text}</span>
      <span className="mt-1 block text-xs text-muted">{LEARN_CARD_NOTE_KO}</span>
    </Link>
  )
}
