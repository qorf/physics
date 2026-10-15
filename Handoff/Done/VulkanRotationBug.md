# Vulkan chassis rotation bug

> **Status, 2026-10-15: done.** The fix (VulkanRotationFix.md) was applied. The "related issues" in section 4 were not all decided; see Handoff.md.

## Summary

The chassis turns the wrong way in Vulkan because `Item3D` mirrors every
rotation it copies between physics and drawing, but copies positions
unchanged. A rotation about y (a vehicle's yaw) is drawn turning the
opposite way from the physics.

OpenGL hides this. Its shader mapping applies two hidden z flips to every
draw. Together with the mirrored rotation, they draw rotations correctly but
mirror the whole picture left to right, which is the "OpenGL is mirrored"
symptom. So both symptoms come from one set of compensating hacks:

| Where | What it does |
|---|---|
| `Item3D` | Mirrors rotations (flips the signs of m02, m12, m20, m21) when copying between physics and drawing. |
| `DefaultShaderMapping3DOpenGL.InvertPositionZ` | Negates the z of every item's position. |
| `DefaultShaderMapping3DOpenGL.InvertViewZ` | Flips the camera matrix: mirrors world z and screen x. |
| `DefaultShaderMapping3DOpenGL`, lights | Negates z on light directions and positions to match. |

Vulkan has none of the shader hacks, so it shows the `Item3D` mirroring
directly.

`CameraMatrix4` is correct. It builds a standard left-handed view (x right,
y up, z forward) and a standard left-handed projection (w = +z, depth 0 to 1
or -1 to 1). Vulkan's negative viewport height correctly turns that into y
up. Nothing else changes the camera matrices.

## The math

Notation:
- R is an item's physics rotation and p its position.
- Z = diag(1, 1, -1) mirrors z, and X = diag(-1, 1, 1) mirrors x.
- P is the projection and V the view.

**Drawing.** `Item3D.SetScreenPositionFromPhysicsPosition` (Item3D.quorum,
about line 3409) sets the drawn rotation to Rd = Z R Z and copies p
unchanged.

**Vulkan** draws P V [Rd | p] = P V [Z R Z | p]. Positions are right, and the
rotation is mirrored. Z R_y(θ) Z = R_y(-θ), so yaw is reversed: the chassis
moves one way and turns the other. This is the bug.

**OpenGL.** `InvertPositionZ` negates the translation's z, giving [Rd | Z p].
`InvertViewZ` negates combined-matrix entries (0,0), (0,1), (0,3), (1,2),
(2,2) and (3,2). That is exactly X (P V) Z.

So OpenGL draws X P V Z [Rd | Z p] = X P V [Z Z R Z | p] = X P V [R Z | p]:
- Positions are right (p).
- Rotations are the physics rotation R, so motion and turning agree.
- Every mesh is mirrored in its own space (the Z on the right).
- The final image is mirrored left to right (X).

Driving looks right, and the picture is mirrored. The two extra reflections
(Z on the mesh, X on the screen) cancel for triangle winding, which is why
OpenGL's back-face culling still works.

## Fix (not applied; standard library changes)

All of these must change together. Fixing only `Item3D` makes Vulkan right
and breaks OpenGL. Fixing only OpenGL makes OpenGL show the reversed yaw.

### 1. Item3D: copy rotations between physics and drawing without mirroring

Three places build one rotation from the other with the signs of m02, m12,
m20 and m21 flipped. Each should copy the entries directly, keeping the
scale division where it is there:
- `SetScreenPositionFromPhysicsPosition` (about lines 3409-3419): physics to
  drawn.
- `Rotate(Vector3, number, boolean)` (about lines 1612-1624): drawn to
  physics.
- `SetYawPitchRoll` (about lines 2040-2055): drawn to physics.

For example, in `SetScreenPositionFromPhysicsPosition`:

```quorum
        matrix:row0column0 = tempMatrix:row0column0
        matrix:row0column1 = tempMatrix:row0column1
        matrix:row0column2 = tempMatrix:row0column2

        matrix:row1column0 = tempMatrix:row1column0
        matrix:row1column1 = tempMatrix:row1column1
        matrix:row1column2 = tempMatrix:row1column2

        matrix:row2column0 = tempMatrix:row2column0
        matrix:row2column1 = tempMatrix:row2column1
        matrix:row2column2 = tempMatrix:row2column2
```

The comment there about converting between left- and right-handed systems
should go. Physics and drawing share one coordinate system, since positions
are copied as they are, so there is nothing to convert.

### 2. OpenGL shader mapping: remove the z flips

In `Shaders/OpenGL/Mapping/DefaultShaderMapping3DOpenGL.quorum`:
- `Begin` (about line 211): remove `InvertViewZ(tempMatrix4)`.
- `MapInputs` (about line 294): remove `InvertPositionZ(tempMatrix4)`, and
  the "lazy hack" comment above it.
- `BindLights` (about line 552): remove `tempVector3:Scale(1, 1, -1)`.
- `BindLights`, directional lights (about line 580): pass
  `tempVector3:GetZ()`, not `-tempVector3:GetZ()`.
- `BindLights`, point lights (about line 615): pass `position:GetZ()`, not
  `-position:GetZ()`.
- After that, `InvertViewZ` and `InvertPositionZ` are unused and can be
  deleted.

OpenGL's depth range is -1 to 1, and its normalized device coordinates have
x right, y up and z into the screen. With `CameraMatrix4`'s left-handed
projection, this needs no adjustment. Triangle winding does not change,
because the two reflections removed (Z and X) cancelled each other, so
culling stays as it is.

### 3. Vehicle: wheel visuals

`Vehicle.ToVisualRotation` (Game/Physics/Vehicles/Vehicle.quorum) applies the
same sign flips "the same conversion Item3D uses". Remove them, so that
`converted` is the physics basis itself, and update the comment.

### 4. Related, not required for this bug

- `Item3D.Rotate` turns around (x, y, -z), negating only the axis's z. This
  is a choice about which way Rotate turns, not a conversion, so it can
  stay. But after the fix it no longer has a hidden counterpart. Rotations
  about z now turn the opposite way from rotations about x and y, compared to
  the "clockwise" wording in the documentation. Decide whether to keep it.
- `SetRotationTransform` sets the drawn rotation but does not update the
  physics rotation, unlike `Rotate` and `SetYawPitchRoll`.
- Check any game code written to compensate. For example, a model built
  facing -z because OpenGL showed it mirrored.

## Testing the fix

1. **Numeric test, already added:** PhysicsTests,
   `Tests/World/Drawing/DrawnRotationMatchesPhysicsTest`. It spins a box
   about y for half a second and checks that the drawn rotation matches the
   physics rotation. It also turns a box with `Rotate(1, 1, 0, 30)` and
   checks that the physics rotation matches the drawn one. It fails now, on
   the four mirrored entries, and should pass after step 1. It runs in either
   API, since it compares matrices and does not read the screen.
2. **Orientation check in both APIs.** Make a small game with the camera at
   (0, 0, -5) looking at the origin. Add three small boxes: a red one at
   (1, 0, 0), a green one at (0, 1, 0), and a blue one at (0, 0, 1) behind
   the center. Expect red on the right, green above, and blue behind the
   center, in both APIs. Today OpenGL shows red on the left.
3. **Asymmetric model.** Load a model with an obvious left and right, such as
   text or a character. It should face the same way in both APIs.
4. **Lighting.** A directional light from the right should light the right
   faces in both APIs. A point light at +z should light the faces toward +z.
   Specular highlights should sit in the same place in both.
5. **AllTerrainVehicle in both APIs.** Steering left should turn the chassis
   left, with the wheels steering and spinning the right way. The scene should
   no longer be mirrored in OpenGL.
6. **Regression.** Rerun PhysicsTests (all should pass, including the new
   test) and the AllTerrainVehicle physics tests. Then check other 3D
   examples, such as the joint examples and BoxDestroy, in both APIs.
