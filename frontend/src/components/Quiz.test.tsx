import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { LessonQuestion } from '../api/client'
import { BANNED_WORDS_RE, GRADE_WORDS_RE } from '../lib/learn'
import { Quiz } from './Quiz'

// Synthetic questions (AAA/BBB only).
const questions: LessonQuestion[] = [
  { prompt_ko: 'AAA를 급등 뒤에 샀다면 무엇을 먼저 보나요?', choices: ['내 규칙', '뉴스', '남의 의견'], answer: 0, why_ko: '미리 정한 규칙이 기준입니다.' },
  { prompt_ko: '분산하면 손실이 사라진다?', choices: ['그렇다', '아니다', '모른다'], answer: 1, why_ko: '분산은 손실의 크기를 줄일 뿐 없애지 않습니다.' },
  { prompt_ko: 'BBB의 건수는 어디서 보나요?', choices: ['코치', '시뮬레이션', '뉴스', '가져오기'], answer: 0, why_ko: '코치 페이지의 습관 점검에 있습니다.' },
]

const group = (i: number) => screen.getByRole('group', { name: new RegExp(`^${i + 1}\\.`) })
const pick = (i: number, choice: number) => fireEvent.click(within(group(i)).getAllByRole('radio')[choice])

describe('Quiz', () => {
  afterEach(cleanup)

  it('renders one labelled radio group per question', () => {
    render(<Quiz questions={questions} onComplete={() => {}} />)
    expect(screen.getAllByRole('group')).toHaveLength(3)
    expect(within(group(0)).getAllByRole('radio')).toHaveLength(3)
    expect(within(group(2)).getAllByRole('radio')).toHaveLength(4)
    for (const status of screen.getAllByRole('status')) expect(status).toHaveTextContent('')
  })

  it('locks a question once answered and explains right away, right or wrong', () => {
    render(<Quiz questions={questions} onComplete={() => {}} />)
    pick(0, 1)
    const radios = within(group(0)).getAllByRole('radio')
    expect(radios.every((r) => (r as HTMLInputElement).disabled)).toBe(true)
    expect(screen.getAllByRole('status')[0]).toHaveTextContent('아니에요. 답은 1번. 미리 정한 규칙이 기준입니다.')
    // A second click on the locked group changes nothing.
    pick(0, 0)
    expect(screen.getAllByRole('status')[0]).toHaveTextContent('아니에요. 답은 1번.')
    pick(1, 1)
    expect(screen.getAllByRole('status')[1]).toHaveTextContent('맞았어요. 분산은 손실의 크기를 줄일 뿐 없애지 않습니다.')
  })

  it('reports the result after the last answer, calls onComplete once, and can be retried', () => {
    const onComplete = vi.fn()
    render(<Quiz questions={questions} onComplete={onComplete} />)
    expect(screen.queryByRole('button', { name: '다시 풀기' })).not.toBeInTheDocument()
    pick(0, 1)
    pick(1, 1)
    expect(onComplete).not.toHaveBeenCalled()
    pick(2, 0)
    expect(onComplete).toHaveBeenCalledTimes(1)
    expect(onComplete).toHaveBeenCalledWith([1, 1, 0])
    expect(screen.getByText('3문제 중 2문제 맞았어요. 틀린 문제의 설명을 다시 읽어 보세요.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '다시 풀기' }))
    expect(screen.queryByRole('button', { name: '다시 풀기' })).not.toBeInTheDocument()
    const radios = within(group(0)).getAllByRole('radio') as HTMLInputElement[]
    expect(radios.every((r) => !r.disabled && !r.checked)).toBe(true)
    pick(0, 0)
    pick(1, 1)
    pick(2, 0)
    expect(onComplete).toHaveBeenCalledTimes(2)
    expect(onComplete).toHaveBeenLastCalledWith([0, 1, 0])
    expect(screen.getByText('3문제 중 3문제 맞았어요. 설명도 한 번 더 읽어 두면 좋아요.')).toBeInTheDocument()
  })

  it('renders nothing without questions and never grades the reader', () => {
    const { container } = render(<Quiz questions={[]} onComplete={() => {}} />)
    expect(container).toBeEmptyDOMElement()
    cleanup()
    render(<Quiz questions={questions} onComplete={() => {}} />)
    pick(0, 2)
    pick(1, 0)
    pick(2, 3)
    expect(document.body.textContent).not.toMatch(GRADE_WORDS_RE)
    expect(document.body.textContent).not.toMatch(BANNED_WORDS_RE)
    expect(document.body.textContent).not.toMatch(/[▲▼]/)
  })
})
