import { describe, expect, it } from 'vitest'

import {
  badCasePhrase,
  bandLabel,
  bandLegend,
  coverageNote,
  edgeLabels,
  esPhrase,
  horizonPhrase,
  isPastTarget,
  midLegend,
  midPhrase,
  modelStatusSentence,
  pctRange,
  pendingPhrase,
  rangePhrase,
  reasonLabel,
  tailPhrase,
  weekRangeHint,
  worstHorizonVerdict,
} from './forecast'

const week = { horizon: '1w', low_ratio: 0.964, high_ratio: 1.045, p_up: 0.53, direction_reason: 'not_significant' }

describe('forecast wording', () => {
  it('names horizons in everyday words, with the next session for stocks', () => {
    expect(horizonPhrase('1d', true)).toBe('내일')
    expect(horizonPhrase('1d', false)).toBe('다음 거래일')
    expect(horizonPhrase('1w', false)).toBe('1주 뒤')
    expect(horizonPhrase('1m', true)).toBe('1개월 뒤')
  })

  it('explains the 10~90% band, the median and the 5% tail without statistics terms', () => {
    expect(rangePhrase('1,381만원', '1,720만원')).toBe('대체로 1,381만원~1,720만원 사이 (10번 중 8번)')
    expect(bandLabel()).toBe('대체로 이 사이 (10번 중 8번)')
    expect(bandLegend()).toBe('10번 중 8번 범위')
    expect(midPhrase('1,537만원')).toBe('1,537만원 안팎')
    expect(midLegend()).toBe('예상 중간값(절반 지점)')
    expect(coverageNote()).toBe('약 80%(10번 중 8번꼴, 급락장에서는 더 자주 벗어남)')
    expect(badCasePhrase()).toBe('운 나쁜 경우 (20번 중 1번꼴)')
    expect(esPhrase()).toBe('가장 나쁜 5% 상황의 평균 손실 (20번 중 1번은 이 정도 또는 그 이상)')
    expect(tailPhrase('bad')).toBe('운 나쁜 경우 (10번 중 1번)')
    expect(tailPhrase('good')).toBe('운 좋은 경우 (10번 중 1번)')
  })

  it('marks a horizon whose target date has already passed as waiting to be scored', () => {
    const today = new Date(2026, 9, 22, 18, 40)
    expect(isPastTarget('2026-10-21', today)).toBe(true)
    expect(isPastTarget('2026-10-22', today)).toBe(false)
    expect(isPastTarget('2026-10-23', today)).toBe(false)
    expect(pendingPhrase('2026-10-21', today)).toBe('채점 대기 (10.21 마감 기준)')
    expect(pendingPhrase('2025-12-31', today)).toBe('채점 대기 (25.12.31 마감 기준)')
  })

  it('writes the home list hint from the one-week ratios, with the rise probability only on an edge', () => {
    expect(weekRangeHint(undefined)).toBeUndefined()
    expect(weekRangeHint({ horizons: [{ ...week, horizon: '1d' }] })).toBeUndefined()
    expect(weekRangeHint({ horizons: [week] })).toBe('1주 변동 범위 대체로 −3.6%~+4.5% 사이 (10번 중 8번) · 참고용')
    expect(weekRangeHint({ horizons: [{ ...week, direction_reason: 'edge', p_up: 0.574 }] })).toBe(
      '1주 변동 범위 대체로 −3.6%~+4.5% 사이 (10번 중 8번) · 오를 확률 57% · 참고용',
    )
  })

  it('writes the quantile band as signed moves from the base price', () => {
    expect(pctRange(96.4, 104.5, 100)).toBe('−3.6%~+4.5%')
    expect(pctRange(101.2, 104.5, 100)).toBe('+1.2%~+4.5%')
    expect(pctRange(100, 100, 100)).toBe('0.0%~0.0%')
    expect(pctRange(1, 2, 0)).toBe('0.0%~0.0%')
  })
})

describe('edge chips', () => {
  it('labels each live reason and never promotes an unknown one', () => {
    expect(reasonLabel('edge')).toEqual({ label: '검증 통과', tone: 'good' })
    expect(reasonLabel('forward_test_pending')).toEqual({ label: '과거 검증 통과 · 실전 검증 대기', tone: 'pending' })
    expect(reasonLabel('not_significant')).toEqual({ label: '우위 없음', tone: 'none' })
    expect(reasonLabel('no_data')).toEqual({ label: '데이터 부족', tone: 'none' })
    expect(reasonLabel('something_new')).toEqual({ label: '우위 없음', tone: 'none' })
  })

  it('gives direction and range their own chip', () => {
    expect(edgeLabels({ direction_reason: 'not_significant', range_reason: 'forward_test_pending' })).toEqual([
      { axis: '방향', label: '우위 없음', tone: 'none' },
      { axis: '범위', label: '과거 검증 통과 · 실전 검증 대기', tone: 'pending' },
    ])
    expect(edgeLabels({ direction_reason: 'edge', range_reason: 'no_data' })).toEqual([
      { axis: '방향', label: '검증 통과', tone: 'good' },
      { axis: '범위', label: '데이터 부족', tone: 'none' },
    ])
  })

  it('picks the most conservative reason per axis across horizons', () => {
    const horizons = [
      { horizon: '1d', direction_reason: 'not_significant', range_reason: 'forward_test_pending' },
      { horizon: '1w', direction_reason: 'no_data', range_reason: 'edge' },
      { horizon: '1m', direction_reason: 'edge', range_reason: 'no_data' },
    ]
    expect(worstHorizonVerdict(horizons)).toEqual({ direction_reason: 'not_significant', range_reason: 'no_data' })
    expect(
      worstHorizonVerdict([
        { direction_reason: 'edge', range_reason: 'edge' },
        { direction_reason: 'edge', range_reason: 'forward_test_pending' },
      ]),
    ).toEqual({ direction_reason: 'edge', range_reason: 'forward_test_pending' })
    expect(worstHorizonVerdict([])).toBeUndefined()
  })
})

describe('modelStatusSentence', () => {
  const verdict = (direction: string, range: string) => ({ direction, range })

  it('says the direction is no better than the up-day baseline and the range is pending', () => {
    const live = {
      stock: {
        '1d': verdict('not_significant', 'forward_test_pending'),
        '1w': verdict('not_significant', 'not_significant'),
        '1m': verdict('not_significant', 'not_significant'),
      },
      crypto: {
        '1d': verdict('not_significant', 'not_significant'),
        '1w': verdict('no_data', 'no_data'),
        '1m': verdict('not_significant', 'not_significant'),
      },
    }
    expect(modelStatusSentence(live)).toBe(
      '오를지 내릴지는 단순 기준선(과거에 오른 날 비율)보다 잘 맞히지 못합니다. ' +
        '가격 범위의 폭은 과거 검증은 통과했지만 아직 실전 검증 전입니다. 참고만 하세요.',
    )
  })

  it('says the range is no different from the simple estimate when nothing passed or is pending', () => {
    const live = { stock: { '1d': verdict('not_significant', 'not_significant') } }
    expect(modelStatusSentence(live)).toBe(
      '오를지 내릴지는 단순 기준선(과거에 오른 날 비율)보다 잘 맞히지 못합니다. ' +
        '가격 범위도 단순 추정과 차이가 없습니다. 참고만 하세요.',
    )
  })

  it('names where the range or direction did pass and keeps "우위 없음" for the rest', () => {
    const live = {
      stock: { '1d': verdict('not_significant', 'edge'), '1w': verdict('edge', 'not_significant') },
      crypto: { '1m': verdict('not_significant', 'edge') },
    }
    expect(modelStatusSentence(live)).toBe(
      '오를지 내릴지는 주식 1주에서 기준선(과거에 오른 날 비율)보다 잘 맞혔고, 그 밖에는 우위 없음입니다. ' +
        '가격 범위의 폭은 주식 1일·코인 1개월에서 조금 더 정확했습니다. 참고만 하세요.',
    )
  })

  it('never mentions a market average and admits when there is no verdict at all', () => {
    expect(modelStatusSentence(null)).toBe('아직 검증 결과가 없어 우위를 확인할 수 없습니다. 참고만 하세요.')
    expect(modelStatusSentence({})).toBe('아직 검증 결과가 없어 우위를 확인할 수 없습니다. 참고만 하세요.')
    const live = { stock: { '1d': verdict('edge', 'edge') } }
    expect(modelStatusSentence(live)).not.toContain('시장 평균')
  })
})
