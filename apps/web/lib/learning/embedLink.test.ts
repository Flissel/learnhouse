import { describe, expect, test } from 'bun:test'
import { isSequencePlayer, withPersonToken } from './embedLink'

describe('embedLink', () => {
  test('only sequence player links get the person token', () => {
    expect(isSequencePlayer('http://100.67.177.45:8090/lernsequenz/praes-1?k=abc')).toBe(true)
    expect(isSequencePlayer('https://www.youtube.com/watch?v=x')).toBe(false)
    expect(isSequencePlayer('')).toBe(false)
  })

  test('the token is appended after the existing query, encoded', () => {
    expect(withPersonToken('http://h:8090/lernsequenz/praes-1?k=abc', 'pay.sig')).toBe(
      'http://h:8090/lernsequenz/praes-1?k=abc&p=pay.sig',
    )
    expect(withPersonToken('http://h:8090/lernsequenz/praes-1', 'a+b')).toBe('http://h:8090/lernsequenz/praes-1?p=a%2Bb')
  })

  test('no token or a foreign link leaves the link alone', () => {
    expect(withPersonToken('http://h:8090/lernsequenz/praes-1?k=abc', '')).toBe('http://h:8090/lernsequenz/praes-1?k=abc')
    expect(withPersonToken('https://www.youtube.com/watch?v=x', 'pay.sig')).toBe('https://www.youtube.com/watch?v=x')
  })
})
