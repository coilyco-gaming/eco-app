import { describe, expect, it } from "vitest"
import { decodeUserHex, encodeUserHex } from "./usersApi"

describe("base16 username codec", () => {
  it("round-trips ascii, unicode, and awkward names", () => {
    for (const name of ["coilysiren", "Citizen #999", "松本", "a b/c", "Ünïcödé"]) {
      expect(decodeUserHex(encodeUserHex(name))).toBe(name)
    }
  })

  it("emits lowercase, separator-free hex", () => {
    expect(encodeUserHex("Eco")).toBe("45636f")
    expect(decodeUserHex("45636F")).toBe("Eco") // tolerant of uppercase input
  })

  it("rejects malformed segments", () => {
    expect(() => decodeUserHex("")).toThrow()
    expect(() => decodeUserHex("abc")).toThrow() // odd length
    expect(() => decodeUserHex("zz")).toThrow() // non-hex
  })
})
