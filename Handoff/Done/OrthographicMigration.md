# Mirrored 2D fix: camera direction and orthographic migration

> **Status, 2026-10-15: done.** Applied, although the text below says otherwise. MathTester still lists the removed Matrix4SetToLookAt and SetToProjection tests.

This replaces the approach in `Mirrored2DFix.md`. None of these changes have
been applied.

In BoxDestroy, the frames-per-second label is drawn at the bottom right with
its text mirrored. The cause is that the 2D camera looks along -z, the old
right-handed convention. Commit `a9ff692` made `CameraMatrix4.SetToLookAt`
left-handed, so a camera looking along -z gets an x axis of (-1, 0, 0), and
every 2D x coordinate is mirrored.

This plan fixes the default camera direction in `Camera`, and moves the
orthographic projection out of `Matrix4` into `CameraMatrix4`, as one shared
function both camera paths use. It touches six files and one compiler test.

## Two findings that shape the code

- `VulkanGraphics` (line 400) sets Vulkan's default coordinate system to
  right-handed: `ndc:SetDefaultCoordinateSpace(ndc:RIGHT_HANDED)`. The
  `LEFT_HANDED` line is commented out just above it. `PerspectiveProjection`
  ignores this setting, since its two branches are identical, so it has
  never mattered. The shared orthographic function will honor it, so Vulkan
  needs to be set to left-handed (edit 5).
- Both existing orthographic functions are right-handed:
  `Matrix4.SetToOrthographic` and `OrthographicCamera`'s
  `ProjectionToVulkanOrthographic`. The new function reproduces each exactly
  when asked for a right-handed projection, which keeps the existing compiler
  test's expected output valid (edit 7).

## 1. Camera.quorum, `on create` (line 81)

```quorum
    on create
        // The world is left-handed, so a camera that has not been aimed looks
        // into the screen, along +z.
        direction:Set(0, 0, 1)
        up:Set(0, 1, 0)
```

## 2. CameraMatrix4.quorum: new orthographic actions

Add these next to `PerspectiveProjection`, following its pattern: one
version uses the game's defaults, and one takes them explicitly.

```quorum
    /*
    This action sets the matrix to an orthographic projection, which shows
    everything at the same size however far away it is. The box between left
    and right, bottom and top, and the near and far planes is mapped to the
    screen. The coordinate system and depth range are the game's defaults,
    from DeviceCoordinates.

    Attribute: Parameter left The left edge of the visible area
    Attribute: Parameter right The right edge of the visible area
    Attribute: Parameter bottom The bottom edge of the visible area
    Attribute: Parameter top The top edge of the visible area
    Attribute: Parameter nearPlane The near plane
    Attribute: Parameter farPlane The far plane
    Attribute: Returns The matrix as an orthographic projection matrix
    */
    action OrthographicProjection(number left, number right, number bottom, number top, number nearPlane, number farPlane) returns Matrix4
        DeviceCoordinates ndc = undefined
        if manager:GetGameGraphics() not= undefined
            ndc = manager:GetGameGraphics():GetDeviceCoordinates()
        else
            DeviceCoordinates coords
            ndc = coords
        end
        return OrthographicProjection(left, right, bottom, top, nearPlane, farPlane, ndc:GetDefaultCoordinateSpace(), ndc:GetDefaultDepthRange())
    end

    /*
    This action sets the matrix to an orthographic projection with the given
    coordinate system and depth range, using the constants in
    DeviceCoordinates. In a left-handed system the camera looks along +z, so
    depth grows as z grows. In a right-handed system it looks along -z, so
    depth grows as z shrinks. The depth range is the range the near and far
    planes are mapped to: 0 to 1 (Vulkan) or -1 to 1 (OpenGL).

    Attribute: Parameter left The left edge of the visible area
    Attribute: Parameter right The right edge of the visible area
    Attribute: Parameter bottom The bottom edge of the visible area
    Attribute: Parameter top The top edge of the visible area
    Attribute: Parameter nearPlane The near plane
    Attribute: Parameter farPlane The far plane
    Attribute: Parameter coordinateSystem LEFT_HANDED or RIGHT_HANDED, from DeviceCoordinates
    Attribute: Parameter depthRange DEPTH_ZERO_TO_ONE or DEPTH_NEGATIVE_ONE_TO_ONE, from DeviceCoordinates
    Attribute: Returns The matrix as an orthographic projection matrix
    */
    action OrthographicProjection(number left, number right, number bottom, number top, number nearPlane, number farPlane,
            integer coordinateSystem, integer depthRange) returns Matrix4
        DeviceCoordinates ndc
        IdentityMatrix()
        parent:Matrix4:row0column0 = 2 / (right - left)
        parent:Matrix4:row1column1 = 2 / (top - bottom)
        parent:Matrix4:row0column3 = -1 * (right + left) / (right - left)
        parent:Matrix4:row1column3 = -1 * (top + bottom) / (top - bottom)

        number facing = 1
        if coordinateSystem = ndc:RIGHT_HANDED
            facing = -1
        end

        if depthRange = ndc:DEPTH_ZERO_TO_ONE
            parent:Matrix4:row2column2 = facing / (farPlane - nearPlane)
            parent:Matrix4:row2column3 = -1 * nearPlane / (farPlane - nearPlane)
        else
            parent:Matrix4:row2column2 = facing * 2 / (farPlane - nearPlane)
            parent:Matrix4:row2column3 = -1 * (farPlane + nearPlane) / (farPlane - nearPlane)
        end
        return me
    end
```

All four combinations:

| Coordinate system | Depth range | z scale | z offset | Same as |
|---|---|---|---|---|
| Right-handed | -1 to 1 | -2/(f-n) | -(f+n)/(f-n) | old `Matrix4.SetToOrthographic` |
| Right-handed | 0 to 1 | -1/(f-n) | -n/(f-n) | old `ProjectionToVulkanOrthographic` |
| Left-handed | -1 to 1 | +2/(f-n) | -(f+n)/(f-n) | new: near maps to -1, far to 1 |
| Left-handed | 0 to 1 | +1/(f-n) | -n/(f-n) | new: near maps to 0, far to 1 |

Unlike `PerspectiveProjection`, the defaults version falls back to
`DeviceCoordinates`' defaults when no game is running. This lets it work
headless, which the compiler test needs.

## 3. OrthographicCamera.quorum

### `Update`: use the shared function, with no API branch

```quorum
    action Update
        number halfWidth = parent:Camera:viewportWidth / (2 * zoom)
        number halfHeight = parent:Camera:viewportHeight / (2 * zoom)
        parent:Camera:projection:OrthographicProjection(-halfWidth, halfWidth, -halfHeight, halfHeight,
            parent:Camera:near, parent:Camera:far)

        parent:Camera:view:SetToLookAt(parent:Camera:position, calcVector:Set(parent:Camera:position):Add(parent:Camera:direction), parent:Camera:up)
        parent:Camera:combined:Set(parent:Camera:projection)
        parent:Camera:combined:Multiply(parent:Camera:view)
        parent:Camera:inverseProjectionView:Set(parent:Camera:combined)
        parent:Camera:inverseProjectionView:Inverse()
        parent:Camera:frustum:Update(parent:Camera:inverseProjectionView)
    end
```

### Delete

- `ProjectionToVulkanOrthographic`
- `CheckIfVulkan`
- the `isVulkan` and `isVulkanCached` fields, which nothing else uses
- any `use` lines that only `CheckIfVulkan` needed, likely `VulkanGraphics`
  and `GraphicsManager`

### `SetToOrthographic(number viewportWidth, number viewportHeight)`

It sets the direction itself, so it needs the same change as `Camera`:

```quorum
    action SetToOrthographic(number viewportWidth, number viewportHeight)
        parent:Camera:up:Set(0, 1, 0)
        parent:Camera:direction:Set(0, 0, 1)
        parent:Camera:position:Set(viewportWidth/(2.0 * zoom), viewportHeight/(2.0 * zoom), 0)
        parent:Camera:viewportWidth = viewportWidth
        parent:Camera:viewportHeight = viewportHeight
        Update()
    end
```

The old "libGDX code originally has a boolean for yDown" comment can be
removed.

## 4. OpenGLPainter2D.quorum

The painter's starting projection (line 384) is the only other place that
used Matrix4's orthographic code. Camera matrices replace it as soon as
drawing begins (line 424).

```quorum
use Libraries.Game.Graphics.CameraMatrix4
...
    CameraMatrix4 projectionMatrix          // line 136, was Matrix4
...
        projectionMatrix:OrthographicProjection(0, display:GetWidth(), 0, display:GetHeight(), 0, 1)   // line 384
```

Lines 424 and 758 (`projectionMatrix:Set(camera:GetCombinedMatrix())`) do
not change.

## 5. VulkanGraphics.quorum, around line 398: left-handed, like the rest of the engine

```quorum
        DeviceCoordinates ndc = GetDeviceCoordinates()
        ndc:SetDefaultCoordinateSpace(ndc:LEFT_HANDED)
        ndc:SetDefaultDepthRange(ndc:DEPTH_ZERO_TO_ONE)
```

OpenGL already gets `LEFT_HANDED` from `DeviceCoordinates`' default.
Perspective projections ignore the setting, so 3D is unaffected. Without
this edit, Vulkan's 2D depth would run backward against the +z camera. That
would not show today, because 2D items sit at z = 0.

## 6. Matrix4.quorum, around lines 1395-1562

Delete these three actions and their documentation:

- `SetToOrthographic2D(x, y, width, height)`
- `SetToOrthographic2D(x, y, width, height, near, far)`
- `SetToOrthographic(left, right, bottom, top, near, far)`

## 7. Compiler test: Library/Tests/Math/Pass/Matrix4SetToOrthographic.quorum

It calls all three removed actions. Rewrite it to use `CameraMatrix4`,
asking for right-handed with a depth range of -1 to 1, so the expected
numbers in `MathTester` stay the same:

```quorum
use Libraries.Game.Graphics.CameraMatrix4
use Libraries.Game.Graphics.DeviceCoordinates

class Matrix4SetToOrthographic
    action Main
        CameraMatrix4 matrix
        DeviceCoordinates ndc

        matrix:OrthographicProjection(0, 100, 0, 100, 0, 1, ndc:RIGHT_HANDED, ndc:DEPTH_NEGATIVE_ONE_TO_ONE)
        // ... same row reads and output as before ...

        matrix:OrthographicProjection(0, 100, 0, 100, 0, 1, ndc:RIGHT_HANDED, ndc:DEPTH_NEGATIVE_ONE_TO_ONE)
        // ... same row reads and output as before ...

        matrix:OrthographicProjection(0, 1, 0, 1, 0, 1, ndc:RIGHT_HANDED, ndc:DEPTH_NEGATIVE_ONE_TO_ONE)
        // ... same row reads and output as before ...
    end
end
```

The first two blocks used to call the two `SetToOrthographic2D` overloads
with the same values, so they now make the same call. The test could be
renamed, for example to `CameraMatrix4OrthographicProjection`, but that also
means editing `MathTester` lines 117 and 1592-1596.

A separate issue: commit `a9ff692` also removed `Matrix4.SetToLookAt` and
`SetToProjection`, and `MathTester` still lists `Matrix4SetToLookAt` and
`Matrix4SetToProjection`. Those tests probably fail to compile now, on their
own, regardless of this change.

## What changes on screen

- 2D in both APIs: the 2D camera now looks along +z, so
  `CameraMatrix4.SetToLookAt` gives an x axis of (1, 0, 0). The
  frames-per-second label should be at the bottom left and read left to
  right, and mouse input should match what is on screen.
- 2D depth is left-handed in both APIs. Items at z = 0 get the same depth as
  before, so draw order does not change.
- 3D does not change, because `Layer3D` aims its camera with `LookAt`. A
  `PerspectiveCamera` that is never aimed now looks along +z instead of -z.
- Not covered: the point-light shadow cube-map faces in `EnvironmentVulkan`,
  which may be mirrored under the left-handed look-at.

## Testing

1. In BoxDestroy, in both APIs, the frames-per-second label should be at the
   bottom left and read left to right.
2. Clicking a 2D button should hit it. This checks that mouse positions are
   turned into 2D coordinates correctly, through the inverse combined
   matrix.
3. Overlapping 2D items should keep their stacking order.
4. The `Matrix4SetToOrthographic` compiler test should pass with its
   expected output unchanged.
5. In any example with point lights, shadows should fall away from the light
   on all sides.
