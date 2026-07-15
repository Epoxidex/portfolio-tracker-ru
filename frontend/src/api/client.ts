export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type ApiFailure = {
  detail?: string;
  error?: string;
  ok?: false;
};

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    cache: "no-store",
    ...options,
    headers: {
      Accept: "application/json",
      ...options.headers,
    },
  });
  const contentType = response.headers.get("content-type") ?? "";
  const payload: unknown = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const failure = typeof payload === "object" && payload !== null
      ? payload as ApiFailure
      : null;
    const message = failure?.detail
      ?? failure?.error
      ?? (typeof payload === "string" && payload.trim()
        ? payload
        : `${response.status} ${response.statusText}`);
    throw new ApiError(message, response.status);
  }

  if (typeof payload === "object" && payload !== null) {
    const failure = payload as ApiFailure;
    if (failure.ok === false) {
      throw new ApiError(failure.error ?? "Операция не выполнена", response.status);
    }
  }

  return payload as T;
}
