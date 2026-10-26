import { useState, type DragEvent, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import type { AssetType, Currency, ImportPreview, ImportPreviewRow, ImportStatus } from '../api/client'
import {
  useCommitImport,
  useImportStatus,
  useManualImport,
  usePreviewScreenshots,
  useSupportedCrypto,
} from '../api/hooks'
import { Card, ErrorBox, Muted, SegmentedControl } from '../components/ui'
import { displaySymbol, formatKrw, formatQty, isoDate } from '../lib/format'

const MAX_FILES = 5

// Preview URLs are created when a file is added and revoked when it is removed, not in an
// effect: StrictMode re-runs effects and would revoke a URL that is still on screen.
type Picked = { file: File; url: string }

type EditableRow = {
  include: boolean
  name: string
  asset_type: AssetType
  symbol: string
  quantity: string
  currency: Currency
  price: string
  fx_rate: string
  source: ImportPreviewRow
}

function toEditable(r: ImportPreviewRow): EditableRow {
  // The screenshot (or the typed-in quantity) shows TOTAL holdings. For a symbol already held,
  // only the extra units are recorded (at the price that keeps the average cost equal to the
  // screenshot's), so a re-upload never double counts. Rows held in the same or a smaller
  // amount start unticked, and so does a row whose price the backend doubts (`warning`): the
  // user confirms it first.
  const delta = r.diff === 'different' && r.delta_quantity != null && r.delta_price != null
  return {
    include: r.status === 'ok' && (r.diff === 'new' || delta) && !r.warning,
    name: r.name,
    asset_type: r.asset_type,
    symbol: r.symbol ? displaySymbol(r.symbol) : '',
    quantity: String((delta ? r.delta_quantity : r.quantity) ?? ''),
    currency: r.currency,
    price: String((delta ? r.delta_price : r.avg_price) ?? ''),
    fx_rate: r.implied_fx != null ? String(r.implied_fx) : '',
    source: r,
  }
}

/**
 * Rows are keyed by the resolved symbol: adding a symbol again, or recognizing a screenshot that
 * shows one already typed in, replaces the earlier row instead of listing it twice. Rows whose
 * ticker could not be resolved have no key and are appended.
 */
function merge(prev: EditableRow[], added: EditableRow[]): EditableRow[] {
  const out = [...prev]
  for (const row of added) {
    const key = row.source.symbol
    const i = key ? out.findIndex((r) => r.source.symbol === key) : -1
    if (i >= 0) out[i] = row
    else out.push(row)
  }
  return out
}

export function Import() {
  const status = useImportStatus()
  const [files, setFiles] = useState<Picked[]>([])
  const preview = usePreviewScreenshots()
  const commit = useCommitImport()
  const [rows, setRows] = useState<EditableRow[]>([])
  const [today] = useState(() => isoDate(new Date()))
  const [tradeDate, setTradeDate] = useState(today)
  const [created, setCreated] = useState<number | null>(null)

  const addFiles = (list: FileList | null) => {
    if (!list) return
    const room = MAX_FILES - files.length
    const picked = Array.from(list)
      .filter((f) => f.type.startsWith('image/'))
      .slice(0, Math.max(room, 0))
      .map((file) => ({ file, url: URL.createObjectURL(file) }))
    setFiles((prev) => [...prev, ...picked])
  }

  const removeFile = (i: number) =>
    setFiles((prev) => {
      URL.revokeObjectURL(prev[i].url)
      return prev.filter((_, j) => j !== i)
    })

  const clearFiles = () =>
    setFiles((prev) => {
      prev.forEach((p) => URL.revokeObjectURL(p.url))
      return []
    })

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    addFiles(e.dataTransfer.files)
  }

  const recognize = () =>
    preview.mutate(files.map((p) => p.file), {
      onSuccess: (data: ImportPreview) => {
        // A new reading replaces the earlier screenshot rows; rows typed in by hand stay.
        setRows((prev) => merge(prev.filter((r) => r.source.origin === 'manual'), data.rows.map(toEditable)))
        setCreated(null)
      },
    })

  const addManual = (added: ImportPreviewRow[]) => {
    setRows((prev) => merge(prev, added.map(toEditable)))
    setCreated(null)
  }

  const update = (i: number, patch: Partial<EditableRow>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  const selected = rows.filter((r) => r.include)
  const submit = () =>
    commit.mutate(
      {
        trade_date: tradeDate,
        rows: selected.map((r) => ({
          asset_type: r.asset_type,
          symbol: r.symbol,
          quantity: r.quantity,
          currency: r.currency,
          price: r.price,
          fx_rate: r.currency === 'KRW' ? null : r.fx_rate || null,
        })),
      },
      {
        onSuccess: (res) => {
          setCreated(res.created)
          setRows([])
          clearFiles()
        },
      },
    )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">보유 종목 가져오기</h1>
        <p className="mt-1 text-sm text-ink-2">
          증권사·거래소 앱의 해외주식/코인 잔고 화면을 캡처해 올리거나, 종목과 수량을 직접 입력하세요. 두 방법
          모두 아래 확인 표에 모이고, 고친 뒤 한 번에 가져옵니다. 토스증권처럼 평균단가가 없는 화면은 평가금액과
          평가손익으로 단가를 계산하고, 직접 입력에서 평균단가를 비우면 현재가로 채웁니다. 매수일은 화면에 없으니
          아래 날짜를 실제 매수일로 바꿔 주세요.
        </p>
      </div>

      {created !== null && (
        <div className="rounded-lg border border-line bg-surface px-4 py-3 text-sm">
          {created}개 종목을 가져왔습니다.{' '}
          <Link to="/" className="text-accent underline">홈</Link>에서 확인하거나{' '}
          <Link to="/projection" className="text-accent underline">장기 시뮬레이션</Link>을 돌려 보세요.
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="1. 스크린샷 선택">
          {status.data && !status.data.configured ? (
            <SetupNeeded status={status.data} />
          ) : (
            <>
              <label
                onDragOver={(e) => e.preventDefault()}
                onDrop={onDrop}
                className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-line px-6 py-10 text-center hover:bg-hover focus-within:ring-2 focus-within:ring-accent"
              >
                <span className="text-sm font-medium">이미지를 끌어다 놓거나 클릭해서 선택</span>
                <span className="mt-1 text-xs text-muted">PNG·JPEG, 한 번에 최대 {MAX_FILES}장, 장당 10MB 이하</span>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  className="sr-only"
                  onChange={(e) => {
                    addFiles(e.target.files)
                    e.target.value = ''
                  }}
                />
              </label>

              {files.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-3">
                  {files.map((p, i) => (
                    <Thumbnail key={p.url} name={p.file.name} url={p.url} onRemove={() => removeFile(i)} />
                  ))}
                </div>
              )}

              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  disabled={files.length === 0 || preview.isPending}
                  onClick={recognize}
                  className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface disabled:opacity-50"
                >
                  {preview.isPending ? '읽는 중… (처음엔 30초 정도)' : '보유 종목 읽기'}
                </button>
                <span className="text-xs text-muted">
                  {status.data?.engine === 'claude'
                    ? '이미지는 인식을 위해 Anthropic API로 전송되며 이 앱에 저장되지 않습니다.'
                    : status.data?.engine === 'ollama'
                      ? `내 PC의 AI(${status.data.model})가 읽습니다. 이미지는 컴퓨터 밖으로 나가지 않습니다.`
                      : '데모 모드: 실제 이미지를 읽지 않고 예시 결과를 보여줍니다.'}
                </span>
              </div>
              {preview.error && (
                <div className="mt-3">
                  <ErrorBox error={preview.error} />
                </div>
              )}
            </>
          )}
        </Card>

        <Card title="또는 직접 입력">
          <ManualEntry onAdd={addManual} />
        </Card>
      </div>

      {preview.data && rows.length === 0 && created === null && !preview.isPending && (
        <Card>
          <Muted>보유 종목을 찾지 못했습니다. 잔고 화면이 잘 보이게 다시 캡처하거나 직접 입력해 주세요.</Muted>
        </Card>
      )}

      {rows.length > 0 && (
        <Card
          title={`2. 확인 및 수정${preview.data?.broker ? ` · ${preview.data.broker}` : ''}`}
        >
          <div className="-mx-5 overflow-x-auto">
            <table className="num w-full min-w-[880px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="px-5 py-2 font-medium">가져오기</th>
                  <th className="px-3 py-2 font-medium">이름</th>
                  <th className="px-3 py-2 font-medium">티커</th>
                  <th className="px-3 py-2 font-medium">수량</th>
                  <th className="px-3 py-2 font-medium">평균단가</th>
                  <th className="px-3 py-2 font-medium">매입 환율</th>
                  <th className="px-5 py-2 font-medium">상태</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-b border-line align-top last:border-0">
                    <td className="px-5 py-2">
                      <input
                        type="checkbox"
                        aria-label={`${r.name} 가져오기`}
                        checked={r.include}
                        onChange={(e) => update(i, { include: e.target.checked })}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <div>{r.name}</div>
                      <div className="text-xs text-muted">
                        {r.asset_type === 'crypto' ? '코인' : '주식'}
                        {r.source.origin === 'manual' && ' · 직접 입력'}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <CellInput value={r.symbol} onChange={(v) => update(i, { symbol: v.toUpperCase() })} width="w-24" />
                      {r.source.ticker_guessed && r.source.symbol && (
                        <div className="mt-1 text-[11px] text-muted">이름으로 추정 · 확인 필요</div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <CellInput value={r.quantity} onChange={(v) => update(i, { quantity: v })} />
                    </td>
                    <td className="px-3 py-2">
                      <CellInput value={r.price} onChange={(v) => update(i, { price: v })} />
                      <div className="mt-1 text-[11px] text-muted">{r.currency}</div>
                      {r.source.price_estimated && (
                        // The backend says how it got the price (market value - P&L, cost / rate,
                        // the current price for a typed-in row without one, ...).
                        <div className="mt-1 max-w-56 text-[11px] text-muted">
                          {r.source.message ?? '원화 매입금액÷오늘 환율로 추정'}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {r.currency === 'KRW' ? (
                        <span className="text-xs text-muted">원화 거래</span>
                      ) : (
                        <CellInput value={r.fx_rate} onChange={(v) => update(i, { fx_rate: v })} placeholder="자동" />
                      )}
                      {r.source.cost_krw != null && (
                        <div className="mt-1 text-[11px] text-muted">매입 {formatKrw(r.source.cost_krw)}</div>
                      )}
                    </td>
                    <td className="px-5 py-2 text-xs">
                      <RowStatus row={r.source} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex flex-wrap items-end gap-4">
            <label className="block">
              <span className="mb-1 block text-xs text-muted">매수일로 기록할 날짜</span>
              <input
                type="date"
                max={today}
                value={tradeDate}
                onChange={(e) => setTradeDate(e.target.value)}
                className="rounded-lg border border-line bg-surface px-3 py-2 text-sm"
              />
            </label>
            <button
              type="button"
              disabled={selected.length === 0 || commit.isPending}
              onClick={submit}
              className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface disabled:opacity-50"
            >
              {selected.length}개 종목 가져오기
            </button>
          </div>
          <p className="mt-2 text-xs text-muted">
            스크린샷과 직접 입력에는 매수일이 없어 위 날짜가 모든 종목의 매수일로 기록됩니다. 실제 매수일로 바꿔야
            자산 추이가 그려집니다(모르면 오늘로 두고 나중에 거래 내역에서 고치세요). 매입 환율이 있으면 원화
            원금은 그 환율로, 없으면 위 날짜의 환율로 계산합니다. 가져온 내용은 거래 내역에서 수정·삭제할 수
            있습니다.
          </p>
          {commit.error && (
            <div className="mt-3">
              <ErrorBox error={commit.error} />
            </div>
          )}
        </Card>
      )}
    </div>
  )
}

type ManualState = {
  asset_type: AssetType
  symbol: string
  quantity: string
  price: string
  currency: Currency
}

const emptyManual = (): ManualState => ({
  asset_type: 'stock',
  symbol: '',
  quantity: '',
  price: '',
  currency: 'USD',
})

const inputClass =
  'w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent'

/**
 * Type a holding in instead of photographing it. The backend turns it into the same preview
 * row a screenshot would give (ticker check, difference from current holdings, price doubts),
 * filling a missing average price with the current one, and the row joins the review table.
 */
function ManualEntry({ onAdd }: { onAdd: (rows: ImportPreviewRow[]) => void }) {
  const crypto = useSupportedCrypto()
  const manual = useManualImport()
  const [form, setForm] = useState<ManualState>(emptyManual)
  const set = <K extends keyof ManualState>(key: K, value: ManualState[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const submit = (e: FormEvent) => {
    e.preventDefault()
    // Numbers stay strings so the backend parses them as exact decimals.
    manual.mutate(
      {
        rows: [
          {
            asset_type: form.asset_type,
            symbol: form.symbol.trim(),
            quantity: form.quantity.trim(),
            avg_price: form.price.trim() || null,
            currency: form.currency,
          },
        ],
      },
      {
        onSuccess: (data) => {
          onAdd(data.rows)
          // Keep the asset type and currency for the next entry; clear the rest.
          setForm((f) => ({ ...emptyManual(), asset_type: f.asset_type, currency: f.currency }))
        },
      },
    )
  }

  const isCrypto = form.asset_type === 'crypto'
  return (
    <form onSubmit={submit} className="space-y-4">
      <p className="text-sm text-ink-2">
        스크린샷 없이 종목과 수량만 적어도 같은 확인 표에 올라갑니다. 평균단가를 비우면 현재가로 채우고 그렇게
        표시합니다.
      </p>
      <div className="flex flex-wrap gap-3">
        <SegmentedControl
          label="자산 종류"
          value={form.asset_type}
          // Coins default to won (bought on Upbit/Bithumb); stocks are always USD.
          onChange={(v) =>
            setForm((f) => ({ ...f, asset_type: v, symbol: '', currency: v === 'crypto' ? 'KRW' : 'USD' }))
          }
          options={[
            { value: 'stock', label: '주식' },
            { value: 'crypto', label: '코인' },
          ]}
        />
        {isCrypto && (
          <SegmentedControl
            label="거래 통화"
            value={form.currency}
            onChange={(v) => set('currency', v)}
            options={[
              { value: 'KRW', label: '원화 (업비트·빗썸)' },
              { value: 'USD', label: '달러 (해외 거래소)' },
            ]}
          />
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label={isCrypto ? '코인' : '티커'}>
          {isCrypto ? (
            <select
              required
              className={inputClass}
              value={form.symbol}
              onChange={(e) => set('symbol', e.target.value)}
            >
              <option value="">선택</option>
              {crypto.data?.map((c) => (
                <option key={c.symbol} value={c.symbol}>
                  {displaySymbol(c.symbol)} · {c.name}
                </option>
              ))}
            </select>
          ) : (
            <input
              required
              className={`${inputClass} uppercase`}
              placeholder="AAPL"
              value={form.symbol}
              onChange={(e) => set('symbol', e.target.value.toUpperCase())}
            />
          )}
        </Field>
        <Field label="수량">
          <input
            required
            inputMode="decimal"
            className={`${inputClass} num`}
            placeholder={isCrypto ? '0.05' : '10'}
            value={form.quantity}
            onChange={(e) => set('quantity', e.target.value)}
          />
        </Field>
        <Field label={`평균단가 (${form.currency}, 선택)`}>
          <input
            inputMode="decimal"
            className={`${inputClass} num`}
            placeholder="비우면 현재가"
            value={form.price}
            onChange={(e) => set('price', e.target.value)}
          />
        </Field>
      </div>
      {!isCrypto && <p className="text-xs text-muted">주식은 달러(USD)로 기록합니다.</p>}
      {manual.error && <ErrorBox error={manual.error} />}
      <button
        type="submit"
        disabled={manual.isPending}
        className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface disabled:opacity-50"
      >
        {manual.isPending ? '확인 중…' : '목록에 추가'}
      </button>
    </form>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted">{label}</span>
      {children}
    </label>
  )
}

/** The screenshot reader is not configured: say how to set it up. Typing holdings in still works. */
function SetupNeeded({ status }: { status: ImportStatus }) {
  const ollama = status.engine === 'ollama'
  return (
    <div className="space-y-2 text-sm text-ink-2">
      <p className="font-medium text-ink">스크린샷 읽기 준비 필요</p>
      <p>{status.problem}</p>
      {ollama ? (
        <ol className="list-decimal space-y-1 pl-5">
          <li>시작 메뉴에서 Ollama 앱을 실행합니다(무료, 내 PC에서 동작).</li>
          <li>
            처음 한 번은 터미널에서{' '}
            <code className="rounded bg-hover px-1">ollama pull {status.model}</code>을 실행해 모델을
            받습니다(약 6GB).
          </li>
          <li>이 페이지를 새로고침합니다.</li>
        </ol>
      ) : (
        <ol className="list-decimal space-y-1 pl-5">
          <li>
            <code className="rounded bg-hover px-1">backend/.env</code>의{' '}
            <code className="rounded bg-hover px-1">AM_ANTHROPIC_API_KEY=</code> 뒤에 키를 붙여넣습니다.
          </li>
          <li>백엔드 서버를 다시 시작합니다.</li>
        </ol>
      )}
      <p className="text-xs text-muted">그동안은 오른쪽의 직접 입력으로 종목을 넣을 수 있습니다.</p>
    </div>
  )
}

function RowStatus({ row }: { row: ImportPreviewRow }) {
  if (row.status !== 'ok') return <span className="text-danger">{row.message}</span>
  // `ok` rows can still carry a doubt (`warning`: two readings disagree) or a note (`message`:
  // how the price was derived). The derivation note sits by the price when it was estimated.
  const confidence = (
    <>
      {row.warning && <div className="max-w-72 text-danger">확인 필요: {row.warning}</div>}
      {row.message && !row.price_estimated && <div className="max-w-72 text-ink-2">{row.message}</div>}
      {row.confidence === 'low' && <div className="text-muted">인식 불확실 · 값을 확인하세요</div>}
    </>
  )
  if (row.diff === 'same')
    return (
      <>
        <span className="text-ink-2">이미 같은 수량 보유</span>
        {confidence}
      </>
    )
  if (row.diff === 'different')
    return (
      <>
        <span className="text-ink-2">
          {row.delta_quantity != null && row.delta_price != null
            ? `현재 ${formatQty(row.current_quantity ?? 0)} → 입력 ${formatQty(row.quantity ?? 0)}: 차이 ${formatQty(row.delta_quantity)}만 매수로 기록`
            : (row.quantity ?? 0) > (row.current_quantity ?? 0)
              ? `현재 ${formatQty(row.current_quantity ?? 0)} 보유. 늘어난 수량의 매입가를 계산할 수 없어 자동 기록하지 않습니다. 거래 내역에서 직접 입력하세요`
              : `입력 수량이 현재(${formatQty(row.current_quantity ?? 0)})보다 적습니다. 매도는 거래 내역에서 직접 기록하세요`}
        </span>
        {confidence}
      </>
    )
  return (
    <>
      <span className="text-ink">신규</span>
      {confidence}
    </>
  )
}

function CellInput({ value, onChange, width = 'w-28', placeholder }: {
  value: string
  onChange: (v: string) => void
  width?: string
  placeholder?: string
}) {
  return (
    <input
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className={`${width} rounded-md border border-line bg-surface px-2 py-1 text-sm outline-none focus:border-accent`}
    />
  )
}

function Thumbnail({ name, url, onRemove }: { name: string; url: string; onRemove: () => void }) {
  return (
    <div className="relative">
      <img src={url} alt={name} className="h-28 w-20 rounded-lg border border-line object-cover" />
      <button
        type="button"
        aria-label={`${name} 제거`}
        onClick={onRemove}
        className="absolute -top-2 -right-2 size-6 rounded-full border border-line bg-surface text-xs"
      >
        ✕
      </button>
    </div>
  )
}
