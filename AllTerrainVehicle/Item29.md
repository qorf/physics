# Item 29: MSAA for 2D (the swapchain stage) under Vulkan

Option A of `MSAA2DPlan.md`, with a separate switch,
`Game:SetMultisampling2D(samples)`. **Vulkan only; nothing in OpenGL
changes. Approved and applied on 2026-10-19** to the branch
`TerrainShader`, on top of Items 27 and 28 (all uncommitted).
`SourceCode/MSAA2DCheck.quorum` is written. **Waiting for a library rebuild
and a run.**

One addition while applying: the 2D painter's pass dependency also waits
for color writes (like the 3D passes since Item 27), since with 2D MSAA a 2D
pass loads the multisampled image an earlier layer wrote.

Paths are under
`quorum-language/Quorum/Library/Standard/Libraries/Game/`.

## What it does

Every pass that draws on the swapchain image draws into **one
multisampled color image** instead, and resolves it into the swapchain
image as it ends. Those passes are every 2D layer, and the 3D layer's
result pass (the lit image and the sky).

- Later layers load the multisampled image, so layers stack exactly as
  today, 2D over 3D included.
- **What gets smoother:** the outer edges of 2D quads that are turned or
  scaled. Edges baked into textures (circles, lines, glyphs) and edges
  computed in shaders (controls, patterns, charts) are unchanged.
  `MSAA2DPlan.md` explains why.
- **Off by default.** It's independent of the 3D scene's MSAA
  (`SetMultisampling`, Item 27). Either or both can be on.

## What was learned while writing the code

1. **Attachment order keeps the clear values.** With 2D MSAA on, the
   swapchain framebuffers become [multisampled color, depth, swapchain
   image]. The clear color stays at index 0 and depth at 1, so
   `VulkanGraphics`'s clear values, which `SetClearScreenColor` changes,
   need no change. With it off, the framebuffers are [swapchain image,
   depth] as today.
2. **Three places described the same attachments:**
   - `VulkanGraphics`, the pass its framebuffers are made with;
   - `VulkanPainter2D`;
   - `VulkanPainter3D`'s result pass.

   They have to match exactly, so they now share one action,
   `VulkanGraphics:MakeSwapchainSubpass(firstLayer, descriptions)`.
3. **2D batches kept a copy of their pipeline** from when they were made
   (`VulkanPainter2DBatch:Create`). After the pipelines are remade for a new
   sample count, old batches would bind a freed pipeline. The batch now
   asks its program for its current pipeline each time.
4. **The multisampled color image can't be transient.** It's stored
   between layers (one layer's pass resolves it, and the next loads it).
   Metal's memoryless storage can't hold data between passes. So it gets
   ordinary memory: 4 bytes × 4 samples = 16 bytes a pixel, about 33 MB at
   1080p, one shared image. The multisampled depth is cleared by every pass
   and never kept, so it is transient (memoryless on Apple GPUs).
5. **Changing the setting:**
   - `VulkanGraphics` remakes its framebuffers at the start of the next
     frame (after waiting for the device), the same way a resize does.
   - Each painter sees that its pass's sample count no longer matches
     (`VulkanRenderPass:GetSampleCount`, Item 27) and remakes its pass.
   - Pipelines are remade when their sample count differs from their
     pass's.

## Files

| File | Change |
|---|---|
| `Graphics/Vulkan/VulkanGraphics.quorum` | the 2D sample count; `MakeSwapchainSubpass`; one action that makes the pass, images and framebuffers, used at start, on resize and when the count changes |
| `Game.quorum` | `SetMultisampling2D`, `GetMultisampling2D` |
| `Graphics/Vulkan/VulkanPainter2D.quorum` | its pass from `MakeSwapchainSubpass`; remade when the count changes; pipelines checked |
| `Graphics/Vulkan/VulkanPainter2DBatch.quorum` | `GetPipeline` reads the program's current pipeline |
| `Graphics/Vulkan/VulkanPainter3D.quorum` | the result pass from `MakeSwapchainSubpass`; remade when the count changes; copy and sky pipelines checked |

No Java, no shaders.

## 1. `Graphics/Vulkan/VulkanGraphics.quorum`

### New fields

After `boolean warnedAboutSampleCount = false` (Item 27):

```
    // MSAA for everything drawn on the swapchain image: 2D layers, and the
    // 3D layers' final copy and sky (Item 29). 1 is off.
    integer multisampleCount2D = 1
    boolean warnedAboutSampleCount2D = false

    // The sample count the swapchain's framebuffers were last made with,
    // and with MSAA, the multisampled color image every pass on them draws
    // into and resolves from. The depth image (depthBufferImage) is
    // multisampled too, then.
    integer swapchainSampleCount = 1
    VulkanImage multisampledColorImage = undefined
    VulkanImageView multisampledColorView = undefined
```

### The sample counts

`GetUsableMultisampleCount` (Item 27) keeps its meaning, but its search
moves into a shared private action:

```
    action GetUsableMultisampleCount returns integer
        integer samples = FindUsableSampleCount(multisampleCount)
        if samples not= multisampleCount and multisampleCount > 1 and not warnedAboutSampleCount
            output "MSAA: " + multisampleCount + " samples asked for; this device can do " + samples + ", so " + samples + " are used."
            warnedAboutSampleCount = true
        end
        return samples
    end

    /*
    This action sets how many samples per pixel are used for everything
    drawn on the screen's own image: 2D layers, and the final picture of 3D
    layers. 1 turns it off; 4 is the usual choice. It smooths the edges of
    turned or scaled 2D items. If the device can't do the count, the highest
    count it can do below it is used. It takes effect at the next frame.

    Attribute: Parameter samples 1, 2, 4 or 8.
    */
    action SetMultisampleCount2D(integer samples)
        if samples < 1
            samples = 1
        end
        multisampleCount2D = samples
        warnedAboutSampleCount2D = false
    end

    /*
    This action returns how many samples per pixel 2D MSAA was asked to use.

    Attribute: Returns The count asked for; 1 means it's off.
    */
    action GetMultisampleCount2D returns integer
        return multisampleCount2D
    end

    /*
    This action returns how many samples per pixel the screen's image is
    really drawn with: the 2D count asked for, or less if the device can't
    do it.

    Attribute: Returns The count in use, 1 for none.
    */
    action GetUsableMultisampleCount2D returns integer
        integer samples = FindUsableSampleCount(multisampleCount2D)
        if samples not= multisampleCount2D and multisampleCount2D > 1 and not warnedAboutSampleCount2D
            output "2D MSAA: " + multisampleCount2D + " samples asked for; this device can do " + samples + ", so " + samples + " are used."
            warnedAboutSampleCount2D = true
        end
        return samples
    end

    /*
    This action returns the sample count the swapchain's framebuffers are
    made with now. Every pass drawing on them must use it.

    Attribute: Returns The sample count.
    */
    action GetSwapchainSampleCount returns integer
        return swapchainSampleCount
    end

    /*
    This action returns the highest power of two, no more than the count
    asked for, that the device's framebuffers can do for color and depth.

    Attribute: Parameter requested The count asked for.
    Attribute: Returns The usable count, 1 if none.
    */
    private action FindUsableSampleCount(integer requested) returns integer
        if requested <= 1 or physicalDevice = undefined
            return 1
        end
        VulkanPhysicalDeviceLimits limits = physicalDevice:GetLimits()
        integer samples = 1
        repeat while samples * 2 <= requested and samples < 64
            samples = samples * 2
        end
        repeat while samples > 1 and not (limits:HasFrameBufferColorSampleSupport(samples) and limits:HasFrameBufferDepthSampleSupport(samples))
            samples = samples / 2
        end
        return samples
    end
```

### `MakeSwapchainSubpass` (new)

```
    /*
    This action describes the attachments of a pass that draws on the
    swapchain image, and returns its one subpass. The 2D painter, the 3D
    painter's result pass, and the swapchain's framebuffers all use it, so
    they always match. Without MSAA the attachments are [swapchain image,
    depth]; with 2D MSAA (Item 29) they are [multisampled color, multisampled
    depth, swapchain image], and the subpass resolves the multisampled color
    into the swapchain image as it ends. Either way the clear color is at 0
    and depth at 1.

    Attribute: Parameter firstLayer True if the pass is the frame's first, which clears the image; false to draw on what earlier layers drew.
    Attribute: Parameter descriptions An empty array, which is filled with the attachments.
    Attribute: Returns The subpass.
    */
    action MakeSwapchainSubpass(boolean firstLayer, Array<VulkanAttachmentDescription> descriptions) returns VulkanSubpassDescription
        integer format = swapchain:GetImageViewInfo():GetFormat()
        integer samples = swapchainSampleCount

        VulkanAttachmentDescription color
        color:SetFormat(format)
        color:SetSamples(samples)
        color:SetStoreOp(constants:ATTACHMENT_STORE_OP_STORE)
        if firstLayer
            color:SetInitialLayout(constants:IMAGE_LAYOUT_UNDEFINED)
            color:SetLoadOp(constants:ATTACHMENT_LOAD_OP_CLEAR)
        elseif samples > 1
            color:SetInitialLayout(constants:IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL)
            color:SetLoadOp(constants:ATTACHMENT_LOAD_OP_LOAD)
        else
            color:SetInitialLayout(constants:IMAGE_LAYOUT_PRESENT_SOURCE)
            color:SetLoadOp(constants:ATTACHMENT_LOAD_OP_LOAD)
        end
        if samples > 1
            // Kept between layers, so the next layer's pass can load it.
            color:SetFinalLayout(constants:IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL)
        else
            color:SetFinalLayout(constants:IMAGE_LAYOUT_PRESENT_SOURCE)
        end
        descriptions:Add(color)

        VulkanAttachmentDescription depth
        depth:SetFormat(constants:FORMAT_D32_SFLOAT)
        depth:SetSamples(samples)
        depth:SetLoadOp(constants:ATTACHMENT_LOAD_OP_CLEAR)
        depth:SetStoreOp(constants:ATTACHMENT_STORE_OP_DONT_CARE)
        depth:SetStencilLoadOp(constants:ATTACHMENT_STORE_OP_DONT_CARE)
        depth:SetStencilStoreOp(constants:ATTACHMENT_STORE_OP_DONT_CARE)
        depth:SetInitialLayout(constants:IMAGE_LAYOUT_UNDEFINED)
        depth:SetFinalLayout(constants:IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL)
        descriptions:Add(depth)

        VulkanSubpassDescription subpass
        subpass:SetPipelineBindPoint(constants:PIPELINE_BIND_POINT_GRAPHICS)

        Array<VulkanAttachmentReference> colorReferences
        VulkanAttachmentReference colorReference
        colorReference:SetAttachmentIndex(0)
        colorReference:SetLayout(constants:IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL)
        colorReferences:Add(colorReference)
        subpass:SetColorAttachments(colorReferences)

        VulkanAttachmentReference depthReference
        depthReference:SetAttachmentIndex(1)
        depthReference:SetLayout(constants:IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL)
        subpass:SetDepthStencilAttachment(depthReference)

        if samples > 1
            // The swapchain image, written only by the resolve.
            VulkanAttachmentDescription target
            target:SetFormat(format)
            target:SetSamples(constants:SAMPLE_COUNT_1_BIT)
            target:SetLoadOp(constants:ATTACHMENT_LOAD_OP_DONT_CARE)
            target:SetStoreOp(constants:ATTACHMENT_STORE_OP_STORE)
            target:SetInitialLayout(constants:IMAGE_LAYOUT_UNDEFINED)
            target:SetFinalLayout(constants:IMAGE_LAYOUT_PRESENT_SOURCE)
            descriptions:Add(target)

            Array<VulkanAttachmentReference> resolveReferences
            VulkanAttachmentReference resolveReference
            resolveReference:SetAttachmentIndex(2)
            resolveReference:SetLayout(constants:IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL)
            resolveReferences:Add(resolveReference)
            subpass:SetResolveAttachments(resolveReferences)
        end
        return subpass
    end
```

### `MakeSwapchainFramebuffers` (new)

This replaces the render pass, depth image and framebuffer code in
`Initialize`, and the depth and framebuffer code in `RegenerateSwapchain`.

```
    /*
    This action makes, at the swapchain's size and the 2D sample count, the
    render pass the swapchain's framebuffers are made with, the depth image,
    the multisampled color image (with 2D MSAA), and one framebuffer per
    swapchain image. Old images are freed. The old framebuffers must already
    be disposed, and the device idle.

    Attribute: Returns True if everything was made.
    */
    private action MakeSwapchainFramebuffers returns boolean
        swapchainSampleCount = GetUsableMultisampleCount2D()
        boolean multisampled = swapchainSampleCount > 1

        Array<VulkanAttachmentDescription> attachmentDescriptions
        Array<VulkanSubpassDescription> subpassDescriptions
        subpassDescriptions:Add(MakeSwapchainSubpass(true, attachmentDescriptions))

        VulkanSubpassDependency dependency
        dependency:SetSourceSubpass(constants:SUBPASS_EXTERNAL)
        dependency:SetDestinationSubpass(0)
        dependency:SetSourceStageMask(constants:PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT + constants:PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT)
        dependency:SetDestinationStageMask(constants:PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT + constants:PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT)
        dependency:SetSourceAccessMask(constants:ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT + constants:ACCESS_COLOR_ATTACHMENT_WRITE_BIT)
        dependency:SetDestinationAccessMask(constants:ACCESS_COLOR_ATTACHMENT_WRITE_BIT + constants:ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT)
        Array<VulkanSubpassDependency> subpassDependencies
        subpassDependencies:Add(dependency)

        // The old pass is let go: VulkanRenderPass:Dispose isn't written yet.
        VulkanRenderPass pass
        renderPass = pass
        if not renderPass:Create(device, attachmentDescriptions, subpassDescriptions, subpassDependencies)
            return false
        end

        if depthBufferImageView not= undefined
            depthBufferImageView:Dispose()
            depthBufferImage:Dispose()
        end
        if multisampledColorView not= undefined
            multisampledColorView:Dispose()
            multisampledColorImage:Dispose()
            multisampledColorView = undefined
            multisampledColorImage = undefined
        end

        integer width = swapchain:GetImageWidth()
        integer height = swapchain:GetImageHeight()

        VulkanImageInfo depthInfo
        depthInfo:SetWidth(width)
        depthInfo:SetHeight(height)
        depthInfo:SetFormat(constants:FORMAT_D32_SFLOAT)
        depthInfo:SetSamples(swapchainSampleCount)
        if multisampled
            // Cleared by every pass and never kept, so it can stay in tile
            // memory where the GPU has it.
            depthInfo:SetUsage(constants:IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT + constants:IMAGE_USAGE_TRANSIENT_ATTACHMENT_BIT)
            depthInfo:SetPreferredMemoryFlags(constants:MEMORY_PROPERTY_LAZILY_ALLOCATED_BIT)
        else
            depthInfo:SetUsage(constants:IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT)
        end
        VulkanImage depthImage
        depthBufferImage = depthImage
        if not depthImage:Create(device, depthInfo)
            return false
        end
        VulkanImageViewInfo depthViewInfo
        depthViewInfo:SetAspectMask(constants:IMAGE_ASPECT_DEPTH_BIT)
        depthViewInfo:SetFormat(constants:FORMAT_D32_SFLOAT)
        VulkanImageView depthView
        depthBufferImageView = depthView
        depthView:Create(device, depthImage, depthViewInfo)

        if multisampled
            // Kept between layers in a frame, so not transient.
            VulkanImageInfo colorInfo
            colorInfo:SetWidth(width)
            colorInfo:SetHeight(height)
            colorInfo:SetFormat(swapchain:GetImageViewInfo():GetFormat())
            colorInfo:SetSamples(swapchainSampleCount)
            colorInfo:SetUsage(constants:IMAGE_USAGE_COLOR_ATTACHMENT_BIT)
            VulkanImage colorImage
            multisampledColorImage = colorImage
            if not colorImage:Create(device, colorInfo)
                return false
            end
            VulkanImageViewInfo colorViewInfo
            colorViewInfo:SetFormat(colorInfo:GetFormat())
            VulkanImageView colorView
            multisampledColorView = colorView
            colorView:Create(device, colorImage, colorViewInfo)
        end

        swapchainFramebuffers:Empty()
        integer i = 0
        repeat while i < swapchain:GetImageCount()
            Array<VulkanImageView> views
            if multisampled
                views:Add(multisampledColorView)
                views:Add(depthBufferImageView)
                views:Add(swapchain:GetImageView(i))
            else
                views:Add(swapchain:GetImageView(i))
                views:Add(depthBufferImageView)
            end
            VulkanFramebuffer framebuffer
            if not framebuffer:Create(device, views, renderPass)
                return false
            end
            swapchainFramebuffers:Add(framebuffer)
            i = i + 1
        end
        return true
    end
```

### `Initialize`

From the comment `Create the RenderPass that will be used for the
Framebuffers.` through the framebuffer loop
(`swapchainFramebuffers:Add(framebuffer)` and its `end`) becomes:

```
        // The render pass, depth image and framebuffers for the swapchain's
        // images, and with 2D MSAA the multisampled color image (Item 29).
        success = MakeSwapchainFramebuffers()
        if not success
            return false
        end
```

### `RegenerateSwapchain`

From `// Also regenerate the depth buffer image and image view at the new
size.` through the end of the framebuffer loop, the depth and framebuffer
parts become one call. The semaphore loop stays as it is:

```
        // The depth image, multisampled image and framebuffers at the new
        // size (Item 29).
        if not MakeSwapchainFramebuffers()
            alert("Failed to create framebuffers during swapchain regeneration!")
        end

        // While it's technically allowed to reuse the previous semaphores, it's possible for a semaphore to be signalled in a way that can't
        // be reset by a SUBOPTIMAL result when preparing frames. For safety, we generate new ones here.
        i = 0
        repeat while i < swapchain:GetImageCount()
            VulkanSemaphore newSemaphore
            success = newSemaphore:Create(device)
            imageAcquiredSemaphores:Set(i, newSemaphore)
            i = i + 1
        end
```

### `BeginNextFrame`

After `if renderingPaused ... end`, before the swapchain image is acquired:

```
        // If the 2D sample count changed, remake the swapchain's
        // framebuffers for it (Item 29), as a resize would. The painters
        // see their passes no longer match, and remake them.
        if GetUsableMultisampleCount2D() not= swapchainSampleCount
            device:WaitUntilIdle()
            integer old = 0
            repeat while old < swapchainFramebuffers:GetSize()
                swapchainFramebuffers:Get(old):Dispose()
                old = old + 1
            end
            if not MakeSwapchainFramebuffers()
                alert("I couldn't remake the screen's framebuffers for " + swapchainSampleCount + " samples per pixel.")
            end
        end
```

## 2. `Game.quorum`

**New field,** after `integer multisampleCount = 1` (Item 27):

```
    // MSAA for 2D and the screen's final image under Vulkan (Item 29).
    integer multisampleCount2D = 1
```

**`StartGame`**, in the Vulkan branch after
`vulkan:SetMultisampleCount(multisampleCount)`:

```
            vulkan:SetMultisampleCount2D(multisampleCount2D)
```

**New actions,** after `GetMultisampling`:

```
    /*
    This action turns multisample anti-aliasing (MSAA) on or off for 2D, and
    for everything drawn on the screen's final image. It smooths the edges
    of 2D items that are turned or scaled. Shapes drawn from textures, such
    as circles and text, and controls are already smooth, and don't change.
    1 turns it off, which is the default; 4 is the usual choice. It works
    with the Vulkan renderer only; OpenGL ignores it. It is separate from
    SetMultisampling, which smooths 3D models. It takes effect at the next
    frame.

    Attribute: Parameter samples How many samples per pixel: 1 (off), 2, 4 or 8.

    Attribute: Example
    use Libraries.Game.Game

    class Main is Game
        action Main
            UseVulkan(true)
            StartGame()
        end

        action CreateGame
            SetMultisampling2D(4)
        end
    end
    */
    action SetMultisampling2D(integer samples)
        multisampleCount2D = samples
        if manager:GetGameGraphics() is VulkanGraphics
            VulkanGraphics vulkan = cast(VulkanGraphics, manager:GetGameGraphics())
            vulkan:SetMultisampleCount2D(samples)
        end
    end

    /*
    This action returns how many samples per pixel 2D MSAA was asked to use
    (see SetMultisampling2D).

    Attribute: Returns The count asked for; 1 means it's off.

    Attribute: Example
    use Libraries.Game.Game

    class Main is Game
        action Main
            StartGame()
        end

        action CreateGame
            SetMultisampling2D(4)
            output "2D MSAA samples: " + GetMultisampling2D()
        end
    end
    */
    action GetMultisampling2D returns integer
        return multisampleCount2D
    end
```

## 3. `Graphics/Vulkan/VulkanPainter2D.quorum`

### `RegenerateRenderPass`

From `VulkanAttachmentDescription outputColorAttachment` through
`subpassDescriptions:Add(subpass)` becomes:

```
        // The attachments match the swapchain's framebuffers, with or
        // without 2D MSAA (Item 29).
        Array<VulkanAttachmentDescription> attachmentDescriptions
        Array<VulkanSubpassDescription> subpassDescriptions
        subpassDescriptions:Add(graphics:MakeSwapchainSubpass(isFirstPass, attachmentDescriptions))
```

`renderPass:Dispose()` at the top, which alerts "NYI", is no longer
reached when the count changes (see `Begin`).

### `Begin`

Right before `// If the render pass isn't defined and valid, regenerate it.`:

```
        // If the 2D sample count changed (Item 29), the swapchain's
        // framebuffers were remade for it; make this painter's pass match.
        // The old pass is let go, since VulkanRenderPass:Dispose isn't
        // written yet.
        if IsRenderPassValid() and renderPass:GetSampleCount() not= graphics:GetSwapchainSampleCount()
            renderPass = undefined
        end
```

### Pipelines

In `Draw` (around line 600):

```
        if vulkanProgram:GetPipeline() = undefined
            vulkanProgram:CreatePipeline(renderPass)
        end
```

becomes

```
        // Made, or made again if it was made for another sample count
        // (Item 29).
        VulkanPipeline programPipeline = vulkanProgram:GetPipeline()
        if programPipeline = undefined
            vulkanProgram:CreatePipeline(renderPass)
        elseif programPipeline:GetInfo():GetRasterizationSamples() not= renderPass:GetSampleCount()
            vulkanProgram:CreatePipeline(renderPass)
        end
```

## 4. `Graphics/Vulkan/VulkanPainter2DBatch.quorum`

`GetPipeline` returns the program's current pipeline, rather than the one
it had when the batch was made:

```
    /*
    This action returns the batch's pipeline: its program's current one,
    which is made again if the 2D sample count changes (Item 29).

    Attribute: Returns The pipeline.
    */
    action GetPipeline returns VulkanPipeline
        VulkanShaderProgram strategy = cast(VulkanShaderProgram, program:GetShaderProgramStrategy())
        return strategy:GetPipeline()
    end
```

The `pipeline` field stays, for the device it was made on (`Create`).

## 5. `Graphics/Vulkan/VulkanPainter3D.quorum`

### The result pass

From `// Final result rendering attachments.` through
`CreateRenderPass(resultRenderPass, resultAttachmentDescriptions, resultColorAttachmentReferences, depthReference)`
becomes:

```
        // Final result rendering attachments: the same as the swapchain's
        // framebuffers, with or without 2D MSAA (Item 29). The first layer
        // clears; later layers draw on what earlier layers drew.
        VulkanSubpassDescription resultSubpass = graphics:MakeSwapchainSubpass(isFirstPass, resultAttachmentDescriptions)
        CreateRenderPass(resultRenderPass, resultAttachmentDescriptions, resultSubpass:GetColorAttachments(),
            resultSubpass:GetDepthStencilAttachment(), resultSubpass:GetResolveAttachments())
```

(`resultColorAttachmentReferences` is no longer used and is removed.)

### `Begin`

The Item 28 check also remakes the passes when the 2D count changed:

```
            if resized or graphics:GetUsableMultisampleCount() not= sceneSampleCount
```

becomes

```
            if resized or graphics:GetUsableMultisampleCount() not= sceneSampleCount or
                resultRenderPass:GetSampleCount() not= graphics:GetSwapchainSampleCount()
```

### Pipelines in the result pass

`NeedsScenePipeline` becomes a general check:

```
    /*
    This action returns true if a pipeline must be made (again): it doesn't
    exist yet, or it was made for a different sample count than its pass
    now uses (Items 27 and 29).

    Attribute: Parameter pipeline The pipeline, or undefined.
    Attribute: Parameter samples The sample count of the pass it draws in.
    Attribute: Returns True if it must be made.
    */
    private action NeedsPipeline(VulkanPipeline pipeline, integer samples) returns boolean
        if pipeline = undefined
            return true
        end
        return pipeline:GetInfo():GetRasterizationSamples() not= samples
    end
```

Uses:
- **Scene pipelines (Item 27):** `NeedsScenePipeline(x)` becomes
  `NeedsPipeline(x, sceneSampleCount)`.
- **The copy pipeline:** `if resultPipeline = undefined` becomes
  `if NeedsPipeline(resultPipeline, resultRenderPass:GetSampleCount())`.
- **The sky pipeline (`RecordSkybox`):** `if pipeline = undefined` becomes
  `if NeedsPipeline(pipeline, resultRenderPass:GetSampleCount())`.

## Size

- `VulkanGraphics`: about +230 −110 (the framebuffer code moves into one
  action).
- `VulkanPainter2D`: −60 +20.
- `VulkanPainter3D`: −45 +25.
- `VulkanPainter2DBatch`: +5.
- `Game`: +60, mostly documentation.

## What changes for existing games

- **With 2D MSAA off** (the default):
  - the swapchain pass, framebuffers and painters' passes are made from
    one shared description. It is identical to the three copies it
    replaces, except that the swapchain pass's dependency also waits for
    color writes, as Item 27's do;
  - 2D batches read their pipeline from their program, which is the same
    pipeline.
- **On a resize:** the same work as before, now in one action, which also
  frees the old depth image views (they were freed before too).
- **OpenGL:** no change. `SetMultisampling2D` only stores the number.

## Risks and things to know

- **Memory with 2D MSAA on:** the multisampled color image, about 33 MB at
  1080p at 4×, plus a transient depth image. Bandwidth: one store and load
  of it per extra layer in a frame.
- **Each pass resolves into the swapchain image,** including passes whose
  result a later layer overwrites. That costs some bandwidth, but it is
  correct: the last layer's resolve is what's shown.
- **The first layer must clear.** That is unchanged (`isFirstPass`), but
  with MSAA it's what starts the multisampled image each frame. A frame
  where no painter draws would show the last frame's resolve, as today.
- **Changing the count** waits for the device, and leaks the old render
  passes (tiny); images are freed.
- **2D items that are blended:** with MSAA, blending happens per sample and
  is then averaged. That looks the same as now, except at the edges.

## Test plan

**`MSAA2DCheck.quorum`** (project; written when this is applied):
- **2D items:** squares, images and buttons turning slowly; some scaled
  non-uniformly; a filled circle and text for comparison.
- **The same over a 3D scene** (a second layer) with the Day sky.
- **Keys:**
  - N steps the 2D count through 1, 2, 4 and 8;
  - M steps the 3D count (Item 27);
  - the console reports the counts asked for and used, and the frame time.
- **What to see:**
  1. Turned squares' edges are smooth at 4, and stair-stepped at 1.
  2. Circles and text look the same either way.
  3. 2D over 3D stacks correctly with any mix of the two counts.
  4. Resizing and minimizing work.
  5. No errors when switching.
- **Then:** TextureUpdateCheck, SkyboxCheck, DriveOpen and TerrainEditor
  with both off, to check nothing changed.

## Rollback

Revert the five files and rebuild the library. There is no Java.
