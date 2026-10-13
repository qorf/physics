# Handoff: physics, graphics and rendering work

Written 2026-10-13 so the work can be picked up in a new session, and
updated the same day after the RenderTree3D work. Read this first, then the
files it points to. The next task is in `RenderTreeIntegration.md`, next to
this file.

## Working rules

- **Do not write to the Quorum standard library** unless the user explicitly
  says so for that specific change.
  - The library is
    `/Users/stefika/Repositories/quorum-language/Quorum/Library/Standard/Libraries`.
  - "Show me", "plan" and "describe" mean no code changes.
  - "Go ahead and make this change" is permission for that change only.
  - The test projects can be changed freely: AllTerrainVehicle, PhysicsTests,
    BoxDestroy, and the joint examples.
- **Never run `Default.jar`, even with `-help`.** It rebuilt the library's
  compiled output once. The user compiles and runs everything and pastes the
  output.
- **Write in the user's style.**
  - Plain, simple language in comments, aimed at someone learning.
  - `Attribute:` documentation on public actions, but no examples unless
    asked.
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
    (for example `math` in `Item3D`, `color` in `Light`).
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

## Repositories and state

| What | Where | State |
|---|---|---|
| Quorum language | `/Users/stefika/Repositories/quorum-language` | Branch `FrustrumCull`, made from `vulkan-rotations` (`cf04997e5`, "Model loader change"). Latest commit `fdb481b8a` ("Added a GetRange action to PointLight"), which moved the point light range into the library (see below). |
| Example games | `/Users/stefika/Repositories/example-games` | Latest commit `5005e2a` ("Small fix"). Includes the GroundFlightTactics fixes. |
| Test and example projects | `/Users/stefika/Repositories/physics/` | AllTerrainVehicle, PhysicsTests, BoxDestroy, HingeJoint3D, SliderJoint3D, BallAndSocketJoint3D, BallAndChain3D. Latest commit `e847925` ("Adjusted the tree. Next comes integrating it."). |
| Bullet source, for reference | `/Users/stefika/Repositories/bullet3` | |
| MoltenVK source | `/Users/stefika/Repositories/MoltenVK` | |

To see all the work on the branch:

```bash
git diff vulkan-3D...vulkan-rotations
```

## Documents in the projects

- `RenderTreeIntegration.md`, next to this file: the plan for adding the
  render tree to `Layer3D`, with what the OpenGL and Vulkan painters do today.
  **This is the next task.**

The documents below were listed in the first version of this handoff, but
were not in the AllTerrainVehicle folder on 2026-10-13. They were probably
never committed. Ask the user before relying on them.

- `AllTerrainVehicle/VulkanRotationBug.md` and `VulkanRotationFix.md`: the
  rotation bug and its fix. `Item3D` mirrored rotations between physics and
  drawing, and OpenGL hid this with z flips.
- `AllTerrainVehicle/Changes.MD`: the branch diff and the hand-check list.
- `AllTerrainVehicle/Bob.md`: the plan for culling, a list of suspicious
  conditions forced true or false, and the left-handed conversion for loaded
  models.
- `BoxDestroy/BoxDestroyPerformance.md`: last release compared with now.
  Total physics time is about 1.6 times lower. Per frame it is estimated
  about 6 times lower; the estimate method is explained in the file.
- `BoxDestroy/OrthographicMigration.md`: the 2D camera fix as applied.
  `Mirrored2DFix.md` there is an earlier approach that was superseded.

## What is finished

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

## Open items

1. **Face culling** (triangles facing away, not the render tree): `Bob.md`
   sections 1 and 3.
   - OpenGL needs a `SetFrontFace` action, set to clockwise while drawing 3D.
   - Remove `if cullFace = 0 or true`.
   - Vulkan has culling turned off (`CULL_MODE_NONE`).
2. **Leftovers from the work-in-progress commit `a9ff692`:**
   - `glDeleteBuffer` is commented out in `DesktopOpenGL.java`, which leaks
     GPU buffers.
   - SPIR-V shaders are compiled with optimization level 0.
   - Commented-out code remains.
   - `PerspectiveProjection` ignores the handedness setting.
3. **Vulkan shadows, never tested** after the left-handed change:
   - `EnvironmentVulkan` directional shadows use a right-handed orthographic
     projection (`ProjectionToVulkanOrthographic`) with a left-handed view.
   - The shadow-snapping offset is written to row 3, and one line reads
     `row3column1 = row3column0 + ...`. Both look like bugs, at about line
     738.
   - The point-light cube faces may be mirrored.
4. **Other library bugs found but not fixed:**
   - `ModelBlueprintOpenGL.ExtendBoundingBox` never advances its loop
     counter.
   - `ModelBlueprintVulkan.ExtendBoundingBox` uses `elseif` between the
     minimum and maximum checks.
   - `Item3D.transformDirty` is never set back to false, so a rotated item
     rebuilds its matrix on every `GetTransform()`.
   - `EnvironmentVulkan` uses `light:GetPosition()` (relative to the parent)
     for point light shadows, where it should probably use the global
     position. A light attached to another item would cast shadows from the
     wrong place.
   - More bugs in `Layer3D`, `Item3D` and `VulkanPainter3DBatch` are listed in
     step 0 of `RenderTreeIntegration.md`.
   - `Frustum.BoundsInFrustum` is commented out, and `Frustum`'s planes may
     face outward now.
   - `CustomizableJoint3D`'s rotation limit treats equal lower and upper
     values as free.
   - `MathTester` still lists the removed `Matrix4SetToLookAt` and
     `Matrix4SetToProjection` tests.
   - `Graphics3DLoader` (`.g3dj`/`.g3db`) is not converted to left-handed.
5. **Possible future work discussed:**
   - Spring joints: a port of Bullet's `btGeneric6DofSpringConstraint`.
     Motor setters and a linear motor would be needed first.
   - The row-based constraint solver, the bigger refactor.

## RenderTree3D: where it stands

The goal is to replace `Layer3D`'s draw-everything loop (`Layer3D.Draw`, line
1236) with view culling, and to support Vulkan shadows and later terrain
streaming and level of detail.

**Decided:**
- A dynamic bounding volume tree, not an octree or quadtree.
- Separate from the physics tree and not generalized. The algorithm is copied
  from `DynamicBoundingVolumeTree3D`.
- In two halves: static (no margin) and dynamic (0.25 margin). A static item
  that moves goes to the dynamic half. A dynamic item still for 120 frames
  goes back to the static half, checked every 30 frames in `EndFrame`.
- Terrain chunks will later go in the static half, with bounds that cover
  every level of detail.
- Not split into transparent and opaque trees. The painters already sort
  transparent items out, transparency can change at any time, and a split
  would not give the back-to-front order anyway.

**Code:** in `AllTerrainVehicle/SourceCode/Rendering/`, package `Rendering`.
It compiles and runs in AllTerrainVehicle alongside the normal drawing. Nothing
in the library uses it yet.

| Class | What it does |
|---|---|
| `RenderTree3D` | The public interface. `Add(item[, isStatic])`, `Add(item, localBounds[, isStatic])`, `Remove`, `Has`, `GetLeaf`, `Moved(item)`, `Moved(leaf)`, `SetLocalBounds`, `EndFrame`, `CollectVisible(camera or matrix, Array)`, `CollectDirectionalShadowCasters(light, cascade, Array)`, `CollectPointShadowCasters(light, Array)` (static casters cached by the static version), `CollectInBox`, `CollectInSphere`, `IsShowing`, `IsShowingWithParents`, `IsStatic`, `GetSize`, `GetStaticSize`, `GetDynamicSize`, `GetStaticHeight`, `GetDynamicHeight`, `GetStaticVersion`. |
| `RenderBoundingVolumeTree3D` | One half: insert by the least increase in perimeter (`DescendCost`), remove, move with a margin, Box2D rotations, and searches by volume, box and sphere. The branch pool and search stacks are `Array`s emptied with `Empty(false)`. |
| `RenderTreeNode3D` | A node, with private fields and getters and setters. `GetBounds` returns the node's own box; `GetBoundsCopy` returns a copy. |
| `CullingVolume3D` | Five planes read from any view-projection matrix (no near plane), stored in a `Number32BitArray`, with a test that returns outside, intersecting or inside. |
| `ShadowCasterCache3D` | One point light's cached static casters. |
| `RenderTreeCheck` | Test code only. Runs the tree beside the game, checks its answers against a hand test of every item, and prints a snapshot every 200 frames of how many items would be drawn from the current view. |

**Choices made at the user's request:**
- Items are `Item3D`. Bounds for `Add(item)` are a box of the item's width,
  height and depth, centered on it. A model gets those from its blueprint
  when it loads. For anything off-center, such as terrain, pass bounds.
- There is no always-drawn list in the tree. Items without bounds make `Add`
  return false, and the owner draws them itself.
- Results are `Array`s the caller empties with `Empty(false)`. Queries don't
  filter hidden items; the caller uses `IsShowing` or `IsShowingWithParents`.
- The point light range is `PointLight:GetRange()` in the library, used by
  both `EnvironmentVulkan` and the tree.
- `Moved(leaf)` avoids a hash table lookup. The owner gets each item's leaf
  once with `GetLeaf` and keeps it.

**In AllTerrainVehicle** (`Main.quorum`): settings `useRenderTree`,
`renderCheckInterval`, `renderTreeMovesAll`, `addPointLight` and
`renderSnapshotInterval`. Items go through `AddToBoth` and `RemoveFromBoth`.
The terrain is added with its own bounds, from its corner.

**Profiling** (two YourKit snapshots in `AllTerrainVehicle/snapshots/`):
- The tree's work a real game would do went from about 2.2% to about 1.3% of
  the game loop, after `Moved(leaf)` and reading constants once. Physics is
  about 86%.
- What is left is mostly `GetTransform` (cost moved from drawing, not added),
  normal reinserts, and copying shadow casters, since the sun's cascades hold
  nearly every item.
- Neither run was in benchmark mode, so there are no frame times yet. Use
  `benchmark = true` and `renderCheckInterval = 0` for timing.

**Next:** the integration plan in `RenderTreeIntegration.md`. It ends with
five decisions for the user.

## Profiling workflow

- **Snapshots** are in each project's `snapshots/` folder. `*.snapshot` is
  ignored by git.
- **Export** a snapshot with:
  `"/Applications/YourKit Java Profiler.app/Contents/Resources/bin/profiler.sh" -export <snapshot> <outdir>`
- **Analysis scripts** from the earlier session compared exported snapshots
  (`cmp.py`, `gc.py`, `subtree.py`). They read `Method-list-CPU.csv` and
  `Call-tree-all-threads.csv`. They were in that session's scratchpad and
  may need recreating.
- **Frames per run** can only be estimated. The estimate uses `Game.DrawAll`
  time, and only holds if drawing costs about the same per frame in both
  runs. Prefer the benchmark modes in AllTerrainVehicle (`benchmark =
  true`), which report frame times directly.
