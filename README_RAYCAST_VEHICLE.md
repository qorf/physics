# Ray Casting and Vehicle Port: Hand-off Notes for Claude

This file lets Claude pick up the work on another machine. Read it first, then
read `Vehicle/VEHICLE_STDLIB_PLAN.md`, which has the full vehicle plan with
Bullet line references, code drafts and expected test values.

Last updated: 2026-10-08.

---

## 1. Goal

Port Bullet's 3D ray casting and its ray cast vehicle (`btRaycastVehicle`) into the
Quorum standard library.

1. **Done (pending test results):** physics ray casts against every 3D shape, plus a
   world-level query.
2. **Next:** move `Vehicle` and `Suspension` from the `Vehicle` test project into the
   standard library, after the changes in the plan.

## 2. Rules from the user (always follow)

1. **Never write code in the Quorum standard library.** Draft code in chat; the user
   integrates and adjusts it.
2. **Only write to disk inside this `physics` repository**, and by default only in
   `Vehicle/`. The user explicitly asked for this file at the `physics` root.
3. **When asked to review, report issues only.** Don't change code.
4. **The `IsCollidable()` check:** skip it when items come from a broadphase query,
   because anything in the broadphase trees is already collidable. Keep it for code
   that gets items some other way (for example, walking a layer's item list
   directly).

## 3. Repositories and key files

Paths are relative to each repository. On the original machine they were:
- Bullet: `~/Repositories/bullet3`
- Quorum standard library: `~/Repositories/quorum-language/Quorum/Library/Standard`
- This repo: `~/Repositories/physics`

**Quorum standard library** (`Libraries/...`):

| File | What's there |
|---|---|
| `Game/Collision/Shapes/CollisionShape3D.quorum` | Base `RayCast(from, to, transform, result) returns boolean` stub (returns false), with the shared contract docs |
| `Game/Collision/Shapes/Box.quorum` | `RayCast`: slab test in box-local space, uses half extents with margin |
| `Game/Collision/Shapes/Sphere.quorum` | `RayCast`: quadratic in world space around `transform:GetOrigin()` |
| `Game/Collision/Shapes/Triangle.quorum` | `RayCast`: port of Bullet `btTriangleRaycastCallback::processTriangle` (both faces, normal flipped toward the ray, edge tolerance `-0.0001·|n|²`) |
| `Game/Collision/Shapes/Cylinder.quorum` | `RayCast`: cap slab test plus side quadratic, uses `GetCoordinate`/`SetCoordinate` for any up axis |
| `Game/Collision/Shapes/HeightmapTerrainShape.quorum` | `RayCast` + private `RayCastCell`: inverse of `terrain:GetTransform()` to grid space, walks cells in ray order, tests both triangles per cell with `Triangle:RayCast` in world space, early stop when `nextCross >= result:GetFraction()` |
| `Game/Collision/RayCastResult3D.quorum` | Result: hit, hit body, hit point, hit normal, fraction |
| `Game/Collision/CollisionManager3D.quorum` | `RayCastPhysics(from, to, result)` and `RayCastPhysics(from, to, ignore, result)`: broadphase query, then `shape:RayCast`, then `SetHitBody` |
| `Game/Layer3D.quorum` | Wrappers around the CollisionManager3D query; physics step is `StepPhysics` (~line 2881) |
| `Compute/Matrix3.quorum` | `Transform(Vector3)` (~line 1910) had a z-row bug (see section 5) |

Relevant commits in the quorum-language repo: `e747474c6`, `006ae81a1`, `1ba62116f`,
`470634989`, `f57c83b40`, `2d792bbfb`.

**This repo:**

| File | What's there |
|---|---|
| `Vehicle/SourceCode/Vehicle.quorum` | Ray cast vehicle (port of `btRaycastVehicle`) |
| `Vehicle/SourceCode/Suspension.quorum` | Wheel data (port of `btWheelInfo`) |
| `Vehicle/SourceCode/PhysicsRaycast.quorum` | Old box-only ray cast, to be deleted |
| `Vehicle/SourceCode/PhysicsRaycastResult.quorum` | Duplicate of `RayCastResult3D`, to be deleted |
| `Vehicle/SourceCode/Main.quorum` | Forklift demo |
| `Vehicle/VEHICLE_STDLIB_PLAN.md` | **The detailed plan.** Read it. |

**Bullet references:**
- `src/BulletDynamics/Vehicle/btRaycastVehicle.cpp` (vehicle, default raycaster ~line 687)
- `src/BulletCollision/CollisionDispatch/btCollisionWorld.cpp` (`rayTestSingleInternal` ~line 286)
- `src/BulletCollision/NarrowPhaseCollision/btRaycastCallback.cpp` (triangle ray test)
- `src/BulletCollision/NarrowPhaseCollision/btSubSimplexConvexCast.cpp` (convex ray test)
- `src/BulletCollision/CollisionShapes/btHeightfieldTerrainShape.cpp` (`performRaycast` ~line 779, `gridRaycast` ~line 517)
- `src/BulletDynamics/Dynamics/btDiscreteDynamicsWorld.cpp` (`updateActions` after `integrateTransforms`, ~lines 486-489)

## 4. Ray cast design decisions (settled)

- **Shape contract:** `RayCast(from, to, transform, result)` works in world space.
  The result is both input and output: a shape only reports a hit *strictly* closer
  than `result:GetFraction()`, so one result can be passed through many shapes. A
  shape sets hit, fraction, world hit point and world normal (unit length, facing the
  ray's start), but **not** the hit body; the caller sets that.
- **Shapes write directly into the result's own vectors** through
  `GetHitPointWorldSpace():Set(...)` and `GetHitNormalWorldSpace():Set(...)`.
- **A ray starting inside a shape, or exactly on its surface, is not a hit.** This
  matches Bullet (its convex cast ends with a zero normal and rejects the hit) as well
  as Unity and Box2D. Box detects it with `enterAxis = -1`, Sphere with `c <= 0`,
  Cylinder with `enterPart = -1`. Triangles have no inside; a ray that touches the
  plane only at an endpoint, or lies in it, is not a hit. Reporting hits from inside
  could be added later as an opt-in setting on `RayCastResult3D` (fraction 0, hit
  point = from, normal = reversed ray direction, the PhysX convention), changed in
  all shapes at once.
- **Margins:** Box and Cylinder use their size *including* the margin, with sharp
  edges (Bullet rounds edges by the margin; this only matters within ~0.04 of an edge
  or rim). Sphere's margin equals its radius. Triangles ignore the margin, like Bullet.
- **The world query resets the result** with `SetToDefault()` before searching.
- **`HeightmapTerrainShape` ignores its `transform` parameter** and uses the terrain's
  own `Matrix4` (`terrain:GetTransform()`), which includes scale and rotation. Without
  its override it would inherit `Box:RayCast`, because it `is Box`.

## 5. Issues found in review (user says fixed; test suite was running)

Confirm these are fixed before building on them:

1. **`Matrix3:Transform` z-row bug.** The z line used `row2column0 * vector:GetZ()`
   instead of `GetX()`. This broke the world normals for Box, Cylinder and Triangle on
   anything turned around Y. It was already being used by `HingeJoint3D` and
   `ConeTwistJoint3D`, so joints may change behaviour with the fix.
   - Test: a box turned 90° around Y, hit on its local +X face, gives normal
     (0, 0, −1). Repeat at ~30°, and for a cylinder side and a triangle. Retest joints
     with bodies turned around Y.
2. **`RayCastResult3D` setters** should copy (`:Set(...)`) instead of keeping the
   caller's vector. Also fix the class comment (it mentions `GetHit`, `GetHitPoint`,
   `GetHitNormal`) and the "friction" → "fraction" typo in `SetToDefault`.
   - Test: set a point, change the caller's vector, call `SetToDefault()`; each side
     keeps its own values.
3. **Naming.** Layer3D had `RayCast` (3 arguments) next to `RayCastPhysics`
   (4 arguments), and the docs referred to a `RayCast` action CollisionManager3D
   doesn't have. Check what names the user settled on before writing Vehicle code
   against them.

## 6. Hand-worked expected values for testing

- **Box** 2×2×2 at origin, ray (0, 10, 0) → (0, −10, 0): fraction 0.45, normal (0, 1, 0).
- **Sphere** radius 2 at (3, 0, 0), ray (3, 10, 0) → (3, −10, 0): fraction 0.4, hit
  (3, 2, 0), normal (0, 1, 0). (a = 400, b = −200, c = 96, discriminant = 1600.)
- **Triangle** corners (0,0,0), (4,0,0), (0,0,4), identity, ray (1, 10, 1) →
  (1, −10, 1): fraction 0.5, hit (1, 0, 1). The triangle's own normal is (0, −16, 0);
  the reported normal is flipped to (0, 1, 0).
- **Cylinder** `Set(2, 4, 2)` (radius 1, half height 2; `Cylinder:Set` does not add the
  margin back, so these are exact), identity:

  | Ray from → to | Fraction | Hit point | Normal |
  |---|---|---|---|
  | (0, 10, 0) → (0, −10, 0) | 0.4 | (0, 2, 0) | (0, 1, 0) |
  | (−6, 1, 0) → (4, 1, 0) | 0.5 | (−1, 1, 0) | (−1, 0, 0) |
  | (−6, 3, 0) → (4, 3, 0) | no hit | | |
  | (0, 0, 0) → (0, 10, 0) | no hit (starts inside) | | |
  | (−3, 5, 0) → (3, −1, 0) | 0.5 | (0, 2, 0) | (0, 1, 0) |
  | (−3, 1, 0) → (3, −5, 0) | 0.3333 | (−1, −1, 0) | (−1, 0, 0) |

- **Terrain**, flat (all-black) height map, ray (x, 10, z) → (x, −10, z): fraction 0.5;
  with the terrain moved to y = 5: fraction 0.25.
- **World query** (Layer3D docs example): 10×1×10 box at y = −0.5, ray (0, 10, 0) →
  (0, −10, 0): fraction about 0.5.
- **Vehicle settling height** on flat ground with k = 25 and four wheels: compression
  ≈ g / (4k) ≈ 0.098 per wheel.

## 7. What remains (in order)

Full details are in `Vehicle/VEHICLE_STDLIB_PLAN.md`.

1. **Switch Vehicle to the standard library query.** In `Vehicle.quorum` ~line 341,
   replace `raycast:Cast(...)` with the Layer3D/CollisionManager3D query using the
   chassis as the ignored item. Remove the `PhysicsRaycast raycast` field. Delete
   `PhysicsRaycast.quorum` and `PhysicsRaycastResult.quorum`. Remove the ±1000
   `hardPointValid` check (~line 337) and the one in `UpdateWheelVisual` (~line 465).
2. **Physics-step hook (plan 2b).** Vehicle currently runs once per *frame* from
   `Main.Update`, but `Layer3D:StepPhysics` runs fixed 1/60 s substeps. Add a blueprint
   (e.g. `PhysicsAction3D` with `UpdatePhysics(Layer3D layer, number timeStep)`), plus
   `Layer3D:AddPhysicsAction`/`RemovePhysicsAction`, called in the `StepPhysics` loop
   after `SolvePhysics(fixedTimeStep)` (Bullet's `updateActions` position). Vehicle
   implements it. Drop the `SetLayer` requirement (`Item3D:GetLayer()` exists). Move
   wheel-visual updates to run once per frame after `SynchronizeTransforms`.
3. **Transforms and steering** (plan section 3, rows 2-4): hardpoint from the chassis
   center-of-mass transform alone; steering about −direction instead of fixed +Y;
   rewrite the axle sign as `forward = axle × normal` (this *is* Bullet's convention,
   `basis2[..][right] = −right`); delete `TransformByChassisBasis`.
4. **Slope correction** (row 1): add Bullet's `clippedInvContactDotSuspension` and
   `suspensionRelativeVelocity` (`btRaycastVehicle.cpp` lines 210-229 and 404).
5. **API decisions** (rows 5-7) and trimming Suspension's public setters for its
   per-step working state (they also keep the caller's vector instead of copying).
6. **Clean-up:** dead debug variables, compute axle/forward once per wheel, store skid
   on the wheel (`GetSkidInfo`), replace private helpers with library ones, add
   `GetWheelTransform`, rewrite docs and the example.
7. **Move** `Vehicle` and `Suspension` into `Libraries/Game/Physics`, and remove them
   from the Vehicle project.

## 8. Open decisions for the user

1. Signed or unsigned vehicle speed.
2. Keep (as a setting) or remove the hidden 0.30 steering clamp.
3. Remove or rename `steeringEnabled`.
4. Name of the physics-step blueprint and the `Layer3D` actions.
5. Final names of the world ray query actions on Layer3D and CollisionManager3D.

## 9. Speed-ups deferred on purpose

- World query: long diagonal rays make a big search box. Walking the bounding-volume
  tree along the ray (Bullet's `rayTestInternal`) would fix it.
- Terrain: clip the ray to the grid before walking it; skip cells by height range
  (Bullet's `ProcessVBoundsAction`).
