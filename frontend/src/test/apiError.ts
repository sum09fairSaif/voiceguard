import { AxiosError, AxiosHeaders, type AxiosResponse } from "axios";

// Builds the error axios throws when the server answers with an error status.
export function apiError(status: number, data: unknown = {}, headers: Record<string, string> = {}) {
  const config = { headers: new AxiosHeaders() };
  const response: AxiosResponse = { status, statusText: "", data, headers, config };
  return new AxiosError("Request failed", "ERR_BAD_RESPONSE", config, {}, response);
}

// Builds the error axios throws when no response arrives (offline or timed out).
export function networkError() {
  return new AxiosError("Network Error", "ERR_NETWORK", { headers: new AxiosHeaders() }, {});
}
