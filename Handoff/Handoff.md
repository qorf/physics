# Handoff: physics, graphics and rendering work

Updated 2026-10-19. This folder holds the handoffs and plans for the work
in the `physics` projects and the Quorum standard library. Read this file
first: "Where things stand", then "What remains", then the working rules.

**Current focus (since 2026-10-17): Open Worlds,** large streamed terrain
with editing tools. Its documents live beside its code in
`AllTerrainVehicle/`. Start with `AllTerrainVehicle/OpenWorldsHandoff.md`,
which has the **priority list** of what remains.

On 2026-10-19:
- **Working and committed:**
  - TerrainEditor (Tier 4's in-game editor);
  - AmbientCG texture sets with height blending;
  - mipmaps and anisotropy;
  - a skybox on the shader system;
  - MSAA for 3D and 2D;
  - resize fixes;
  - `vSyncEnabled` under Vulkan.

  The library commits are `804c85c40` to `8a656d7c3` on `TerrainShader`, then
  `0b5de0b62` (spotlights) on `MakeAWish`.
- **Freeing memory everywhere** is done (`AllTerrainVehicle/MemoryPlan.md`):
  - Items 31 to 35 are committed (`8d0ca607f`, `b1d8e1a8e`) and run.
  - Item 36 is for review.
- **Now: spotlights and water** (`SpotlightPlan.md`, `WaterPlan.md`;
  stopped here on 2026-10-19):
  - Spotlights for Vulkan are committed (`Item37.md`, `0b5de0b62`) and
    not yet run. DriveOpen has headlights (N for night, H for the lights).
  - Water phase 1 (`Item38.md`) is for review, not applied.
  - See `OpenWorldsHandoff.md`, "Where we are", for the next steps.

## The files in this folder

| File | What it is |
|---|---|
| `Handoff.md` | This file: the summary. |
| `CarModel.md` | Plan (2026-10-16): a Kenney car with separate wheels in place of the box chassis. Not started as far as the Open Worlds documents know; DriveOpen still loads the ToyCar. The Kenney kit is in `AllTerrainVehicle/CarKit/`. |
| `LoadParts.md` | Plan (2026-10-16): `Model:LoadParts`, loading a model's parts separately (a library change). Not started. |
| `TestFrustrum.md` | Was the next task before Open Worlds started; not revisited since 2026-10-15. Tests for the frustum culling library: tree tests with no window, layer tests in a game, and checks by eye. |
| `PhysicsTestsMove.md` | The task after: moving the 93 unit tests and 28 world tests into Quorum's test suite, and the frustrum tests with them. |
| `Open/Layer3DTrees.md` | The design of `Layer3D`'s trees and culling (batches 1 to 3, all done), with the transparency details, risks, and testing lists. The reference for the culling work. |
| `Open/Changes.MD` | The `vulkan-3D...vulkan-rotations` diff and its "check by hand" list, partly open. |
| `Open/README_RAYCAST_VEHICLE.md`, `Open/VEHICLE_STDLIB_PLAN.md` | The ray cast vehicle port. Mostly done; a few decisions and clean-ups may remain (see "What remains"). |
| `Done/*.md` | Records of finished work: `ShadowDistance`, `ItemReporting`, `CollideTriangleSpeedups`, `VulkanRotationBug`, `VulkanRotationFix`, `OrthographicMigration`, `BoxDestroyPerformance`, `SLIDER_JOINT_FIX`. Each has a status line at the top. |

Removed on 2026-10-15, as replaced or out of date (still in git history,
before this commit): `RenderTreeIntegration.md` and `LibraryStaging/` (an
earlier culling plan and its staged library files, never applied; the
staged files include a Vulkan shadow-only draw path and the batch
`castsShadows` fix, if those are wanted later), and the early forklift
notes in `Vehicle/` (`BUG_FIXES`, `COMPARISON_WITH_BULLET`,
`FIXES_SUMMARY`, `NUMERICAL_INSTABILITY_FOUND`, `STANDARD_LIBRARY_NOTES`,
`WHEEL_DISAPPEARANCE_FIX`). `BoxDestroy/Mirrored2DFix.md`, which was never
committed, was deleted; `Done/OrthographicMigration.md` replaced it.
`Bob.md` (face culling) and `Shadows.md` (shadow casters and the Vulkan
shadow bugs) were deleted as no longer relevant; neither was committed.

## Repositories

| What | Where | State |
|---|---|---|
| Quorum language | `~/Repositories/quorum-language` | **Now branch `MakeAWish`** (from Item 37, commit `0b5de0b62`; never switch branches, use the one checked out). Before that, branch `TerrainShader` (Open Worlds library changes `804c85c40` to `8a656d7c3`, all committed). Earlier: branch `FrustrumCull2`. Commit `581a60746` ("Closer to frustrum") is batch 1. Batch 2 (`Game/Layer3D.quorum`, new `Game/Item3DBackToFrontComparison.quorum`) was uncommitted on 2026-10-14; check `git status`. |
| Test and example projects | `~/Repositories/physics` | This repository. |
| Example games | `~/Repositories/example-games` | Includes the GroundFlightTactics fixes. |
| Bullet source, for reference | `~/Repositories/bullet3` | |
| MoltenVK source | `~/Repositories/MoltenVK` | |

The home folder is `/Users/stefik` on one machine and `/Users/stefika` on
the other; older notes use either.

Snapshots (`*.snapshot`) are not in git. The two that matter for the
culling work are `AllTerrainVehicle/snapshots/Default-2026-10-14-shutdown-4`
(batch 1, drawing everything) and `-5` (batch 2, culled).

## Where things stand

The work so far, in order:

1. **Physics:** Bullet port fixes, joints, the ray cast vehicle in the
   library, box-box and triangle colliders, and 121 tests (see "What is
   finished" below).
2. **The left-handed world** in both APIs, and the Vulkan rotation fix.
3. **Vulkan shadows** work again (the orthographic projection's z sign, and
   the shader's cascade choice).
4. **CollideTriangle speedups** 1, 3 and 5 (`Done/CollideTriangleSpeedups.md`).
5. **Frustum culling in the library** (`Open/Layer3DTrees.md`):
   - Render trees in `Libraries.Game.Graphics.Trees`: a bounding volume
     tree, a quadtree and an octree, each split into static and dynamic
     parts, with searches for the camera's view, boxes, spheres and shadow
     casters.
   - Items tell their layer when they move, change size, or their physics
     changes (`Done/ItemReporting.md`).
   - `Item3D:GetRenderBounds`, overridden by `Terrain`.
   - A shadow distance on `DirectionalLight`, for culling only
     (`Done/ShadowDistance.md`), default 50.
   - `Layer3D` keeps its items in a render tree, and its bodies in awake
     and sleeping trees, instead of an array. The actions that used an
     index (`Get(integer)`, `AddToFront` and so on) are gone; `Has(Item3D)`
     is new. Physics walks only the awake bodies.
   - `Layer3D.Draw` draws what the camera sees, and in Vulkan what could
     cast a shadow into view. Transparent models are drawn last, farthest
     first. `GetRenderTree` and `SetRenderTree` let a game use a quadtree
     or octree.
   - AllTerrainVehicle uses the plain `Layer3D` again; the test layers are
     gone.
   - No painter changes were made.
6. **Open Worlds** (2026-10-17 on), in `AllTerrainVehicle/`:
   - Terrain3D-style regions, streaming, collision near the player, coarse
     distant terrain, and texture splatting, all in
     `Libraries.Game.Graphics.Worlds` in the project.
   - Library changes on `TerrainShader`: meshes update in place, per-model
     shader programs, and a fix for a crash after minimizing.
   - Records: `OpenWorldsHandoff.md` and the files it lists.

All of the culling work compiled and ran in AllTerrainVehicle on
2026-10-14. The last profile (batch 2 against batch 1, per second of run):

| | Batch 1 | Batch 2 |
|---|---|---|
| `DrawAll` | 67 | 53 (−21%) |
| `VulkanPainter3D.Render` | 7.4 | 1.8 (a quarter of the models reach the painter) |
| `CollectVisible` | — | 6.2 |
| `CollectShadowCasters` (sun distance 20) | — | 0.4 |
| `UpdateRenderTree` | — | 9.8 (half is `Model.GetTransform`, paid in drawing before) |

Main-thread CPU is about even; the saving should be on the GPU. Physics is
about 90% of the frame either way.

## What remains

**Open Worlds** (current): the priority list is in
`AllTerrainVehicle/OpenWorldsHandoff.md`, and the library order in
`AllTerrainVehicle/LibraryChangesPlan.md`. Library changes for it are on the
`quorum-language` branch `MakeAWish` from Item 37 on (before that
`TerrainShader`; never switch branches, use the one checked out); everything applied is committed
(the last is `0b5de0b62`, on `MakeAWish`).
In short:
1. **spotlights and water** (`SpotlightPlan.md`, `WaterPlan.md`):
   - spotlights for Vulkan are committed (`Item37.md`, `0b5de0b62`) and
     waiting for a run (SpotlightCheck, DriveOpen at night with H);
   - water phase 1 (`Item38.md`) is for review;
   - the next to write is `Item39.md` (the water pass);
   freeing memory is done (Items 31 to 35 committed and run; Item 36,
   per-frame garbage, for review);
2. run the checks not yet reported (2D MSAA, a resize with MSAA, vsync,
   minimize);
3. small fixes:
   - #22 (texture groups);
   - `Material`'s zero diffuse;
   - a game-level after-physics hook, and blending drawn positions between
     physics steps;
4. better ground, and fog;
5. world-making: height layers, rule-based painting, splines;
6. larger work: many materials, instancing, Quorum Studio brushes.

The items below are the earlier work, paused while Open Worlds goes on.

### Next: test the culling work (`TestFrustrum.md`)

- 22 tree tests that need no window (`CullingVolume3D`, each tree kind,
  shadow casters, `GetRenderBounds`, the back-to-front sort), checked
  against counting by hand.
- 14 layer tests in a running game, using small counting test classes to
  see what `Layer3D.Draw` hands the painter.
- By the user: benchmark frame times (batch 1 is commit `581a60746`),
  shadows at sun distance 0, 20 and 50, transparency in Vulkan,
  GroundFlightTactics, BoxDestroy, the joint examples, and the scene editor.
- Before any of that: run the 93 unit tests and 28 world tests on the
  current library. They were last run before the Layer3D change.

### Then: move the tests into Quorum (`PhysicsTestsMove.md`)

- The 93 unit tests go in as Quorum's Science tests do, in-process, with a
  `PhysicsTester` registered in `CompilerTestSuite.quorum`.
- The 28 world tests need a game window. Suggested: one game program in
  Quorum's output tests that runs them all and prints the result. Later,
  perhaps, `Layer3D` made to work without a window.
- A `RayCastNearestTest` name clash between the two suites must be fixed.

### Follow-ups to the culling work (none started; each needs a go-ahead)

- "Items drawn" counts on `Layer3D`, for testing.
- A shadow-only draw path in the Vulkan painter, so off-screen casters skip
  the scene pass.
- Shadow casters per cascade or per light.
- Vulkan transparency (`Open/Layer3DTrees.md`, end of Transparency):
  transparent queues after opaque ones (fixes the texture-group bug), one
  draw command per transparent model, a forward pass.
- `Model:GetRenderBounds` from the blueprint's measured corners, after the
  `ExtendBoundingBox` bugs are fixed.
- `Model.Load(blueprint, matrix)` should call `NotifyMoved()`.
- Known risks (`Open/Layer3DTrees.md`, Risks): item order is now the
  tree's (drawing, update, input ties, scene save order); games using the
  removed index actions no longer compile; adding or removing other items
  during a walk can skip or repeat items.

### Vulkan shadows

From the shadow notes, removed 2026-10-15. Shadows work; these were
left over:

- Fix 3: `lastSplitDistance` is never updated, so cascades overlap.
- Fix 4: the snapping offset is written into row 3.
- Depth clamp for the shadow pass, so casters far toward the light are not
  clipped.
- Point lights: the cube faces may be mirrored, and the light's local
  position is used instead of its global one.
- The batch `castsShadows` flag is decided by the last model in a batch.

### Leftovers from the left-handed work (`Open/Changes.MD`)

- From commit `a9ff692`: `glDeleteBuffer` commented out in
  `DesktopOpenGL.java` (leaks GPU buffers); SPIR-V compiled at
  optimization 0; commented-out code; `PerspectiveProjection` ignores
  handedness.
- The "check by hand" list at the end of `Open/Changes.MD`.
- Waiting on the user: GroundFlightTactics in both APIs after the Java
  plugins are rebuilt.

### Library bugs found but not fixed

- `ModelBlueprintOpenGL.ExtendBoundingBox` never advances its counter;
  `ModelBlueprintVulkan.ExtendBoundingBox` uses `elseif` between the
  minimum and maximum checks.
- `Item3D.transformDirty` is never set back to false, so a turned item
  rebuilds its matrix on every `GetTransform()`.
- `Item3D.Remove` fails when the item is not on a layer.
- `Item3D.Rotate` negates the axis's z, so z turns go the other way from x
  and y; `SetRotationTransform` does not update the physics rotation
  (`Done/VulkanRotationBug.md`, section 4).
- `Frustum.BoundsInFrustum` is commented out, and `Frustum`'s planes may
  face outward.
- `CustomizableJoint3D` treats equal lower and upper limits as free.
- `MathTester` still lists the removed `Matrix4SetToLookAt` and
  `Matrix4SetToProjection` tests.
- `Graphics3DLoader` (`.g3dj`, `.g3db`) is not converted to left-handed.
- Vulkan's `Render` keeps adding to its lists while the game is paused.

### Vehicle (`Open/VEHICLE_STDLIB_PLAN.md`, `Open/README_RAYCAST_VEHICLE.md`)

Possibly open; check against the library `Game/Physics/Vehicles` before
working on them: slope correction, the `steeringEnabled` flag, signed speed
and the 0.30 steering clamp, setters that keep the caller's vector, the
`[TIRE-SOLVE]` debug output (`Vehicle.quorum` about line 756),
`GetWheelTransform` and `GetSkidInfo`.

### Later, discussed but not planned

- Spring joints (Bullet's `btGeneric6DofSpringConstraint`); needs motor
  setters and a linear motor first.
- The row-based constraint solver.
- The 2D render trees (`AllTerrainVehicle/SourceCode/Rendering2D/`), not
  in the library.

## Working rules

- **Do not write to the Quorum standard library** unless the user explicitly
  says so for that specific change.
  - The library is
    `~/Repositories/quorum-language/Quorum/Library/Standard/Libraries`.
  - "Show me", "plan" and "describe" mean no code changes.
  - "Go ahead and make this change" is permission for that change only.
  - The test projects can be changed freely: AllTerrainVehicle, PhysicsTests,
    BoxDestroy, and the joint examples.
- **Never run `Default.jar`, even with `-help`.** It rebuilt the library's
  compiled output once. The user compiles and runs everything and pastes the
  output.
- **Write in the user's style.**
  - Plain, simple language in comments, aimed at someone learning.
  - `Attribute: Parameter` and `Attribute: Returns` on every action,
    private ones too.
  - `Attribute: Example` on every class: simple, a few lines, and it must
    compile.
  - Readability matters more than small speedups. The user declined two
    CollideTriangle speedups as "much harder to read, even if correct".
  - Descriptive names. The user picks final names, and prefers `GetSize` for
    sizes and `Has...` for boolean questions.
- **Before changing code, show the exact before and after** when the user
  asks to see it.
- **Quorum gotchas** that have caused compile errors:
  - Reserved words can't be names: `blueprint`, `parent`, `input`, `output`,
    `me`.
  - Fields and locals declared without a value construct themselves.
  - No single-line `if`.
  - An operator that continues a line goes at the end of the line.
  - Subclasses can only reach a parent's fields with `parent:Class:field`.
  - Constants must be literal values.
  - `BoundingBox:IsValid` rejects flat boxes.
  - `List` is a linked list, so each `Add` creates a node.
  - `Array:Empty(false)` clears an array but keeps its storage. `Empty()`
    with no argument creates a new backing array, and `SetSize` to a smaller
    size creates a new array too.
  - `Integer32BitArray:SetSize` throws its contents away.
  - Reading a constant, even inside its own class, compiles to an action
    call. In loops that run often, copy it into a field or local first.
  - A subclass can't declare a field with the same name as a parent's field
    (for example `math` in `Item3D`, `color` in `Light`). New fields in
    `Layer3D` or `Item3D` can clash with subclasses in games.
  - A subclass must not call a parent's private actions.
  - Generic classes are written `RenderTreeIterator3D<Item3D> is
    Iterator<Item3D>`.
  - `Array:Sort(comparison, temp)` writes into `temp` by index, so `temp`
    must already be at least as large.
  - Comparing a field of a parent type with `me` can fail to compile; copy
    `me` into a local of that type first.
- **Rules for graphics and rendering code:**
  - **Do not put anything about physics into the render tree.** It must not
    look at physics state such as `IsSimulated`. The test project's
    `RenderTreeCheck` uses physics to choose what to report as moved, but
    that stays in the test code.
  - Avoid `Array<number>` and other autoboxing arrays. Use `Number32BitArray`
    (or the 64-bit or integer versions).
  - Avoid `List` in code that runs every frame. Use `Array` with
    `Empty(false)`.
  - No public fields. Use private fields with getters and setters, so access
    can be limited or profiled later.
  - The render tree works with `Item3D`, not `ModelBlueprint` or `Model`.

## What is finished (before the culling work)

### Physics
- Bullet port fixes:
  - `BoundingBox` `Combine` and `Clamp` call `CalculateDimensions`.
  - `Contains`, `GetMatrix`, the shape `Copy` actions and cylinder up axis
    and inertia are fixed.
  - `Box.Set` now keeps the margin inside the given size, like Bullet.
  - `Triangle.IsInside` is fixed.
- Joint fixes:
  - `ApplyTorqueImpulse` now applies an angular impulse.
  - The hinge and slider no longer overwrite the axis with `CrossProduct`.
  - The ball and socket joint reads velocity per axis.
  - The slider's projected pivot is fixed.
- Vehicle: the chassis sleeps properly. A resting chassis reads 9.8 / 60
  upward between steps, and that is correct.
- Tests:
  - Tier A, in the AllTerrainVehicle project: 93 unit tests, run from
    `RunPhysicsTests.quorum`.
  - Tier B, in the PhysicsTests project: 28 world tests that run inside a
    game window, including `DrawnRotationMatchesPhysicsTest`. All passed at
    last report.
- Joint examples for documentation: HingeJoint3D, SliderJoint3D,
  BallAndSocketJoint3D and BallAndChain3D (a wrecking ball on a chain,
  using `CustomizableJoint3D`).

### Graphics: the left-handed world, in both APIs
- `Item3D` and `Vehicle` copy rotations between physics and drawing without
  mirroring them.
- OpenGL: the z flips are removed (`InvertViewZ`, `InvertPositionZ` and the
  light z negations).
- 2D:
  - `Camera` now faces +z by default.
  - The orthographic projection moved from `Matrix4` into `CameraMatrix4` as
    `OrthographicProjection`.
  - Vulkan's coordinate system default is now left-handed.
- `MeshBuilder` texture u is mirrored for left-handed (box, cylinder,
  ellipse, sphere).
- Model loading:
  - The OpenGL `.obj` reader flips z and swaps triangle order.
  - The Assimp loader (Vulkan) uses `MakeLeftHanded | FlipWindingOrder`,
    without `FlipUVs`, because the loader already flips v.
- Scenes: files are saved with `"Version": 2.0`. Older files have their 3D
  rotations mirrored once and their 2D camera flipped when they are loaded
  (`DefaultSceneManager`).
- GroundFlightTactics:
  - The `GridPlane` branch is now chosen with
    `manager:GetGameGraphics() is VulkanGraphics`.
  - The spinner is placed relative to its parent.

Waiting on the user: confirmation that GroundFlightTactics looks right in
both APIs after the Java plugins are rebuilt.

## Profiling workflow

- **Snapshots** are in each project's `snapshots/` folder. `*.snapshot` is
  ignored by git.
- **Export** a snapshot with:
  `"/Applications/YourKit Java Profiler.app/Contents/Resources/bin/profiler.sh" -export <snapshot> <outdir>`
- **Use that app's `profiler.sh`.** The one inside
  `YourKit-Java-Profiler-2022.9.app` is too old for these snapshots and
  fails with "Not a YourKit Java Profiler snapshot". A snapshot still being
  written fails the same way; wait a minute and retry.
- **`ProfilingTools/subtree.py`** prints part of an exported call tree:
  `python3 ProfilingTools/subtree.py <outdir> 'Layer3D.Draw(' 2` shows each
  call matching the text, with two levels below it (calls of 40 samples or
  more). Compare runs per second of uptime (in the export's `Summary.txt`),
  since runs differ in length.
- **Frames per run** can only be estimated. The estimate uses `Game.DrawAll`
  time, and only holds if drawing costs about the same per frame in both
  runs. Prefer the benchmark modes in AllTerrainVehicle (`benchmark =
  true`), which report frame times directly.
