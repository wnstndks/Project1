import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { LearnSkills, LearnWeek, LessonList } from '../api/client'
import { ApiError } from '../api/client'
import { BANNED_WORDS_RE, GRADE_WORDS_RE } from '../lib/learn'
import { LearnCard } from './LearnCard'

// Synthetic values only (AAA/BBB).
const lessons: LessonList = {
  lessons: [
    { id: 'diversification-basics', title_ko: '분산', level: 'basic', minutes: 3, skill_codes: ['concentration'], watch_kinds: [], summary_ko: '요약', progress: null },
    { id: 'chasing-buys', title_ko: '추격 매수', level: 'basic', minutes: 4, skill_codes: ['chasing'], watch_kinds: [], summary_ko: '요약', progress: null },
    { id: 'earnings-week', title_ko: '실적 발표 주간', level: 'intermediate', minutes: 5, skill_codes: [], watch_kinds: ['earnings'], summary_ko: '요약', progress: null },
  ],
  read_count: 0,
  total: 3,
  default_first_topics: ['diversification-basics', 'chasing-buys'],
  load_errors: [],
  caveats: [],
}

const skills: LearnSkills = {
  as_of: '2026-11-02',
  empty: false,
  trades_total: 9,
  trades_in_window: 9,
  suspicious_excluded: 0,
  window_start: '2025-11-02',
  window_end: '2026-11-02',
  skills: [],
  first_topics: ['chasing-buys', 'diversification-basics'],
  first_topics_source: 'ranking',
  disclaimer_ko: '투자 조언이 아닙니다.',
  caveats: [],
}

const week: LearnWeek = {
  start: '2026-11-02',
  end: '2026-11-09',
  items: [
    { kind: 'earnings', severity: 'soon', title_ko: 'AAA 실적 발표 예정일', detail_ko: '', route: '/rules', date: '2026-11-03', symbol: 'AAA', lesson_id: 'earnings-week', estimated: true },
    { kind: 'policy_unset', severity: 'setup', title_ko: '투자 정책을 아직 적지 않았어요', detail_ko: '', route: '/coach', date: null, symbol: null, lesson_id: null, estimated: false },
  ],
  stale_symbols: [],
  errors: [],
  caveats: [],
  disclaimer_ko: '투자 조언이 아닙니다.',
}

type Q<T> = { data?: T; error?: unknown; isLoading?: boolean }
const state: { lessons: Q<LessonList>; skills: Q<LearnSkills>; week: Q<LearnWeek> } = { lessons: {}, skills: {}, week: {} }

vi.mock('../api/hooks', () => ({
  useLessons: () => state.lessons,
  useLearnSkills: () => state.skills,
  useLearnWeek: () => state.week,
}))

const renderCard = () =>
  render(
    <MemoryRouter>
      <LearnCard />
    </MemoryRouter>,
  )

describe('LearnCard', () => {
  beforeEach(() => {
    state.lessons = { data: lessons }
    state.skills = { data: skills }
    state.week = { data: week }
  })
  afterEach(cleanup)

  it('renders nothing while any of the three responses is loading or failed', () => {
    state.week = { isLoading: true }
    expect(renderCard().container).toBeEmptyDOMElement()
    cleanup()
    state.week = { data: week }
    state.skills = { error: new ApiError(500, '서버 오류') }
    expect(renderCard().container).toBeEmptyDOMElement()
    cleanup()
    state.skills = { data: skills }
    state.lessons = { error: new Error('네트워크') }
    expect(renderCard().container).toBeEmptyDOMElement()
  })

  it('summarises the week count and the first topic, links to the study page and says it is not advice', () => {
    renderCard()
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/learn')
    expect(link).toHaveTextContent('투자 공부')
    expect(screen.getByText('이번 주 볼 것 2개 · 먼저 볼 주제: 추격 매수 →')).toBeInTheDocument()
    expect(screen.getByText('내 기록으로 고른 읽는 순서예요. 투자 조언이 아닙니다.')).toBeInTheDocument()
  })

  it('falls back to the lesson count and the basics-first topic without a trade record', () => {
    state.skills = { data: { ...skills, empty: true, first_topics: [], first_topics_source: 'default' } }
    state.week = { data: { ...week, items: [] } }
    renderCard()
    expect(screen.getByText('공부 목록 3개 · 먼저 볼 주제: 분산 →')).toBeInTheDocument()
  })

  it('never uses an advice word, a grading word, an arrow glyph or a gain/loss colour', () => {
    const { container } = renderCard()
    const text = container.textContent ?? ''
    expect(text).not.toMatch(BANNED_WORDS_RE)
    expect(text).not.toMatch(GRADE_WORDS_RE)
    expect(text).not.toMatch(/[▲▼]/)
    expect(container.querySelector('[class*="text-gain"], [class*="text-loss"]')).toBeNull()
  })
})
