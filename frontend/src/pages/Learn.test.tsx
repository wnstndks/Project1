import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { LearnSkills, LearnWeek, LessonList } from '../api/client'
import { ApiError } from '../api/client'
import { BANNED_WORDS_RE, GRADE_WORDS_RE } from '../lib/learn'
import { Learn } from './Learn'

// Synthetic values only (AAA/BBB).
const lessons: LessonList = {
  lessons: [
    { id: 'diversification-basics', title_ko: '분산: 종목 수가 아니라 같이 움직이는 정도', level: 'basic', minutes: 3, skill_codes: ['concentration'], watch_kinds: [], summary_ko: '같이 움직이는 종목은 분산이 아닙니다.', progress: null },
    { id: 'chasing-buys', title_ko: '추격 매수: 급등 뒤에 사는 습관', level: 'basic', minutes: 4, skill_codes: ['chasing'], watch_kinds: [], summary_ko: '급등 뒤에 사는 습관을 봅니다.', progress: { lesson_id: 'chasing-buys', read_at: '2026-11-01T00:00:00', quiz_score: 2, quiz_total: 3, quiz_at: '2026-11-01T00:00:00' } },
    { id: 'earnings-week', title_ko: '실적 발표 주간에 보는 것', level: 'intermediate', minutes: 5, skill_codes: [], watch_kinds: ['earnings'], summary_ko: '발표 전에 내 규칙을 확인합니다.', progress: null },
  ],
  read_count: 1,
  total: 3,
  default_first_topics: ['diversification-basics', 'chasing-buys', 'earnings-week'],
  load_errors: [],
  caveats: [],
}

const skills: LearnSkills = {
  as_of: '2026-11-02',
  empty: false,
  trades_total: 9,
  trades_in_window: 9,
  suspicious_excluded: 1,
  window_start: '2025-11-02',
  window_end: '2026-11-02',
  skills: [
    {
      code: 'chasing', label_ko: '급등 뒤 매수', level: 'strong', level_ko: '뚜렷함', sample_n: 5, min_sample: 5,
      window_start: '2025-11-02', window_end: '2026-11-02',
      lines: [{ text_ko: '봉이 있던 매수 5건 중 2건이 급등 뒤 매수', value: 40, n: 5, trade_ids: [3, 7], symbols: ['AAA'] }],
      lesson_ids: ['chasing-buys'], caveat_ko: null, excluded_suspicious: 0,
    },
    {
      code: 'no_journal', label_ko: '메모 없는 거래', level: 'insufficient', level_ko: '기록 부족', sample_n: 2, min_sample: 5,
      window_start: '2025-11-02', window_end: '2026-11-02',
      lines: [], lesson_ids: ['trade-journal'], caveat_ko: '거래가 5건보다 적어요.', excluded_suspicious: 0,
    },
  ],
  first_topics: ['chasing-buys', 'diversification-basics'],
  first_topics_source: 'ranking',
  disclaimer_ko: '투자 조언이 아닙니다.',
  caveats: ['단가 확인이 필요한 거래 1건은 뺐어요.'],
}

const week: LearnWeek = {
  start: '2026-11-02',
  end: '2026-11-09',
  items: [
    { kind: 'earnings', severity: 'soon', title_ko: 'AAA 실적 발표 예정일', detail_ko: '그 전에 내 손절선을 확인해 두기', route: '/rules', date: '2026-11-03', symbol: 'AAA', lesson_id: 'earnings-week', estimated: true },
    { kind: 'market_closure', severity: 'setup', title_ko: '미국 휴장', detail_ko: '', route: null, date: '2026-11-26', symbol: null, lesson_id: null, estimated: false },
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

const renderPage = () =>
  render(
    <MemoryRouter>
      <Learn />
    </MemoryRouter>,
  )

const card = (title: string) => screen.getByRole('heading', { name: title }).closest('section')!

function resetState() {
  state.lessons = { data: lessons }
  // The evidence routes failing hides their sections; the lesson list still works.
  state.skills = { error: new ApiError(500, '서버 오류') }
  state.week = { error: new ApiError(500, '서버 오류') }
}

describe('Learn page', () => {
  beforeEach(resetState)
  afterEach(cleanup)

  it('shows the heading, the intro, the honesty line and the footer', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1, name: '투자 공부' })).toBeInTheDocument()
    expect(screen.getByText(/예측·종목 선택·투자 조언이 아닙니다/)).toBeInTheDocument()
    expect(screen.getByText('공부는 판단의 질을 높이지만 수익을 보장하지 않습니다.')).toBeInTheDocument()
    expect(screen.getByText('투자 조언이 아닙니다. 공부 자료는 일반 원칙이며, 내 상황에 맞는지는 스스로 판단합니다.')).toBeInTheDocument()
  })

  it('lists every lesson with level, minutes and progress, and filters by level', () => {
    renderPage()
    const list = card('전체 공부 목록')
    expect(within(list).getByText('1/3 읽음')).toBeInTheDocument()
    expect(within(list).getAllByRole('link')).toHaveLength(3)
    const chasing = within(list).getByRole('link', { name: /추격 매수/ })
    expect(chasing).toHaveAttribute('href', '/learn/chasing-buys')
    expect(chasing).toHaveTextContent('기초 · 4분 · 급등 뒤에 사는 습관을 봅니다.')
    expect(chasing).toHaveTextContent('읽음 ✓ · 셀프 체크 2/3')
    expect(within(list).getByRole('link', { name: /실적 발표 주간/ })).toHaveTextContent('중급 · 5분')

    fireEvent.click(within(list).getByRole('radio', { name: '중급' }))
    expect(within(list).getAllByRole('link')).toHaveLength(1)
    expect(within(list).getByRole('link', { name: /실적 발표 주간/ })).toBeInTheDocument()
    fireEvent.click(within(list).getByRole('radio', { name: '기초' }))
    expect(within(list).getAllByRole('link')).toHaveLength(2)
    fireEvent.click(within(list).getByRole('radio', { name: '전체' }))
    expect(within(list).getAllByRole('link')).toHaveLength(3)
  })

  it('shows the basics-first topics with the default note while there is no evidence, and hides the other sections', () => {
    renderPage()
    const first = card('먼저 볼 주제')
    expect(within(first).getByText('거래 기록이 없어 기초부터 순서대로 보여 드려요.')).toBeInTheDocument()
    const links = within(first).getAllByRole('link')
    expect(links.map((l) => l.getAttribute('href'))).toEqual([
      '/learn/diversification-basics',
      '/learn/chasing-buys',
      '/learn/earnings-week',
    ])
    expect(screen.queryByRole('heading', { name: '이번 주 볼 것' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '내 기록으로 본 습관' })).not.toBeInTheDocument()
  })

  it('renders the week list and the habit evidence in server order when they are there', () => {
    state.skills = { data: skills }
    state.week = { data: week }
    renderPage()
    const weekCard = card('이번 주 볼 것')
    expect(within(weekCard).getByText('이번 주')).toBeInTheDocument()
    expect(within(weekCard).getByText('준비')).toBeInTheDocument()
    expect(within(weekCard).getByText(/11월 3일 \(.\) · AAA 실적 발표 예정일/)).toBeInTheDocument()
    expect(within(weekCard).getByText('(추정)')).toBeInTheDocument()
    expect(within(weekCard).getByText('그 전에 내 손절선을 확인해 두기')).toBeInTheDocument()
    expect(within(weekCard).getByRole('link', { name: 'AAA 보기' })).toHaveAttribute('href', '/assets/AAA')
    expect(within(weekCard).getByRole('link', { name: '보기' })).toHaveAttribute('href', '/rules')
    expect(within(weekCard).getByRole('link', { name: '관련 주제' })).toHaveAttribute('href', '/learn/earnings-week')
    expect(within(weekCard).getByText('휴장·조기 폐장')).toBeInTheDocument()

    const habits = card('내 기록으로 본 습관')
    const chips = within(habits).getAllByText(/^(뚜렷함|조금 보임|걸린 것 없음|기록 부족) · /)
    expect(chips.map((c) => c.textContent)).toEqual(['뚜렷함 · 급등 뒤 매수', '기록 부족 · 메모 없는 거래'])
    expect(within(habits).getByText('봉이 있던 매수 5건 중 2건이 급등 뒤 매수 · 표본 5건')).toBeInTheDocument()
    expect(within(habits).getByText(/표본 5건 · 2025년 11월 2일부터 2026년 11월 2일까지/)).toBeInTheDocument()
    expect(within(habits).getByText('거래가 5건보다 적어요.')).toBeInTheDocument()
    expect(within(habits).getByText('단가 확인이 필요한 거래 1건은 뺐어요.')).toBeInTheDocument()
    expect(habits.querySelector('[class*="text-gain"], [class*="text-loss"]')).toBeNull()

    const first = card('먼저 볼 주제')
    expect(within(first).getByText(/내 기록에서 걸린 항목이 많은 순서예요/)).toBeInTheDocument()
    expect(within(first).getAllByRole('link').map((l) => l.getAttribute('href'))).toEqual([
      '/learn/chasing-buys',
      '/learn/diversification-basics',
    ])
  })

  it('shows the holdings count as the sample of a today-only habit, never "표본 0건"', () => {
    state.skills = {
      data: {
        ...skills,
        skills: [
          {
            code: 'class_drift', label_ko: '자산군 비중 벗어남', level: 'insufficient', level_ko: '기록 부족', sample_n: 3, min_sample: 1,
            window_start: null, window_end: '2026-11-02',
            lines: [{ text_ko: '지금 주식 70.0% · 코인 30.0%', value: null, n: 3, trade_ids: [], symbols: [] }],
            lesson_ids: ['rebalancing-bands'], caveat_ko: '정책을 아직 적지 않았어요.', excluded_suspicious: 0,
          },
        ],
      },
    }
    state.week = { data: week }
    renderPage()
    const habits = card('내 기록으로 본 습관')
    expect(within(habits).getByText('표본 3건 · 오늘 기준')).toBeInTheDocument()
    expect(within(habits).getByText('지금 주식 70.0% · 코인 30.0% · 표본 3건')).toBeInTheDocument()
    expect(within(habits).getByText('정책을 아직 적지 않았어요.')).toBeInTheDocument()
    expect(within(habits).queryByText(/표본 0건/)).not.toBeInTheDocument()
  })

  it('says so when the week has nothing, and keeps the empty-record note for habits', () => {
    state.skills = { data: { ...skills, empty: true, skills: skills.skills.map((s) => ({ ...s, level: 'insufficient' as const, lines: [] })), first_topics: [], first_topics_source: 'default' } }
    state.week = { data: { ...week, items: [] } }
    renderPage()
    expect(within(card('이번 주 볼 것')).getByText('이번 주에 확인할 항목이 없어요.')).toBeInTheDocument()
    const habits = card('내 기록으로 본 습관')
    expect(within(habits).getByText(/거래 기록이 없어/)).toBeInTheDocument()
    expect(within(habits).getAllByText(/^기록 부족 · /)).toHaveLength(2)
    expect(within(card('먼저 볼 주제')).getByText('거래 기록이 없어 기초부터 순서대로 보여 드려요.')).toBeInTheDocument()
  })

  it('says when a lesson could not be loaded instead of silently listing fewer', () => {
    const caveat = '강의 1편을 불러오지 못했어요. 목록에서 빠져 있습니다(개발 중 오류).'
    state.lessons = {
      data: { ...lessons, load_errors: [{ lesson_id: 'ex-dividend-date', error: 'ValueError: body too long' }], caveats: [caveat] },
    }
    renderPage()
    const list = card('전체 공부 목록')
    expect(within(list).getByText(caveat)).toBeInTheDocument()
    expect(within(list).getAllByRole('link')).toHaveLength(3)
    // The raw error text is for the API, not the screen.
    expect(screen.queryByText(/ValueError/)).not.toBeInTheDocument()
  })

  it('shows a skeleton while the list loads and the error when it fails', () => {
    state.lessons = { isLoading: true }
    const { container } = renderPage()
    expect(container.querySelector('.animate-pulse')).not.toBeNull()
    cleanup()
    state.lessons = { error: new Error('서버 오류') }
    renderPage()
    expect(screen.getByRole('alert')).toHaveTextContent('서버 오류')
  })

  it('never shows an advice word, a grading word or an arrow', () => {
    state.skills = { data: skills }
    state.week = { data: week }
    renderPage()
    const text = document.body.textContent ?? ''
    expect(text).not.toMatch(BANNED_WORDS_RE)
    expect(text).not.toMatch(GRADE_WORDS_RE)
    expect(text).not.toMatch(/[▲▼]/)
    expect(document.body.querySelector('[class*="text-gain"], [class*="text-loss"]')).toBeNull()
  })
})
