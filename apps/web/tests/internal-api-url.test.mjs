import { afterEach, describe, expect, test } from 'bun:test'

import { getServerAPIUrl } from '../services/config/config.ts'

const originalInternalUrl = process.env.LEARNHOUSE_INTERNAL_API_URL

afterEach(() => {
  if (originalInternalUrl === undefined) {
    delete process.env.LEARNHOUSE_INTERNAL_API_URL
  } else {
    process.env.LEARNHOUSE_INTERNAL_API_URL = originalInternalUrl
  }
})

describe('server API URL resolution', () => {
  test('prefers the private Docker service URL for server-side requests', () => {
    process.env.LEARNHOUSE_INTERNAL_API_URL = 'http://learnhouse-api:9000/api/v1/'

    expect(getServerAPIUrl()).toBe('http://learnhouse-api:9000/api/v1/')
  })

  test('normalizes a configured private URL to one trailing slash', () => {
    process.env.LEARNHOUSE_INTERNAL_API_URL = 'http://learnhouse-api:9000/api/v1'

    expect(getServerAPIUrl()).toBe('http://learnhouse-api:9000/api/v1/')
  })
})
