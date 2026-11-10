'use client'

import { use } from 'react'
import Einladung from '@components/Learning/Einladung'

interface EinladungPageProps {
  params: Promise<{ token: string }>
}

export default function EinladungPage(props: EinladungPageProps) {
  const { token } = use(props.params)
  return <Einladung token={token} />
}
