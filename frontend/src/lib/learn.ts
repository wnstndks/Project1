/**
 * Wording for the learn coach (DECISIONS.md D-034): evidence from my own trade log, what to
 * check this week, and the study material behind each concept.
 *
 * Wording rules, enforced by `learnPhrases.test.ts` with the same regexes as the backend:
 * - never `추천|사세요|파세요|오를|예상 수익|수익(을|이)?\s?보장(?!하지 않)|반드시|확실히|무조건|틀림없이`
 *   ("수익을 보장하지 않습니다" is the honesty line and is allowed);
 * - never grade the person: no `실력|점수|등급|레벨`; habit levels are the strength of evidence
 *   (뚜렷함 / 조금 보임 / 걸린 것 없음 / 기록 부족) and every evidence line carries its sample;
 * - evidence and lessons get no gain/loss colour and no ▲▼: nothing here is a result.
 * Nothing here computes evidence: every figure comes from `/api/learn/*` as it is.
 */
import type {
  LearnEvidenceLine,
  LearnLevel,
  LearnSeverity,
  LearnSkill,
  LearnSkills,
  LearnWatchItem,
  LearnWeek,
  LessonDetail,
  LessonList,
  LessonProgress,
  LessonSummary,
} from '../api/client'
import { windowSpanPhrase } from './coach'
import { formatDate } from './format'

/** Same regexes as `backend/app/learn/model.py` (BANNED_PATTERN, GRADE_PATTERN). */
export const BANNED_WORDS_RE = /추천|사세요|파세요|오를|예상 수익|수익(을|이)?\s?보장(?!하지 않)|반드시|확실히|무조건|틀림없이/
export const GRADE_WORDS_RE = /실력|점수|등급|레벨/

export const LEARN_INTRO_KO =
  '내 거래 기록에서 보이는 습관, 이번 주에 확인할 것, 그 개념의 공부 자료를 모았어요. 예측·종목 선택·투자 조언이 아닙니다.'
export const LEARN_HONESTY_KO = '공부는 판단의 질을 높이지만 수익을 보장하지 않습니다.'
export const LEARN_FOOTER_KO = '투자 조언이 아닙니다. 공부 자료는 일반 원칙이며, 내 상황에 맞는지는 스스로 판단합니다.'
export const FIRST_TOPICS_NOTE_KO = '내 기록에서 걸린 항목이 많은 순서예요. 읽는 순서일 뿐, 무엇을 사고팔지와는 관계없어요.'
export const FIRST_TOPICS_DEFAULT_NOTE_KO = '거래 기록이 없어 기초부터 순서대로 보여 드려요.'
export const NO_RECORD_EXAMPLE_KO = '내 기록에서 걸린 거래가 없어 일반 예시를 보여 드려요.'
export const EMPTY_WEEK_KO = '이번 주에 확인할 항목이 없어요.'
export const EXTERNAL_LINK_NOTE_KO = '외부 링크는 새 탭에서 열리며 내용은 각 기관의 책임입니다.'
export const EVIDENCE_NOTE_KO = '내 거래 기록에서 집계한 증거이며, 예측이나 신호가 아닙니다.'
export const LEARN_CARD_NOTE_KO = '내 기록으로 고른 읽는 순서예요. 투자 조언이 아닙니다.'

export const LEVEL_LABELS_KO: Record<LearnLevel, string> = {
  strong: '뚜렷함',
  some: '조금 보임',
  none: '걸린 것 없음',
  insufficient: '기록 부족',
}

/** Chip tone per level; the text always carries the level too. */
export const LEVEL_TONE: Record<LearnLevel, string> = {
  strong: 'bg-danger/10 text-danger',
  some: 'bg-accent-soft text-accent',
  none: 'bg-fill text-ink-2',
  insufficient: 'bg-fill text-muted',
}

/** Habit labels (mirror of `strategy/skills.SKILL_LABELS_KO`) for chips drawn from a lesson's
 *  `skill_codes` before the evidence has loaded. */
export const SKILL_LABELS_KO: Record<string, string> = {
  concentration: '한 곳에 몰림',
  oversizing: '한 번에 크게 걸기',
  rule_breaking: '정한 규칙 어기기',
  chasing: '급등 뒤 매수',
  loss_holding: '손실은 오래, 이익은 빨리',
  cost_blindness: '비용 무시',
  no_journal: '메모 없는 거래',
  short_holding: '짧은 보유·잦은 회전',
  class_drift: '자산군 비중 벗어남',
}

export const LESSON_LEVEL_LABELS_KO: Record<string, string> = { basic: '기초', intermediate: '중급' }

export const SECTION_KIND_LABELS_KO: Record<string, string> = {
  fact: '사실',
  principle: '일반 원칙',
  app: '이 앱에서는',
}

export const WATCH_KIND_LABELS_KO: Record<string, string> = {
  kill_switch: '킬스위치',
  rule_triggered: '규칙 발동',
  suspicious_trade: '단가 확인',
  pending_action: '배당·분할 확인',
  earnings: '실적 발표',
  ex_dividend: '배당락',
  rule_near_cut: '손절선 근접',
  rule_near_add: '추매선 근접',
  near_cap: '비중 상한 근접',
  market_closure: '휴장·조기 폐장',
  events_stale: '일정 갱신 실패',
  policy_unset: '정책 미설정',
  cash_missing: '현금 미입력',
  cash_stale: '현금 기준일 경과',
}

export const SEVERITY_LABELS_KO: Record<LearnSeverity, string> = {
  now: '지금 확인',
  soon: '이번 주',
  setup: '준비',
}

/** Chip tone per severity; the label always says it. */
export const SEVERITY_TONE: Record<LearnSeverity, string> = {
  now: 'bg-danger/10 text-danger',
  soon: 'bg-accent-soft text-accent',
  setup: 'bg-fill text-ink-2',
}

// --- sentences ---------------------------------------------------------------------------------------

/** `…문장 · 표본 12건`; a line without a sample (a note) stays as it is. */
export function skillLine(l: Pick<LearnEvidenceLine, 'text_ko' | 'n'>): string {
  return l.n === null || l.n === undefined ? l.text_ko : `${l.text_ko} · 표본 ${l.n}건`
}

/** The window one habit's evidence covers; today-only habits (concentration, class drift) say so. */
export function skillWindowPhrase(s: Pick<LearnSkill, 'window_start' | 'window_end'>): string {
  return s.window_start ? windowSpanPhrase(s.window_start, s.window_end) : '오늘 기준'
}

/** `11월 3일 (화) · 실적 발표 예정일(추정)` or `이번 주 · 킬스위치 켜짐`. */
export function watchItemPhrase(item: Pick<LearnWatchItem, 'date' | 'title_ko'>, today = new Date()): string {
  return item.date ? `${formatDate(item.date, 'long', today)} · ${item.title_ko}` : `이번 주 · ${item.title_ko}`
}

function lessonTitle(lessons: Pick<LessonList, 'lessons'>, id: string | undefined): string | undefined {
  return id ? lessons.lessons.find((l) => l.id === id)?.title_ko : undefined
}

/**
 * One sentence for the home card: `이번 주 볼 것 2개 · 먼저 볼 주제: 추격 매수 →`, or with no trade
 * record `공부 목록 14개 · 먼저 볼 주제: 분산 →`. Nothing (hidden card) while any of the three
 * responses is missing.
 */
export function learnSummary(
  week: Pick<LearnWeek, 'items'> | undefined,
  skills: Pick<LearnSkills, 'empty' | 'first_topics'> | undefined,
  lessons: Pick<LessonList, 'lessons' | 'total' | 'default_first_topics'> | undefined,
): string | undefined {
  if (!week || !skills || !lessons) return undefined
  const title = lessonTitle(lessons, skills.first_topics[0] ?? lessons.default_first_topics[0])
  const topic = title ? ` · 먼저 볼 주제: ${title}` : ''
  const head = skills.empty ? `공부 목록 ${lessons.total}개` : `이번 주 볼 것 ${week.items.length}개`
  return `${head}${topic} →`
}

/** `''` | `읽음 ✓` | `읽음 ✓ · 셀프 체크 2/3` | `셀프 체크 2/3`. A check mark, not a grade. */
export function progressLabel(p: LessonProgress | null | undefined): string {
  if (!p) return ''
  const parts: string[] = []
  if (p.read_at) parts.push('읽음 ✓')
  if (p.quiz_score !== null && p.quiz_total !== null) parts.push(`셀프 체크 ${p.quiz_score}/${p.quiz_total}`)
  return parts.join(' · ')
}

/** `3/14 읽음`. */
export function progressTotal(list: Pick<LessonSummary, 'progress'>[]): string {
  const read = list.filter((l) => l.progress?.read_at).length
  return `${read}/${list.length} 읽음`
}

/** After the last self-check question. Never a grade: it points back to the explanations. */
export function quizResultPhrase(score: number, total: number): string {
  const head = `${total}문제 중 ${score}문제 맞았어요.`
  return score >= total ? `${head} 설명도 한 번 더 읽어 두면 좋아요.` : `${head} 틀린 문제의 설명을 다시 읽어 보세요.`
}

export type RefMarker = { text: string } | { ref: number }

/** `'수수료[1]는 …[2]'` → `[{text:'수수료'},{ref:1},{text:'는 …'},{ref:2}]`, for footnote links. */
export function refMarkers(text: string): RefMarker[] {
  const out: RefMarker[] = []
  const re = /\[(\d+)\]/g
  let last = 0
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > last) out.push({ text: text.slice(last, m.index) })
    out.push({ ref: Number(m[1]) })
    last = m.index + m[0].length
  }
  if (last < text.length) out.push({ text: text.slice(last) })
  return out
}

export type OwnExample = {
  text: string
  /** The one symbol the line is about, when there is exactly one (for the `/assets/:symbol` link). */
  symbol?: string
  symbols: string[]
  tradeIds: number[]
  route?: string
}

/**
 * "From my records" on a lesson page: the evidence lines of the habits the lesson explains
 * (`skill_codes`) and the week items of the kinds it covers (`watch_kinds`), joined on the
 * client from the shared `skills` / `week` caches. Empty while either is missing.
 */
export function ownExamples(
  lesson: Pick<LessonDetail, 'skill_codes' | 'watch_kinds'>,
  skills: Pick<LearnSkills, 'skills'> | undefined,
  week: Pick<LearnWeek, 'items'> | undefined,
): OwnExample[] {
  const out: OwnExample[] = []
  for (const s of skills?.skills ?? []) {
    if (!lesson.skill_codes.includes(s.code)) continue
    for (const l of s.lines) {
      out.push({
        text: skillLine(l),
        symbol: l.symbols.length === 1 ? l.symbols[0] : undefined,
        symbols: l.symbols,
        tradeIds: l.trade_ids,
      })
    }
  }
  for (const item of week?.items ?? []) {
    if (!lesson.watch_kinds.includes(item.kind)) continue
    out.push({
      text: item.detail_ko ? `${watchItemPhrase(item)} — ${item.detail_ko}` : watchItemPhrase(item),
      symbol: item.symbol ?? undefined,
      symbols: item.symbol ? [item.symbol] : [],
      tradeIds: [],
      route: item.route ?? undefined,
    })
  }
  return out
}
