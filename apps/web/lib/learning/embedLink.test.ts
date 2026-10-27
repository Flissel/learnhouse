import { describe, expect, test } from 'bun:test'
import { isSequencePlayer, withPersonToken } from './embedLink'

const ORIGIN = 'http://100.67.177.45:8090'

describe('embedLink', () => {
  test('only sequence player links are candidates for the person token', () => {
    expect(isSequencePlayer(`${ORIGIN}/lernsequenz/praes-1?k=abc`)).toBe(true)
    expect(isSequencePlayer('https://www.youtube.com/watch?v=x')).toBe(false)
    expect(isSequencePlayer('')).toBe(false)
  })

  test('the token is appended only for the trusted player origin, encoded', () => {
    expect(withPersonToken(`${ORIGIN}/lernsequenz/praes-1?k=abc`, 'pay.sig', ORIGIN)).toBe(
      `${ORIGIN}/lernsequenz/praes-1?k=abc&p=pay.sig`,
    )
    expect(withPersonToken(`${ORIGIN}/lernsequenz/praes-1`, 'a+b', ORIGIN)).toBe(`${ORIGIN}/lernsequenz/praes-1?p=a%2Bb`)
  })

  test('a look-alike link on another origin never gets the token', () => {
    // A course author could embed any URL; the token must not leak to it.
    expect(withPersonToken('https://evil.example/lernsequenz/praes-1?k=abc', 'pay.sig', ORIGIN)).toBe(
      'https://evil.example/lernsequenz/praes-1?k=abc',
    )
    expect(withPersonToken('http://100.67.177.45:8091/lernsequenz/x', 'pay.sig', ORIGIN)).toBe('http://100.67.177.45:8091/lernsequenz/x')
    expect(withPersonToken(`${ORIGIN}/anderes/lernsequenz/x`, 'pay.sig', ORIGIN)).toBe(`${ORIGIN}/anderes/lernsequenz/x`)
    expect(withPersonToken(`${ORIGIN}/lernsequenz/x`, 'pay.sig', null)).toBe(`${ORIGIN}/lernsequenz/x`)
    expect(withPersonToken('not a url', 'pay.sig', ORIGIN)).toBe('not a url')
  })

  test('no token leaves the link alone', () => {
    expect(withPersonToken(`${ORIGIN}/lernsequenz/praes-1?k=abc`, '', ORIGIN)).toBe(`${ORIGIN}/lernsequenz/praes-1?k=abc`)
  })
})
