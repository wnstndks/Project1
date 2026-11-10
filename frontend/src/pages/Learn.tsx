import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import type { LearnSkills, LearnWeek, LessonList } from '../api/client'
import { useLearnSkills, useLearnWeek, useLessons } from '../api/hooks'
import { SkillChip } from '../components/SkillChip'
import { Card, ErrorBox, ListRow, SegmentedControl, Skeleton } from '../components/ui'
import { displaySymbol } from '../lib/format'
import {
  EMPTY_WEEK_KO,
  EVIDENCE_NOTE_KO,
  FIRST_TOPICS_DEFAULT_NOTE_KO,
  FIRST_TOPICS_NOTE_KO,
  LEARN_FOOTER_KO,
  LEARN_HONESTY_KO,
  LEARN_INTRO_KO,
  LESSON_LEVEL_LABELS_KO,
  progressLabel,
  progressTotal,
  SEVERITY_LABELS_KO,
  SEVERITY_TONE,
  skillLine,
  skillWindowPhrase,
  WATCH_KIND_LABELS_KO,
  watchItemPhrase,
} from '../lib/learn'

type LevelFilter = 'all' | 'basic' | 'intermediate'
const LEVEL_OPTIONS: { value: LevelFilter; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'basic', label: '기초' },
  { value: 'intermediate', label: '중급' },
]

/**
 * The learn coach page (D-034): what to check this week, habits seen in my own trade log,
 * the topics to read first and the whole lesson list. Not a signal, not a rule check, not a
 * policy check and not advice; the habit chips describe the evidence, never the person, and
 * nothing on the page carries a gain/loss colour.
 */
export function Learn() {
  const lessons = useLessons()
  const skills = useLearnSkills()
  const week = useLearnWeek()

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">투자 공부</h1>
        <p className="mt-2 max-w-3xl text-sm text-ink-2">{LEARN_INTRO_KO}</p>
        <p className="mt-1 text-sm text-ink-2">{LEARN_HONESTY_KO}</p>
      </header>

      <WeekSection week={week.data} loading={week.isLoading} />
      <SkillsSection skills={skills.data} loading={skills.isLoading} />
      <FirstTopicsCard skills={skills.data} lessons={lessons.data} />

      <SectionState title="전체 공부 목록" error={lessons.error} loading={!lessons.data && !lessons.error}>
        {lessons.data && <LessonListBody data={lessons.data} />}
      </SectionState>

      <p className="text-xs text-muted">{LEARN_FOOTER_KO}</p>
    </div>
  )
}

/** Loading and error states shared by the sections (the coach page's shape). */
function SectionState({ title, error, loading, children }: {
  title: string
  error: unknown
  loading: boolean
  children: ReactNode
}) {
  return (
    <Card title={title}>
      {error ? <ErrorBox error={error} /> : loading ? <Skeleton className="h-40" /> : children}
    </Card>
  )
}

// --- this week --------------------------------------------------------------------------------------

/** Hidden until the week route answers (it lands with the next work package); a failure hides it too. */
function WeekSection({ week, loading }: { week: LearnWeek | undefined; loading: boolean }) {
  if (loading) return <Skeleton className="h-24" />
  if (!week) return null
  return (
    <Card title="이번 주 볼 것">
      {week.items.length === 0 ? (
        <p className="text-sm text-muted">{EMPTY_WEEK_KO}</p>
      ) : (
        <ul className="divide-y divide-line">
          {week.items.map((item, i) => (
            <li key={`${item.kind}-${item.symbol ?? ''}-${item.date ?? ''}-${i}`} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-3">
              <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${SEVERITY_TONE[item.severity]}`}>
                {SEVERITY_LABELS_KO[item.severity]}
              </span>
              <span className="text-xs text-muted">{WATCH_KIND_LABELS_KO[item.kind] ?? item.kind}</span>
              <span className="num text-[15px] font-semibold text-ink">
                {watchItemPhrase(item)}
                {item.estimated && <span className="ml-1 text-xs font-normal text-muted">(추정)</span>}
              </span>
              {item.detail_ko && <span className="basis-full text-sm text-ink-2">{item.detail_ko}</span>}
              {item.symbol && (
                <Link to={`/assets/${encodeURIComponent(item.symbol)}`} className="text-sm text-accent hover:underline">
                  {displaySymbol(item.symbol)} 보기
                </Link>
              )}
              {item.route && (
                <Link to={item.route} className="text-sm text-accent hover:underline">
                  보기
                </Link>
              )}
              {item.lesson_id && (
                <Link to={`/learn/${item.lesson_id}`} className="text-sm text-accent hover:underline">
                  관련 주제
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}
      <Caveats items={[...week.caveats, ...week.errors]} />
    </Card>
  )
}

// --- habits in my records ---------------------------------------------------------------------------

/** Hidden until the skills route answers (next work package); server order is kept as it is. */
function SkillsSection({ skills, loading }: { skills: LearnSkills | undefined; loading: boolean }) {
  if (loading) return <Skeleton className="h-24" />
  if (!skills) return null
  return (
    <Card title="내 기록으로 본 습관">
      <p className="text-sm text-ink-2">{EVIDENCE_NOTE_KO}</p>
      {skills.empty && <p className="mt-2 text-sm text-muted">거래 기록이 없어 모든 습관이 "기록 부족"이에요.</p>}
      <ul className="mt-4 space-y-5">
        {skills.skills.map((s) => (
          <li key={s.code}>
            <div className="flex flex-wrap items-center gap-2">
              <SkillChip level={s.level} label={s.label_ko} />
              <span className="num text-xs text-muted">
                표본 {s.sample_n}건 · {skillWindowPhrase(s)}
              </span>
            </div>
            {s.lines.length > 0 && (
              <ul className="num mt-2 space-y-1 text-[15px] text-ink">
                {s.lines.map((l) => <li key={l.text_ko}>{skillLine(l)}</li>)}
              </ul>
            )}
            {s.caveat_ko && <p className="mt-1 text-xs text-muted">{s.caveat_ko}</p>}
            {s.lesson_ids.length > 0 && (
              <p className="mt-2 flex flex-wrap gap-2">
                {s.lesson_ids.map((id) => (
                  <Link key={id} to={`/learn/${id}`} className="rounded-md bg-fill px-2 py-0.5 text-xs font-semibold text-accent hover:underline">
                    관련 주제 →
                  </Link>
                ))}
              </p>
            )}
          </li>
        ))}
      </ul>
      <Caveats items={skills.caveats} />
    </Card>
  )
}

// --- first topics and the list ------------------------------------------------------------------------

/**
 * Three topics to read first: from the habit ranking when the evidence is there, else the
 * basics-first order the lesson list carries. "Read first", never "recommended".
 */
function FirstTopicsCard({ skills, lessons }: { skills: LearnSkills | undefined; lessons: LessonList | undefined }) {
  if (!lessons) return null
  const ranked = skills && skills.first_topics_source === 'ranking' && skills.first_topics.length > 0
  const ids = ranked ? skills.first_topics : lessons.default_first_topics
  const items = ids.map((id) => lessons.lessons.find((l) => l.id === id)).filter((l) => l !== undefined)
  if (items.length === 0) return null
  return (
    <Card title="먼저 볼 주제">
      <p className="mb-2 text-sm text-ink-2">{ranked ? FIRST_TOPICS_NOTE_KO : FIRST_TOPICS_DEFAULT_NOTE_KO}</p>
      <div className="divide-y divide-line">
        {items.map((l, i) => (
          <ListRow
            key={l.id}
            to={`/learn/${l.id}`}
            avatar={<span className="num flex size-10 shrink-0 items-center justify-center rounded-full bg-fill text-sm font-bold text-ink-2">{i + 1}</span>}
            title={l.title_ko}
            subtitle={lessonSubtitle(l)}
            value={progressLabel(l.progress)}
            chevron
          />
        ))}
      </div>
    </Card>
  )
}

function lessonSubtitle(l: LessonList['lessons'][number]): string {
  return [LESSON_LEVEL_LABELS_KO[l.level] ?? l.level, `${l.minutes}분`, l.summary_ko].join(' · ')
}

function LessonListBody({ data }: { data: LessonList }) {
  const [level, setLevel] = useState<LevelFilter>('all')
  const shown = data.lessons.filter((l) => level === 'all' || l.level === level)
  return (
    <>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl label="수준" options={LEVEL_OPTIONS} value={level} onChange={setLevel} />
        <span className="num text-sm text-ink-2">{progressTotal(data.lessons)}</span>
      </div>
      {shown.length === 0 ? (
        <p className="text-sm text-muted">이 수준의 강의가 아직 없어요.</p>
      ) : (
        <div className="divide-y divide-line">
          {shown.map((l) => (
            <ListRow
              key={l.id}
              to={`/learn/${l.id}`}
              title={l.title_ko}
              subtitle={lessonSubtitle(l)}
              value={progressLabel(l.progress)}
              chevron
            />
          ))}
        </div>
      )}
      {/* A lesson that failed its content contract is left out and said so, never hidden. */}
      <Caveats items={data.caveats} />
    </>
  )
}

function Caveats({ items }: { items: string[] }) {
  if (items.length === 0) return null
  return (
    <ul className="mt-4 space-y-1 text-xs text-muted">
      {items.map((c) => <li key={c}>{c}</li>)}
    </ul>
  )
}
