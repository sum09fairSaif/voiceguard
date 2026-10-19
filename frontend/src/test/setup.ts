import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { clearToken } from "../api/session";

afterEach(() => {
  cleanup();
  // Clears both sessionStorage and the in-memory copy, so no test inherits a
  // signed-in session from the one before.
  clearToken();
});
