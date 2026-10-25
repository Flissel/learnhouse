// @ts-expect-error Bun supplies this test module at runtime; the app omits Bun types.
import { afterEach, beforeEach, describe, expect, mock, test } from "bun:test"

mock.module("server-only", () => ({}))

const {
  LearningBootstrapError,
  bootstrapLocalLearningMode,
} = await import("./bootstrap")

const BOOTSTRAP_KEY = "test-only-local-bootstrap-key-32-characters"
const INTERNAL_API_URL = "http://learnhouse-api:9000/api/v1/"

describe("bootstrapLocalLearningMode", () => {
  beforeEach(() => {
    process.env.LEARNHOUSE_LOCAL_LEARNING_MODE = "true"
    process.env.LEARNHOUSE_LOCAL_BOOTSTRAP_KEY = BOOTSTRAP_KEY
    process.env.LEARNHOUSE_INTERNAL_API_URL = INTERNAL_API_URL
  })

  afterEach(() => {
    delete process.env.LEARNHOUSE_LOCAL_LEARNING_MODE
    delete process.env.LEARNHOUSE_LOCAL_BOOTSTRAP_KEY
    delete process.env.LEARNHOUSE_INTERNAL_API_URL
  })

  test("uses the server key to request provisioning readiness without browser credentials", async () => {
    const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = []
    const fetcher: typeof fetch = async (input, init) => {
      calls.push({ input, init })
      return new Response(
        JSON.stringify({
          status: "created",
          owner: { username: "admin" },
          organization: { name: "Default Organization", slug: "default" },
          locale: "en",
          permissions: ["admin"],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      )
    }

    const result = await bootstrapLocalLearningMode({ fetcher })

    expect(result).toEqual({
      status: "created",
      owner: { username: "admin" },
      organization: { name: "Default Organization", slug: "default" },
      locale: "en",
      permissions: ["admin"],
    })
    expect("authenticated" in result).toBeFalse()
    expect(JSON.stringify(result)).not.toContain(BOOTSTRAP_KEY)
    expect(JSON.stringify(result)).not.toContain(INTERNAL_API_URL)
    expect(calls).toHaveLength(1)
    expect(String(calls[0].input)).toBe(
      "http://learnhouse-api:9000/api/v1/learning/bootstrap",
    )
    expect(calls[0].init).toEqual({
      method: "POST",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "X-LearnHouse-Local-Bootstrap-Key": BOOTSTRAP_KEY,
      },
    })
    expect(calls[0].init?.credentials).toBeUndefined()
  })

  test("fails closed before fetch when mode, key, or internal URL is invalid", async () => {
    let calls = 0
    const fetcher: typeof fetch = async () => {
      calls += 1
      return new Response(null, { status: 204 })
    }

    const expectSafeConfigurationFailure = async (secretValue?: string) => {
      const operation = bootstrapLocalLearningMode({ fetcher })
      await expect(operation).rejects.toThrow(
        "Local learning bootstrap is not configured securely",
      )
      await operation.catch((error: unknown) => {
        if (secretValue) {
          expect(String(error)).not.toContain(secretValue)
        }
        expect(String(error)).not.toContain(BOOTSTRAP_KEY)
        expect(String(error)).not.toContain(INTERNAL_API_URL)
      })
    }

    delete process.env.LEARNHOUSE_LOCAL_LEARNING_MODE
    await expectSafeConfigurationFailure()

    process.env.LEARNHOUSE_LOCAL_LEARNING_MODE = "true"
    process.env.LEARNHOUSE_LOCAL_BOOTSTRAP_KEY = "too-short"
    await expectSafeConfigurationFailure("too-short")

    process.env.LEARNHOUSE_LOCAL_BOOTSTRAP_KEY = BOOTSTRAP_KEY
    delete process.env.LEARNHOUSE_INTERNAL_API_URL
    await expectSafeConfigurationFailure()

    const invalidInternalUrl = "ftp://learnhouse-api:9000/api/v1/"
    process.env.LEARNHOUSE_INTERNAL_API_URL = invalidInternalUrl
    await expectSafeConfigurationFailure(invalidInternalUrl)
    expect(calls).toBe(0)
  })

  test("rejects success payloads containing authentication or credential fields", async () => {
    const fetcher: typeof fetch = async () =>
      new Response(
        JSON.stringify({
          status: "created",
          owner: { username: "admin" },
          organization: { name: "Default Organization", slug: "default" },
          locale: "en",
          permissions: ["admin"],
          authenticated: true,
          password: "must-not-appear-in-errors",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      )

    const operation = bootstrapLocalLearningMode({ fetcher })

    await expect(operation).rejects.toThrow(
      "Invalid local learning bootstrap response",
    )
    await operation.catch((error: unknown) => {
      expect(String(error)).not.toContain("must-not-appear-in-errors")
      expect(String(error)).not.toContain(BOOTSTRAP_KEY)
      expect(String(error)).not.toContain(INTERNAL_API_URL)
    })
  })

  test("reports a safe status-only error for a rejected request", async () => {
    const fetcher: typeof fetch = async () =>
      new Response(
        JSON.stringify({
          detail: "Rejected",
          bootstrapKey: BOOTSTRAP_KEY,
        }),
        { status: 403, headers: { "content-type": "application/json" } },
      )

    const operation = bootstrapLocalLearningMode({ fetcher })

    await expect(operation).rejects.toEqual(new LearningBootstrapError(403))
    await operation.catch((error: unknown) => {
      expect(String(error)).not.toContain(BOOTSTRAP_KEY)
      expect(String(error)).not.toContain(INTERNAL_API_URL)
    })
  })

  test("wraps transport errors without exposing request headers", async () => {
    const fetcher: typeof fetch = async () => {
      throw new Error(`failed with ${BOOTSTRAP_KEY} at ${INTERNAL_API_URL}`)
    }

    const operation = bootstrapLocalLearningMode({ fetcher })

    await expect(operation).rejects.toThrow(
      "Local learning bootstrap request failed",
    )
    await operation.catch((error: unknown) => {
      expect(String(error)).not.toContain(BOOTSTRAP_KEY)
      expect(String(error)).not.toContain(INTERNAL_API_URL)
    })
  })

  test("rejects malformed success payloads", async () => {
    const fetcher: typeof fetch = async () =>
      new Response(JSON.stringify({ status: "created" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      })

    await expect(
      bootstrapLocalLearningMode({ fetcher }),
    ).rejects.toThrow("Invalid local learning bootstrap response")
  })
})
