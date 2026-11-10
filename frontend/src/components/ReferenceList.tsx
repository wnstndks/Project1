import type { LessonReference } from '../api/client'

const LANG_KO: Record<string, string> = { ko: '한국어', en: '영어' }

/**
 * A lesson's outside sources, numbered the way the body cites them (`[n]` → `#ref-n`). Links
 * open in a new tab and say so for screen readers; publisher, language and the month the
 * author last checked the page are printed so the reader can judge the source.
 */
export function ReferenceList({ references }: { references: LessonReference[] }) {
  return (
    <ol className="space-y-3 text-sm">
      {references.map((r, i) => (
        <li key={r.url} id={`ref-${i + 1}`} className="flex gap-2">
          <span className="num shrink-0 text-muted">[{i + 1}]</span>
          <div className="min-w-0">
            <a
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
              aria-label={`${r.title} 원문 (새 탭)`}
            >
              {r.title}
            </a>
            <div className="num mt-0.5 text-xs text-ink-2">
              {r.publisher} · {LANG_KO[r.lang] ?? r.lang} · {r.accessed} 확인
            </div>
            {r.note_ko && <div className="mt-0.5 text-xs text-muted">{r.note_ko}</div>}
          </div>
        </li>
      ))}
    </ol>
  )
}
