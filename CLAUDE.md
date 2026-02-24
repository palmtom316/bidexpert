# BidExpert Project Guidelines

## Debugging: Systematic Four-Phase Process

NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.

### Phase 1: Root Cause Investigation
Before attempting ANY fix:
1. Read error messages carefully — full stack traces, line numbers, error codes
2. Reproduce consistently — if not reproducible, gather more data, don't guess
3. Check recent changes — git diff, recent commits, new dependencies
4. In multi-component systems, add diagnostic logging at each component boundary BEFORE proposing fixes
5. Trace data flow backward — find where bad value originates, not where it crashes

### Phase 2: Pattern Analysis
1. Find working examples of similar code in the codebase
2. Compare working vs broken — list every difference
3. Understand all dependencies and assumptions

### Phase 3: Hypothesis and Testing
1. Form single hypothesis: "X is the root cause because Y"
2. Test with SMALLEST possible change, one variable at a time
3. Didn't work? New hypothesis. DON'T stack fixes

### Phase 4: Implementation
1. Create failing test case first
2. Implement single fix addressing root cause
3. Verify fix — test passes, no regressions
4. If 3+ fixes failed: STOP — question the architecture, discuss before continuing

Red flags (return to Phase 1): "quick fix for now", "just try X", "probably X", proposing solutions before tracing data flow.

## Verification Before Completion

NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE.

Before claiming ANY status:
1. IDENTIFY what command proves the claim
2. RUN the full command (fresh, not cached)
3. READ full output, check exit code
4. VERIFY output confirms the claim
5. ONLY THEN make the claim

Never use "should", "probably", "seems to" — run the verification.

## Defense-in-Depth Validation

When fixing a bug caused by invalid data, validate at EVERY layer:
- Layer 1: Entry point — reject invalid input at API boundary
- Layer 2: Business logic — ensure data makes sense for the operation
- Layer 3: Environment guards — prevent dangerous operations in specific contexts (e.g. refuse destructive ops outside tmpdir in tests)
- Layer 4: Debug instrumentation — log context for forensics

Single validation = "we fixed the bug". Multiple layers = "we made the bug impossible".

## Root Cause Tracing

When errors occur deep in execution:
1. Observe the symptom
2. Find immediate cause — what code directly triggers it?
3. Ask "what called this?" — trace up the call chain
4. Keep tracing until you find the original trigger
5. Fix at source, not at symptom
6. Add defense-in-depth validation at each layer

If you can't trace manually, add `console.error()` with stack traces before the problematic operation.

## Test-Driven Development

NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.

Red-Green-Refactor cycle:
1. RED — Write one minimal failing test for the desired behavior
2. Verify RED — Run it, confirm it fails for the right reason (feature missing, not typo)
3. GREEN — Write simplest code to pass the test. No extras
4. Verify GREEN — Run it, confirm all tests pass
5. REFACTOR — Clean up. Keep tests green. Don't add behavior
6. Repeat

Write code before the test? Delete it. Start over. No "reference", no "adapt".

## Parallel Agent Dispatch

When facing 3+ independent failures:
1. Group failures by independent domain
2. Create focused agent tasks — specific scope, clear goal, constraints, expected output
3. Dispatch in parallel — one agent per problem domain
4. Review and integrate — check for conflicts, run full suite

Don't use when: failures are related, need full system context, or agents would edit same files.

## Plan Execution

When executing implementation plans:
1. Load and review plan critically — raise concerns before starting
2. Execute in batches of 3 tasks
3. Report after each batch with verification output
4. Wait for feedback before continuing
5. STOP and ask when blocked — don't guess

## When Stuck — Problem-Solving Dispatch

| Stuck Type | Technique |
|------------|-----------|
| Complexity spiraling (5+ ways, growing special cases) | Simplify — find what to eliminate |
| Need innovation (conventional solutions inadequate) | Cross-domain collision thinking |
| Recurring patterns (same issue in different places) | Meta-pattern recognition |
| Forced by assumptions ("must be done this way") | Inversion — what if opposite? |
| Scale uncertainty (will it work in production?) | Test at extremes (10x, 100x) |
| Code broken (wrong behavior, test failing) | Systematic debugging (Phase 1-4 above) |
| Multiple independent problems | Parallel agent dispatch |
| Root cause unknown | Backward tracing |

Full skill details: `~/.claude/skills/`

Skills libraries:
- `~/.claude/skills/superpowers/` — obra/superpowers: systematic development methodology (debugging, TDD, planning, code review, etc.)
- `~/.claude/skills/` — ComposioHQ/awesome-claude-skills: content creation, design, dev tools, MCP builder, etc.
