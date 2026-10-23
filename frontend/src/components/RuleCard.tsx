import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import type { RuleCheckAll } from '../api/client'
import { useRuleCheck } from '../api/hooks'
import { formatKrw, formatKrwShort } from '../lib/format'
import {
  addPricePhrase,
  blockedPhrase,
  distancePhrase,
  formatInCurrency,
  probPhrase,
  RULES_FOOTNOTE_KO,
} from '../lib/rules'
import { RuleStatusChip } from './RuleStatusChip'
import { Card, ErrorBox, InfoRow, Muted, Skeleton } from './ui'

/**
 * "내 규칙 점검" on the asset page: the user's own rules against this position. Levels are in
 * the position's currency (dollars for stocks, won for coins held on Upbit) with a won
 * conversion at today's rate (`fx`) in small print; distances are in that currency too.
 * Everything shown comes from `/api/rules/check`; nothing is recomputed here.
 */
export function RuleCard({ symbol, fx }: { symbol: string; fx?: number }) {
  const rules = useRuleCheck()
  return (
    <Card title="내 규칙 점검">
      {rules.error ? (
        <ErrorBox error={rules.error} />
      ) : !rules.data ? (
        <Skeleton className="h-40" />
      ) : (
        <RuleCardBody data={rules.data} symbol={symbol} fx={fx} />
      )}
    </Card>
  )
}

function RuleCardBody({ data, symbol, fx }: { data: RuleCheckAll; symbol: string; fx?: number }) {
  const check = data.checks.find((c) => c.symbol === symbol)
  if (!check) {
    const skipped = data.skipped.find((s) => s.symbol === symbol)
    return (
      <>
        <Muted>{skipped ? `점검하지 못했습니다: ${skipped.reason}` : '이 종목의 규칙 점검 결과가 없습니다.'}</Muted>
        <Footnote />
      </>
    )
  }
  const krwPosition = check.currency === 'KRW'
  // Won view of a dollar level at today's rate; a won position needs none.
  const toKrw = (v: number): number | undefined => (krwPosition ? v : fx !== undefined ? v * fx : undefined)
  const inPos = (v: number) => formatInCurrency(v, check.currency)
  const { levels, rule } = check
  const fired = check.triggers.filter((t) => t.kind !== 'info')
  const info = check.triggers.filter((t) => t.kind === 'info')
  const prob = probPhrase(check, data.labels.prob_caveat)
  const riskKrw = toKrw(levels.risk_amount)
  const blocked = blockedPhrase(check.blocked_labels)
  const cutBasis = levels.trailing_stop_price > levels.cut_loss_price ? '고점 기준' : '평균단가 기준'

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <RuleStatusChip status={check.status} label={check.chip_ko} className="text-[12px]" />
        <span className="text-[15px] font-semibold">{check.label_ko}</span>
        <span className="num text-xs text-muted">
          현재가 {inPos(check.price)} · 평균단가 {inPos(check.avg_cost)}
        </span>
      </div>

      <dl className="divide-y divide-line">
        <InfoRow
          label={
            <>
              손절 검토 가격
              <Sub>{cutBasis} · 평균단가 −{rule.cut_loss_pct}%</Sub>
            </>
          }
          value={<Level main={inPos(levels.cut_price)} krw={krwPosition ? undefined : toKrw(levels.cut_price)} note={distancePhrase('손절 검토 가격', check.cut_distance_pct)} />}
        />
        <InfoRow
          label={
            <>
              추적 손절 가격
              <Sub>
                최근 {rule.trailing_lookback_days}봉 고점 {inPos(levels.trailing_high)} 대비 −{rule.trailing_drop_pct}%
              </Sub>
            </>
          }
          value={<Level main={inPos(levels.trailing_stop_price)} krw={krwPosition ? undefined : toKrw(levels.trailing_stop_price)} />}
        />
        <InfoRow
          label={
            <>
              다음 추매 가격
              <Sub>
                {levels.next_add_step !== null
                  ? `${levels.next_add_step}/${rule.add_max_steps}회차 · 평균단가 −${Number((rule.add_step_pct * levels.next_add_step).toFixed(2))}%`
                  : `완료 ${check.add_steps_done}회`}
                {rule.add_requires_above_ma_short && ` · ${rule.ma_short}일선 위에서만`}
              </Sub>
            </>
          }
          value={
            levels.add_price !== null ? (
              <Level main={inPos(levels.add_price)} krw={krwPosition ? undefined : toKrw(levels.add_price)} note={distancePhrase('다음 추매가', check.add_distance_pct)} />
            ) : (
              <span className="font-normal text-ink-2">{addPricePhrase(check)}</span>
            )
          }
        />
        <InfoRow
          label={`${rule.ma_short}일 · ${rule.ma_long}일 이동평균`}
          value={
            <>
              {levels.ma_short !== null ? inPos(levels.ma_short) : <span className="font-normal text-muted">봉 부족</span>}
              <span className="mx-1.5 text-muted">·</span>
              {levels.ma_long !== null ? inPos(levels.ma_long) : <span className="font-normal text-muted">봉 부족</span>}
            </>
          }
        />
        <InfoRow
          label={
            <>
              비중
              <Sub>목표 {levels.target_weight_pct !== null ? `${levels.target_weight_pct}%` : '설정 없음'}</Sub>
            </>
          }
          value={
            <>
              {check.weight_pct.toFixed(1)}%
              {check.weight_room_pt !== null && (
                <span className="ml-1.5 text-xs font-normal text-muted">상한까지 {check.weight_room_pt.toFixed(1)}%p</span>
              )}
            </>
          }
        />
        <InfoRow
          label="손절 시 손실"
          value={
            <>
              약 {riskKrw !== undefined ? formatKrwShort(riskKrw) : inPos(levels.risk_amount)}
              {check.risk_pct_equity !== null && (
                <span className="ml-1.5 text-xs font-normal text-muted">총자산의 {check.risk_pct_equity.toFixed(1)}%</span>
              )}
            </>
          }
        />
      </dl>

      <p className={`text-sm ${prob.available ? 'text-ink-2' : 'text-muted'}`}>{prob.text}</p>

      <div>
        <h3 className="text-sm font-semibold">발동한 조건</h3>
        {fired.length ? (
          <ul className="mt-1 space-y-1 text-sm">
            {fired.map((t) => (
              <li key={t.code}>
                <span className="font-medium">{t.label_ko}</span>
                <span className="num ml-1.5 text-ink-2">{t.detail}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-sm text-muted">없음</p>
        )}
        {(blocked || info.length > 0 || check.notes.length > 0 || check.history_error || data.kill_switch.tripped) && (
          <ul className="mt-2 space-y-1 text-xs text-muted">
            {blocked && <li className="text-ink-2">{blocked}</li>}
            {data.kill_switch.tripped && <li className="text-danger">킬스위치 발동 중: 추매 검토를 내지 않습니다 ({data.kill_switch.detail})</li>}
            {info.map((t) => (
              <li key={t.code}>
                <span className="font-medium text-ink-2">{t.label_ko}</span>
                <span className="num ml-1.5">{t.detail}</span>
              </li>
            ))}
            {check.notes.map((n) => <li key={n}>{n}</li>)}
            {check.history_error && <li className="text-danger">{check.history_error}</li>}
          </ul>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span className="num">
          확정 봉 기준 {check.as_of} · 봉 {check.bars}개
        </span>
        <Link to="/rules" className="font-medium text-accent hover:underline">
          규칙 바꾸기 →
        </Link>
      </div>
      <Footnote usdAtTodayRate={!krwPosition && fx !== undefined} />
    </div>
  )
}

function Sub({ children }: { children: ReactNode }) {
  return <span className="num block text-xs text-muted">{children}</span>
}

/** A level in the position currency, its won view in small print, and the distance under it. */
function Level({ main, krw, note }: { main: string; krw?: number; note?: string }) {
  return (
    <>
      {main}
      {krw !== undefined && <span className="ml-1.5 text-xs font-normal text-muted">{formatKrw(krw)}</span>}
      {note && <div className="text-xs font-normal text-ink-2">{note}</div>}
    </>
  )
}

/** `usdAtTodayRate`: the won figures beside a dollar position's levels and loss use today's rate. */
function Footnote({ usdAtTodayRate = false }: { usdAtTodayRate?: boolean }) {
  return (
    <p className="text-xs text-muted">
      {RULES_FOOTNOTE_KO}
      {usdAtTodayRate && ' 달러 종목의 원화 금액은 오늘 환율로 환산했습니다.'}
    </p>
  )
}
