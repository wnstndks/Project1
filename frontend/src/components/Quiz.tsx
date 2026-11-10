import { useState } from 'react'

import type { LessonQuestion } from '../api/client'
import { quizResultPhrase } from '../lib/learn'

/**
 * A lesson's self-check (D-034): one radio group per question. A choice locks the question and
 * explains right away (`맞았어요. …` / `아니에요. 답은 n번. …`), announced through `role="status"`.
 * After the last question the result sentence appears with "다시 풀기"; `onComplete` fires once
 * per attempt with the chosen indices, and the server does the scoring that is stored. Nothing
 * here is a grade of the reader.
 */
export function Quiz({ questions, onComplete }: {
  questions: LessonQuestion[]
  onComplete: (answers: number[]) => void
}) {
  const [attempt, setAttempt] = useState(0)
  const [answers, setAnswers] = useState<(number | null)[]>(() => questions.map(() => null))
  if (questions.length === 0) return null

  const done = answers.every((a) => a !== null)
  const score = answers.filter((a, i) => a === questions[i].answer).length

  const choose = (qi: number, ci: number) => {
    if (answers[qi] !== null) return
    const next = answers.map((a, i) => (i === qi ? ci : a))
    setAnswers(next)
    if (next.every((a) => a !== null)) onComplete(next as number[])
  }

  const retry = () => {
    setAnswers(questions.map(() => null))
    setAttempt((n) => n + 1)
  }

  return (
    <div className="space-y-6">
      {questions.map((q, qi) => {
        const picked = answers[qi]
        const answered = picked !== null
        const correct = picked === q.answer
        return (
          <fieldset key={`${attempt}-${qi}`} className="space-y-2">
            <legend className="mb-2 text-[15px] font-semibold text-ink">
              <span className="num">{qi + 1}.</span> {q.prompt_ko}
            </legend>
            {q.choices.map((c, ci) => (
              <label
                key={c}
                className={`flex cursor-pointer items-start gap-2 rounded-lg px-3 py-2 text-[15px] ${
                  answered && ci === q.answer ? 'bg-accent-soft' : 'hover:bg-hover'
                } ${answered ? 'cursor-default' : ''}`}
              >
                <input
                  type="radio"
                  name={`quiz-${attempt}-${qi}`}
                  value={ci}
                  checked={picked === ci}
                  disabled={answered}
                  onChange={() => choose(qi, ci)}
                  className="mt-1 accent-[var(--accent)]"
                />
                <span>
                  <span className="num mr-1 text-muted">{ci + 1}번</span>
                  {c}
                </span>
              </label>
            ))}
            <p role="status" className="min-h-5 text-sm text-ink-2">
              {answered && (correct ? `맞았어요. ${q.why_ko}` : `아니에요. 답은 ${q.answer + 1}번. ${q.why_ko}`)}
            </p>
          </fieldset>
        )
      })}
      {done && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-fill px-4 py-3 text-sm">
          <span className="font-semibold">{quizResultPhrase(score, questions.length)}</span>
          <button
            type="button"
            onClick={retry}
            className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-semibold hover:bg-hover"
          >
            다시 풀기
          </button>
        </div>
      )}
    </div>
  )
}
