# Item 27: MSAA for the Vulkan renderer

The exact code for `MSAAPlan.md`, with the recommended answers to its four
decisions:
1. option A: a multisampled G-buffer resolved in the scene pass, with
   coverage-aware lighting;
2. the switch is `Game:SetMultisampling(samples)`, which OpenGL ignores,
   stored on `VulkanGraphics` for every 3D painter;
3. off by default;
4. one multisampled set shared across frames.

**Vulkan only; nothing in OpenGL changes. Approved and applied on
2026-10-19** to the `quorum-language` branch `TerrainShader` (uncommitted;
Items 25 and 26 are already committed). `SourceCode/MSAACheck.quorum` is written. **Waiting
for a library rebuild and a run.** There is no Java, so the plugins don't
need rebuilding for this item.

Paths are under
`quorum-language/Quorum/Library/Standard/Libraries/Game/`.

## What was learned while writing the code

1. **The sample count must be one setting for the whole game,** not one
   per painter. Every `Layer3D`'s painter draws with the same default 3D
   program, whose pipeline is shared. So the count lives on
   `VulkanGraphics`, and a pipeline is made again whenever its own sample
   count (`GetInfo():GetRasterizationSamples()`) differs from the scene
   pass's. That check is safe however many painters there are.
2. **Attachment order keeps the old code working.** The single-sample
   G-buffer images stay at framebuffer positions 0 to 3 and depth at 4, and
   the multisampled copies go at 5 to 8. The barrier after the scene pass
   and the lighting pass's descriptors read positions 0 to 3, so they need
   no change. The clear values gain four entries for 5 to 8.
3. **A latent slip in the lighting pass.** Its attachment list adds
   `albedoAttachment` (the scene's) where `lightColorAttachment` was clearly
   meant. Today the two are identical, so it worked. With MSAA, albedo
   becomes a resolve target with load op `DONT_CARE`, which would break the
   lighting pass's clear. It is corrected to `lightColorAttachment`.
4. **The result pass** reused the scene's depth description. It gets its
   own single-sample copy.
5. **`VulkanRenderPass:Dispose` isn't written** (it alerts "NYI"). So when
   the count changes, the painter waits for the device to go idle, lets go
   of its old passes, and builds new ones. The old passes and G-buffer
   images aren't freed, like other Vulkan resources today (order 11).
   Changing the count is rare, so this is acceptable for now.
6. **Lazy memory without failing.** Requesting VMA's
   `GPU_LAZILY_ALLOCATED` fails on GPUs that have no such memory. So the
   multisampled images keep the default usage and **prefer**
   `LAZILY_ALLOCATED`, with `TRANSIENT_ATTACHMENT` usage. Apple GPUs then
   get memoryless storage, and other GPUs get ordinary memory.

## Files

| File | Change |
|---|---|
| `Graphics/Vulkan/VulkanRenderPass.quorum` | `sampleCount`, worked out in `Create`; `GetSampleCount` |
| `Graphics/Shaders/Vulkan/VulkanShaderProgram.quorum` | pipelines take their pass's sample count |
| `Graphics/Vulkan/VulkanGraphics.quorum` | `SetMultisampleCount`, `GetMultisampleCount`, `GetUsableMultisampleCount` |
| `Game.quorum` | `SetMultisampling`, `GetMultisampling`; passes the setting on when Vulkan starts |
| `Graphics/Vulkan/VulkanPainter3D.quorum` | the multisampled scene pass, shared images, rebuilding on change, pipeline checks, the two fixes above |
| `Graphics/Shaders/Vulkan/Fragment/DefaultLightingFragmentShaderVulkan.quorum` | coverage-aware G-buffer reads |

No Java.

## 1. `Graphics/Vulkan/VulkanRenderPass.quorum`

**New field,** after `boolean initialized = false`:

```
    // The most samples any attachment has: 1, or the MSAA sample count for
    // a multisampled pass (Item 27). Pipelines made for this pass use it.
    integer sampleCount = 1
```

**`Create`** works it out before creating:

```
    action Create(VulkanDevice device, Array<VulkanAttachmentDescription> attachments,
        Array<VulkanSubpassDescription> subpasses, Array<VulkanSubpassDependency> subpassDependencies) returns boolean
        sampleCount = 1
        integer i = 0
        repeat while i < attachments:GetSize()
            integer samples = attachments:Get(i):GetSamples()
            if samples > sampleCount
                sampleCount = samples
            end
            i = i + 1
        end

        boolean success = CreateNative(device, attachments, subpasses, subpassDependencies)
        ...unchanged...
    end
```

**New action:**

```
    /*
    This action returns how many samples per pixel the pass draws with: 1,
    or the MSAA sample count for a multisampled pass. Pipelines drawing in
    the pass must use the same count.

    Attribute: Returns The sample count.
    */
    action GetSampleCount returns integer
        return sampleCount
    end
```

## 2. `Graphics/Shaders/Vulkan/VulkanShaderProgram.quorum`

In `CreatePipeline`, after
`VulkanPipelineInfo info = GetShaderMapping():CreatePipelineInfo(me, device)`:

```
        // A pipeline must use the same sample count as the pass it draws in:
        // 1, except in the scene pass with MSAA on (Item 27).
        info:SetRasterizationSamples(renderPass:GetSampleCount())
```

## 3. `Graphics/Vulkan/VulkanGraphics.quorum`

**New field** (with the others near the top):

```
    // MSAA for 3D (Item 27): how many samples per pixel the game asked for.
    // 1 is off. GetUsableMultisampleCount gives the count the device can do.
    integer multisampleCount = 1
    boolean warnedAboutSampleCount = false
```

**New actions** (after `SetClearScreenColor`):

```
    /*
    This action sets how many samples per pixel 3D scenes are drawn with,
    for multisample anti-aliasing (MSAA): 1 turns it off; 2, 4 or 8 smooth
    the stair-stepped edges of 3D models, 4 being the usual choice. If the
    device can't do the count, the highest count it can do below it is
    used. It takes effect at the next frame.

    Attribute: Parameter samples 1, 2, 4 or 8.
    */
    action SetMultisampleCount(integer samples)
        if samples < 1
            samples = 1
        end
        multisampleCount = samples
        warnedAboutSampleCount = false
    end

    /*
    This action returns how many samples per pixel the game asked for.

    Attribute: Returns The count asked for; 1 means MSAA is off.
    */
    action GetMultisampleCount returns integer
        return multisampleCount
    end

    /*
    This action returns how many samples per pixel 3D scenes are really
    drawn with: the count asked for, or the highest count the device's
    framebuffers can do below it, for both color and depth.

    Attribute: Returns The count in use, 1 for no MSAA.
    */
    action GetUsableMultisampleCount returns integer
        if multisampleCount <= 1 or physicalDevice = undefined
            return 1
        end
        VulkanPhysicalDeviceLimits limits = physicalDevice:GetLimits()
        integer samples = 1
        repeat while samples * 2 <= multisampleCount and samples < 64
            samples = samples * 2
        end
        repeat while samples > 1 and not (limits:HasFrameBufferColorSampleSupport(samples) and limits:HasFrameBufferDepthSampleSupport(samples))
            samples = samples / 2
        end
        if samples not= multisampleCount and not warnedAboutSampleCount
            output "MSAA: " + multisampleCount + " samples asked for; this device can do " + samples + ", so " + samples + " are used."
            warnedAboutSampleCount = true
        end
        return samples
    end
```

## 4. `Game.quorum`

**New field** (near `GameStateManager manager`):

```
    // MSAA for 3D under Vulkan (Item 27), passed to the graphics when they
    // start. 1 is off.
    integer multisampleCount = 1
```

**In `StartGame`**, the Vulkan branch that makes the shader manager also
passes the setting on:

```
        elseif graphics is VulkanGraphics
            VulkanShaderManager shaderManager
            me:shaderManager = shaderManager
            VulkanGraphics vulkan = cast(VulkanGraphics, graphics)
            vulkan:SetMultisampleCount(multisampleCount)
        end
```

**New actions** (after `GetSkybox`):

```
    /*
    This action turns multisample anti-aliasing (MSAA) for 3D on or off.
    MSAA smooths the stair-stepped edges of 3D models by testing several
    points in each pixel along their edges. 1 turns it off, which is the
    default. 4 is the usual choice: it costs little on most graphics
    hardware. 2 and 8 are also possible, if the device supports them;
    otherwise the highest count it can do below is used. It works with the
    Vulkan renderer only; OpenGL ignores it. It can be called at any time,
    such as from a settings menu, and takes effect at the next frame.

    Attribute: Parameter samples How many samples per pixel: 1 (off), 2, 4 or 8.

    Attribute: Example
    use Libraries.Game.Game

    class Main is Game
        action Main
            UseVulkan(true)
            StartGame()
        end

        action CreateGame
            SetMultisampling(4)
        end
    end
    */
    action SetMultisampling(integer samples)
        multisampleCount = samples
        if manager:GetGameGraphics() is VulkanGraphics
            VulkanGraphics vulkan = cast(VulkanGraphics, manager:GetGameGraphics())
            vulkan:SetMultisampleCount(samples)
        end
    end

    /*
    This action returns how many samples per pixel MSAA was asked to use (see
    SetMultisampling).

    Attribute: Returns The count asked for; 1 means MSAA is off.

    Attribute: Example
    use Libraries.Game.Game

    class Main is Game
        action Main
            StartGame()
        end

        action CreateGame
            SetMultisampling(4)
            output "MSAA samples: " + GetMultisampling()
        end
    end
    */
    action GetMultisampling returns integer
        return multisampleCount
    end
```

## 5. `Graphics/Vulkan/VulkanPainter3D.quorum`

### New fields

After `boolean renderCascadesSeparately = false`:

```
    // MSAA (Item 27): the sample count the scene pass was last built with,
    // and the multisampled images it draws into, shared by every frame's
    // framebuffer (they are transient, and each frame's scene pass waits
    // for the previous one's writes).
    integer sceneSampleCount = 1
```

### `Begin`: rebuild when the count changes

Right before `if not AreRenderPassesValid()`:

```
        // If the game's MSAA sample count changed since the passes were
        // made, make them again (Item 27). Earlier frames may still be using
        // the old framebuffers, so wait for the device first. The old passes
        // are let go rather than disposed, since VulkanRenderPass:Dispose
        // isn't written yet.
        if AreRenderPassesValid() and graphics:GetUsableMultisampleCount() not= sceneSampleCount
            graphics:GetDevice():WaitUntilIdle()
            sceneRenderPass = undefined
            shadowRenderPass = undefined
            lightRenderPass = undefined
            resultRenderPass = undefined
        end
```

### `RegenerateRenderPasses`

**After** `VulkanConstants constants` (where `graphics` and `device` are
set):

```
        // The scene pass's sample count: 1, or the MSAA count (Item 27).
        sceneSampleCount = graphics:GetUsableMultisampleCount()
        boolean multisampled = sceneSampleCount > 1
```

**The scene attachments**, from `// Scene render attachments.` through
`CreateRenderPass(sceneRenderPass, ...)`, become:

```
        // Scene render attachments. Without MSAA, the scene is drawn straight
        // into the four G-buffer images (attachments 0 to 3) and depth (4).
        // With MSAA (Item 27), it is drawn into multisampled copies
        // (attachments 5 to 8, and a multisampled depth at 4), which the
        // subpass resolves into the four G-buffer images as it finishes. The
        // lighting pass reads the G-buffer images either way.
        integer positionFormat = constants:FORMAT_R32G32B32A32_SFLOAT
        integer gBufferFormat = constants:FORMAT_R16G16B16A16_SFLOAT
        sceneAttachmentDescriptions:Add(MakeSceneColorAttachment(positionFormat, 1, multisampled))
        repeat 3 times
            sceneAttachmentDescriptions:Add(MakeSceneColorAttachment(gBufferFormat, 1, multisampled))
        end

        VulkanAttachmentDescription depthDescription
        depthDescription:SetFormat(constants:FORMAT_D32_SFLOAT)
        depthDescription:SetSamples(sceneSampleCount)
        depthDescription:SetLoadOp(constants:ATTACHMENT_LOAD_OP_CLEAR)
        depthDescription:SetStoreOp(constants:ATTACHMENT_STORE_OP_DONT_CARE)
        depthDescription:SetStencilLoadOp(constants:ATTACHMENT_STORE_OP_DONT_CARE)
        depthDescription:SetStencilStoreOp(constants:ATTACHMENT_STORE_OP_DONT_CARE)
        depthDescription:SetInitialLayout(constants:IMAGE_LAYOUT_UNDEFINED)
        depthDescription:SetFinalLayout(constants:IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL)
        sceneAttachmentDescriptions:Add(depthDescription)

        Array<VulkanAttachmentReference> sceneResolveReferences = undefined
        if multisampled
            sceneAttachmentDescriptions:Add(MakeSceneColorAttachment(positionFormat, sceneSampleCount, false))
            repeat 3 times
                sceneAttachmentDescriptions:Add(MakeSceneColorAttachment(gBufferFormat, sceneSampleCount, false))
            end
            Array<VulkanAttachmentReference> resolveReferences
            sceneResolveReferences = resolveReferences
        end

        // Position, albedo, normals and PBR: drawn into 0 to 3, or into 5 to
        // 8 and resolved into 0 to 3.
        integer gBufferIndex = 0
        repeat while gBufferIndex < 4
            VulkanAttachmentReference colorReference
            if multisampled
                colorReference:SetAttachmentIndex(5 + gBufferIndex)
                VulkanAttachmentReference resolveReference
                resolveReference:SetAttachmentIndex(gBufferIndex)
                resolveReference:SetLayout(constants:IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL)
                sceneResolveReferences:Add(resolveReference)
            else
                colorReference:SetAttachmentIndex(gBufferIndex)
            end
            colorReference:SetLayout(constants:IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL)
            sceneColorAttachmentReferences:Add(colorReference)
            gBufferIndex = gBufferIndex + 1
        end

        VulkanAttachmentReference sceneDepthReference
        sceneDepthReference:SetAttachmentIndex(4)
        sceneDepthReference:SetLayout(constants:IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL)

        // Now that we have all of the required attachment info, create the scene render pass.
        CreateRenderPass(sceneRenderPass, sceneAttachmentDescriptions, sceneColorAttachmentReferences, sceneDepthReference, sceneResolveReferences)
```

**The lighting pass:** `lightAttachmentDescriptions:Add(albedoAttachment)`
becomes `lightAttachmentDescriptions:Add(lightColorAttachment)`.

**The result pass:** `resultAttachmentDescriptions:Add(depthDescription)`
and the comment above it become:

```
        // The result pass draws into the swapchain's framebuffer, whose depth
        // is single-sample. The scene's depth may be multisampled (Item 27),
        // so this pass has its own description.
        VulkanAttachmentDescription resultDepthDescription
        resultDepthDescription:SetFormat(constants:FORMAT_D32_SFLOAT)
        resultDepthDescription:SetSamples(constants:SAMPLE_COUNT_1_BIT)
        resultDepthDescription:SetLoadOp(constants:ATTACHMENT_LOAD_OP_CLEAR)
        resultDepthDescription:SetStoreOp(constants:ATTACHMENT_STORE_OP_DONT_CARE)
        resultDepthDescription:SetStencilLoadOp(constants:ATTACHMENT_STORE_OP_DONT_CARE)
        resultDepthDescription:SetStencilStoreOp(constants:ATTACHMENT_STORE_OP_DONT_CARE)
        resultDepthDescription:SetInitialLayout(constants:IMAGE_LAYOUT_UNDEFINED)
        resultDepthDescription:SetFinalLayout(constants:IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL)
        resultAttachmentDescriptions:Add(resultDepthDescription)
```

**The framebuffers.** Before
`repeat while i < swapchain:GetImageCount()`:

```
        // With MSAA, the multisampled images every frame draws into: position,
        // albedo, normals, PBR, and depth (Item 27).
        Array<VulkanImageView> multisampledViews
        VulkanImageView multisampledDepthView = undefined
        if multisampled
            multisampledViews:Add(MakeMultisampledView(device, constants:FORMAT_R32G32B32A32_SFLOAT,
                constants:IMAGE_USAGE_COLOR_ATTACHMENT_BIT, constants:IMAGE_ASPECT_COLOR_BIT, swapchainWidth, swapchainHeight))
            repeat 3 times
                multisampledViews:Add(MakeMultisampledView(device, constants:FORMAT_R16G16B16A16_SFLOAT,
                    constants:IMAGE_USAGE_COLOR_ATTACHMENT_BIT, constants:IMAGE_ASPECT_COLOR_BIT, swapchainWidth, swapchainHeight))
            end
            multisampledDepthView = MakeMultisampledView(device, constants:FORMAT_D32_SFLOAT,
                constants:IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT, constants:IMAGE_ASPECT_DEPTH_BIT, swapchainWidth, swapchainHeight)
        end
```

In the loop, the depth image block (from `// Also create an image for depth
usage.` through `renderImageViews:Add(depthImageView)`) becomes:

```
            // Depth: the shared multisampled one with MSAA, or this frame's own.
            if multisampled
                renderImageViews:Add(multisampledDepthView)
            else
                VulkanImageInfo depthImageInfo
                depthImageInfo:SetWidth(swapchainWidth)
                depthImageInfo:SetHeight(swapchainHeight)
                depthImageInfo:SetUsage(constants:IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT)
                depthImageInfo:SetFormat(constants:FORMAT_D32_SFLOAT)

                VulkanImage depthImage
                depthImage:Create(device, depthImageInfo)

                VulkanImageViewInfo depthViewInfo
                depthViewInfo:SetAspectMask(constants:IMAGE_ASPECT_DEPTH_BIT)
                depthViewInfo:SetFormat(depthImageInfo:GetFormat())

                VulkanImageView depthImageView
                depthImageView:Create(device, depthImage, depthViewInfo)
                renderImageViews:Add(depthImageView)
            end

            // With MSAA, the multisampled G-buffer images come after depth,
            // at 5 to 8.
            integer multisampledIndex = 0
            repeat while multisampledIndex < multisampledViews:GetSize()
                renderImageViews:Add(multisampledViews:Get(multisampledIndex))
                multisampledIndex = multisampledIndex + 1
            end
```

### `CreateRenderPass`

The existing action passes no resolve references through:

```
    private action CreateRenderPass(VulkanRenderPass renderPass,
Array<VulkanAttachmentDescription> attachmentDescriptions,
Array<VulkanAttachmentReference> colorReferences,
VulkanAttachmentReference depthReference) returns boolean
        return CreateRenderPass(renderPass, attachmentDescriptions, colorReferences, depthReference, undefined)
    end
```

The new form is the old body, plus the resolve references and the color
write in the dependency:

```
    /*
    This action makes a render pass with one subpass. With resolve
    references, the subpass resolves each multisampled color attachment
    into the matching single-sample one as it finishes (Item 27).
    */
    private action CreateRenderPass(VulkanRenderPass renderPass,
Array<VulkanAttachmentDescription> attachmentDescriptions,
Array<VulkanAttachmentReference> colorReferences,
VulkanAttachmentReference depthReference,
Array<VulkanAttachmentReference> resolveReferences) returns boolean
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        VulkanConstants constants

        VulkanSubpassDescription subpass
        subpass:SetPipelineBindPoint(constants:PIPELINE_BIND_POINT_GRAPHICS)
        subpass:SetColorAttachments(colorReferences)
        subpass:SetDepthStencilAttachment(depthReference)
        if resolveReferences not= undefined
            subpass:SetResolveAttachments(resolveReferences)
        end

        Array<VulkanSubpassDescription> subpassDescriptions
        subpassDescriptions:Add(subpass)

        VulkanSubpassDependency dependency
        dependency:SetSourceSubpass(constants:SUBPASS_EXTERNAL)
        dependency:SetDestinationSubpass(0)
        dependency:SetSourceStageMask(constants:PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT + constants:PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT)
        dependency:SetDestinationStageMask(constants:PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT + constants:PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT)
        // Color writes too, so a pass waits for the previous frame's writes
        // to attachments they share, such as the MSAA images (Item 27).
        dependency:SetSourceAccessMask(constants:ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT + constants:ACCESS_COLOR_ATTACHMENT_WRITE_BIT)
        dependency:SetDestinationAccessMask(constants:ACCESS_COLOR_ATTACHMENT_WRITE_BIT + constants:ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT)

        Array<VulkanSubpassDependency> subpassDependencies
        subpassDependencies:Add(dependency)

        boolean success = renderPass:Create(graphics:GetDevice(), attachmentDescriptions, subpassDescriptions, subpassDependencies)
        return success
    end
```

### New private actions

```
    /*
    This action describes one of the scene pass's color attachments.

    Attribute: Parameter format The image format.
    Attribute: Parameter samples 1, or the MSAA sample count.
    Attribute: Parameter resolveTarget True for a G-buffer image that a multisampled one resolves into.
    Attribute: Returns The attachment description.
    */
    private action MakeSceneColorAttachment(integer format, integer samples, boolean resolveTarget) returns VulkanAttachmentDescription
        VulkanConstants constants
        VulkanAttachmentDescription attachment
        attachment:SetFormat(format)
        attachment:SetSamples(samples)
        if resolveTarget
            // Only the resolve writes it, so its old contents don't matter,
            // and it is stored for the lighting pass.
            attachment:SetLoadOp(constants:ATTACHMENT_LOAD_OP_DONT_CARE)
            attachment:SetStoreOp(constants:ATTACHMENT_STORE_OP_STORE)
        elseif samples > 1
            // Multisampled: cleared, drawn and resolved, never stored, so it
            // can stay in the GPU's tile memory.
            attachment:SetLoadOp(constants:ATTACHMENT_LOAD_OP_CLEAR)
            attachment:SetStoreOp(constants:ATTACHMENT_STORE_OP_DONT_CARE)
        else
            attachment:SetLoadOp(constants:ATTACHMENT_LOAD_OP_CLEAR)
            attachment:SetStoreOp(constants:ATTACHMENT_STORE_OP_STORE)
        end
        attachment:SetInitialLayout(constants:IMAGE_LAYOUT_UNDEFINED)
        attachment:SetFinalLayout(constants:IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL)
        return attachment
    end

    /*
    This action makes one multisampled image for MSAA, and a view of it. It
    is transient, and asks for lazily allocated memory, which tile-based
    GPUs (Apple's, and phones') keep in tile memory only; other GPUs give it
    ordinary memory.

    Attribute: Parameter device The Vulkan device.
    Attribute: Parameter format The image format.
    Attribute: Parameter usage Color or depth attachment usage.
    Attribute: Parameter aspect The color or depth aspect, for the view.
    Attribute: Parameter width The width in pixels.
    Attribute: Parameter height The height in pixels.
    Attribute: Returns The image's view.
    */
    private action MakeMultisampledView(VulkanDevice device, integer format, integer usage, integer aspect,
            integer width, integer height) returns VulkanImageView
        VulkanConstants constants
        VulkanImageInfo info
        info:SetWidth(width)
        info:SetHeight(height)
        info:SetFormat(format)
        info:SetSamples(sceneSampleCount)
        info:SetUsage(usage + constants:IMAGE_USAGE_TRANSIENT_ATTACHMENT_BIT)
        info:SetPreferredMemoryFlags(constants:MEMORY_PROPERTY_LAZILY_ALLOCATED_BIT)
        VulkanImage image
        if not image:Create(device, info)
            alert("I couldn't make a multisampled image for MSAA with " + sceneSampleCount + " samples.")
        end

        VulkanImageViewInfo viewInfo
        viewInfo:SetFormat(format)
        viewInfo:SetAspectMask(aspect)
        VulkanImageView view
        view:Create(device, image, viewInfo)
        return view
    end

    /*
    This action returns true if a scene pipeline must be made (again): it
    doesn't exist yet, or it was made for a different MSAA sample count than
    the scene pass now uses.

    Attribute: Parameter pipeline The pipeline, or undefined.
    Attribute: Returns True if it must be made.
    */
    private action NeedsScenePipeline(VulkanPipeline pipeline) returns boolean
        if pipeline = undefined
            return true
        end
        return pipeline:GetInfo():GetRasterizationSamples() not= sceneSampleCount
    end
```

### `End`: the two scene pipelines

```
        if currentPipeline = undefined
```

becomes `if NeedsScenePipeline(currentPipeline)`, and

```
                if programStrategy:GetPipeline() = undefined
```

becomes `if NeedsScenePipeline(programStrategy:GetPipeline())`.

### Clear values

In `End`, where `sceneClearValues` is first filled, four more entries
follow the depth one, for the multisampled attachments 5 to 8 (unused
without MSAA):

```
        if sceneClearValues:IsEmpty()
            repeat 4 times
                sceneClearValues:AddColor(0, 0, 0, 0)
            end
            sceneClearValues:AddDepthStencil(1, 0)
            // The multisampled G-buffer copies, with MSAA (Item 27).
            repeat 4 times
                sceneClearValues:AddColor(0, 0, 0, 0)
            end
        end
```

## 6. `DefaultLightingFragmentShaderVulkan.quorum`

In `main`, after the G-buffer reads:

```glsl
	vec4 rawAlbedo = texture(albedoSampler, v_samplerCoordinate);
	vec3 albedo = rawAlbedo.rgb;
	vec3 normal = texture(normalsSampler, v_samplerCoordinate).rgb;
	vec4 rawWorldPosition = texture(positionSampler, v_samplerCoordinate);
	vec3 worldPosition = rawWorldPosition.xyz;
	vec3 pbr = texture(pbrSampler, v_samplerCoordinate).rgb;

	// With MSAA (Item 27), an edge pixel's G-buffer values are averages of
	// its samples, and samples where nothing was drawn hold zeros. Geometry
	// writes a position w of 1, so w is the share of the pixel covered.
	// Dividing by it gives the model's own values back, so silhouettes
	// against the sky are lit correctly and have no dark halo. Without MSAA,
	// coverage is exactly 1 or 0, and nothing changes.
	float coverage = rawWorldPosition.w;
	float uncover = coverage > 0.0001 ? 1.0 / coverage : 0.0;
	albedo = albedo * uncover;
	worldPosition = worldPosition * uncover;
	pbr = pbr * uncover;
```

and

```glsl
	vec4 viewPos = sceneInfo.cameraViewMatrix * rawWorldPosition;
```

becomes

```glsl
	vec4 viewPos = sceneInfo.cameraViewMatrix * vec4(worldPosition, 1.0);
```

The output, `outputColor = vec4(color.rgb, rawAlbedo.a)`, stays. Its alpha
is coverage times the model's alpha, which the result pass uses to blend
the edge onto the sky.

## Size

- `VulkanPainter3D`: about +150 −40.
- `VulkanGraphics`: +60.
- `Game`: +60, mostly documentation.
- `VulkanRenderPass`: +20.
- `VulkanShaderProgram`: +3.
- The lighting shader: +12.

## What changes for existing games

- **Nothing while MSAA is off,** which is the default:
  - the same passes, attachments and framebuffers;
  - the lighting shader's coverage is 1 or 0;
  - the clear values gain four unused entries;
  - the render pass dependency also waits for color writes (stricter, and
    correct).
- **The lighting pass's attachment** is now the description written for it
  (`lightColorAttachment`), which was identical anyway.
- **OpenGL:** no change. `Game:SetMultisampling` only stores the number.

## Risks and things to know

- **Memory** (`MSAAPlan.md`, Memory): about none on Apple GPUs. About
  365 MB at 4× 1080p on GPUs without lazily allocated memory, with one
  shared set.
- **Changing the count leaks** the old passes and G-buffer images (order
  11). Change it rarely, as from a settings screen, not every frame.
- **The first frame after a change** waits for the GPU to go idle (a short
  hitch).
- **Older Macs without 32-bit MSAA:** MoltenVK resolves the position image
  with a compute shader. Correct, but slower.
- **Edges between two models** are lit on averaged values (option A's
  limit). If that shows, option C (a custom resolve subpass) is next.
- **Alpha-cut edges and shading sparkle** aren't smoothed by MSAA
  (`MSAAPlan.md`).

## Test plan

**`MSAACheck.quorum`** (project; written when this is applied):
- **The scene:**
  - the Day sky;
  - a row of thin posts receding into the distance;
  - wires (long thin boxes) at a slight angle;
  - three slowly turning boxes, one in front of another;
  - a ground plane with a sun and shadows.
- **M** steps the asked-for count through 1, 2, 4 and 8. The console
  prints the count asked for, the count used (`GetUsableMultisampleCount`),
  and the average frame time every two seconds.
- **What to see:**
  1. At 1: stair-stepped edges, the same as today.
  2. At 4: smooth edges on posts, wires and box silhouettes, with no dark
     or light halo against the sky.
  3. Where boxes overlap, smooth edges and no bright or dark fringes.
  4. Shadows and lighting are unchanged inside surfaces.
  5. Switching counts causes only a short hitch, and no errors.
  6. Resizing the window with MSAA on still works.
- **Then:** TerrainEditor and DriveOpen with `SetMultisampling(4)`, and
  TextureUpdateCheck and SkyboxCheck with it off and on.

## Rollback

Revert the six files, and rebuild the library. There is no Java.
