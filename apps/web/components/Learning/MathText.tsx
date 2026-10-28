import { Component, type ReactNode } from 'react'
import { BlockMath, InlineMath } from 'react-katex'
import 'katex/dist/katex.min.css'

import { splitMath, type MathPart } from './mathSplit'

/** Shows the raw source when KaTeX cannot set a formula. */
class Fallback extends Component<{ raw: string; children: ReactNode }, { failed: boolean; raw: string }> {
  state = { failed: false, raw: this.props.raw }
  static getDerivedStateFromProps(props: { raw: string }, state: { failed: boolean; raw: string }) {
    return props.raw === state.raw ? null : { failed: false, raw: props.raw }
  }
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

/** With `math`, $…$ / $$…$$ formulas are set by KaTeX; without it (e.g. Terminal course) the text stays plain. */
export default function MathText({ text, math }: { text: string; math?: boolean }) {
  if (!math) return <>{text}</>
  return (
    <>
      {splitMath(text).map((part, index) => <Part key={index} part={part} />)}
    </>
  )
}
