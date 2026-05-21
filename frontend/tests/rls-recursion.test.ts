import { describe, it, expect } from "vitest";
import { createClient } from "@supabase/supabase-js";

// Regression tests for "infinite recursion detected in policy" (Postgres 42P17).
//
// A recursive RLS policy is one whose USING/WITH CHECK expression queries
// the same table the policy is attached to (directly or via a view) without
// going through a SECURITY DEFINER helper. When that happens, ANY query
// against the table — even one that returns zero rows — fails with
// `infinite recursion detected in policy for relation "<table>"` and SQLSTATE
// 42P17. These tests catch that class of regression by issuing a harmless
// SELECT against each historically-affected table as an anonymous user and
// asserting we do NOT get back the recursion error.
//
// We use the publishable (anon) key with no auth session on purpose: RLS is
// still evaluated, so a recursive policy will still blow up, but a correctly
// written policy simply returns 0 rows. We accept any non-recursion outcome.

const SUPABASE_URL =
  process.env.VITE_SUPABASE_URL ?? process.env.SUPABASE_URL;
const SUPABASE_KEY =
  process.env.VITE_SUPABASE_PUBLISHABLE_KEY ??
  process.env.SUPABASE_PUBLISHABLE_KEY;

const TABLES = [
  "session_participants",
  "chat_messages",
  "tasks",
  "library_files",
] as const;

const hasEnv = Boolean(SUPABASE_URL && SUPABASE_KEY);

describe.skipIf(!hasEnv)("RLS policies do not recurse", () => {
  const supabase = createClient(SUPABASE_URL!, SUPABASE_KEY!, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  for (const table of TABLES) {
    it(`${table}: SELECT does not raise 42P17 (infinite recursion)`, async () => {
      const { error } = await supabase.from(table).select("*").limit(1);

      if (error) {
        // Postgres recursion error — the regression we're guarding against.
        expect(error.code, `recursive RLS on ${table}: ${error.message}`).not.toBe("42P17");
        expect(
          error.message.toLowerCase(),
          `recursive RLS on ${table}`,
        ).not.toContain("infinite recursion");
      }
      // No error → policy ran cleanly (possibly returning 0 rows). Both are OK.
    });
  }
});

if (!hasEnv) {
  // Surface a clear signal when the test was skipped due to missing env so
  // CI doesn't silently pass without actually checking anything.
  // eslint-disable-next-line no-console
  console.warn(
    "[rls-recursion.test] Skipped: VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY not set.",
  );
}