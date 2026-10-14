# Plan: Moving Vehicle and Suspension into the Standard Library

This plan compares `Vehicle.quorum` and `Suspension.quorum` against Bullet's
`btRaycastVehicle.cpp` / `btWheelInfo`, the new shape ray casts
(`CollisionShape3D:RayCast` and its overrides in Box, Sphere, Triangle, Cylinder,
HeightmapTerrainShape), and how `Layer3D` steps physics.

Overall, the tire and suspension math is a close port of Bullet. The bigger problems
are how the vehicle plugs into the physics step, and a few places where it is tied
to the forklift demo.

Line numbers refer to the files as they were when this plan was written.

---

## 1. Bullet to Quorum mapping

| Bullet | Quorum target | Status |
|---|---|---|
| `btRaycastVehicle` | `Libraries.Game.Physics.Vehicle` | Port is close; changes below |
| `btWheelInfo` + `btWheelInfo::RaycastInfo` | `Libraries.Game.Physics.Suspension` | Port is close; its public API needs trimming |
| `btVehicleRaycaster` / `btDefaultVehicleRaycaster` | World ray query in the standard library (new) | `PhysicsRaycast` is deleted |
| `btCollisionWorld::ClosestRayResultCallback` | `RayCastResult3D` | Already exists; one bug to fix (section 2a) |
| `btActionInterface` + `world->addAction()` | A hook in the physics step (new) | Missing; this is the biggest gap |

---

## 2. Blocking changes

### 2a. Replace `PhysicsRaycast` with a standard library world query

- **Add** `CollisionManager3D:RayCast(from, to, ignore, result)`, with a convenience
  wrapper `Layer3D:RayCast(...)`. Loop: broadphase query, call
  `item:GetShape():RayCast(from, to, item:GetCollisionTransform(), result)`, and call
  `result:SetHitBody(item)` when it returns true. Keep looping so the closest hit wins.
  No `BOX` filter or cast to `Box`; other shapes fall back to the base stub.

  ```quorum
  boolean hitAnything = false
  repeat while nodeIterator:HasNext()
      Item3DNode itemNode = nodeIterator:Next()
      Item3D item = itemNode:GetItem()
      CollisionShape3D shape = item:GetShape()
      if item not= ignoreBody and shape not= undefined and item:IsCollidable()
          if shape:RayCast(from, to, item:GetCollisionTransform(), result)
              result:SetHitBody(item)
              hitAnything = true
          end
      end
  end
  return hitAnything
  ```

- **Match Bullet's filter.** `btDefaultVehicleRaycaster::castRay`
  (`btRaycastVehicle.cpp:687`) only accepts a hit if the body `hasContactResponse()`.
  Quorum's closest equivalent is `Item3D:IsCollidable()` (`Item3D.quorum:2586`), so the
  query should skip items without it. Otherwise wheels could rest on trigger volumes.
- Bullet doesn't ignore the chassis explicitly. It relies on rays that start inside a
  shape not hitting it. Keep `ignore` anyway, because a hardpoint can sit just below
  the chassis box.
- **Fix** the setter bugs in `RayCastResult3D` (see below).
- **Delete** `PhysicsRaycast.quorum` and `PhysicsRaycastResult.quorum` from the Vehicle
  project.
- **Remove** the `hardPointValid` ±1000 check (`Vehicle.quorum:337`) and the matching
  check in `UpdateWheelVisual` (`:465`). They hide problems instead of fixing them.

#### RayCastResult3D setter fix

The bug (`RayCastResult3D.quorum:75`):

```quorum
action SetHitPointWorldSpace(Vector3 hitPoint)
    me:hitPointWorldSpace = hitPointWorldSpace
end
```

The parameter is named `hitPoint` but never used. Inside the action,
`hitPointWorldSpace` means the field, so the line copies the field onto itself and
the call silently does nothing. Nothing currently calls it (the shapes write through
`GetHitPointWorldSpace():Set(...)`), which is why it hasn't shown up.

A second problem: `SetHitNormalWorldSpace` "works", but it replaces the field with the
caller's vector instead of copying the values. The result then shares that vector
with the caller: later shapes and `SetToDefault()` would change the caller's vector,
and a reused caller vector would change the result. The ray cast design depends on
the result owning its vectors, so both setters should copy.

Proposed fix:

```quorum
/*
Sets the ray's contact position in world space. The values of the passed
vector are copied, so the vector may be safely reused by the caller.

Attribute: Parameter hitPointWorldSpace The contact position in world space.
*/
action SetHitPointWorldSpace(Vector3 hitPointWorldSpace)
    me:hitPointWorldSpace:Set(hitPointWorldSpace)
end

/*
Sets the surface direction at the contact point, in world space. The
values of the passed vector are copied, so the vector may be safely
reused by the caller.

Attribute: Parameter hitNormalWorldSpace The surface direction in world space.
*/
action SetHitNormalWorldSpace(Vector3 hitNormalWorldSpace)
    me:hitNormalWorldSpace:Set(hitNormalWorldSpace)
end
```

`SetHitBody` storing a reference is fine; it is meant to point at the actual `Item3D`.

Smaller doc fixes in the same file:
- The class comment mentions `GetHit`, `GetHitPoint` and `GetHitNormal`; the actions
  are `IsHit`, `GetHitPointWorldSpace` and `GetHitNormalWorldSpace`.
- The `SetToDefault` comment says "1.0 for friction"; it should say "fraction".

Tests:
1. Set (1, 2, 3) with `SetHitPointWorldSpace(p)`; `GetHitPointWorldSpace()` returns
   (1, 2, 3). Before the fix it returns (0, 0, 0).
2. Then `p:Set(9, 9, 9)`; the result still says (1, 2, 3) (value was copied).
3. `SetToDefault()`; `p` is still (9, 9, 9) (result doesn't share `p`).
4. Same checks for `SetHitNormalWorldSpace`. Before the fix, step 1 passes but steps 2
   and 3 fail.

### 2b. Run the vehicle inside the physics step, not once per frame

Today `Main.Update` calls `vehicle:Update(seconds)` with the **frame** time, but
`Layer3D:StepPhysics` (`Layer3D.quorum:2881`) runs fixed **1/60 s** steps, up to
`maxSubSteps` per frame. As a result:

- **Frames with no physics step:** the vehicle still applies impulses, with nothing
  to resolve them.
- **Frames with two steps:** the vehicle runs only once.
- **Changing frame rates:** impulses are scaled by the frame time rather than the
  physics step, so the car drives differently.

Bullet calls `updateAction(world, timeStep)` once per fixed step, right after
`integrateTransforms` (`btDiscreteDynamicsWorld.cpp:486-489`).

Plan:
- Add a small blueprint, for example `PhysicsAction3D` with
  `action UpdatePhysics(Layer3D layer, number timeStep)`.
- Add `Layer3D:AddPhysicsAction` and `RemovePhysicsAction`.
- Call each registered action inside the `StepPhysics` loop, after
  `SolvePhysics(fixedTimeStep)` (which already ends with `IntegrateTransforms`), before
  `SynchronizeTransforms`. That's the same position Bullet uses.
- `Vehicle` implements the blueprint. Users write `layer:AddPhysicsAction(vehicle)` and
  no longer call `Update` themselves.
- **Drop `SetLayer` as a requirement.** The layer is passed to each update, and
  `Item3D:GetLayer()` (`Item3D.quorum:2394`) can supply it otherwise.
- **Move wheel-visual updates out of the physics step.** Visuals should follow the
  chassis as drawn after `SynchronizeTransforms`, the way Bullet's demo uses
  `updateWheelTransform(i, true)` with the interpolated transform. Otherwise the
  wheels jitter against an interpolated chassis. Do this with a separate per-frame
  `UpdateVisuals()`, or have the layer call it after syncing.

---

## 3. Bullet fidelity (math changes)

| # | Issue | Where | Bullet | Plan |
|---|---|---|---|---|
| 1 | **Missing slope correction** (`m_clippedInvContactDotSuspension`). Spring and damping forces come out wrong when the ground normal isn't parallel to the suspension (slopes, terrain). | `UpdateWheel` ~line 375 | `rayCast` lines 210-229 and `updateSuspension` line 404: `denominator = normal·direction`. If it's ≥ −0.1, use relative velocity 0 and 1/0.1; otherwise multiply both by `inv = −1/denominator`. | Add it, and store `clippedInvContactDotSuspension` and `suspensionRelativeVelocity` on `Suspension` like `btWheelInfo` does. Matters now that terrain ray casts exist. |
| 2 | **Hardpoint mixes two frames.** Uses `chassis:GetX/Y/Z()` (drawn position) with the center-of-mass basis. | `UpdateWheel` lines 293-305 | `updateWheelTransformsWS` uses one chassis transform for everything. | Use `chassis:GetCenterOfMassTransform():Transform(connectionPoint)` and `GetBasis():Transform(...)`. Delete `TransformByChassisBasis` (duplicates `Matrix3:Transform`). |
| 3 | **Steering always rotates about chassis +Y.** | `UpdateWheel` line 321, `UpdateWheelVisual` line 478 | `steeringOrn(up, steering)` where `up = −directionCS` (lines 106-107). | Rotate about −direction using the existing `SetToAxisRotation`, so suspensions that don't point straight down still work. |
| 4 | **Axle-sign comment is wrong, code is right.** "Main supplies +X axles, while Bullet's ForkLift uses −X" is misleading. Bullet itself negates the axle: `basis2[..][right] = −right` (lines 113-115). | `CalculateTireImpulses` lines 613-615, 692-693 | forward = normal × (−axle) = axle × normal | Write it directly as `forward = axle × normal`, document it as the library's convention, remove the reference to Main. |
| 5 | **Speed is unsigned.** | `Update` line 214 | Negative when moving backward (lines 265-276). | Make it signed along the chassis forward axis (needs a forward-axis setting), or keep unsigned and add `GetForwardSpeed`. |
| 6 | **Hidden steering clamp of 0.30.** Main's 0.45 is silently cut to 0.30. | `steeringClamp`, `SetSteering` | The vehicle has no clamp. | Add `Get/SetSteeringClamp`, or remove the clamp. |
| 7 | **`steeringEnabled` gate** makes `SetSteering` on a rear wheel silently do nothing. | `UpdateWheel` line 316 | No gate; `m_bIsFrontWheel` is informational only. | Remove the gate, or rename to `IsFrontWheel` and keep it informational. |

Places where Quorum differs from Bullet on purpose. Keep them, but document them:

- **Suspension length clamp:** Bullet's `rayCast` (lines 196-200) has a quirk: below
  the minimum, it jumps to the *maximum*. Quorum clamps correctly.
- **Ground body:** Bullet always uses `getFixedBody()` (line 190, "@todo for driving
  on dynamic/movable objects"). Quorum uses the body that was actually hit. It
  subtracts that body's velocity and pushes it back with the side impulse. Better for
  pallets and moving platforms.
- **Wheel spin direction:** Bullet uses the chassis forward axis projected onto the
  ground. Quorum uses axle × up, so steered wheels spin along the direction they're
  pointed.

---

## 4. Clean-up for the standard library

### Vehicle

- **Remove dead debug code:**
  - `angularBeforeUpdate` and `angularAfterSuspension` (lines 215, 224);
  - `torque` and `before` in `ApplySuspensionImpulses`;
  - `angularBefore`, `forwardTorque`, `sideTorque` and `totalTorque` in
    `ApplyStoredImpulses`;
  - the commented-out `[TIRE-SOLVE]` output line (656).
- **Work out axle and forward once per wheel per step.** Currently calculated twice,
  in both loops of `CalculateTireImpulses`. Store them on the wheel, the way Bullet
  keeps `m_axle[]` and `m_forwardWS[]`.
- **Store skid on the wheel** instead of allocating `skidInfo`, `sideValues` and
  `forwardValues` arrays every step. Expose as `GetSkidInfo`, like Bullet's
  `m_skidInfo` (useful for skid sounds and tire marks).
- **Replace private helpers with library ones where they exist:**
  - `MultiplyRotations` → `Matrix3:Multiply(a, b)`
  - `TransformByChassisBasis` → `Matrix3:Transform`
  - `ToVisualRotation`'s sign flip → whatever `Item3D` already uses to copy physics
    rotations, so the conversion lives in one place
  - Keep `Clamp` private, because `Math` has no `Clamp`.
- **Add `GetWheelTransform(index, ...)`,** like Bullet's `getWheelTransformWS`, for
  users who draw wheels themselves instead of using `SetVisual`.
- **Rewrite the class docs** for the hook-based usage, with a trimmed example based on
  the forklift.

### Suspension

- **Make the per-step working state private or read-only.** Currently public, with
  setters that keep the caller's vector instead of copying it (same problem as
  `RayCastResult3D`):
  - impulses: `SuspensionImpulse`, `TireImpulse`, `TireForwardImpulse`,
    `TireSideImpulse`;
  - contact offsets: `SuspensionChassisPoint`, `SuspensionGroundPoint`,
    `TireChassisPoint`, `TireGroundPoint`;
  - per-step state: `SetInContact`, `SetGroundBody`, `SetSuspensionForce`,
    `SetDeltaRotation`;
  - all the world-space setters.
- **Keep read-only getters** for what Bullet exposes on `RaycastInfo`: contact point
  and normal, whether it's in contact, the ground body, suspension length, suspension
  force, rotation, and skid.
- **Keep the configuration setters** (stiffness, damping, travel and so on), but make
  each one copy its vector with `:Set`.
- **Defaults already match `btVehicleTuning`.** `maxSuspensionTravel` is in meters
  where Bullet uses centimeters; the docs should say so.

---

## 5. Suggested order

1. Fix `RayCastResult3D`, add the world `RayCast` with the `IsCollidable` filter, and
   switch Vehicle over. Delete `PhysicsRaycast`.
2. Add the physics-step hook. Make Vehicle implement it, and split out visual updates.
3. Fix the transforms and steering axis (section 3, rows 2-4).
4. Add the slope correction (row 1).
5. Settle the API decisions (rows 5-7) and trim Suspension's surface.
6. Remove dead code and replace helpers. Write docs and the example.
7. Move both classes into `Libraries/Game/Physics`, and remove them from the Vehicle
   project to avoid duplicate classes.

---

## 6. Verification plan

- **Shape ray casts** (expected values worked out by hand):
  - Box: 2×2×2 at origin, ray (0, 10, 0) → (0, −10, 0): fraction 0.45, normal (0, 1, 0).
  - Sphere: radius 2 at (3, 0, 0), ray (3, 10, 0) → (3, −10, 0): fraction 0.4, hit
    (3, 2, 0), normal (0, 1, 0).
  - Triangle: corners (0,0,0), (4,0,0), (0,0,4), ray (1, 10, 1) → (1, −10, 1): fraction
    0.5, hit (1, 0, 1), normal (0, 1, 0) (flipped toward the ray).
  - Cylinder: radius 1, half height 2 (`Set(2, 4, 2)`), identity transform:

    | Ray from → to | Fraction | Hit point | Normal |
    |---|---|---|---|
    | (0, 10, 0) → (0, −10, 0) | 0.4 | (0, 2, 0) | (0, 1, 0) |
    | (−6, 1, 0) → (4, 1, 0) | 0.5 | (−1, 1, 0) | (−1, 0, 0) |
    | (−6, 3, 0) → (4, 3, 0) | no hit | | |
    | (0, 0, 0) → (0, 10, 0) | no hit (starts inside) | | |
    | (−3, 5, 0) → (3, −1, 0) | 0.5 | (0, 2, 0) | (0, 1, 0) |
    | (−3, 1, 0) → (3, −5, 0) | 0.3333 | (−1, −1, 0) | (−1, 0, 0) |

  - Terrain: flat (all-black) height map, ray (x, 10, z) → (x, −10, z): fraction 0.5;
    with the terrain moved to y = 5: fraction 0.25.
- **Settling height on flat ground:** Bullet's spring force is `k·compression·mass`
  per wheel. With four wheels and k = 25, the chassis should settle at compression
  ≈ g / (4k) = 9.8 / 100 ≈ **0.098** per wheel. Check after each step above.
- **Frame-rate independence (after step 2):** same throttle at different frame rates
  should give the same speed after N seconds.
- **Slope (after step 4):** on a tilted box ground, the chassis should hold the same
  suspension compression measured along the suspension axis.
- **Terrain:** drive on a `HeightmapTerrainShape`. Wheels should pick up the ground
  body, and the car should climb and descend without sinking in or bouncing.
- **Conventions:** positive engine force drives forward along the documented axis,
  and positive steering turns the way the docs say.

---

## 7. Open decisions

1. Signed or unsigned speed (section 3, row 5).
2. Keep (as a setting) or remove the steering clamp (row 6).
3. Remove or rename `steeringEnabled` (row 7).
4. Name of the physics-step blueprint and the `Layer3D` actions (section 2b).
5. Whether the world ray query lives on `CollisionManager3D`, `Layer3D`, or both.
