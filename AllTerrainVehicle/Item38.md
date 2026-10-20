# Item 38: time and camera data for 3D shaders (water, phase 1)

**Status (2026-10-19, end of session): for review.** Nothing is applied yet. This is phase
1 of `WaterPlan.md`, with its recommended answer to decision 2: do it first,
as its own Item.

**Branch:** whichever is checked out in `quorum-language` (`MakeAWish` now).
It never switches.

**Scope:** Vulkan only. **OpenGL is not touched.**

Paths: **G/** = `Quorum/Library/Standard/Libraries/Game/Graphics/`,
**P** = `G/Vulkan/VulkanPainter3D.quorum`.

## Why

Water needs these in its shaders:
- **time,** for moving ripples;
- **the camera's position,** for fresnel and reflections;
- **the screen size and the camera's near and far planes,** to find a
  pixel on screen and its distance.

So do later effects: grass and trees swaying in wind, distance-based detail
on the terrain, fog.

**Today the 3D camera uniform holds only `projectionViewMatrix`,** 64 bytes,
visible only to vertex shaders. No 3D shader can get any of the above.

## The change

**The 3D camera uniform** (set 0, binding 0, one buffer per frame slot)
grows from 64 to 96 bytes, in std140 layout:

| Offset | Field | Set by the painter, every frame |
|---|---|---|
| 0 | `mat4 projectionViewMatrix` | unchanged |
| 64 | `vec3 cameraPosition` | the camera's position |
| 76 | `float time` | seconds since the painter started drawing, wrapped every hour |
| 80 | `vec2 screenSize` | the swapchain image's width and height, in pixels |
| 88 | `float nearPlane` | `camera:GetNear()` |
| 92 | `float farPlane` | `camera:GetFar()` |

**It becomes visible to fragment shaders too.** Two places describe this
binding, and they must match exactly for the painter's descriptor set to
work with every 3D pipeline:
- the painter's own camera layout (P);
- `VulkanPipelineInfoCreator:AddDefaultInfo3D`, which every 3D shader
  mapping uses (`DefaultShaderMapping3DVulkan`, so also the terrain splat
  program, and future water and custom programs).

**About time:**
- It adds `Game:GetSecondsBetweenFrames()` each frame the painter draws.
- It stops while the window is minimized, since nothing is drawn.
- It wraps at 3,600 seconds, so a 32-bit float keeps millisecond
  precision. Shaders that animate with it should use periods that divide
  an hour (most do), or accept a small jump once an hour.

**Existing shaders don't change behaviour.**
- `DefaultVertexShader3DVulkan` declares the larger block, and still reads
  only the matrix, at offset 0.
- Fragment shaders that don't declare the block are unaffected.
- **The terrain splat program,** in the project, uses the default vertex
  shader and its own fragment shader, which doesn't read the block, so it
  needs no change.

## The code

### P (`G/Vulkan/VulkanPainter3D.quorum`)

**New fields,** after `Number32BitArray matrix4Array`:

```
    // The 3D camera uniform's contents (Item 38): the projection-view
    // matrix, then the camera's position, time, the screen size, and the
    // near and far planes. 24 numbers, 96 bytes.
    Number32BitArray cameraDataArray
    constant integer CAMERA_DATA_SIZE = 24

    // Seconds since this painter started drawing, wrapped every hour, for
    // shaders that animate (Item 38).
    number shaderTime = 0
    constant number SHADER_TIME_WRAP = 3600
```

**`on create`.** After `matrix4Array:SetSize(16)`, add:

```
        cameraDataArray:SetSize(CAMERA_DATA_SIZE)
```

**The camera layout** (in `Begin`, where `cameraBuffers:IsEmpty()`). The line

```
            uniformsBinding:SetStageFlags(constants:SHADER_STAGE_VERTEX_BIT)
```

becomes:

```
            // The camera uniform carries time and the camera's position as
            // well, for fragment shaders such as water (Item 38). This must
            // match AddDefaultInfo3D.
            uniformsBinding:SetStageFlags(constants:SHADER_STAGE_VERTEX_BIT + constants:SHADER_STAGE_FRAGMENT_BIT)
```

**The camera buffers.** In the same block:

```
                // These buffers are for a 4x4 matrix of floats, so 4 bytes * 16 values.
                VulkanBuffer buffer
                buffer:CreateMappableBuffer(device, 4 * 16, constants:BUFFER_USAGE_UNIFORM_BUFFER_BIT)
```

becomes:

```
                // The camera uniform: 24 numbers of 4 bytes (Item 38).
                VulkanBuffer buffer
                buffer:CreateMappableBuffer(device, 4 * CAMERA_DATA_SIZE, constants:BUFFER_USAGE_UNIFORM_BUFFER_BIT)
```

**Filling it in `End`.** The lines

```
Number32BitArray projectionViewMatrix = MatrixToArray(camera:GetCombinedMatrix())
        currentCameraMapping:Set(projectionViewMatrix)
```

become:

```
        Number32BitArray projectionViewMatrix = MatrixToArray(camera:GetCombinedMatrix())
        FillCameraData(projectionViewMatrix, graphics)
        currentCameraMapping:Set(cameraDataArray)
```

**The new private action,** after `MatrixToArray`:

```
    /*
    This action fills the 3D camera uniform's contents for this frame: the
    projection-view matrix, the camera's position, the shader time (moved on
    by this frame's length), the screen size, and the camera's near and far
    planes (Item 38).

    Attribute: Parameter projectionViewMatrix The matrix, as 16 numbers.
    Attribute: Parameter graphics The Vulkan graphics.
    */
    private action FillCameraData(Number32BitArray projectionViewMatrix, VulkanGraphics graphics)
        integer i = 0
        repeat while i < 16
            cameraDataArray:Set(i, projectionViewMatrix:Get(i))
            i = i + 1
        end

        shaderTime = shaderTime + gameState:GetGame():GetSecondsBetweenFrames()
        if shaderTime >= SHADER_TIME_WRAP
            shaderTime = shaderTime - SHADER_TIME_WRAP
        end

        // GetPosition returns the camera's own vector, so nothing is made.
        Vector3 cameraPosition = camera:GetPosition()
        cameraDataArray:Set(16, cameraPosition:GetX())
        cameraDataArray:Set(17, cameraPosition:GetY())
        cameraDataArray:Set(18, cameraPosition:GetZ())
        cameraDataArray:Set(19, shaderTime)

        VulkanSwapchain frameSwapchain = graphics:GetSwapchain()
        cameraDataArray:Set(20, frameSwapchain:GetImageWidth())
        cameraDataArray:Set(21, frameSwapchain:GetImageHeight())
        cameraDataArray:Set(22, camera:GetNear())
        cameraDataArray:Set(23, camera:GetFar())
    end
```

`Camera` has no `GetX`; `GetPosition` returns its own `position` field
(checked), so no new object is made each frame. `graphics` and
`currentCameraMapping` are already defined in `End`, where these lines are.
`Vector3` is already used by the painter.

### `G/Vulkan/VulkanPipelineInfoCreator.quorum`, `AddDefaultInfo3D`

```
        // Add a uniform for the camera, used during the vertex shader stage.
        AddDescriptorSetLayoutBinding(constants:SHADER_STAGE_VERTEX_BIT, constants:DESCRIPTOR_TYPE_UNIFORM_BUFFER)
```

becomes:

```
        // Add a uniform for the camera: the projection-view matrix, and the
        // camera's position, time, screen size and near and far planes, for
        // vertex and fragment shaders (Item 38). This must match the 3D
        // painter's camera layout.
        AddDescriptorSetLayoutBinding(constants:SHADER_STAGE_VERTEX_BIT + constants:SHADER_STAGE_FRAGMENT_BIT, constants:DESCRIPTOR_TYPE_UNIFORM_BUFFER)
```

### `G/Shaders/Vulkan/Vertex/DefaultVertexShader3DVulkan.quorum`

The block

```glsl
layout(set = 0, binding = 0) uniform Camera
{
    mat4 projectionViewMatrix;
} camera;
```

becomes:

```glsl
// The 3D camera uniform (Item 38). Only the matrix is used here; the rest
// is for shaders that need time or the camera's position, such as water.
layout(set = 0, binding = 0) uniform Camera
{
    mat4 projectionViewMatrix;
    vec3 cameraPosition;
    float time;
    vec2 screenSize;
    float nearPlane;
    float farPlane;
} camera;
```

**How other 3D shaders use it.** A custom shader that wants these values,
vertex or fragment, declares the same block at set 0, binding 0. The
`G/Shaders/Vulkan/...` 2D shaders have their own `Camera` block from the 2D
painter, and are not affected.

## What changes

**Nothing on screen.** This only makes values available.

**Memory:** 32 more bytes per frame slot.

**Cost:** 8 more numbers written each frame.

## Test plan

1. **DriveOpen, TerrainWalk, MSAACheck, SkyboxCheck, SpotlightCheck:**
   everything draws as before, including the splatted terrain (a custom
   program, so its pipeline layout must still match the painter's set).
2. **With the Vulkan validation layer on, if available:** no
   descriptor-set or pipeline-layout mismatch messages.
3. **Water (Item 39)** will be the first real user. Until then the values
   can be seen by temporarily tinting a fragment shader with
   `fract(camera.time)`. That isn't part of this Item.

## Rollback

Revert the Item 38 changes in the three files.
