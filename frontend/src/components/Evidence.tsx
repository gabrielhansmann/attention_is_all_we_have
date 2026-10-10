import { LiveLibrary } from '../features/library/LiveLibrary'
import { EvidencePage } from '../features/evidence/EvidencePage'

export function Evidence() {
  return <>
    <div className="page-heading"><div><p className="eyebrow">EVIDENCE LIBRARY</p><h1>Every claim has a source.</h1><p>Browse loaded files, coverage and cited evidence from the database.</p></div></div>
    <section className="live-evidence"><div className="flex flex-col gap-10"><LiveLibrary /><EvidencePage /></div></section>
  </>
}
