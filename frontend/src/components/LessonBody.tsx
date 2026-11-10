import { Fragment } from 'react'
import { Link } from 'react-router-dom'

import type { LessonSection } from '../api/client'
import { refMarkers, SECTION_KIND_LABELS_KO } from '../lib/learn'

/** Body text with `[n]` footnotes turned into links to the reference list. */
export function Footnoted({ text }: { text: string }) {
  return (
    <>
      {refMarkers(text).map((m, i) =>
        'ref' in m ? (
          <a key={i} href={`#ref-${m.ref}`} className="num text-accent hover:underline" aria-label={`참고 자료 ${m.ref}`}>
            [{m.ref}]
          </a>
        ) : (
          <Fragment key={i}>{m.text}</Fragment>
        ),
      )}
    </>
  )
}

/**
 * A lesson's sections: heading with its kind chip (사실 / 일반 원칙 / 이 앱에서는), paragraphs,
 * bullets, a callout, and for an app section the link to the screen it talks about. Structured
 * JSX, no markdown library (D-034). Nothing here is coloured as a gain or a loss.
 */
export function LessonBody({ sections }: { sections: LessonSection[] }) {
  return (
    <div className="space-y-6">
      {sections.map((s) => (
        <section key={s.heading_ko} className="rounded-2xl bg-surface p-6">
          <header className="mb-3 flex flex-wrap items-center gap-2">
            <h2 className="text-[17px] font-bold text-ink">{s.heading_ko}</h2>
            <span className="rounded-md bg-fill px-2 py-0.5 text-xs font-semibold text-ink-2">
              {SECTION_KIND_LABELS_KO[s.kind] ?? s.kind}
            </span>
          </header>
          <div className="space-y-3 text-[15px] leading-relaxed text-ink">
            {s.paragraphs.map((p) => (
              <p key={p}>
                <Footnoted text={p} />
              </p>
            ))}
            {s.bullets && s.bullets.length > 0 && (
              <ul className="list-disc space-y-1 pl-5">
                {s.bullets.map((b) => (
                  <li key={b}>
                    <Footnoted text={b} />
                  </li>
                ))}
              </ul>
            )}
            {s.callout_ko && (
              <p className="rounded-lg bg-fill px-4 py-3 text-sm">
                <Footnoted text={s.callout_ko} />
              </p>
            )}
            {s.route && (
              <Link to={s.route} className="inline-block text-sm font-semibold text-accent hover:underline">
                화면 보기 →
              </Link>
            )}
          </div>
        </section>
      ))}
    </div>
  )
}
