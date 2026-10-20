# Item 39: the water pass and WaterSurface (water, phase 2)

**Status (2026-10-19): for review.** Nothing is applied yet. This is phase 2
of `WaterPlan.md`, with its recommended answers:
- decision 1: a general **forward** stage that any program can use, not
  water only;
- decision 3: depth color, shore fade, ripples and sun glint first; the sky
  reflection is Item 41;
- decision 5: the water classes go in `Libraries.Game.Graphics.Worlds`,
  beside the terrain, in the project for now (Item 71 moves them).

**Needs Item 38 first.** The water shader reads time and the camera's
position from the camera uniform, and the forward layout uses Item 38's
stage flags for it.

**Branch:** whichever is checked out in `quorum-language` (`MakeAWish` now).
It never switches.

**Scope:** Vulkan only. **OpenGL is not touched** (Item 68 is OpenGL water).
Under OpenGL, `WaterShaderProgram:Install` alerts.

Paths: **G/** = `Quorum/Library/Standard/Libraries/Game/Graphics/`,
**P** = `G/Vulkan/VulkanPainter3D.quorum`, **W/** =
`AllTerrainVehicle/SourceCode/Worlds/`.

## How it works

**The frame today:** scene (G-buffer), shadows, lighting into the lit image,
then the result pass (sky, then the lit image over it).

**After this Item:** the lighting render pass draws its full-screen
triangle, then, **in the same pass**, draws every *forward* program's
models over the lit image, blended. Nothing else changes:
- no new render pass, framebuffer or image;
- the G-buffer and shadows don't see forward models: they aren't drawn in
  the scene pass and don't cast shadows;
- with nothing forward in the scene, the frame is exactly as before.

**Why inside the lighting pass:** the lit image is already its color
attachment, at one sample, and the G-buffer images are already readable
there (the lighting draw samples them). So a forward draw needs no barrier
and no new pass.

**A forward program** is any custom 3D program whose mapping says
`UsesForwardPass()`. Its pipeline is made with `AddForwardInfo3D`, which
gives it this layout:

| Set | Holds | Bound by the painter from |
|---|---|---|
| 0 | camera uniform (Item 38) + the immutable sampler | the frame's camera set, as in the scene pass |
| 1 | the global textures | the queue's texture group, as in the scene pass |
| 2 | the G-buffer: position, albedo, normal, PBR | the lighting pass's set 0 (`lightDescriptors`) |
| 3 | lights and scene data | the lighting pass's set 1 (`environment:GetLightDataDescriptorSet`) |

Sets 2 and 3 are made with exactly the bindings the lighting pass's sets
use, so the same descriptor sets bind to both pipelines. (Item 41 adds set 4,
the sky cube.)

**Push constants: 128 bytes,** the most every device allows:

| Bytes | Holds | Written by |
|---|---|---|
| 0 to 7 | the queue's instance buffer address | the painter, as in the scene pass |
| 8 to 79 | the program's own 18 numbers | the program's mapping, `FillForwardData` |
| 80 to 127 | 12 numbers of scene data for forward programs | the painter: zeros here; Item 41 fills them with the sky's rotation |

The buffer is made at exactly 128 bytes, since `SetPushConstantsCommand`
pushes the buffer's whole capacity.

**The pipeline:**
- one color attachment, blended: color by source alpha, and alpha so it
  only grows (`ONE`, `ONE_MINUS_SOURCE_ALPHA`);
- no depth test or write (the pass has no depth); the shader compares with
  the G-buffer position instead;
- no culling, so water is seen from below too;
- one sample, as the lighting pass.

### The water shader, per pixel

1. **What is behind:** the G-buffer position at this pixel
   (`texelFetch` at `gl_FragCoord`), divided by its coverage, as the
   lighting pass does for MSAA edges.
   - Ground **in front** of the water (closer to the camera): the pixel is
     discarded.
   - **Nothing** behind (sky): the water is fully opaque, deep colored. This
     is open sea past the land. It must be opaque there, because the result
     pass blends the lit image over the sky by its alpha.
2. **Depth and thickness:**
   - *depth* is how far the ground is below the surface, straight down;
   - *thickness* is how much water the eye looks through, along the view
     ray.
3. **Color:** shallow to deep color by `1 - exp(-depth × clarity)`.
4. **Opacity:** shallow alpha to deep alpha by `1 - exp(-thickness ×
   clarity)`, so looking across water shows less of the bottom than
   looking down into it.
5. **Shore fade:** opacity × `depth / shoreFade`, clamped, so the edge is
   soft.
6. **Ripples:** a generated, tileable normal map, read twice, at two
   scales, moving in two directions with time. The two are added as slopes.
7. **Light:** ambient, plus each light (directional, point, spot) with
   Cook-Torrance and water's reflectance (0.02). Point lights and
   spotlights use the same range fade and cone as the lighting pass, so
   headlights shine on water. **No shadows on water yet.**
8. **The glint stays visible on clear water:** the reflected light is added
   on top of the water's own color, and raises the alpha by its own
   brightness. So a sun glint on almost clear shallows still shows.

### The water classes (project, W/)

- **`WaterShaderProgram`:** the program and every water setting. One
  program per look; every `WaterSurface` given it shares its settings. It
  makes its own normal map when installed.
- **`WaterShaderMapping`:** the forward mapping; hands the program's
  settings to the painter each frame.
- **`WaterFragmentShader`:** the shader above.
- **`WaterSurface`:** a `Model`: a flat plane drawn with a water program.

**Why settings are per program and not per model:** a forward program's
models are drawn in one indirect draw per texture group, with one set of
push constants. Per-model settings would need a new per-model buffer. One
program per look is enough for a sea and lakes.

## The code: library

### 1. `G/Shaders/Vulkan/Mapping/VulkanShaderMapping.quorum`

**New `use`,** after `use Libraries.Game.Graphics.Vulkan.VulkanCommandBuffer`:

```
use Libraries.Containers.Number32BitArray
```

**New field,** after `boolean useDefaultResources3D = false`:

```
    // A forward program draws after the deferred lighting, over the lit
    // image, instead of into the G-buffer (Item 39). Water is one.
    boolean forwardPass = false
```

**New actions,** after `UseDefaultResources3D`:

```
    /*
    This action returns true if the program draws after the deferred
    lighting, over the lit image, instead of into the G-buffer: a forward
    program, such as water (Item 39). Its pipeline should be made with
    VulkanPipelineInfoCreator:AddForwardInfo3D.

    Attribute: Returns True for a forward program.
    */
    action UsesForwardPass returns boolean
        return forwardPass
    end

    /*
    This action sets whether the program draws after the deferred lighting,
    over the lit image (Item 39). A forward program's models aren't drawn
    into the G-buffer and cast no shadows.

    Attribute: Parameter forward True for a forward program.
    */
    action UseForwardPass(boolean forward)
        forwardPass = forward
    end

    /*
    This action fills a forward program's own push constant data for the
    frame: 18 numbers, sent after the instance buffer address (Item 39).
    The painter sets them all to 0 first, so a mapping only sets the ones it
    uses. The shader reads them, in order, after the address. Mappings that
    aren't forward don't need it.

    Attribute: Parameter program The program being drawn.
    Attribute: Parameter data The 18 numbers to fill.
    */
    action FillForwardData(ShaderProgram program, Number32BitArray data)
    end
```

### 2. `G/Vulkan/VulkanPipelineInfoCreator.quorum`

**New action,** after `AddDefaultInfo3D`:

```
    /*
    This action adds the resources for a forward 3D program (Item 39): one
    drawn by the VulkanPainter3D after the deferred lighting, over the lit
    image, such as water. It uses the default 3D vertex data, so the
    default 3D vertex shader works with it. Its layout is:
    - set 0: the camera uniform and the immutable sampler, as in
      AddDefaultInfo3D;
    - set 1: the global textures;
    - set 2: the G-buffer: position, albedo, normal and PBR samplers;
    - set 3: the lights (a storage buffer) and the scene data (a uniform).
    Its push constants are 128 bytes: the instance buffer address, then 18
    numbers from the mapping's FillForwardData, then 12 numbers of scene
    data from the painter. It blends over the lit image, with no depth test
    and no culling.

    The program's mapping must also say UseDefaultResources3D(true) and
    UseForwardPass(true).
    */
    action AddForwardInfo3D
        CheckHasBegun()

        GameStateManager gameState
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        VulkanTextureManager textureManager = graphics:GetTextureManager()

        VulkanConstants constants

        // One color attachment, the lit image. Color blends by the source's
        // alpha; alpha only grows, so the water over the sky stays as
        // opaque as the water.
        VulkanPipelineColorBlendAttachmentState litBlend
        litBlend:SetBlendEnable(true)
        litBlend:SetSourceColorBlendFactor(constants:BLEND_FACTOR_SOURCE_ALPHA)
        litBlend:SetDestinationColorBlendFactor(constants:BLEND_FACTOR_ONE_MINUS_SOURCE_ALPHA)
        litBlend:SetColorBlendOp(constants:BLEND_OP_ADD)
        litBlend:SetSourceAlphaBlendFactor(constants:BLEND_FACTOR_ONE)
        litBlend:SetDestinationAlphaBlendFactor(constants:BLEND_FACTOR_ONE_MINUS_SOURCE_ALPHA)
        litBlend:SetAlphaBlendOp(constants:BLEND_OP_ADD)
        colorBlendAttachments:Add(litBlend)

        AddDynamicViewport()
        AddDynamicScissor()

        // Set 0: the camera uniform (Item 38) and the immutable sampler,
        // exactly as AddDefaultInfo3D, so the painter's camera set binds.
        AddDescriptorSetLayoutBinding(constants:SHADER_STAGE_VERTEX_BIT + constants:SHADER_STAGE_FRAGMENT_BIT, constants:DESCRIPTOR_TYPE_UNIFORM_BUFFER)
        VulkanDescriptorSetLayoutBinding samplerBinding = AddDescriptorSetLayoutBinding(constants:SHADER_STAGE_FRAGMENT_BIT, constants:DESCRIPTOR_TYPE_SAMPLER)
        Array<VulkanSampler> immutableSamplers
        immutableSamplers:Add(textureManager:GetDefaultSampler())
        samplerBinding:SetImmutableSamplers(immutableSamplers)

        // Set 1: the global textures.
        AddDescriptorSetLayout(textureManager:GetGlobalTextureDescriptorSetLayout())

        // Set 2: the G-buffer, with the same bindings as the lighting pass's
        // set 0, so the painter binds the same descriptor sets.
        repeat 4 times
            AddDescriptorSetLayoutBinding(constants:SHADER_STAGE_FRAGMENT_BIT, constants:DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER)
        end
        FinishDescriptorSetLayout()

        // Set 3: the lights and scene data, as the lighting pass's set 1.
        AddDescriptorSetLayoutBinding(constants:SHADER_STAGE_FRAGMENT_BIT, constants:DESCRIPTOR_TYPE_STORAGE_BUFFER)
        AddDescriptorSetLayoutBinding(constants:SHADER_STAGE_FRAGMENT_BIT, constants:DESCRIPTOR_TYPE_UNIFORM_BUFFER)
        FinishDescriptorSetLayout()

        // 128 bytes: the address, the program's 18 numbers, and the
        // painter's 12. The painter's buffer is exactly this size.
        VulkanPushConstantRange pushConstants
        pushConstants:SetSize(128)
        pushConstants:SetStage(constants:SHADER_STAGE_VERTEX_BIT + constants:SHADER_STAGE_FRAGMENT_BIT)
        pushConstants:Create()
        SetPushConstantRange(pushConstants)

        // The lighting pass has no depth; the shader compares with the
        // G-buffer position instead. Water is seen from below too.
        info:SetDepthTestEnable(false)
        info:SetDepthWriteEnable(false)
        info:SetCullMode(constants:CULL_MODE_NONE)
    end
```

Every type here is already used by `AddDefaultInfo3D` in the same file.

### 3. P (`G/Vulkan/VulkanPainter3D.quorum`)

**New fields,** after `VulkanPushConstantBuffer pushConstants`:

```
    // Forward programs (Item 39), such as water, draw in the lighting pass
    // after the lighting. Their push constants are 128 bytes: the instance
    // address, the program's 18 numbers, then 12 numbers of scene data.
    VulkanPushConstantBuffer forwardPushConstants = undefined
    Number32BitArray forwardProgramData
    constant integer FORWARD_PUSH_CONSTANT_SIZE = 128
    constant integer FORWARD_PROGRAM_DATA_SIZE = 18
    constant integer FORWARD_SCENE_DATA_SIZE = 12
```

**`on create`.** After `pushConstants:Create(8)`, add:

```
        forwardProgramData:SetSize(FORWARD_PROGRAM_DATA_SIZE)
```

**The scene pass's custom-program loop** (in `End`, after "Then draw the
models that have their own shader programs"). The line

```
            if HasDrawCommands(programQueues)
                VulkanShaderProgram programStrategy = cast(VulkanShaderProgram, program:GetShaderProgramStrategy())
                if NeedsPipeline(programStrategy:GetPipeline(), sceneSampleCount)
```

becomes:

```
            // Forward programs draw later, in the lighting pass (Item 39).
            if HasDrawCommands(programQueues) and not IsForwardProgram(program)
                VulkanShaderProgram programStrategy = cast(VulkanShaderProgram, program:GetShaderProgramStrategy())
                if NeedsPipeline(programStrategy:GetPipeline(), sceneSampleCount)
```

**The shadow queues.** The loop

```
        programIndex = 0
        repeat while programIndex < customPrograms:GetSize()
            Array<VulkanDrawQueue3D> programQueues = GetCurrentProgramQueues(customPrograms:Get(programIndex))
            queueCounter = 0
            repeat while queueCounter < programQueues:GetSize()
                shadowQueues:Add(programQueues:Get(queueCounter))
                queueCounter = queueCounter + 1
            end
            programIndex = programIndex + 1
        end
```

becomes:

```
        programIndex = 0
        repeat while programIndex < customPrograms:GetSize()
            // Forward models, such as water, cast no shadows (Item 39).
            if not IsForwardProgram(customPrograms:Get(programIndex))
                Array<VulkanDrawQueue3D> programQueues = GetCurrentProgramQueues(customPrograms:Get(programIndex))
                queueCounter = 0
                repeat while queueCounter < programQueues:GetSize()
                    shadowQueues:Add(programQueues:Get(queueCounter))
                    queueCounter = queueCounter + 1
                end
            end
            programIndex = programIndex + 1
        end
```

**The lighting pass.** The lines

```
        DrawCommand lightDrawCommand
        lightDrawCommand:SetVertexCount(3)
        commandBuffer:Record(lightDrawCommand)

        // End the render pass.
        EndRenderPassCommand endLightRenderPass
```

become:

```
        DrawCommand lightDrawCommand
        lightDrawCommand:SetVertexCount(3)
        commandBuffer:Record(lightDrawCommand)

        // Then the forward programs, such as water, over the lit image, in
        // the same pass (Item 39).
        RecordForwardPrograms(commandBuffer, swapchain, resourceIndex, currentCameraDescriptor)

        // End the render pass.
        EndRenderPassCommand endLightRenderPass
```

`currentCameraDescriptor`, `swapchain` and `resourceIndex` are already
defined earlier in `End`.

**New private actions,** after `CheckCustomProgram`:

```
    /*
    This action returns true if a program draws after the deferred
    lighting, over the lit image, such as water (Item 39).

    Attribute: Parameter program The program.
    Attribute: Returns True for a forward program.
    */
    private action IsForwardProgram(ShaderProgram program) returns boolean
        VulkanShaderProgram strategy = cast(VulkanShaderProgram, program:GetShaderProgramStrategy())
        return strategy:GetShaderMapping():UsesForwardPass()
    end

    /*
    This action draws the forward programs' models, such as water, in the
    lighting pass, after the lighting (Item 39). Each program's pipeline is
    made for the lighting pass. The camera and textures are bound as in the
    scene pass, the G-buffer and light data as in the lighting pass, and
    the push constants carry the instance address, the program's own data
    and the forward scene data.

    Attribute: Parameter commandBuffer The frame's command buffer, in the lighting pass.
    Attribute: Parameter swapchain The swapchain.
    Attribute: Parameter resourceIndex The frame slot.
    Attribute: Parameter cameraDescriptor The frame's camera descriptor set.
    */
    private action RecordForwardPrograms(VulkanCommandBuffer commandBuffer, VulkanSwapchain swapchain, integer resourceIndex, VulkanDescriptorSet cameraDescriptor)
        VulkanConstants constants
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        VulkanTextureManager textureManager = graphics:GetTextureManager()

        integer programIndex = 0
        repeat while programIndex < customPrograms:GetSize()
            ShaderProgram program = customPrograms:Get(programIndex)
            Array<VulkanDrawQueue3D> programQueues = GetCurrentProgramQueues(program)
            if IsForwardProgram(program) and HasDrawCommands(programQueues)
                VulkanShaderProgram strategy = cast(VulkanShaderProgram, program:GetShaderProgramStrategy())
                if NeedsPipeline(strategy:GetPipeline(), lightRenderPass:GetSampleCount())
                    strategy:CreatePipeline(lightRenderPass)
                end
                VulkanPipeline pipeline = strategy:GetPipeline()
                VulkanPipelineLayout layout = pipeline:GetInfo():GetLayout()

                BindPipelineCommand bindPipeline
                bindPipeline:SetPipeline(pipeline)
                commandBuffer:Record(bindPipeline)
                SetViewportAndScissor(commandBuffer, swapchain)

                BindDescriptorSetCommand cameraBind
                cameraBind:SetPipelineLayout(layout)
                cameraBind:SetDescriptorSet(cameraDescriptor)
                commandBuffer:Record(cameraBind)

                BindDescriptorSetCommand gBufferBind
                gBufferBind:SetPipelineLayout(layout)
                gBufferBind:SetDescriptorSet(lightDescriptors:Get(resourceIndex))
                gBufferBind:SetSetIndex(2)
                commandBuffer:Record(gBufferBind)

                BindDescriptorSetCommand lightDataBind
                lightDataBind:SetPipelineLayout(layout)
                lightDataBind:SetDescriptorSet(environment:GetLightDataDescriptorSet(resourceIndex))
                lightDataBind:SetSetIndex(3)
                commandBuffer:Record(lightDataBind)

                // The program's own numbers, the same for all its queues.
                integer slot = 0
                repeat while slot < FORWARD_PROGRAM_DATA_SIZE
                    forwardProgramData:Set(slot, 0)
                    slot = slot + 1
                end
                strategy:GetShaderMapping():FillForwardData(program, forwardProgramData)

                if forwardPushConstants = undefined
                    VulkanPushConstantBuffer buffer
                    buffer:Create(FORWARD_PUSH_CONSTANT_SIZE)
                    forwardPushConstants = buffer
                end

                integer group = 0
                repeat while group < programQueues:GetSize()
                    VulkanDrawQueue3D queue = programQueues:Get(group)
                    if queue not= undefined and queue:GetDrawCommandCount() > 0
                        BindDescriptorSetCommand texturesBind
                        texturesBind:SetPipelineLayout(layout)
                        texturesBind:SetDescriptorSet(textureManager:GetGlobalTextureDescriptorSet(group))
                        texturesBind:SetSetIndex(1)
                        commandBuffer:Record(texturesBind)

                        forwardPushConstants:ResetWritePosition()
                        forwardPushConstants:AddBufferPointer(queue:GetInstanceDataBuffer())
                        slot = 0
                        repeat while slot < FORWARD_PROGRAM_DATA_SIZE
                            forwardPushConstants:AddNumber32Bit(forwardProgramData:Get(slot))
                            slot = slot + 1
                        end
                        // The forward scene data: unused until Item 41.
                        repeat FORWARD_SCENE_DATA_SIZE times
                            forwardPushConstants:AddNumber32Bit(0)
                        end

                        SetPushConstantsCommand setPushConstants
                        setPushConstants:SetData(forwardPushConstants)
                        setPushConstants:SetPipelineLayout(layout)
                        setPushConstants:SetStageFlags(constants:SHADER_STAGE_VERTEX_BIT + constants:SHADER_STAGE_FRAGMENT_BIT)
                        commandBuffer:Record(setPushConstants)

                        DrawIndirectCommand draw
                        draw:SetDrawCommands(queue:GetDrawCommandBuffer())
                        draw:SetDrawCount(queue:GetDrawCommandCount())
                        commandBuffer:Record(draw)
                    end
                    group = group + 1
                end
            end
            programIndex = programIndex + 1
        end
    end
```

**What doesn't change in P:**
- Forward models go into their program's queues as any custom program's
  do (`GetBatch`, `GetProgramBatch`, `CheckCustomProgram`), and the queues
  are reset and filled as before. `CheckCustomProgram` still requires
  `UsesDefaultResources3D`, which the water mapping sets.
- The lighting pipeline's own binds are untouched. The forward binds come
  after its draw, so the lighting draw sees exactly what it did.
- Resizes and MSAA changes: the lighting pass is made again
  compatibly at one sample, so the forward pipelines, like the lighting
  pipeline, stay valid. `NeedsPipeline` remakes them if the sample count
  ever differs.

## The code: project (`Libraries.Game.Graphics.Worlds`, W/)

### 4. `W/WaterShaderMapping.quorum` (new)

```
package Libraries.Game.Graphics.Worlds

use Libraries.Game.Graphics.Shaders.Vulkan.Mapping.VulkanShaderMapping
use Libraries.Game.Graphics.Shaders.Vulkan.VulkanShaderProgram
use Libraries.Game.Graphics.Shaders.Programs.ShaderProgram
use Libraries.Game.Graphics.Vulkan.VulkanDevice
use Libraries.Game.Graphics.Vulkan.VulkanPipelineInfo
use Libraries.Game.Graphics.Vulkan.VulkanPipelineInfoCreator
use Libraries.Containers.Number32BitArray

/*
WaterShaderMapping describes the water program's Vulkan pipeline: a forward
program (library item 39), drawn after the deferred lighting, over the lit
image, with the default 3D vertex data, the G-buffer and the lights. Each
frame it gives the painter the water program's settings.

Attribute: Example
use Libraries.Game.Graphics.Worlds.WaterShaderMapping

WaterShaderMapping mapping
*/
class WaterShaderMapping is VulkanShaderMapping
    on create
        UseDefaultResources3D(true)
        UseForwardPass(true)
    end

    /*
    This action makes the pipeline description for water.

    Attribute: Parameter program The water program.
    Attribute: Parameter device The Vulkan device.
    Attribute: Returns The pipeline description.
    */
    action CreatePipelineInfo(VulkanShaderProgram program, VulkanDevice device) returns VulkanPipelineInfo
        VulkanPipelineInfoCreator creator
        creator:Begin(device)
        creator:AddForwardInfo3D()
        return creator:Finish()
    end

    /*
    This action gives the painter the water program's 18 settings for the
    frame.

    Attribute: Parameter program The program being drawn.
    Attribute: Parameter data The 18 numbers to fill.
    */
    action FillForwardData(ShaderProgram program, Number32BitArray data)
        if program is WaterShaderProgram
            WaterShaderProgram water = cast(WaterShaderProgram, program)
            water:FillData(data)
        end
    end
end
```

### 5. `W/WaterShaderProgram.quorum` (new)

```
package Libraries.Game.Graphics.Worlds

use Libraries.Game.GameStateManager
use Libraries.Game.Graphics.Shaders.ShaderManager
use Libraries.Game.Graphics.Shaders.Programs.ShaderProgram
use Libraries.Game.Graphics.Vulkan.VulkanGraphics
use Libraries.Game.Graphics.Color
use Libraries.Game.Graphics.Texture
use Libraries.Game.Graphics.PixelMap
use Libraries.Game.Graphics.Format
use Libraries.Containers.Number32BitArray
use Libraries.Compute.Math

/*
WaterShaderProgram draws water: lakes and seas over the terrain. It is a
forward program (library item 39): drawn after the lighting, over what is
already there, so it can look through to the ground below. Deeper water is
darker, the edge fades softly into the shore, ripples move with time, and
the sun and lamps glint on it.

The program holds every setting. Give it to WaterSurfaces with their Load
action; every surface using one program looks the same. Install it once,
before the first surface is loaded. It needs Vulkan.

Attribute: Example
use Libraries.Game.Game
use Libraries.Game.Graphics.Worlds.WaterShaderProgram
use Libraries.Game.Graphics.Worlds.WaterSurface

class Main is Game
    WaterShaderProgram water
    WaterSurface lake

    action Main
        StartGame()
    end

    action CreateGame
        water:Install()
        water:SetClarity(0.3)
        lake:Load(40, 40, water)
        lake:SetPosition(0, 2, 0)
        Add(lake)
    end
end
*/
class WaterShaderProgram is ShaderProgram
    WaterFragmentShader waterFragment
    Texture normalMap = undefined
    Color shallowColor = undefined
    Color deepColor = undefined
    number waveScale = 8
    number waveSpeed = 0.6
    number waveDirectionX = 1
    number waveDirectionZ = 0.35
    number clarity = 0.35
    number shoreFade = 0.5
    number roughness = 0.06
    number reflectionStrength = 1
    number normalStrength = 1
    // The generated normal map's size, in pixels; it tiles.
    constant integer NORMAL_MAP_SIZE = 128
    Math math

    on create
        Color colors
        shallowColor = colors:CustomColor(0.10, 0.42, 0.40, 0.25)
        deepColor = colors:CustomColor(0.02, 0.10, 0.16, 0.92)
    end

    /*
    This action compiles the program as "Water Shader Program" and makes
    its ripple texture. Call it once, before loading any WaterSurface with
    it.
    */
    action Install
        Install("Water Shader Program")
    end

    /*
    This action compiles the program under a name, and makes its ripple
    texture. Each program installed needs its own name.

    Attribute: Parameter programName The name to register the program under.
    */
    action Install(text programName)
        GameStateManager gameState
        if not (gameState:GetGameGraphics() is VulkanGraphics)
            alert("Water needs Vulkan for now; OpenGL water is a later step (Item 68).")
        end
        ShaderManager manager = gameState:GetShaderManager()
        SetName(programName)
        Add(manager:GetDefaultVertexShader3D())
        Add(waterFragment)
        WaterShaderMapping mapping
        SetShaderMapping(mapping)
        Compile()
        if normalMap = undefined
            normalMap = MakeNormalMap()
        end
    end

    /*
    This action returns the ripple texture: a normal map that tiles,
    made when the program is installed.

    Attribute: Returns The normal map, or undefined before Install.
    */
    action GetNormalMap returns Texture
        return normalMap
    end

    /*
    This action sets the color of shallow water, and its alpha is how
    much of the ground shows through it, from 0 (all of it) to 1 (none).

    Attribute: Parameter color The shallow color.
    */
    action SetShallowColor(Color color)
        shallowColor = color
    end

    /*
    This action returns the color of shallow water.

    Attribute: Returns The shallow color.
    */
    action GetShallowColor returns Color
        return shallowColor
    end

    /*
    This action sets the color of deep water, and its alpha is how much of
    the ground shows through deep water, from 0 (all of it) to 1 (none).

    Attribute: Parameter color The deep color.
    */
    action SetDeepColor(Color color)
        deepColor = color
    end

    /*
    This action returns the color of deep water.

    Attribute: Returns The deep color.
    */
    action GetDeepColor returns Color
        return deepColor
    end

    /*
    This action sets how quickly the water darkens and hides the ground
    as it gets deeper. 0 is perfectly clear; 1 is muddy within a meter or
    so.

    Attribute: Parameter value How murky the water is, 0 or more.
    */
    action SetClarity(number value)
        if value < 0
            value = 0
        end
        clarity = value
    end

    /*
    This action returns how quickly the water darkens with depth.

    Attribute: Returns The value from SetClarity.
    */
    action GetClarity returns number
        return clarity
    end

    /*
    This action sets how deep the water is, in world units, before its edge
    stops fading into the shore. 0 gives a hard edge.

    Attribute: Parameter depth The depth over which the edge fades.
    */
    action SetShoreFade(number depth)
        if depth < 0
            depth = 0
        end
        shoreFade = depth
    end

    /*
    This action returns the depth over which the edge fades.

    Attribute: Returns The value from SetShoreFade.
    */
    action GetShoreFade returns number
        return shoreFade
    end

    /*
    This action sets how many world units one tile of the larger ripples
    covers. The smaller ripples are a little under half that.

    Attribute: Parameter size The size of a ripple tile, more than 0.
    */
    action SetWaveScale(number size)
        if size <= 0
            alert("The wave scale must be more than 0, but was given " + size + ".")
        end
        waveScale = size
    end

    /*
    This action returns the size of a ripple tile.

    Attribute: Returns The value from SetWaveScale.
    */
    action GetWaveScale returns number
        return waveScale
    end

    /*
    This action sets how fast the ripples move, in world units a second.

    Attribute: Parameter speed The ripples' speed.
    */
    action SetWaveSpeed(number speed)
        waveSpeed = speed
    end

    /*
    This action returns how fast the ripples move.

    Attribute: Returns The value from SetWaveSpeed.
    */
    action GetWaveSpeed returns number
        return waveSpeed
    end

    /*
    This action sets the way the wind pushes the ripples, along the ground.
    Only the direction matters.

    Attribute: Parameter x The direction's x part.
    Attribute: Parameter z The direction's z part.
    */
    action SetWaveDirection(number x, number z)
        waveDirectionX = x
        waveDirectionZ = z
    end

    /*
    This action sets how rough the surface is for glints: small values give
    sharp sun glints, larger ones a broad sheen.

    Attribute: Parameter value The roughness, from 0.02 to 1.
    */
    action SetRoughness(number value)
        roughness = math:Clamp(value, 0.02, 1)
    end

    /*
    This action returns the surface's roughness.

    Attribute: Returns The value from SetRoughness.
    */
    action GetRoughness returns number
        return roughness
    end

    /*
    This action sets how much of the sky the water reflects (library item
    41), from 0 for none to 1 for all the physics allows.

    Attribute: Parameter strength The reflection's strength.
    */
    action SetReflectionStrength(number strength)
        reflectionStrength = math:Clamp(strength, 0, 1)
    end

    /*
    This action returns how much of the sky the water reflects.

    Attribute: Returns The value from SetReflectionStrength.
    */
    action GetReflectionStrength returns number
        return reflectionStrength
    end

    /*
    This action sets how strong the ripples look: 0 is a flat mirror, 1 is
    normal, and 2 is choppy.

    Attribute: Parameter strength The ripples' strength.
    */
    action SetNormalStrength(number strength)
        if strength < 0
            strength = 0
        end
        normalStrength = strength
    end

    /*
    This action returns how strong the ripples look.

    Attribute: Returns The value from SetNormalStrength.
    */
    action GetNormalStrength returns number
        return normalStrength
    end

    /*
    This action writes the settings, in the order WaterFragmentShader reads
    them: the shallow and deep colors, the waves (scale, speed, direction),
    the look (clarity, shore fade, roughness, reflection), and the ripples'
    strength. WaterShaderMapping calls it each frame.

    Attribute: Parameter data The 18 numbers to fill.
    */
    action FillData(Number32BitArray data)
        data:Set(0, shallowColor:GetRed())
        data:Set(1, shallowColor:GetGreen())
        data:Set(2, shallowColor:GetBlue())
        data:Set(3, shallowColor:GetAlpha())
        data:Set(4, deepColor:GetRed())
        data:Set(5, deepColor:GetGreen())
        data:Set(6, deepColor:GetBlue())
        data:Set(7, deepColor:GetAlpha())
        data:Set(8, waveScale)
        data:Set(9, waveSpeed)
        data:Set(10, waveDirectionX)
        data:Set(11, waveDirectionZ)
        data:Set(12, clarity)
        data:Set(13, shoreFade)
        data:Set(14, roughness)
        data:Set(15, reflectionStrength)
        data:Set(16, normalStrength)
        data:Set(17, 0)
    end

    /*
    This action makes the ripple texture: a normal map of the slopes of ten
    waves added together. Each wave fits a whole number of times across the
    texture, so it tiles with no seam. Each pixel's red and green are its
    slope along x and along the rows, and blue is up.

    Attribute: Returns The normal map, with mipmaps so distant water doesn't shimmer.
    */
    private action MakeNormalMap returns Texture
        // Each wave: how many times it fits across (x, then rows), its
        // height, and where it starts.
        Number32BitArray waves
        waves:SetSize(40)
        SetWave(waves, 0, 1, 2, 0.90, 0.3)
        SetWave(waves, 1, 2, -1, 0.80, 1.7)
        SetWave(waves, 2, -3, 1, 0.50, 4.1)
        SetWave(waves, 3, 1, 4, 0.45, 2.6)
        SetWave(waves, 4, 5, 2, 0.30, 5.3)
        SetWave(waves, 5, -4, -5, 0.25, 0.9)
        SetWave(waves, 6, 7, -3, 0.18, 3.4)
        SetWave(waves, 7, 3, 8, 0.15, 1.2)
        SetWave(waves, 8, -9, 5, 0.10, 4.8)
        SetWave(waves, 9, 11, 6, 0.08, 2.2)

        PixelMap map
        Format format
        format:SetValue(format:RGBA8888)
        map:CreatePixelMap(NORMAL_MAP_SIZE, NORMAL_MAP_SIZE, format)
        Color colors
        number step = 2 * math:pi / NORMAL_MAP_SIZE
        // How steep the slopes are made, before the shader's strength.
        number steepness = 2
        integer y = 0
        repeat while y < NORMAL_MAP_SIZE
            integer x = 0
            repeat while x < NORMAL_MAP_SIZE
                number slopeX = 0
                number slopeY = 0
                integer wave = 0
                repeat while wave < 10
                    number acrossX = waves:Get(wave * 4)
                    number acrossY = waves:Get(wave * 4 + 1)
                    number height = waves:Get(wave * 4 + 2)
                    number start = waves:Get(wave * 4 + 3)
                    number change = height * math:Cosine(step * (acrossX * x + acrossY * y) + start)
                    slopeX = slopeX + change * step * acrossX
                    slopeY = slopeY + change * step * acrossY
                    wave = wave + 1
                end
                number normalX = -slopeX * steepness
                number normalY = -slopeY * steepness
                number length = math:SquareRoot(normalX * normalX + normalY * normalY + 1)
                map:SetPixel(x, y, colors:CustomColor(0.5 + 0.5 * normalX / length, 0.5 + 0.5 * normalY / length,
                    0.5 + 0.5 / length, 1))
                x = x + 1
            end
            y = y + 1
        end
        Texture made
        made:LoadFromPixelMap(map, format, true)
        return made
    end

    /*
    This action stores one wave of the ripple texture.

    Attribute: Parameter waves The waves, four numbers each.
    Attribute: Parameter index Which wave.
    Attribute: Parameter acrossX How many times it fits across the texture's width.
    Attribute: Parameter acrossY How many times it fits down the texture's rows.
    Attribute: Parameter height Its height.
    Attribute: Parameter start Where it starts, in radians.
    */
    private action SetWave(Number32BitArray waves, integer index, number acrossX, number acrossY, number height, number start)
        waves:Set(index * 4, acrossX)
        waves:Set(index * 4 + 1, acrossY)
        waves:Set(index * 4 + 2, height)
        waves:Set(index * 4 + 3, start)
    end
end
```

**About the normal map's rows:** whether a pixel row runs along +z or −z
in the texture coordinates only mirrors the ripple pattern. The slopes
stay consistent with each other, so it can't look wrong on moving water.

### 6. `W/WaterFragmentShader.quorum` (new)

```
package Libraries.Game.Graphics.Worlds

use Libraries.Game.Graphics.Shaders.Shader

/*
WaterFragmentShader colors water (library item 39). It is drawn after the
deferred lighting, over the lit image, and reads the G-buffer's position to
see what is behind the water: deeper water is darker, the edge fades into
the shore, and water behind the ground is hidden. Two layers of ripples
move with time, and every light shines and glints on the surface. It
needs the camera data of library item 38.

Its settings come from WaterShaderProgram, through the push constants,
after the instance buffer address.

Attribute: Example
use Libraries.Game.Graphics.Worlds.WaterFragmentShader

WaterFragmentShader shader
*/
class WaterFragmentShader is Shader
    on create
        SetType(parent:Shader:FRAGMENT_SHADER)
        SetName("Water Fragment Shader")
        SetCode(GetVersionHeader() +
"
" +
"// Adds support for nonuniformEXT and unsized descriptor arrays.
#extension GL_EXT_nonuniform_qualifier : require
#extension GL_EXT_buffer_reference: require
#extension GL_EXT_buffer_reference2: enable
#extension GL_EXT_scalar_block_layout: require
#extension GL_EXT_shader_explicit_arithmetic_types_int64 : require

const float PI = 3.14159265359;
// How much light water reflects looking straight down.
const float WATER_REFLECTANCE = 0.02;

// The 3D camera uniform (library item 38).
layout(set = 0, binding = 0) uniform Camera
{
    mat4 projectionViewMatrix;
    vec3 cameraPosition;
    float time;
    vec2 screenSize;
    float nearPlane;
    float farPlane;
} camera;

layout(set = 0, binding = 1) uniform sampler immutableSampler;
layout(set = 1, binding = 0) uniform texture2D globalTextures[];

// The G-buffer's position: what is drawn behind or in front of the water.
layout(set = 2, binding = 0) uniform sampler2D positionSampler;

struct Light
{
	vec3 positionDirection;
	uint lightType;
	float intensity;
	vec3 color;
	vec3 spotDirection;
	float range;
	float cosInner;
	float cosOuter;
	vec2 spare;
};

layout(scalar, set = 3, binding = 0) readonly buffer Lights
{
	Light array[];
} lights;

layout(scalar, set = 3, binding = 1) uniform SceneInfo
{
	vec3 cameraPosition;
	float ambientIntensity;
	vec3 ambientColor;
	uint lightsCount;
	mat4 cameraViewMatrix;
} sceneInfo;

struct Material {
	uint diffuseColor;
	uint textureIndex;
	uint hasNormalMap;
	uint hasRoughMap;
	uint normalMapIndex;
	uint roughMapIndex;
	float roughness;
	float metallic;
	uint flags;
	float textureScale;
	uint reserved1;
	uint reserved2;
};

layout(scalar, buffer_reference) buffer Materials
{
	Material data;
};

struct InstanceData {
   uint vertexPadding1;
   uint vertexPadding2;
   uint indexPadding1;
   uint indexPadding2;
   Materials materials;
   uint textureOverride;
   uint textureIndex;
   uint diffuseColorOverride;
   uint diffuseColor;
   mat4 modelTransform;
};

layout(scalar, buffer_reference) buffer Instances {
   InstanceData[] data;
};

// 128 bytes (library item 39): the instance address, the water program's
// 18 numbers, then the painter's 12 numbers of forward scene data.
layout(scalar, push_constant) uniform PushConstants {
   Instances instances;
   // rgb, and how much of the ground it hides
   vec4 shallowColor;
   vec4 deepColor;
   // tile size, speed, direction x, direction z
   vec4 waves;
   // clarity, shore fade, roughness, reflection strength
   vec4 look;
   // ripple strength, spare
   vec2 detail;
   // The forward scene data: the sky's rotation (library item 41).
   vec3 skyColumn0;
   vec3 skyColumn1;
   vec3 skyColumn2;
   float skyInverter;
   float hasSky;
   float sceneSpare;
} water;

layout(location = 1) flat in uint v_entityID;
layout(location = 4) flat in uint v_hasTextureOverride;
layout(location = 5) flat in uint v_textureOverrideIndex;
layout(location = 6) in vec4 v_position;

layout(location = 0) out vec4 outputColor;

vec3 readRipples(uint normalMap, vec2 coordinates)
{
    return texture(nonuniformEXT(sampler2D(globalTextures[normalMap], immutableSampler)), coordinates).rgb * 2.0 - 1.0;
}

// The surface's normal: two layers of ripples, a larger one moving with
// the wind and a smaller one moving a little across it, added as slopes.
vec3 waterNormal(uint normalMap, vec3 surface)
{
    float scale = max(water.waves.x, 0.01);
    vec2 direction = water.waves.zw;
    if (dot(direction, direction) < 0.0001)
        direction = vec2(1.0, 0.0);
    direction = normalize(direction);
    vec2 across = normalize(direction + vec2(-direction.y, direction.x) * 0.6);
    float travel = water.waves.y * camera.time;

    float smallScale = scale * 0.43;
    vec2 coordinatesA = (surface.xz + direction * travel) / scale;
    vec2 coordinatesB = (surface.xz + across * travel * 0.8) / smallScale;
    vec3 a = readRipples(normalMap, coordinatesA);
    vec3 b = readRipples(normalMap, coordinatesB);

    // The map's red is the slope along x and its green along z, and blue
    // is up.
    vec2 slope = (a.xy + b.xy) * water.detail.x;
    return normalize(vec3(slope.x, a.z * b.z, slope.y));
}

// How much of a light's strength reaches a distance, as in the lighting
// pass (library item 37).
float rangeAttenuation(float distance, float range)
{
    float inverseSquare = 1.0 / max(distance * distance, 0.0001);
    if (range <= 0.0)
        return inverseSquare;
    float ratio = distance / range;
    float window = clamp(1.0 - ratio * ratio * ratio * ratio, 0.0, 1.0);
    return inverseSquare * window * window;
}

// One light on the water (Cook-Torrance, as the lighting pass, with
// water's reflectance). The light the water's color gives back goes to
// body, and the glint to glint.
void lightOnWater(vec3 L, vec3 radiance, vec3 V, vec3 N, vec3 waterColor, float roughness, inout vec3 body, inout vec3 glint)
{
    float NdotL = max(dot(N, L), 0.0);
    if (NdotL <= 0.0)
        return;
    vec3 H = normalize(V + L);
    float NdotV = max(dot(N, V), 0.0001);
    float NdotH = max(dot(N, H), 0.0);

    float a = roughness * roughness;
    float a2 = a * a;
    float d = NdotH * NdotH * (a2 - 1.0) + 1.0;
    float distribution = a2 / (PI * d * d + 0.0000001);
    float k = (roughness + 1.0) * (roughness + 1.0) / 8.0;
    float geometry = (NdotV / (NdotV * (1.0 - k) + k)) * (NdotL / (NdotL * (1.0 - k) + k));
    float fresnel = WATER_REFLECTANCE + (1.0 - WATER_REFLECTANCE) * pow(1.0 - max(dot(H, V), 0.0), 5.0);

    float specular = distribution * geometry * fresnel / (4.0 * NdotV * NdotL + 0.0001);
    body += (1.0 - fresnel) * waterColor / PI * radiance * NdotL;
    glint += specular * radiance * NdotL;
}

void main()
{
    Instances instances = water.instances;
    InstanceData instanceData = instances.data[v_entityID];
    Materials materials = instanceData.materials;
    Material material = materials.data;
    // The water's ripple texture is its plane's texture.
    uint normalMap = material.textureIndex;
    if (v_hasTextureOverride == 1u)
        normalMap = v_textureOverrideIndex;

    vec3 surface = v_position.xyz;
    vec3 toSurface = surface - camera.cameraPosition;
    float surfaceDistance = length(toSurface);
    vec3 V = -toSurface / max(surfaceDistance, 0.0001);

    // What was drawn at this pixel. The position's w is how much of the
    // pixel was covered (MSAA, library item 27), so dividing by it gives
    // the position back at the edges of models.
    vec4 behind = texelFetch(positionSampler, ivec2(gl_FragCoord.xy), 0);
    bool hasGround = behind.w > 0.0001;
    float thickness = 100000.0;
    float depth = 100000.0;
    if (hasGround)
    {
        vec3 ground = behind.xyz / behind.w;
        float groundDistance = length(ground - camera.cameraPosition);
        // Ground in front of the water hides it.
        if (groundDistance <= surfaceDistance)
            discard;
        thickness = groundDistance - surfaceDistance;
        depth = max(surface.y - ground.y, 0.0);
    }

    // Deeper water is darker. The more water the eye looks through, the
    // less of the ground shows.
    float clarity = max(water.look.x, 0.0);
    vec3 waterColor = mix(water.shallowColor.rgb, water.deepColor.rgb, 1.0 - exp(-depth * clarity));
    float opacity = mix(water.shallowColor.a, water.deepColor.a, 1.0 - exp(-thickness * clarity));
    // A soft edge where the water meets the shore.
    if (water.look.y > 0.0)
        opacity *= clamp(depth / water.look.y, 0.0, 1.0);
    // Over the sky, open water is opaque: the result pass blends the lit
    // image over the sky by its alpha.
    if (!hasGround)
        opacity = 1.0;

    vec3 N = waterNormal(normalMap, surface);
    // Seen from below, the surface faces down.
    if (V.y < 0.0)
        N.y = -N.y;
    float roughness = clamp(water.look.z, 0.02, 1.0);

    vec3 body = sceneInfo.ambientColor * sceneInfo.ambientIntensity * waterColor;
    vec3 glint = vec3(0.0);
    for (uint i = 0u; i < sceneInfo.lightsCount; i++)
    {
        Light light = lights.array[i];
        if (light.lightType == 1u)
        {
            lightOnWater(normalize(-light.positionDirection), light.color * light.intensity, V, N, waterColor, roughness, body, glint);
        }
        else
        {
            vec3 toLight = light.positionDirection - surface;
            float distance = length(toLight);
            vec3 L = toLight / max(distance, 0.0001);
            float strength = light.intensity * rangeAttenuation(distance, light.range);
            if (light.lightType == 2u)
            {
                float cosAngle = dot(-L, light.spotDirection);
                float cone = clamp((cosAngle - light.cosOuter) / max(light.cosInner - light.cosOuter, 0.0001), 0.0, 1.0);
                strength *= cone * cone;
            }
            if (strength > 0.0)
                lightOnWater(L, light.color * strength, V, N, waterColor, roughness, body, glint);
        }
    }

    // The glint is added on top, and shows even on clear water: the
    // blend gives color × alpha + behind × (1 - alpha), so the color is
    // divided by the alpha here.
    float glintAlpha = clamp(max(glint.r, max(glint.g, glint.b)), 0.0, 1.0);
    float alpha = clamp(opacity + glintAlpha * (1.0 - opacity), 0.0, 1.0);
    vec3 color = (body * opacity + glint) / max(alpha, 0.0001);
    outputColor = vec4(color, alpha);
}"
        )
    end
end
```

**Which inputs it reads:** it declares only the default vertex shader's
outputs it uses (locations 1, 4, 5 and 6). The others are written and
ignored, which Vulkan allows.

### 7. `W/WaterSurface.quorum` (new)

```
package Libraries.Game.Graphics.Worlds

use Libraries.Game.Graphics.Model

/*
WaterSurface is a flat sheet of water: a Model drawn with a
WaterShaderProgram, after the lighting, over the ground (library item 39).
Its look comes from the program. Place it at the water's level with
SetPosition, or SetLevel. Water has no collision.

Attribute: Example
use Libraries.Game.Game
use Libraries.Game.Graphics.Worlds.WaterShaderProgram
use Libraries.Game.Graphics.Worlds.WaterSurface

class Main is Game
    WaterShaderProgram water
    WaterSurface lake

    action Main
        StartGame()
    end

    action CreateGame
        water:Install()
        lake:Load(40, 40, water)
        lake:SetLevel(2)
        Add(lake)
    end
end
*/
class WaterSurface is Model
    WaterShaderProgram waterProgram = undefined

    /*
    This action makes the water a flat sheet, width along x and depth along
    z, centered on its position, drawn with a water program.

    Attribute: Parameter width The sheet's size along x.
    Attribute: Parameter depth The sheet's size along z.
    Attribute: Parameter program An installed water program.
    */
    action Load(number width, number depth, WaterShaderProgram program)
        if program = undefined or program:GetNormalMap() = undefined
            alert("A WaterSurface needs an installed WaterShaderProgram. Call the program's Install action first.")
        end
        waterProgram = program
        LoadPlane(width, depth, program:GetNormalMap())
        SetShaderProgram(program)
    end

    /*
    This action returns the water program the surface is drawn with.

    Attribute: Returns The water program, or undefined before Load.
    */
    action GetWaterProgram returns WaterShaderProgram
        return waterProgram
    end

    /*
    This action moves the surface up or down to a height, keeping it where
    it is along x and z.

    Attribute: Parameter level The water's height.
    */
    action SetLevel(number level)
        SetPosition(GetX(), level, GetZ())
    end

    /*
    This action returns the water's height.

    Attribute: Returns The surface's y position.
    */
    action GetLevel returns number
        return GetY()
    end
end
```

## The code: test program

### 8. `AllTerrainVehicle/SourceCode/WaterCheck.quorum` (new)

A pool scene with no terrain, so only water is being tested:
- a sand floor 6 units down;
- a ramp rising out of the water on one side, for the shore fade;
- a half-sunk ball and two posts;
- a 60 × 60 water sheet at height 0;
- the Day sky, the sun and ambient light.

```
use Libraries.Game.Game
use Libraries.Game.InputMonitor
use Libraries.Game.Graphics.Color
use Libraries.Game.Graphics.Model
use Libraries.Game.Graphics.Label
use Libraries.Game.Graphics.Skybox
use Libraries.Game.Graphics.AmbientLight
use Libraries.Game.Graphics.DirectionalLight
use Libraries.Game.Graphics.Worlds.WaterShaderProgram
use Libraries.Game.Graphics.Worlds.WaterSurface
use Libraries.Interface.Events.KeyboardEvent
use Libraries.Compute.Math

/*
WaterCheck tests the water pass (library item 39, Item39.md) on Vulkan: a
pool with a sloping ramp, a half-sunk ball and two posts, under the Day
sky.

What to see:
1. The deep middle is darker than the water over the ramp.
2. The water's edge on the ramp fades softly, with no hard line.
3. Looking down near the ramp shows the ramp through the water; looking
   across the pool shows less of the floor.
4. The ripples move along +x and a little across; Z and X change their
   speed, 0 stops them.
5. The sun glints on the water facing it, even over the clear shallows.
6. The ball and posts hide the water behind them, and their sunk parts
   show through it, darker the deeper they go.
7. U and J raise and lower the water: the shore line moves up and down the
   ramp.
8. Under the water (J until the camera is below it), the surface seen from
   below is drawn and lit.
9. With MSAA (M), the ball's edge against the water has no dark halo.

Keys: arrows turn and tilt, W S move, Page Up and Page Down rise and sink,
U J water level, C V clarity down and up, Z X wave speed, M MSAA.

Attribute: Example
// WaterCheck is a main program: set it as the project's main file and run
// it.
*/
class WaterCheck is Game
    Skybox skybox
    Label label
    InputMonitor monitor
    KeyboardEvent keys
    Math math
    DirectionalLight sun
    AmbientLight ambient
    WaterShaderProgram water
    WaterSurface pool
    Model floor
    Model ramp
    Model ball
    Model postA
    Model postB

    number cameraX = -18
    number cameraY = 5
    number cameraZ = -18
    number yaw = 45
    number pitch = -15
    number waterLevel = 0

    boolean mWasDown = false

    action Main
        SetScreenSize(1200, 700)
        UseVulkan(true)
        StartGame()
    end

    action CreateGame
        text folder = "Skyboxes/Day/"
        skybox:Load(folder + "right.png", folder + "left.png", folder + "top.png", folder + "bottom.png",
            folder + "front.png", folder + "back.png")
        SetSkybox(skybox)

        Color colors
        sun:SetColor(colors:White())
        sun:SetIntensity(2.5)
        sun:SetDirection(-1, -1.2, 2)
        Add(sun)
        ambient:SetColor(0.35, 0.38, 0.42, 1)
        SetAmbientLight(ambient)

        Color sand = colors:CustomColor(0.76, 0.68, 0.50, 1)
        floor:LoadBox(60, 1, 60, sand)
        floor:SetPosition(0, -6.5, 0)
        Add(floor)

        // A ramp from the floor up out of the water along +x.
        ramp:LoadBox(30, 1, 20, sand)
        ramp:SetPosition(18, -3, 0)
        ramp:Rotate(0, 0, 1, 18)
        Add(ramp)

        ball:LoadSphere(5, 5, 5, colors:CustomColor(0.8, 0.3, 0.2, 1))
        ball:SetPosition(-6, 0, 6)
        Add(ball)

        postA:LoadBox(1, 12, 1, colors:CustomColor(0.4, 0.4, 0.45, 1))
        postA:SetPosition(-10, -1, -8)
        Add(postA)
        postB:LoadBox(1, 12, 1, colors:CustomColor(0.4, 0.4, 0.45, 1))
        postB:SetPosition(4, -1, -12)
        Add(postB)

        water:Install()
        pool:Load(60, 60, water)
        pool:SetLevel(waterLevel)
        Add(pool)

        PlaceCamera()
        label:SetPosition(10, 10)
        label:SetText("Arrows turn, W S move, PgUp PgDn rise, U J water level, C V clarity, Z X wave speed, M MSAA")
        Add(label)
        output "Water check: started. The pool's middle should be darker than the ramp's shallows."
    end

    action Update(number seconds)
        number turnSpeed = 60
        if monitor:IsKeyPressed(keys:LEFT)
            yaw = yaw - turnSpeed * seconds
        end
        if monitor:IsKeyPressed(keys:RIGHT)
            yaw = yaw + turnSpeed * seconds
        end
        if monitor:IsKeyPressed(keys:UP)
            pitch = math:Clamp(pitch + turnSpeed * seconds, -89, 89)
        end
        if monitor:IsKeyPressed(keys:DOWN)
            pitch = math:Clamp(pitch - turnSpeed * seconds, -89, 89)
        end
        number moveSpeed = 8
        number yawRadians = math:DegreesToRadians(yaw)
        if monitor:IsKeyPressed(keys:W)
            cameraX = cameraX + math:Sine(yawRadians) * moveSpeed * seconds
            cameraZ = cameraZ + math:Cosine(yawRadians) * moveSpeed * seconds
        end
        if monitor:IsKeyPressed(keys:S)
            cameraX = cameraX - math:Sine(yawRadians) * moveSpeed * seconds
            cameraZ = cameraZ - math:Cosine(yawRadians) * moveSpeed * seconds
        end
        if monitor:IsKeyPressed(keys:PAGE_UP)
            cameraY = cameraY + moveSpeed * seconds
        end
        if monitor:IsKeyPressed(keys:PAGE_DOWN)
            cameraY = cameraY - moveSpeed * seconds
        end
        PlaceCamera()

        if monitor:IsKeyPressed(keys:U)
            waterLevel = waterLevel + 2 * seconds
            pool:SetLevel(waterLevel)
        end
        if monitor:IsKeyPressed(keys:J)
            waterLevel = waterLevel - 2 * seconds
            pool:SetLevel(waterLevel)
        end
        if monitor:IsKeyPressed(keys:C)
            water:SetClarity(water:GetClarity() - 0.2 * seconds)
        end
        if monitor:IsKeyPressed(keys:V)
            water:SetClarity(water:GetClarity() + 0.2 * seconds)
        end
        if monitor:IsKeyPressed(keys:Z)
            water:SetWaveSpeed(water:GetWaveSpeed() - 0.5 * seconds)
        end
        if monitor:IsKeyPressed(keys:X)
            water:SetWaveSpeed(water:GetWaveSpeed() + 0.5 * seconds)
        end
        if monitor:IsKeyPressed(keys:NUM_0)
            water:SetWaveSpeed(0)
        end

        boolean mDown = monitor:IsKeyPressed(keys:M)
        if mDown and not mWasDown
            integer nextCount = GetMultisampling() * 2
            if nextCount > 8
                nextCount = 1
            end
            SetMultisampling(nextCount)
            output "Water check: asked for " + nextCount + " samples per pixel."
        end
        mWasDown = mDown
    end

    /*
    This action puts the camera at its position, facing by its yaw and
    pitch.
    */
    action PlaceCamera
        number yawRadians = math:DegreesToRadians(yaw)
        number pitchRadians = math:DegreesToRadians(pitch)
        number directionX = math:Sine(yawRadians) * math:Cosine(pitchRadians)
        number directionY = math:Sine(pitchRadians)
        number directionZ = math:Cosine(yawRadians) * math:Cosine(pitchRadians)
        GetCamera3D():SetPosition(cameraX, cameraY, cameraZ)
        GetCamera3D():LookAt(cameraX + directionX, cameraY + directionY, cameraZ + directionZ)
    end
end
```

Every name used here exists: `SetMultisampling` and `GetMultisampling`
(as MSAACheck), `keys:PAGE_UP`, `keys:PAGE_DOWN`, `keys:NUM_0`,
`LoadSphere(width, height, depth, Color)` and `Item3D:Rotate(x, y, z,
degrees)`.

## What changes

**On screen:** nothing in programs without water. With water, a water
sheet over the ground.

**Cost per frame, with water in view:**
- one pipeline bind, four descriptor binds and one indirect draw per
  water program;
- the water's pixels only: one G-buffer read, two ripple reads, and a loop
  over the lights.

**Memory:**
- the ripple texture, 128 × 128 with mipmaps: about 85 KB per program;
- the 128-byte push buffer.

## Limits (later Items)

- **No sky reflection** until Item 41. Low angles look flat until then.
- **No fog on water** until Item 40.
- **No shadows on water.**
- **No refraction** (the bottom doesn't wobble) and **no moving geometry**
  (the sheet is flat): `WaterPlan.md`'s later steps, Item 66.
- **Water over water isn't sorted.** Two sheets overlapping on screen draw
  in the order they were added. Lakes and seas rarely overlap.
- **Water edges aren't anti-aliased with MSAA,** since the lit image has one
  sample. The shore fade hides most of it.
- **No collision or buoyancy:** the car drives along the bottom.

## Test plan

1. **WaterCheck,** each point in its header.
2. **DriveOpen, TerrainWalk, MSAACheck, SkyboxCheck, SpotlightCheck:**
   everything draws as before (no forward programs, so the new path draws
   nothing).
3. **The terrain splat program still draws and casts shadows:** it is a
   custom program that isn't forward.
4. **With the validation layer, if available:** no messages about
   descriptor set compatibility, push constant ranges, or pipeline and
   render pass compatibility.
5. **Memory report:** steady while the water is in view for a minute.

## Rollback

- Revert the library changes in the three files: the mapping, the creator
  and P.
- Delete the five new project files.
