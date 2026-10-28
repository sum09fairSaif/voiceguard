import { describe, expect, it } from "vitest";
import { validateSignIn } from "./signInValidation";

describe("validateSignIn", () => {
  it("accepts an email and any non-empty password", () => {
    expect(validateSignIn({ email: " sam@example.com ", password: "x" })).toEqual({});
  });

  it("asks for a valid email", () => {
    expect(validateSignIn({ email: "sam@", password: "x" }).email).toBe("Enter a valid email address.");
  });

  it("asks for a password without applying the signup rules", () => {
    expect(validateSignIn({ email: "sam@example.com", password: "" }).password).toBe("Enter your password.");
    expect(validateSignIn({ email: "sam@example.com", password: "short" }).password).toBeUndefined();
  });
});
