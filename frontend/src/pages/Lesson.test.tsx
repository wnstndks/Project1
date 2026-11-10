import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { LearnSkills, LearnWeek, LessonDetail, LessonProgressInput } from '../api/client'
import { ApiError } from '../api/client'
import { BANNED_WORDS_RE, GRADE_WORDS_RE } from '../lib/learn'
import { Lesson } from './Lesson'

// Synthetic lesson (AAA/BBB only).
const lesson: LessonDetail = {
  id: 'chasing-buys',
  title_ko: '추격 매수: 급등 뒤에 사는 습관',
  level: 'basic',
  minutes: 4,
  body_chars: 1200,
  skill_codes: ['chasing'],
  watch_kinds: ['rule_near_cut'],
  summary_ko: '급등을 보고 뒤늦게 사면 되돌림을 그대로 맞기 쉽습니다. 내 기록에서 얼마나 자주 그랬는지 봅니다.',
  sections: [
    { heading_ko: '급등 뒤 매수란', kind: 'fact', paragraphs: ['매수 전 20봉 동안 15% 넘게 오른 뒤 산 거래를 말합니다[1].'], bullets: null, callout_ko: null, route: null },
    { heading_ko: '기다리는 선택지', kind: 'principle', paragraphs: ['급등 뒤에는 기다리는 선택지도 있습니다.'], bullets: ['미리 정한 가격대', '나눠서 사기'], callout_ko: '한 번에 결정하지 않아도 됩니다.', route: null },
    { heading_ko: '이 앱에서 보는 곳', kind: 'app', paragraphs: ['코치의 습관 점검에서 급등 뒤 매수 건수를 봅니다.'], bullets: null, callout_ko: null, route: '/coach' },
  ],
  general_example_ko: 'AAA가 3주 만에 크게 상승했다는 소식을 보고 샀다면, 매수 전 20봉의 움직임을 먼저 보는 연습이 됩니다. BBB는 미리 정한 가격대까지 기다린 경우입니다.',
  references: [
    { title: 'Herd Instinct', url: 'https://www.investopedia.com/terms/h/herdinstinct.asp', publisher: 'Investopedia', lang: 'en', note_ko: '영어 자료. 군중 심리를 설명합니다.', accessed: '2026-10' },
    { title: '투자 심리 바로 알기', url: 'https://www.fss.or.kr/edu', publisher: '금융감독원', lang: 'ko', note_ko: 'e-금융교육센터 자료.', accessed: '2026-10' },
  ],
  quiz: [
    { prompt_ko: '급등 뒤 매수의 기준은?', choices: ['20봉 동안 15% 넘게 오른 뒤 산 것', '하락 뒤 산 것', '나눠서 산 것'], answer: 0, why_ko: '코치의 기준은 20봉 15%입니다.' },
    { prompt_ko: '급등 뒤에 사도 손실은 없다?', choices: ['그렇다', '아니다', '모른다'], answer: 1, why_ko: '급등은 되돌림을 동반할 수 있습니다.' },
    { prompt_ko: '이 앱에서 건수를 보는 곳은?', choices: ['코치 습관 점검', '시뮬레이션', '뉴스'], answer: 0, why_ko: '코치 페이지의 습관 점검에 있습니다.' },
  ],
  takeaway_ko: '급등 뒤에는 한 박자 쉬고 내 규칙을 먼저 본다.',
  progress: null,
}

const skills: LearnSkills = {
  as_of: '2026-11-02',
  empty: false,
  trades_total: 9,
  trades_in_window: 9,
  suspicious_excluded: 0,
  window_start: '2025-11-02',
  window_end: '2026-11-02',
  skills: [
    {
      code: 'chasing', label_ko: '급등 뒤 매수', level: 'strong', level_ko: '뚜렷함', sample_n: 5, min_sample: 5,
      window_start: '2025-11-02', window_end: '2026-11-02',
      lines: [{ text_ko: '봉이 있던 매수 5건 중 2건이 급등 뒤 매수', value: 40, n: 5, trade_ids: [3, 7], symbols: ['AAA'] }],
      lesson_ids: ['chasing-buys'], caveat_ko: null, excluded_suspicious: 0,
    },
  ],
  first_topics: ['chasing-buys'],
  first_topics_source: 'ranking',
  disclaimer_ko: '투자 조언이 아닙니다.',
  caveats: [],
}

const week: LearnWeek = {
  start: '2026-11-02',
  end: '2026-11-09',
  items: [
    { kind: 'rule_near_cut', severity: 'soon', title_ko: 'BBB 손절선까지 3.2%', detail_ko: '내가 정한 손절 규칙의 발동가가 가깝습니다.', route: '/rules', date: null, symbol: 'BBB', lesson_id: 'chasing-buys', estimated: false },
  ],
  stale_symbols: [],
  errors: [],
  caveats: [],
  disclaimer_ko: '투자 조언이 아닙니다.',
}

type Q<T> = { data?: T; error?: unknown; isLoading?: boolean }
const state: { lesson: Q<LessonDetail>; skills: Q<LearnSkills>; week: Q<LearnWeek>; pending: boolean } = {
  lesson: {},
  skills: {},
  week: {},
  pending: false,
}
const save = vi.fn((_body: LessonProgressInput) => {})

vi.mock('../api/hooks', () => ({
  useLesson: () => state.lesson,
  useLearnSkills: () => state.skills,
  useLearnWeek: () => state.week,
  useSaveProgress: () => ({ mutate: save, isPending: state.pending, error: null }),
}))

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/learn/chasing-buys']}>
      <Routes>
        <Route path="/learn/:lessonId" element={<Lesson />} />
      </Routes>
    </MemoryRouter>,
  )

function resetState() {
  save.mockClear()
  state.lesson = { data: lesson }
  // Until the evidence routes land they answer 404: the page must not depend on them.
  state.skills = { error: new ApiError(404, 'Not Found') }
  state.week = { error: new ApiError(404, 'Not Found') }
  state.pending = false
}

describe('Lesson page', () => {
  beforeEach(resetState)
  afterEach(cleanup)

  it('shows the header, chips, summary, the general example and the honesty lines', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1, name: lesson.title_ko })).toBeInTheDocument()
    expect(screen.getByText('기초')).toBeInTheDocument()
    expect(screen.getByText('4분')).toBeInTheDocument()
    expect(screen.getByText('급등 뒤 매수')).toBeInTheDocument()
    expect(screen.getByText(lesson.summary_ko)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '← 공부 목록' })).toHaveAttribute('href', '/learn')
    // No evidence: the note and the AAA/BBB example.
    expect(screen.getByText('내 기록에서 걸린 거래가 없어 일반 예시를 보여 드려요.')).toBeInTheDocument()
    expect(screen.getByText(lesson.general_example_ko)).toBeInTheDocument()
    expect(screen.getByText('급등 뒤에는 한 박자 쉬고 내 규칙을 먼저 본다.')).toBeInTheDocument()
    expect(screen.getByText('투자 조언이 아닙니다. 공부 자료는 일반 원칙이며, 내 상황에 맞는지는 스스로 판단합니다.')).toBeInTheDocument()
    expect(screen.getByText('공부는 판단의 질을 높이지만 수익을 보장하지 않습니다.')).toBeInTheDocument()
  })

  it('renders the sections with their kind chips, bullets, callout, screen link and footnote link', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 2, name: '급등 뒤 매수란' })).toBeInTheDocument()
    expect(screen.getByText('사실')).toBeInTheDocument()
    expect(screen.getByText('일반 원칙')).toBeInTheDocument()
    expect(screen.getByText('이 앱에서는')).toBeInTheDocument()
    expect(screen.getByText('미리 정한 가격대')).toBeInTheDocument()
    expect(screen.getByText('한 번에 결정하지 않아도 됩니다.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '화면 보기 →' })).toHaveAttribute('href', '/coach')
    expect(screen.getByRole('link', { name: '참고 자료 1' })).toHaveAttribute('href', '#ref-1')
  })

  it('lists references as new-tab links with publisher, language and the month checked', () => {
    renderPage()
    const link = screen.getByRole('link', { name: 'Herd Instinct 원문 (새 탭)' })
    expect(link).toHaveAttribute('href', 'https://www.investopedia.com/terms/h/herdinstinct.asp')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(document.getElementById('ref-1')).toHaveTextContent('Investopedia · 영어 · 2026-10 확인')
    expect(document.getElementById('ref-2')).toHaveTextContent('금융감독원 · 한국어 · 2026-10 확인')
    expect(screen.getByText('외부 링크는 새 탭에서 열리며 내용은 각 기관의 책임입니다.')).toBeInTheDocument()
  })

  it('shows my own records when the evidence and week caches have lines for this lesson', () => {
    state.skills = { data: skills }
    state.week = { data: week }
    renderPage()
    const card = screen.getByRole('heading', { name: '내 기록에서' }).closest('section')!
    expect(within(card).getByText('봉이 있던 매수 5건 중 2건이 급등 뒤 매수 · 표본 5건')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'AAA 보기' })).toHaveAttribute('href', '/assets/AAA')
    expect(within(card).getByRole('link', { name: '거래 2건 보기' })).toHaveAttribute('href', '/transactions')
    expect(within(card).getByText(/이번 주 · BBB 손절선까지 3.2% — 내가 정한 손절 규칙/)).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'BBB 보기' })).toHaveAttribute('href', '/assets/BBB')
    expect(within(card).getByRole('link', { name: '화면 보기' })).toHaveAttribute('href', '/rules')
    expect(within(card).queryByText(lesson.general_example_ko)).not.toBeInTheDocument()
    // Evidence is never coloured as a gain or a loss.
    expect(card.querySelector('[class*="text-gain"], [class*="text-loss"]')).toBeNull()
    expect(card.textContent).not.toMatch(/[▲▼]/)
  })

  it('explains each self-check answer, then saves the answers once', () => {
    renderPage()
    const groups = screen.getAllByRole('group')
    expect(groups).toHaveLength(3)
    fireEvent.click(within(groups[0]).getAllByRole('radio')[1])
    expect(screen.getAllByRole('status')[0]).toHaveTextContent('아니에요. 답은 1번. 코치의 기준은 20봉 15%입니다.')
    expect(save).not.toHaveBeenCalled()
    fireEvent.click(within(groups[1]).getAllByRole('radio')[1])
    expect(screen.getAllByRole('status')[1]).toHaveTextContent('맞았어요. 급등은 되돌림을 동반할 수 있습니다.')
    fireEvent.click(within(groups[2]).getAllByRole('radio')[0])
    expect(screen.getByText('3문제 중 2문제 맞았어요. 틀린 문제의 설명을 다시 읽어 보세요.')).toBeInTheDocument()
    expect(save).toHaveBeenCalledTimes(1)
    expect(save).toHaveBeenCalledWith({ answers: [1, 1, 0] })
  })

  it('marks the lesson read with a pressed button, and shows the saved state', () => {
    renderPage()
    const button = screen.getByRole('button', { name: '읽었어요' })
    expect(button).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(button)
    expect(save).toHaveBeenCalledWith({ read: true })
    cleanup()

    state.lesson = { data: { ...lesson, progress: { lesson_id: lesson.id, read_at: '2026-11-01T00:00:00', quiz_score: null, quiz_total: null, quiz_at: null } } }
    renderPage()
    const read = screen.getByRole('button', { name: '읽음 ✓' })
    expect(read).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(read)
    expect(save).toHaveBeenLastCalledWith({ read: false })
    cleanup()

    state.pending = true
    renderPage()
    expect(screen.getByRole('button', { name: '저장 중…' })).toBeDisabled()
  })

  it('shows a not-found message with a link back to the list on 404', () => {
    state.lesson = { error: new ApiError(404, 'Not Found', 'lesson_not_found') }
    renderPage()
    expect(screen.getByRole('alert')).toHaveTextContent('이 강의를 찾을 수 없어요.')
    expect(screen.getByRole('link', { name: '공부 목록으로 →' })).toHaveAttribute('href', '/learn')
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument()
  })

  it('shows a skeleton while loading', () => {
    state.lesson = { isLoading: true }
    const { container } = renderPage()
    expect(container.querySelector('.animate-pulse')).not.toBeNull()
  })

  it('never shows an advice word, a grading word, an arrow or a gain/loss colour', () => {
    state.skills = { data: skills }
    state.week = { data: week }
    renderPage()
    const groups = screen.getAllByRole('group')
    fireEvent.click(within(groups[0]).getAllByRole('radio')[2])
    fireEvent.click(within(groups[1]).getAllByRole('radio')[1])
    fireEvent.click(within(groups[2]).getAllByRole('radio')[0])
    const text = document.body.textContent ?? ''
    expect(text).not.toMatch(BANNED_WORDS_RE)
    expect(text).not.toMatch(GRADE_WORDS_RE)
    expect(text).not.toMatch(/[▲▼]/)
    expect(document.body.querySelector('[class*="text-gain"], [class*="text-loss"]')).toBeNull()
  })
})
