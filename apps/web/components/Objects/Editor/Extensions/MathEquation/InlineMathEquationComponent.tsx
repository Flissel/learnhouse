import { NodeViewWrapper } from '@tiptap/react'
import React, { lazy, Suspense } from 'react'
import { useEditorProvider } from '@components/Contexts/Editor/EditorContext'

const InlineMath = lazy(() => {
  // Load katex CSS when the component is first used
  import('katex/dist/katex.min.css')
  return import('react-katex').then(m => ({ default: m.InlineMath }))
})

function InlineMathEquationComponent(props: any) {
  const equation: string = props.node.attrs.math_equation
  const editorState = useEditorProvider() as any
  const isEditable = editorState?.isEditable

  const edit = () => {
    if (!isEditable) return
    const next = window.prompt('LaTeX', equation)
    if (next !== null) {
      props.updateAttributes({ math_equation: next })
    }
  }

  // Math notation is left-to-right by specification, in every language.
  return (
    <NodeViewWrapper as="span" className="inline-math-equation" dir="ltr">
      <span onDoubleClick={edit} className={isEditable ? 'cursor-pointer' : undefined}>
        <Suspense fallback={<span className="text-gray-400">{equation}</span>}>
          <InlineMath>{equation}</InlineMath>
        </Suspense>
      </span>
    </NodeViewWrapper>
  )
}

export default InlineMathEquationComponent
