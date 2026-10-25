import "server-only"

const BOOTSTRAP_HEADER = "X-LearnHouse-Local-Bootstrap-Key"
const BOOTSTRAP_KEY_MIN_LENGTH = 32
const CONFIGURATION_ERROR =
  "Local learning bootstrap is not configured securely"

export interface LocalLearningBootstrap {
  status: "created" | "ready"
  owner: {
    username: string
  }
  organization: {
    name: string
    slug: string
  }
  locale: string
  permissions: string[]
}

export class LearningBootstrapError extends Error {
  readonly status: number

  constructor(status: number) {
    super(`Local learning bootstrap failed (${status})`)
    this.name = "LearningBootstrapError"
    this.status = status
  }
}

interface BootstrapOptions {
  fetcher?: typeof fetch
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const actual = Object.keys(value)
  return (
    actual.length === expected.length &&
    expected.every((key) => Object.prototype.hasOwnProperty.call(value, key))
  )
}

function parseBootstrapResponse(value: unknown): LocalLearningBootstrap {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "status",
      "owner",
      "organization",
      "locale",
      "permissions",
    ]) ||
    (value.status !== "created" && value.status !== "ready")
  ) {
    throw new Error("Invalid local learning bootstrap response")
  }
  const owner = value.owner
  const organization = value.organization
  const permissions = value.permissions
  if (
    !isRecord(owner) ||
    !hasExactKeys(owner, ["username"]) ||
    typeof owner.username !== "string" ||
    !isRecord(organization) ||
    !hasExactKeys(organization, ["name", "slug"]) ||
    typeof organization.name !== "string" ||
    typeof organization.slug !== "string" ||
    typeof value.locale !== "string" ||
    !Array.isArray(permissions) ||
    !permissions.every((permission) => typeof permission === "string")
  ) {
    throw new Error("Invalid local learning bootstrap response")
  }

  return {
    status: value.status,
    owner: { username: owner.username },
    organization: {
      name: organization.name,
      slug: organization.slug,
    },
    locale: value.locale,
    permissions: [...permissions],
  }
}

function getBootstrapConfiguration(): {
  endpoint: string
  key: string
} {
  const enabled =
    process.env.LEARNHOUSE_LOCAL_LEARNING_MODE?.trim().toLowerCase() === "true"
  const key = process.env.LEARNHOUSE_LOCAL_BOOTSTRAP_KEY ?? ""
  if (!enabled || key.length < BOOTSTRAP_KEY_MIN_LENGTH) {
    throw new Error(CONFIGURATION_ERROR)
  }

  const configuredUrl = process.env.LEARNHOUSE_INTERNAL_API_URL ?? ""
  let internalApiUrl: URL
  try {
    internalApiUrl = new URL(configuredUrl)
  } catch {
    throw new Error(CONFIGURATION_ERROR)
  }
  if (
    (internalApiUrl.protocol !== "http:" &&
      internalApiUrl.protocol !== "https:") ||
    internalApiUrl.username !== "" ||
    internalApiUrl.password !== "" ||
    internalApiUrl.search !== "" ||
    internalApiUrl.hash !== "" ||
    !internalApiUrl.pathname.endsWith("/api/v1/")
  ) {
    throw new Error(CONFIGURATION_ERROR)
  }

  return {
    endpoint: new URL("learning/bootstrap", internalApiUrl).toString(),
    key,
  }
}

export async function bootstrapLocalLearningMode(
  options: BootstrapOptions = {},
): Promise<LocalLearningBootstrap> {
  const { endpoint, key } = getBootstrapConfiguration()
  const fetcher = options.fetcher ?? fetch
  let response: Response
  try {
    response = await fetcher(endpoint, {
      method: "POST",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        [BOOTSTRAP_HEADER]: key,
      },
    })
  } catch {
    throw new Error("Local learning bootstrap request failed")
  }

  if (!response.ok) {
    throw new LearningBootstrapError(response.status)
  }

  try {
    return parseBootstrapResponse(await response.json())
  } catch {
    throw new Error("Invalid local learning bootstrap response")
  }
}
