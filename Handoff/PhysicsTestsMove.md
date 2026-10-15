# Plan: moving the physics tests into Quorum's test suite

Written 2026-10-15. A plan for review. **Nothing has been moved.**

Quorum's tests live in the `quorum-language` repository, not in the
standard library folder itself. This plan puts the physics tests written
in the `physics` projects there, so they run with the rest of Quorum's
tests. The frustrum tests from `TestFrustrum.md` follow the same path once
written.

## What there is to move

| Suite | Where now | Tests | Needs a window? |
|---|---|---|---|
| **Tier A** (unit tests) | `AllTerrainVehicle/SourceCode/Tests/Physics/**`, tester `Tests/PhysicsTester.quorum`, runner `RunPhysicsTests.quorum` | 93 | No |
| **Tier B** (world tests) | `PhysicsTests/SourceCode/Tests/World/**`, tester `Tests/PhysicsWorldTester.quorum`, runner `Main.quorum` (a `Game`) | 28 | Yes: `Layer3D` reads the game display when created |

**Tier A, by folder:** Positions (6), Matrices (3), Bounds (5), Shapes (8),
Contacts (9), Narrowphase (9), RayCasts (5), Routing (2), Geometry (7),
Clipping (4), Colliders (31), Comparisons (4). The base class
`PhysicsTest` (722 lines) holds the checks and the helpers that build
shapes, triangles and transforms. The four Comparisons tests use `Random`
with fixed seeds, so they give the same result every run.

**Tier B, by group:** Motion (9), Joints (10), Vehicles (3), RayCasts (5),
Drawing (1). The base class `PhysicsWorldTest` builds a `Layer3D` with
physics, steps it with `TestForCollisions(1/60)`, and adds ground, boxes,
spheres, slopes and a vehicle. Its tester wraps each test in
`check`/`detect`, so a test that stops with an error fails with the error
in its message instead of stopping the run.

**Not moved** (they stay in the projects):

- `AllTerrainVehicle/SourceCode/Benchmarks/TriangleColliderTiming.quorum`:
  timing, no pass or fail.
- `AllTerrainVehicle/SourceCode/Spikes/HeadlessWorldSpike.quorum`: a probe
  of whether `Layer3D` works without a window.
- The other projects (BoxDestroy, BoxSmashTest, BoxGoThroughTest,
  ConeAndTwist, Rope3DTest, the four joint examples, Vehicle, Vehicles,
  Terrain, TerrainSplatting, TerrainWalk, and AllTerrainVehicle's game):
  interactive demos with no checks. Several need image files.

## How Quorum runs its tests

Paths are relative to `quorum-language/Quorum`.

- `SourceCode/CompilerTestSuite.quorum` is the runner. It holds one
  `Tester` and a set of tester classes, and prints one line per tester
  ("Math Tests: 123/125"), then a summary and the failed tests.
- There are two kinds of tests:
  - **Output tests** (Math, Matrix and most others): a small program in
    `Library/Tests/<Area>/Pass/`, compiled and run in a separate Java
    process, its printed lines compared with the expected ones listed in a
    tester such as `SourceCode/Tests/MathTester.quorum`.
  - **In-process tests** (Science): classes that are `Test`, in
    `SourceCode/Tests/Science/**` (package `Science.Tests`), run by
    `SourceCode/Tests/ScienceTester.quorum` with `tester:Run(test)`. No
    separate compile or process.
- Tier A was written to match the Science kind. `PhysicsTester` is already
  in package `Libraries.Language.Compile.Test`, and
  `RunPhysicsTests.quorum` says it does locally what the suite does for
  `ScienceTester`.
- There are no Game, Layer3D or physics tests in Quorum today. The five
  programs in `Library/Tests/Game/Pass/` are not run by any tester.
- The suite is run by running `CompilerTestSuite.quorum`, or
  `java -jar Quorum.jar -test` (the user runs it; see the working rules in
  `Handoff.md`).

## Step 1: make sure both suites pass where they are

Both suites were last reported passing before the Layer3D trees work. Run
them again on the current library:

- Tier A: set `RunPhysicsTests.quorum` as AllTerrainVehicle's main file.
  Expect "93 of 93 passed".
- Tier B: run `PhysicsTests`. Expect "28 of 28 passed".

Fix anything that fails before moving.

## Step 2: move Tier A

1. Copy `AllTerrainVehicle/SourceCode/Tests/Physics/**` to
   `Quorum/SourceCode/Tests/Physics/**`, keeping the folders and the
   package `Physics.Tests`. This mirrors `SourceCode/Tests/Science/**`.
2. Copy `AllTerrainVehicle/SourceCode/Tests/PhysicsTester.quorum` to
   `Quorum/SourceCode/Tests/PhysicsTester.quorum`. Its `GetName` should
   read like the others ("Physics Tests").
3. Register it in `CompilerTestSuite.quorum`, as `ScienceTester` is:
   - `use Libraries.Language.Compile.Test.PhysicsTester`;
   - a field, `PhysicsTester physicsChecks`;
   - in `on create`, `physicsChecks:SetTester(tester)`;
   - in `Main`, after the science tests:
     ```
     physicsChecks:Test()
     output physicsChecks:GetName() + GetCurrentTestPassText()
     ```
4. Check that the Quorum project compiles the new folder. If the project
   lists source folders, add `SourceCode/Tests/Physics`.
5. The user runs the suite. Expect "Physics Tests: 93/93".
6. Remove the copies from AllTerrainVehicle (`Tests/`, `RunPhysicsTests`),
   so there is one copy. `TriangleColliderTiming` extends `PhysicsTest`,
   so it either keeps a copy of `PhysicsTest` or moves with it. Decide
   when this step comes (question 3).

## Step 3: move Tier B

Tier B cannot run in-process, since the suite is not a `Game` and
`Layer3D` needs the game display. The choices:

- **(a) One output test that is a game (suggested first).** A program in
  `Library/Tests/Game/Pass/PhysicsWorldTests.quorum` that is a `Game`,
  runs all the world tests in `CreateGame`, prints one line such as
  "28 of 28 passed" and the names of any failures, then calls `Exit`. A
  new `GameTester` in `SourceCode/Tests/` lists that one program with the
  expected line "28 of 28 passed". The world tests themselves go in
  `Library/Tests/Game/Pass/PhysicsWorld/**`, compiled with the program.
  - It opens a window while it runs, so the suite needs a machine with a
    display. A build server without one would fail this test.
  - A failure shows as one failed test; the printed names say which.
- **(b) Make `Layer3D` work without a window** (a library change). Its
  `on create` reads the display size and makes the painter. Both could
  wait until the layer is first drawn or added to a game. Then Tier B
  moves like Tier A, in-process, with no window. This is the better end
  state, but it changes `Layer3D` and needs care with the editor and
  existing games.
- **(c) Leave Tier B in the `PhysicsTests` project.** No change, but it is
  not run with Quorum's tests.

Suggested: (a) now, (b) later as its own plan if the user wants it.

**Name clash to fix first:** both suites have a `Physics.Tests`
`RayCastNearestTest` (Tier A's checks a shape, Tier B's checks the
layer's ray cast). Put Tier B in its own package, `Physics.WorldTests`, or
rename it `WorldRayCastNearestTest`.

## Step 4: the frustrum tests

When `TestFrustrum.md` is done, its Tier A tests move as in step 2
(`SourceCode/Tests/Trees/**`, `RenderTreeTester`), and its Tier B tests as
in step 3, in the same game program or a second one.

## Things to check along the way

- The suite also runs some tests as JavaScript and Python. The Science
  tests are only run on Java; the physics tests should be the same.
- The test classes' header comments derive the expected numbers. Keep
  them; they explain the tests.
- The suite deletes `Output/` and rebuilds the library first, so a library
  change shows up in the next run.
- The world tests take a few seconds of simulated physics each. Time the
  run, so the suite does not get much slower.

## Open questions for the user

1. Tier B: (a), (b) or (c)?
2. Package names: keep `Physics.Tests` for Tier A, and use
   `Physics.WorldTests` for Tier B?
3. Remove the test copies from AllTerrainVehicle and PhysicsTests once
   they are in Quorum, or keep the projects as a quicker way to run them?
4. Should the old, unused `Library/Tests/Game/Pass/` programs be run by
   the new `GameTester` too, or left alone?
