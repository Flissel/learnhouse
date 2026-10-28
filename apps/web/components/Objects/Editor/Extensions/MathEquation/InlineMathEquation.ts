import { mergeAttributes, Node } from '@tiptap/core'
import { ReactNodeViewRenderer } from '@tiptap/react'
import dynamic from 'next/dynamic'

const InlineMathEquationComponent = dynamic(
  () => import('./InlineMathEquationComponent'),
  { ssr: false }
)

// A formula inside a sentence ($...$ in the lesson text); the block variant is blockMathEquation.
export default Node.create({
  name: 'inlineMathEquation',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      math_equation: {
        default: '',
      },
    }
  },

  parseHTML() {
    return [
      {
        tag: 'inline-math-equation',
      },
    ]
  },

  renderHTML({ HTMLAttributes }) {
    return ['inline-math-equation', mergeAttributes(HTMLAttributes)]
  },

  addNodeView() {
    return ReactNodeViewRenderer(InlineMathEquationComponent as any)
  },
})
