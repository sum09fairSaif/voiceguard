import { describe, expect, it } from "vitest";
import { validateSignup } from "./signupValidation";

const VALID = { fullName: "Alex Morgan", email: "alex@example.com", password: "correct-horse" };

describe("validateSignup", () => {
  it("accepts a complete form", () => {
    expect(validateSignup(VALID)).toEqual({});
  });

  it("flags every empty field", () => {
    expect(validateSignup({ fullName: "", email: "", password: "" })).toEqual({
      fullName: "Enter your full name.",
      email: "Enter a valid email address.",
      password: "Use at least 8 characters.",
    });
  });

  it("treats a name of only spaces as empty", () => {
    expect(validateSignup({ ...VALID, fullName: "   " }).fullName).toBe("Enter your full name.");
  });

  it("refuses a name over 100 characters", () => {
    expect(validateSignup({ ...VALID, fullName: "a".repeat(101) }).fullName).toBe(
      "Full name must be 100 characters or fewer.",
    );
  });

  it.each(["alex", "alex@", "alex@example", "alex example@x.com"])("refuses the email %s", (email) => {
    expect(validateSignup({ ...VALID, email }).email).toBe("Enter a valid email address.");
  });

  it("refuses a 7-character password and accepts 8", () => {
    expect(validateSignup({ ...VALID, password: "1234567" }).password).toBeDefined();
    expect(validateSignup({ ...VALID, password: "12345678" }).password).toBeUndefined();
  });

  it("measures the password limit in bytes, like bcrypt", () => {
    // 24 three-byte characters = 72 bytes (allowed); 25 = 75 bytes (refused).
    expect(validateSignup({ ...VALID, password: "€".repeat(24) }).password).toBeUndefined();
    expect(validateSignup({ ...VALID, password: "€".repeat(25) }).password).toBe(
      "That password is too long. Try a shorter one.",
    );
  });
});
