# Shadow distance on DirectionalLight, for culling

> **Status, 2026-10-15: done.** Applied to the library (default distance 50, not 0 as written below). Kept as a record.

Written 2026-10-14. A proposal for review. **Nothing has been changed.**

Library paths are relative to
`quorum-language/Quorum/Library/Standard/Libraries/Game`.

## Scope

This is about frustum culling only. A directional light gets a shadow
distance, and the render tree uses it to decide which off-screen items are
handed to the painter as shadow casters. **Nothing about rendering
changes:** no change to `EnvironmentVulkan`, the cascades, the shaders or
the GPU data. Shadow fading, and fitting the cascades to the distance, can
come later as separate work.

Today the distance lives on the layers in AllTerrainVehicle
(`CullingLayer3D:SetShadowDistance` and `TreeLayer3D:SetShadowDistance`),
and the column of space it describes is built there too. This moves the
value onto the light, and the column into the render tree, so any layer
that culls gets it from the light.

## Summary of changes

| File | Change |
|---|---|
| `Graphics/DirectionalLight.quorum` | A `shadowDistance` setting, with a getter and setter, and `Copy` |
| `Graphics/Trees/CullingVolume3D.quorum` | `SetShadowColumn`: the column of space that can cast a light's shadow within a distance of a point |
| `Graphics/Trees/RenderTree3D.quorum` | A new `CollectDirectionalShadowCasters(light, camera, results)` that uses the light's distance, or its cascades if it has none (blank here) |
| `Graphics/Trees/StaticDynamicRenderTree3D.quorum` | Its implementation |
| AllTerrainVehicle (not the library) | The layers read the light's distance instead of their own |

## What changes in behavior

- **With a distance of 0, the default,** nothing changes. The tree finds
  the light has no distance and searches each of its cascades, as the
  layers do now.
- **With a distance set,** off-screen items outside the column are no
  longer drawn as shadow casters. The cascades still reach the camera's far
  plane, so items on screen still cast shadows at any distance. Shadows
  from items that are neither on screen nor within the distance disappear.
  That is the trade-off the layers make today, with the value now coming
  from the light.

---

## Part 1: `Graphics/DirectionalLight.quorum`

New field, after `intensity`:

```
    // How far from the camera this light's shadow casters are looked for
    // when a layer culls, or 0 for no limit. See SetShadowDistance.
    number shadowDistance = 0
```

New actions:

```
    /*
    This action sets how far from the camera this light's shadows are kept
    when a layer culls what it draws. An object that is off screen is only
    drawn into this light's shadows if it could cast a shadow within this
    distance of the camera. Objects on screen are drawn either way.

    A smaller distance means fewer objects are drawn into the shadows. A
    distance of 0 means there is no limit, and every object that could cast
    a shadow into the camera's view is drawn into them.

    This does not change how the shadows themselves are drawn.

    Attribute: Parameter distance How far from the camera shadow casters are
    kept, in world units, or 0 for no limit.
    */
    action SetShadowDistance(number distance)
        if distance < 0
            shadowDistance = 0
        else
            shadowDistance = distance
        end
    end

    /*
    This action returns how far from the camera this light's shadow casters
    are kept when a layer culls, or 0 if there is no limit.

    Attribute: Returns The shadow distance.
    */
    action GetShadowDistance returns number
        return shadowDistance
    end
```

It does not call `GetEnvironment():LightChanged(me)`. The environment does
not use the value, so there is nothing for it to redo.

`Copy` copies it:

```
    action Copy returns DirectionalLight
        DirectionalLight copy
        copy:SetLight(GetColor(), GetDirection())
        copy:SetShadowDistance(shadowDistance)
        return copy
    end
```

---

## Part 2: `Graphics/Trees/CullingVolume3D.quorum`

Today the layers build the column as a matrix, then the volume reads planes
from the matrix. The column's five planes can be written directly, which is
simpler to read and needs no matrix.

New action, after `Set(Matrix4 matrix)`. It adds `use Libraries.Compute.Vector3`.

```
    /*
    This action sets the volume to the column of space that can cast a
    directional light's shadow within a distance of a point, such as the
    camera.

    The column is a square, twice the distance wide, centered on the point
    and running along the light's direction. Toward the light it has no
    end, so a tall object far toward the light is still inside it. Away
    from the light, it ends the distance past the point, since anything
    farther is behind whatever its shadow would fall on.

    Its five planes face inward, as those read from a matrix do:

        Two at the distance on either side of the point, along a direction
        across the light.

        Two the same, along the other direction across the light.

        One the distance past the point, along the light.

    Attribute: Parameter direction The direction the light shines in. It
    does not need to be unit length.
    Attribute: Parameter x The x coordinate of the column's center.
    Attribute: Parameter y The y coordinate of the column's center.
    Attribute: Parameter z The z coordinate of the column's center.
    Attribute: Parameter distance How far the column reaches to each side,
    and past the center.
    Attribute: Returns False if the direction has no length, in which case
    the volume is left empty and finds nothing.
    */
    action SetShadowColumn(Vector3 direction, number x, number y, number z, number distance) returns boolean
        planeCount = 0

        number forwardX = direction:GetX()
        number forwardY = direction:GetY()
        number forwardZ = direction:GetZ()
        number length = math:SquareRoot(forwardX * forwardX + forwardY * forwardY + forwardZ * forwardZ)
        if length = 0
            return false
        end
        forwardX = forwardX / length
        forwardY = forwardY / length
        forwardZ = forwardZ / length

        // A direction across the light: up crossed with the light's
        // direction, using z as up if the light points nearly straight up
        // or down.
        number upX = 0
        number upY = 1
        number upZ = 0
        if math:AbsoluteValue(forwardY) > 0.99
            upY = 0
            upZ = 1
        end
        number rightX = upY * forwardZ - upZ * forwardY
        number rightY = upZ * forwardX - upX * forwardZ
        number rightZ = upX * forwardY - upY * forwardX
        number rightLength = math:SquareRoot(rightX * rightX + rightY * rightY + rightZ * rightZ)
        rightX = rightX / rightLength
        rightY = rightY / rightLength
        rightZ = rightZ / rightLength

        // The other direction across the light, at right angles to both.
        number sideX = forwardY * rightZ - forwardZ * rightY
        number sideY = forwardZ * rightX - forwardX * rightZ
        number sideZ = forwardX * rightY - forwardY * rightX

        // How far the center is along each direction.
        number rightAt = rightX * x + rightY * y + rightZ * z
        number sideAt = sideX * x + sideY * y + sideZ * z
        number forwardAt = forwardX * x + forwardY * y + forwardZ * z

        // A point p is inside when each of these is 0 or more, as for the
        // planes read from a matrix.
        AddPlane(rightX, rightY, rightZ, distance - rightAt)
        AddPlane(-rightX, -rightY, -rightZ, distance + rightAt)
        AddPlane(sideX, sideY, sideZ, distance - sideAt)
        AddPlane(-sideX, -sideY, -sideZ, distance + sideAt)
        AddPlane(-forwardX, -forwardY, -forwardZ, distance + forwardAt)
        return true
    end
```

For example, `rightX * px + rightY * py + rightZ * pz + (distance - rightAt)`
is the point's distance along the right direction, minus the center's, plus
the distance. It is 0 or more for points no more than the distance to the
left of the center. The far plane works the same way along the light.

`GetPlaneCount`'s comment, "5, or fewer if the matrix gave a plane with no
direction", stays true.

---

## Part 3: `Graphics/Trees/RenderTree3D.quorum`

The tree reads the distance from the light, so the layer only passes the
light and the camera. If the light has no distance, the tree searches each
of the light's cascades instead, so the layer no longer needs to know how
many cascades there are: the light has shadow data for each cascade, and
`GetShadowData` returns undefined past the last one.

New blank action, after the existing `CollectDirectionalShadowCasters`:

```
    /*
    This action adds the items that could cast a shadow from a directional
    light into view to the results, using the light's own limits.

    If the light has a shadow distance (see
    DirectionalLight:SetShadowDistance), the items found are those in the
    column of space running from the camera toward the light, as wide as
    twice the distance. Objects on screen are not limited by this. A layer
    finds those with CollectVisible.

    If the light has no shadow distance, the items found are those that
    could cast a shadow into any of the light's cascades, the same as
    calling the action that takes a cascade for each one. A light without
    shadow data, such as in OpenGL, then adds nothing.

    Attribute: Parameter light The directional light.
    Attribute: Parameter camera The camera the shadow distance is measured
    from.
    Attribute: Parameter results The array to add the items to.
    */
    action CollectDirectionalShadowCasters(DirectionalLight light, Camera camera, Array<Item3D> results)
    end
```

The existing action of the same name takes a cascade number instead of a
camera, so the two do not clash, and it stays for anything that wants one
cascade at a time.

---

## Part 4: `Graphics/Trees/StaticDynamicRenderTree3D.quorum`

New action, after the existing `CollectDirectionalShadowCasters`. It adds
`use Libraries.Game.Graphics.Camera` and `use Libraries.Compute.Vector3`.

```
    /*
    This action adds the items that could cast a shadow from a directional
    light into view to the results: those within the light's shadow
    distance of the camera, or, if it has none, those that could cast a
    shadow into any of its cascades. See RenderTree3D.

    Attribute: Parameter light The directional light.
    Attribute: Parameter camera The camera the shadow distance is measured
    from.
    Attribute: Parameter results The array to add the items to.
    */
    action CollectDirectionalShadowCasters(DirectionalLight light, Camera camera, Array<Item3D> results)
        number distance = light:GetShadowDistance()
        if distance > 0
            Vector3 center = camera:GetPosition()
            if volume:SetShadowColumn(light:GetDirection(), center:GetX(), center:GetY(), center:GetZ(), distance)
                staticPart:Collect(volume, results)
                dynamicPart:Collect(volume, results)
            end
            return now
        end

        integer cascade = 0
        repeat while light:GetShadowData(cascade) not= undefined
            CollectDirectionalShadowCasters(light, cascade, results)
            cascade = cascade + 1
        end
    end
```

It reuses the tree's `volume`, as the other searches do.

---

## Part 5: AllTerrainVehicle (not the library)

**`CullingLayer3D` and `TreeLayer3D`:**

- Remove `shadowDistance`, `shadowColumn`, `SetShadowDistance`,
  `GetShadowDistance` and `SetShadowColumn`.
- In `CollectShadowCasters`, each directional light becomes one call. The
  `cascadeCount` field, and the code that reads it from `VulkanGraphics`,
  go away too:

```
            tree:CollectDirectionalShadowCasters(directionalLights:Next(), GetCamera(), found)
```

(`renderTree` in TreeLayer3D.)

**`Main`:** set the distance on the sun, where it is created, instead of
on the layer:

```
        sunlight:SetShadowDistance(shadowDistance)
```

and remove `layer:SetShadowDistance(shadowDistance)` from both layers'
setup.

## Testing

- With the same distance as before (40, or 20), the "shadow casters found"
  counts in the log should match the last run's for the same views. The
  column is the same; only where it is built has moved.
- A distance of 0 on the light should give the per-cascade counts from
  before the column existed.
- Two directional lights with different distances should each use their
  own.
- Optional, for the tree on its own: a test like the CullingVolume3D
  example, checking that a box beside the camera, within the distance, is
  inside, one past the distance to the side is outside, and one far toward
  the light is inside.
