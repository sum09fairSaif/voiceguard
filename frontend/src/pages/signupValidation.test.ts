import { describe, expect, it } from "vitest";
import { PASSWORD_PROBLEMS, passwordStrength, validateSignup } from "./signupValidation";

const VALID = { fullName: "Alex Morgan", email: "alex@example.com", password: "correct-horse-battery" };

describe("validateSignup", () => {
  it("accepts a complete form", () => {
    expect(validateSignup(VALID)).toEqual({});
  });

  it("flags every empty field", () => {
    expect(validateSignup({ fullName: "", email: "", password: "" })).toEqual({
      fullName: "Enter your full name.",
      email: "Enter a valid email address.",
      password: "Use at least 15 characters.",
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

  it("refuses a 14-character password and accepts 15", () => {
    expect(validateSignup({ ...VALID, password: "a-good-pass-14" }).password).toBeDefined();
    expect(validateSignup({ ...VALID, password: "a-good-pass-15!" }).password).toBeUndefined();
  });

  it("measures the password limit in bytes, like bcrypt", () => {
    // 24 three-byte characters = 72 bytes (allowed); 25 = 75 bytes (refused).
    expect(validateSignup({ ...VALID, password: "€".repeat(24) }).password).toBeUndefined();
    expect(validateSignup({ ...VALID, password: "€".repeat(25) }).password).toBe(
      "That password is too long. Try a shorter one.",
    );
  });
});


describe("passwordStrength", () => {
  it.each([
    ["", 0, ""],
    ["lantern", 0, "8 more characters"],
    ["mmmmmmmmmmmmmmmmm", 1, "Too predictable"],
    ["fghijklmnopqrstuvw", 1, "Too predictable"],
    ["horsebatteryhorsebattery", 1, "Too predictable"],
    ["lantern-orchid-41", 2, "Good"],
    ["lantern orchid tide river", 3, "Strong"],
  ])("rates %j", (password, level, label) => {
    expect(passwordStrength(password)).toEqual({ level, label });
  });

  it("never asks for particular kinds of character", () => {
    // NIST: no composition rules. All lowercase letters and spaces can be Strong.
    expect(passwordStrength("quiet violet harbour mornings").level).toBe(3);
  });
});

describe("PASSWORD_PROBLEMS", () => {
  it("has our own words for every reason the server gives", () => {
    for (const type of ["password_common", "password_personal", "password_repetitive", "password_sequential"]) {
      expect(PASSWORD_PROBLEMS[type]).toMatch(/^That password/);
    }
  });
});
