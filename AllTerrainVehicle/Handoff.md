# Handoff: physics, graphics and rendering work

Written 2026-10-13 so the work can be picked up in a new session. Read this
first, then the files it points to.

## Working rules

- **Do not write to the Quorum standard library** unless the user explicitly
  says so for that specific change.
  - The library is
    `/Users/stefik/Repositories/quorum-language/Quorum/Library/Standard/Libraries`.
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
  - `Array:Empty(false)` clears an array but keeps its storage.

## Repositories and state

| What | Where | State |
|---|---|---|
| Quorum language | `/Users/stefik/Repositories/quorum-language` | Branch `vulkan-rotations`. Latest commit `cf04997e5` ("Model loader change"). Clean apart from untracked `Quorum/resources/`. |
| Example games | `/Users/stefik/Repositories/example-games` | Latest commit `5005e2a` ("Small fix"). Includes the GroundFlightTactics fixes. |
| Test and example projects | `/Users/stefik/Repositories/physics/` | AllTerrainVehicle, PhysicsTests, BoxDestroy, HingeJoint3D, SliderJoint3D, BallAndSocketJoint3D, BallAndChain3D |
| Bullet source, for reference | `/Users/stefik/Repositories/bullet3` | |
| MoltenVK source | `/Users/stefik/Repositories/MoltenVK` | |

To see all the work on the branch:

```bash
git diff vulkan-3D...vulkan-rotations
```

`Changes.MD` in this folder holds that diff, followed by a list of things to
check by hand.

## Documents in the projects

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

1. **Culling:** `Bob.md` sections 1 and 3.
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

## Current task: RenderTree3D

The goal is to replace `Layer3D`'s draw-everything loop (`Layer3D.Draw`, line
1236) with view culling, and to support Vulkan shadows and later terrain
streaming and level of detail.

**Decided so far:**
- A dynamic bounding volume tree, not an octree or quadtree.
- Separate from the physics tree and not generalized. The algorithm is copied
  from `DynamicBoundingVolumeTree3D`.
- In two halves: static (no margin) and dynamic (0.25 margin).
- Terrain chunks will later go in the static half, with bounds that cover
  every level of detail.

**Code:** five classes in `AllTerrainVehicle/SourceCode/Rendering/`, package
`Rendering`. They are not compiled yet after the latest changes, and nothing
uses them.

| Class | What it does |
|---|---|
| `RenderTree3D` | The public interface. `Add(item)` assumes static. `Add(item, isStatic)`, `Add(item, localBounds[, isStatic])`, `Remove` (also clears a point light's cache), `Has`, `Moved`, `SetLocalBounds`, `EndFrame`, `CollectVisible(camera or matrix, List)`, `CollectDirectionalShadowCasters(light, cascade, List)`, `CollectPointShadowCasters(light, List)` (static casters cached by the static version), `CollectInBox`, `CollectInSphere`, `IsShowing`, `IsShowingWithParents`, `GetSize`, `GetStaticSize`, `GetDynamicSize`, `GetStaticVersion`. |
| `RenderBoundingVolumeTree3D` | One half: insert by the least increase in perimeter, remove, move with a margin, Box2D rotations, and searches by volume, box and sphere. |
| `RenderTreeNode3D` | A node, with public fields for speed. The parent field is `parentNode`. |
| `CullingVolume3D` | Five planes read from any view-projection matrix (no near plane), with a test that returns outside, intersecting or inside. |
| `ShadowCasterCache3D` | One point light's cached static casters. |

**Choices made at the user's request:**
- Item types are `Item3D`, not `Model`.
- There is no always-drawn list in the tree. Items without bounds make `Add`
  return false, and the owner draws them itself.
- Results are `List`s, and queries don't filter hidden items. The caller
  uses `IsShowing` or `IsShowingWithParents`.
- `IsDepthZeroToOne` was removed by dropping the near plane.

**Open questions:**
- **List or Array.** No indexing is needed on return. But `List` allocates a
  node on every `Add`, while a reused `Array` with `Empty(false)` does not.
  I recommended `Array` for the results and the internal stacks; this is
  waiting on a measurement.
- **The user said they will review the classes, then re-evaluate.** Next
  steps after that:
  1. Compile, and fix errors the user pastes.
  2. Unit tests against a brute-force check, in the PhysicsTests style.
  3. Connect it to `Layer3D` in a test project: call `Moved` for changed
     items, then `CollectVisible`, then `painter:Render`, then `EndFrame`.
  4. Per-pass lists for Vulkan's shared instance buffer, in `VulkanPainter3D`
     around line 1322.
  5. Benchmark with BoxDestroy and AllTerrainVehicle.

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
