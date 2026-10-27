'use client'

import { use } from 'react'
import NotesShell from '@components/Learning/NotesShell'

interface NotesPageProps {
  params: Promise<{ orgslug: string }>
}

export default function NotesPage(props: NotesPageProps) {
  const { orgslug } = use(props.params)
  return <NotesShell orgslug={orgslug} />
}
