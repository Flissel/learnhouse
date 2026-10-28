import { Component, type ReactNode } from 'react'
import { BlockMath, InlineMath } from 'react-katex'
import 'katex/dist/katex.min.css'

import { splitMath, type MathPart } from './mathSplit'

export { splitMath }

/** Shows the raw source when KaTeX cannot set a formula. */
class Fallback extends Component<{ raw: string; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.raw : this.props.children
  }
}

function Part({ part }: { part: MathPart }) {
  if (part.kind === 'text') return <>{part.value}</>
  const raw = part.kind === 'block' ? `$$${part.value}$$` : `$${part.value}$`
  return (
    <Fallback raw={raw}>
      {part.kind === 'block'
        ? <BlockMath errorColor="#b91c1c" math={part.value} renderError={() => <>{raw}</>} />
        : <InlineMath errorColor="#b91c1c" math={part.value} renderError={() => <>{raw}</>} />}
    </Fallback>
  )
}

/** Text with $…$ / $$…$$ formulas set by KaTeX; everything else stays plain text. */
export default function MathText({ text }: { text: string }) {
  return (
    <>
      {splitMath(text).map((part, index) => <Part key={index} part={part} />)}
    </>
  )
}
