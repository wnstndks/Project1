import { describe, expect, it } from 'vitest'

import type { LearnSkills, LearnWeek, LessonDetail, LessonList } from '../api/client'
import {
  BANNED_WORDS_RE,
  EMPTY_WEEK_KO,
  EVIDENCE_NOTE_KO,
  EXTERNAL_LINK_NOTE_KO,
  FIRST_TOPICS_DEFAULT_NOTE_KO,
  FIRST_TOPICS_NOTE_KO,
  GRADE_WORDS_RE,
  LEARN_CARD_NOTE_KO,
  LEARN_FOOTER_KO,
  LEARN_HONESTY_KO,
  LEARN_INTRO_KO,
  learnSummary,
  LESSON_LEVEL_LABELS_KO,
  LEVEL_LABELS_KO,
  LEVEL_TONE,
  NO_RECORD_EXAMPLE_KO,
  ownExamples,
  progressLabel,
  progressTotal,
  quizResultPhrase,
  refMarkers,
  SECTION_KIND_LABELS_KO,
  SEVERITY_LABELS_KO,
  SKILL_LABELS_KO,
  skillLine,
  skillWindowPhrase,
  WATCH_KIND_LABELS_KO,
  watchItemPhrase,
} from './learn'

// Synthetic values only (public repo): AAA/BBB.
const skills: LearnSkills = {
  as_of: '2026-11-02',
  empty: false,
  trades_total: 12,
  trades_in_window: 9,
  suspicious_excluded: 1,
  window_start: '2025-11-02',
  window_end: '2026-11-02',
  skills: [
    {
      code: 'chasing',
      label_ko: '급등 뒤 매수',
      level: 'strong',
      level_ko: '뚜렷함',
      sample_n: 5,
      min_sample: 5,
      window_start: '2025-11-02',
      window_end: '2026-11-02',
      lines: [{ text_ko: '봉이 있던 매수 5건 중 2건이 급등 뒤 매수', value: 40, n: 5, trade_ids: [3, 7], symbols: ['AAA'] }],
      lesson_ids: ['chasing-buys'],
      caveat_ko: null,
      excluded_suspicious: 0,
    },
    {
      code: 'concentration',
      label_ko: '한 곳에 몰림',
      level: 'some',
      level_ko: '조금 보임',
      sample_n: 2,
      min_sample: 1,
      window_start: null,
      window_end: '2026-11-02',
      lines: [{ text_ko: '가장 큰 종목 AAA가 투자금의 60%', value: 60, n: null, trade_ids: [], symbols: ['AAA', 'BBB'] }],
      lesson_ids: ['diversification-basics'],
      caveat_ko: '평가액 기준이에요.',
      excluded_suspicious: 0,
    },
  ],
  first_topics: ['chasing-buys', 'diversification-basics'],
  first_topics_source: 'ranking',
  disclaimer_ko: '공부는 판단의 질을 높이지만 수익을 보장하지 않습니다. 투자 조언이 아닙니다.',
  caveats: [],
}

const week: LearnWeek = {
  start: '2026-11-02',
  end: '2026-11-09',
  items: [
    { kind: 'earnings', severity: 'soon', title_ko: '실적 발표 예정일', detail_ko: '그 전에 내 손절선을 확인해 두기', route: '/rules', date: '2026-11-03', symbol: 'AAA', lesson_id: 'earnings-week', estimated: true },
    { kind: 'kill_switch', severity: 'now', title_ko: '킬스위치 켜짐', detail_ko: '', route: '/coach', date: null, symbol: null, lesson_id: 'stop-loss-and-rules', estimated: false },
  ],
  stale_symbols: [],
  errors: [],
  caveats: [],
  disclaimer_ko: '투자 조언이 아닙니다.',
}

const lessons: LessonList = {
  lessons: [
    { id: 'diversification-basics', title_ko: '분산', level: 'basic', minutes: 3, skill_codes: ['concentration'], watch_kinds: [], summary_ko: '요약', progress: null },
    { id: 'chasing-buys', title_ko: '추격 매수', level: 'basic', minutes: 4, skill_codes: ['chasing'], watch_kinds: [], summary_ko: '요약', progress: { lesson_id: 'chasing-buys', read_at: '2026-11-01T00:00:00', quiz_score: 2, quiz_total: 3, quiz_at: '2026-11-01T00:00:00' } },
    { id: 'earnings-week', title_ko: '실적 발표 주간', level: 'intermediate', minutes: 5, skill_codes: [], watch_kinds: ['earnings'], summary_ko: '요약', progress: null },
  ],
  read_count: 1,
  total: 3,
  default_first_topics: ['diversification-basics', 'chasing-buys'],
  load_errors: [],
  caveats: [],
}

const lesson: Pick<LessonDetail, 'skill_codes' | 'watch_kinds'> = { skill_codes: ['chasing'], watch_kinds: ['earnings'] }

const TODAY = new Date('2026-11-02T00:00:00')

describe('learn wording: fixed sentences and labels', () => {
  const fixed = [
    LEARN_INTRO_KO,
    LEARN_HONESTY_KO,
    LEARN_FOOTER_KO,
    FIRST_TOPICS_NOTE_KO,
    FIRST_TOPICS_DEFAULT_NOTE_KO,
    NO_RECORD_EXAMPLE_KO,
    EMPTY_WEEK_KO,
    EXTERNAL_LINK_NOTE_KO,
    EVIDENCE_NOTE_KO,
    LEARN_CARD_NOTE_KO,
    ...Object.values(LEVEL_LABELS_KO),
    ...Object.values(SKILL_LABELS_KO),
    ...Object.values(LESSON_LEVEL_LABELS_KO),
    ...Object.values(SECTION_KIND_LABELS_KO),
    ...Object.values(WATCH_KIND_LABELS_KO),
    ...Object.values(SEVERITY_LABELS_KO),
  ]

  it('never uses an advice word or a grading word', () => {
    for (const s of fixed) {
      expect(s, s).not.toMatch(BANNED_WORDS_RE)
      expect(s, s).not.toMatch(GRADE_WORDS_RE)
    }
    // The regex itself allows the honesty line and rejects a promise.
    expect('수익을 보장하지 않습니다').not.toMatch(BANNED_WORDS_RE)
    expect('수익을 보장합니다').toMatch(BANNED_WORDS_RE)
    expect('수익 보장').toMatch(BANNED_WORDS_RE)
    expect('반드시 오릅니다').toMatch(BANNED_WORDS_RE)
  })

  it('covers every level, 14 watch kinds and 3 severities, with the agreed texts', () => {
    expect(LEVEL_LABELS_KO).toEqual({ strong: '뚜렷함', some: '조금 보임', none: '걸린 것 없음', insufficient: '기록 부족' })
    expect(Object.keys(WATCH_KIND_LABELS_KO)).toHaveLength(14)
    expect(WATCH_KIND_LABELS_KO.ex_dividend).toBe('배당락')
    expect(SEVERITY_LABELS_KO).toEqual({ now: '지금 확인', soon: '이번 주', setup: '준비' })
    expect(LEVEL_TONE.strong).toContain('text-danger')
    expect(LEVEL_TONE.insufficient).toContain('text-muted')
    for (const tone of Object.values(LEVEL_TONE)) expect(tone).not.toMatch(/text-(gain|loss)/)
  })
})

describe('learn wording: generated sentences', () => {
  it('always prints the sample on an evidence line that has one', () => {
    expect(skillLine(skills.skills[0].lines[0])).toBe('봉이 있던 매수 5건 중 2건이 급등 뒤 매수 · 표본 5건')
    expect(skillLine({ text_ko: '메모 없음', n: 0 })).toBe('메모 없음 · 표본 0건')
    expect(skillLine({ text_ko: '평가액 기준', n: null })).toBe('평가액 기준')
    for (const s of skills.skills) for (const l of s.lines) if (l.n !== null) expect(skillLine(l)).toMatch(/표본 \d+건$/)
  })

  it('names the window, or "today" for a today-only habit', () => {
    expect(skillWindowPhrase(skills.skills[0])).toBe('2025년 11월 2일부터 2026년 11월 2일까지')
    expect(skillWindowPhrase(skills.skills[1])).toBe('오늘 기준')
  })

  it('reads a week item with its date, or "이번 주" without one', () => {
    expect(watchItemPhrase(week.items[0], TODAY)).toMatch(/^11월 3일 \(.\) · 실적 발표 예정일$/)
    expect(watchItemPhrase(week.items[1], TODAY)).toBe('이번 주 · 킬스위치 켜짐')
  })

  it('summarises for the home card only when all three responses are there', () => {
    expect(learnSummary(undefined, skills, lessons)).toBeUndefined()
    expect(learnSummary(week, undefined, lessons)).toBeUndefined()
    expect(learnSummary(week, skills, undefined)).toBeUndefined()
    expect(learnSummary(week, skills, lessons)).toBe('이번 주 볼 것 2개 · 먼저 볼 주제: 추격 매수 →')
    const noRecord: LearnSkills = { ...skills, empty: true, first_topics: [], first_topics_source: 'default' }
    expect(learnSummary({ items: [] }, noRecord, lessons)).toBe('공부 목록 3개 · 먼저 볼 주제: 분산 →')
    // An unknown first topic drops the topic part rather than inventing a title.
    expect(learnSummary(week, { ...skills, first_topics: ['nope'] }, lessons)).toBe('이번 주 볼 것 2개 →')
  })

  it('labels progress in its four shapes and counts the list', () => {
    expect(progressLabel(null)).toBe('')
    expect(progressLabel(undefined)).toBe('')
    expect(progressLabel({ lesson_id: 'x', read_at: '2026-11-01T00:00:00', quiz_score: null, quiz_total: null, quiz_at: null })).toBe('읽음 ✓')
    expect(progressLabel({ lesson_id: 'x', read_at: '2026-11-01T00:00:00', quiz_score: 2, quiz_total: 3, quiz_at: '2026-11-01T00:00:00' })).toBe('읽음 ✓ · 셀프 체크 2/3')
    expect(progressLabel({ lesson_id: 'x', read_at: null, quiz_score: 2, quiz_total: 3, quiz_at: '2026-11-01T00:00:00' })).toBe('셀프 체크 2/3')
    expect(progressTotal(lessons.lessons)).toBe('1/3 읽음')
    expect(progressTotal([])).toBe('0/0 읽음')
  })

  it('tells the self-check result without grading words, for every score', () => {
    expect(quizResultPhrase(2, 3)).toBe('3문제 중 2문제 맞았어요. 틀린 문제의 설명을 다시 읽어 보세요.')
    expect(quizResultPhrase(3, 3)).toBe('3문제 중 3문제 맞았어요. 설명도 한 번 더 읽어 두면 좋아요.')
    for (const score of [0, 1, 2, 3]) {
      const s = quizResultPhrase(score, 3)
      expect(s).not.toMatch(GRADE_WORDS_RE)
      expect(s).not.toMatch(BANNED_WORDS_RE)
    }
  })

  it('splits footnote markers out of a sentence', () => {
    expect(refMarkers('수수료[1]는 거래마다 붙습니다[2]')).toEqual([
      { text: '수수료' },
      { ref: 1 },
      { text: '는 거래마다 붙습니다' },
      { ref: 2 },
    ])
    expect(refMarkers('각주 없음')).toEqual([{ text: '각주 없음' }])
    expect(refMarkers('[3] 앞에')).toEqual([{ ref: 3 }, { text: ' 앞에' }])
    expect(refMarkers('')).toEqual([])
  })

  it('joins a lesson with the evidence lines and week items it explains', () => {
    const out = ownExamples(lesson, skills, week)
    expect(out).toHaveLength(2)
    expect(out[0]).toEqual({
      text: '봉이 있던 매수 5건 중 2건이 급등 뒤 매수 · 표본 5건',
      symbol: 'AAA',
      symbols: ['AAA'],
      tradeIds: [3, 7],
    })
    expect(out[1].text).toMatch(/^11월 3일 \(.\) · 실적 발표 예정일 — 그 전에 내 손절선을 확인해 두기$/)
    expect(out[1]).toMatchObject({ symbol: 'AAA', tradeIds: [], route: '/rules' })
    // A line about several symbols links each, with no single `symbol`.
    const multi = ownExamples({ skill_codes: ['concentration'], watch_kinds: [] }, skills, week)
    expect(multi).toHaveLength(1)
    expect(multi[0].symbol).toBeUndefined()
    expect(multi[0].symbols).toEqual(['AAA', 'BBB'])
    // Nothing matching, or nothing loaded: empty, so the page falls back to the general example.
    expect(ownExamples({ skill_codes: ['no_journal'], watch_kinds: ['cash_stale'] }, skills, week)).toEqual([])
    expect(ownExamples(lesson, undefined, undefined)).toEqual([])
  })

  it('never uses the banned words in any generated sentence', () => {
    const sentences = [
      ...skills.skills.flatMap((s) => s.lines.map(skillLine)),
      skillWindowPhrase(skills.skills[0]),
      skillWindowPhrase(skills.skills[1]),
      ...week.items.map((i) => watchItemPhrase(i, TODAY)),
      learnSummary(week, skills, lessons) ?? '',
      progressLabel(lessons.lessons[1].progress),
      progressTotal(lessons.lessons),
      ...ownExamples(lesson, skills, week).map((e) => e.text),
    ]
    for (const s of sentences) {
      expect(s, s).not.toMatch(BANNED_WORDS_RE)
      expect(s, s).not.toMatch(GRADE_WORDS_RE)
      expect(s, s).not.toMatch(/[▲▼]/)
    }
  })
})
