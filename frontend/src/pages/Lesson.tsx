import { Link, useParams } from 'react-router-dom'

import type { LessonDetail } from '../api/client'
import { ApiError } from '../api/client'
import { useLearnSkills, useLearnWeek, useLesson, useSaveProgress } from '../api/hooks'
import { LessonBody } from '../components/LessonBody'
import { Quiz } from '../components/Quiz'
import { ReferenceList } from '../components/ReferenceList'
import { Card, ErrorBox, Skeleton } from '../components/ui'
import { displaySymbol } from '../lib/format'
import {
  EXTERNAL_LINK_NOTE_KO,
  LEARN_FOOTER_KO,
  LEARN_HONESTY_KO,
  LESSON_LEVEL_LABELS_KO,
  NO_RECORD_EXAMPLE_KO,
  ownExamples,
  SKILL_LABELS_KO,
  type OwnExample,
} from '../lib/learn'

/**
 * One lesson (D-034): summary, "from my records" (evidence lines and week items joined on the
 * client from the shared `skills` / `week` caches; a general AAA/BBB example when there is
 * nothing), the structured body, the one-line takeaway, references, the self-check and the
 * "읽었어요" button. Static content; not a signal, not a rule check, not advice, and no
 * gain/loss colour anywhere on the page.
 */
export function Lesson() {
  const { lessonId } = useParams()
  const lesson = useLesson(lessonId)

  return (
    <div className="space-y-6">
      <Link to="/learn" className="inline-block text-sm text-ink-2 hover:text-ink">
        ← 공부 목록
      </Link>
      {lesson.error ? (
        <>
          <ErrorBox
            error={
              lesson.error instanceof ApiError && lesson.error.status === 404
                ? '이 강의를 찾을 수 없어요.'
                : lesson.error
            }
          />
          <Link to="/learn" className="inline-block text-sm font-semibold text-accent hover:underline">
            공부 목록으로 →
          </Link>
        </>
      ) : !lesson.data ? (
        <Skeleton className="h-96" />
      ) : (
        <LessonView key={lesson.data.id} lesson={lesson.data} />
      )}
    </div>
  )
}

function LessonView({ lesson }: { lesson: LessonDetail }) {
  const save = useSaveProgress(lesson.id)
  const read = !!lesson.progress?.read_at
  const chips = [
    LESSON_LEVEL_LABELS_KO[lesson.level] ?? lesson.level,
    `${lesson.minutes}분`,
    ...lesson.skill_codes.map((c) => SKILL_LABELS_KO[c] ?? c),
  ]

  return (
    <>
      <header>
        <h1 className="text-2xl font-bold">{lesson.title_ko}</h1>
        <p className="mt-2 flex flex-wrap gap-2">
          {chips.map((c) => (
            <span key={c} className="num rounded-md bg-fill px-2 py-0.5 text-xs font-semibold text-ink-2">
              {c}
            </span>
          ))}
        </p>
        <p className="mt-3 max-w-3xl text-[15px] text-ink-2">{lesson.summary_ko}</p>
      </header>

      <OwnRecords lesson={lesson} />

      <LessonBody sections={lesson.sections} />

      <div className="rounded-2xl border border-line bg-surface p-6">
        <h2 className="text-[13px] font-semibold text-muted">핵심 한 줄</h2>
        <p className="mt-1 text-[17px] font-semibold text-ink">{lesson.takeaway_ko}</p>
      </div>

      <Card title="참고 자료">
        <ReferenceList references={lesson.references} />
        <p className="mt-4 text-xs text-muted">{EXTERNAL_LINK_NOTE_KO}</p>
      </Card>

      <Card title="셀프 체크">
        <Quiz questions={lesson.quiz} onComplete={(answers) => save.mutate({ answers })} />
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          aria-pressed={read}
          disabled={save.isPending}
          onClick={() => save.mutate({ read: !read })}
          className={`rounded-xl px-5 py-2.5 text-sm font-semibold disabled:opacity-60 ${
            read ? 'bg-fill text-ink' : 'bg-accent text-white hover:opacity-90'
          }`}
        >
          {save.isPending ? '저장 중…' : read ? '읽음 ✓' : '읽었어요'}
        </button>
        {save.error && <span className="text-sm text-danger">{String(save.error instanceof Error ? save.error.message : save.error)}</span>}
      </div>

      <footer className="space-y-1 text-xs text-muted">
        <p>{LEARN_FOOTER_KO}</p>
        <p>{LEARN_HONESTY_KO}</p>
      </footer>
    </>
  )
}

/**
 * Evidence from my own records for this lesson's habits and week items. The two queries are
 * shared with the learn page (five-minute cache); while either is loading or failed the
 * general example is shown instead, so the lesson never waits on them.
 */
function OwnRecords({ lesson }: { lesson: LessonDetail }) {
  const skills = useLearnSkills()
  const week = useLearnWeek()
  const examples = ownExamples(lesson, skills.data, week.data)
  return (
    <Card title="내 기록에서">
      {examples.length === 0 ? (
        <>
          <p className="text-sm text-muted">{NO_RECORD_EXAMPLE_KO}</p>
          <p className="num mt-2 text-[15px] text-ink">{lesson.general_example_ko}</p>
        </>
      ) : (
        <ul className="space-y-3">
          {examples.map((e, i) => (
            <li key={i}>
              <OwnExampleRow example={e} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function OwnExampleRow({ example }: { example: OwnExample }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <span className="num text-[15px] text-ink">{example.text}</span>
      {example.symbols.map((s) => (
        <Link key={s} to={`/assets/${encodeURIComponent(s)}`} className="text-sm text-accent hover:underline">
          {displaySymbol(s)} 보기
        </Link>
      ))}
      {example.tradeIds.length > 0 && (
        <Link to="/transactions" className="text-sm text-accent hover:underline">
          거래 {example.tradeIds.length}건 보기
        </Link>
      )}
      {example.route && (
        <Link to={example.route} className="text-sm text-accent hover:underline">
          화면 보기
        </Link>
      )}
    </div>
  )
}
