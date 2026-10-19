# Item 31: safe disposal, and a retirement queue

**Status (2026-10-19): plan, for review.** Nothing is applied yet. This is
the first Item of `MemoryPlan.md` (its sections 1 and 2). Every later
memory Item builds on it.

Vulkan only. OpenGL code isn't touched. It goes on `quorum-language`
branch `TerrainShader`.

Paths:
- **G/** = `Quorum/Library/Standard/Libraries/Game/Graphics/Vulkan/`
- **S/** = `Quorum/Library/Standard/Libraries/Game/Graphics/Shaders/Vulkan/`
- **J/** = `Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/Vulkan/`

The decisions in `MemoryPlan.md` don't affect this Item.

## What it fixes

1. **Pipelines can't be freed: `VulkanPipeline:Dispose` isn't implemented
   yet.** Its body is a placeholder, `alert("NYI")`. This Item implements
   it.
   - `VulkanShaderProgram:CreatePipeline` disposes the old pipeline
     whenever it makes a new one.
   - So today, changing the sample count at runtime stops at that
     placeholder the first time a pipeline is rebuilt: M in MSAACheck, N
     in MSAA2DCheck.
   - Disposing on the spot would also be wrong once implemented: earlier
     frames may still be drawing with the old pipeline. So the old
     pipeline is retired (below), and disposed once those frames finish.
2. **`VulkanBuffer.StopMapping` passes the mapped pointer to VMA, not the
   allocation, and never clears the pointer.**
   - `MaterialVulkan:Prepare` calls it once per material. So every
     material today hands VMA a bad handle. It has seemed harmless only by
     luck.
   - `Dispose` calls it too.
   - `MeshVulkan`, `AnimationFrameVulkan` and `VulkanTextureManager` all
     have their `StopMapping` calls commented out, "crash in some cases".
     This is the likely reason.
3. **No `Dispose` is safe to call twice,** and several aren't written:
   - **not implemented yet (a placeholder `alert("NYI")`):** pipelines, render passes, descriptor set layouts and
     descriptor pools;
   - **missing:** pipeline layouts and samplers;
   - **declared in Quorum, with no Java action:** the push constant buffer.
4. **`VulkanDrawIndirectDataMappedMemory.Dispose`** calls `free()` on
   memory VMA owns, which corrupts the heap.
5. **Nothing can wait for the GPU before freeing.** This Item adds
   `VulkanGraphics:Retire`, which holds an object until every frame that
   might use it has finished, then disposes it. Every later Item uses it.
6. **Small fixes in the same files:**
   - `VulkanRenderPass.java` writes the stencil load and store ops into
     `finalLayout`. All three depth attachments that set stencil ops end
     in `GENERAL` (1) instead of their intended layout.
   - Its first check tests subpasses twice and never tests dependencies.
   - The render-complete semaphores are chosen by frame slot. Presenting
     waits on them per swapchain image, so they should be chosen by
     swapchain image (the Vulkan samples' "present semaphore reuse"
     problem).
   - The command buffer is reset with `RELEASE_RESOURCES` every frame,
     although the comment above it says it shouldn't.
7. **A memory report** (`VulkanGraphics:GetMemoryReport`), so this Item and
   later ones can be measured.

## The rule `Retire` follows

- `BeginNextFrame` counts frames (`frameNumber`).
- Frame *F* uses frame slot `F mod N`, where *N* is the swapchain image
  count.
- `BeginNextFrame` waits on that slot's fence, which last guarded frame
  *F − N*. A fence also covers everything submitted to the queue before
  it.
- **So something retired during frame *c*** (it was used at most by frames
  up to *c*) **is safe to dispose at the start of frame *c + N*,** after
  the fence wait. That is when `Retire` disposes it.
- When the device is idle and nothing has been recorded yet this frame,
  everything waiting can go at once (`ReleaseRetiredNow`).
  `BeginNextFrame` does this after its two `WaitUntilIdle`s, for the
  swapchain and the 2D sample count.
  - **Not** in the painters' `Begin`. The frame's command buffer is already
    recording there, and may use something retired earlier in the same
    frame.

Objects wait in one array, oldest first. Each object carries its own frame
number, so retiring makes no extra objects.

## The code

### New file `G/VulkanRetirable.quorum`

```
package Libraries.Game.Graphics.Vulkan

/*
VulkanRetirable is the parent of Vulkan objects that can be handed to
VulkanGraphics:Retire. Retire keeps such an object until every frame that
might still be using it on the GPU has finished, then calls its Release
action, which frees it.

Attribute: Example
// In a class that made a buffer and now replaces it:
// VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
// graphics:Retire(oldBuffer)
*/
class VulkanRetirable
    // The frame number at which this object may be freed (Item 31).
    integer retireFrame = 0

    /*
    This action frees the object's Vulkan resources. VulkanGraphics calls
    it once no frame on the GPU can still be using the object.
    */
    blueprint action Release

    /*
    This action returns the frame number at which the object may be freed.

    Attribute: Returns The frame number.
    */
    action GetRetireFrame returns integer
        return retireFrame
    end

    /*
    This action sets the frame number at which the object may be freed.

    Attribute: Parameter frame The frame number.
    */
    action SetRetireFrame(integer frame)
        retireFrame = frame
    end
end
```

### Classes that become retirable

Each of these classes changes its declaration to `is VulkanRetirable` and
gains the same `Release`:

| File | Class line becomes |
|---|---|
| `G/VulkanBuffer.quorum` | `class VulkanBuffer is VulkanRetirable` |
| `G/VulkanImage.quorum` | `class VulkanImage is VulkanRetirable` |
| `G/VulkanImageView.quorum` | `class VulkanImageView is VulkanRetirable` |
| `G/VulkanFramebuffer.quorum` | `class VulkanFramebuffer is VulkanRetirable` |
| `G/VulkanPipeline.quorum` | `class VulkanPipeline is VulkanRetirable` |
| `G/VulkanPipelineLayout.quorum` | `class VulkanPipelineLayout is VulkanRetirable` |
| `G/VulkanRenderPass.quorum` | `class VulkanRenderPass is VulkanRetirable` |
| `G/VulkanDescriptorSetLayout.quorum` | `class VulkanDescriptorSetLayout is VulkanRetirable` |
| `G/VulkanSampler.quorum` | `class VulkanSampler is VulkanRetirable` |

The added action, before each class's final `end`:

```
    /*
    This action frees the object once VulkanGraphics:Retire knows no frame
    on the GPU still uses it (Item 31). It is the same as Dispose.
    */
    action Release
        Dispose()
    end
```

### `G/VulkanPipeline.quorum`

`Dispose` (today `alert("NYI")`) becomes:

```
    /*
    This action frees the pipeline and the pipeline layout made for it.
    Doing it twice does nothing. The GPU must have finished every frame
    that used the pipeline: use VulkanGraphics:Retire unless the device is
    idle.
    */
    action Dispose
        if not initialized
            return now
        end
        DisposeNative(device)
        if info not= undefined
            VulkanPipelineLayout layout = info:GetLayout()
            if layout not= undefined
                layout:Dispose()
            end
        end
        initialized = false
    end

    private system action DisposeNative(VulkanDevice device)
```

**Why the pipeline owns its layout:**
- Every shader mapping's `CreatePipelineInfo` starts a new info through
  `VulkanPipelineInfoCreator:Begin`. `Finish` then makes a new pipeline
  layout in it (checked for all 18 mappings).
- So each layout belongs to exactly one pipeline.
- The descriptor set layouts the creator makes aren't freed here. Painters
  and mappings make descriptor sets from them and may update those sets
  later, which Vulkan forbids once the layout is destroyed. Item 32
  handles them.

### `J/VulkanPipeline.java`

The new field, after `vulkanPipelineHandle`:

```java
    // True if CreateNative made its own empty layout, which Dispose frees.
    private boolean ownsLayout = false;
```

In `CreateNative`, set `ownsLayout = true;` after
`vulkanPipelineLayoutHandle = handleBuffer.get(0);` in the
`info.GetLayout() == null` branch. Today that branch can't run: the info's
`layout` field is always made. But it must free what it makes if it ever
does.

The new action, after `GetPipelineHandle`:

```java
    public void DisposeNative(VulkanDevice_ quorumDevice)
    {
        VkDevice vulkanDevice = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanDevice)quorumDevice).plugin_.GetDevice();
        if (vulkanPipelineHandle != 0L)
            vkDestroyPipeline(vulkanDevice, vulkanPipelineHandle, null);
        if (ownsLayout && vulkanPipelineLayoutHandle != 0L)
            vkDestroyPipelineLayout(vulkanDevice, vulkanPipelineLayoutHandle, null);
        vulkanPipelineHandle = 0L;
        vulkanPipelineLayoutHandle = 0L;
        ownsLayout = false;
    }
```

(`VK10.*` is already imported statically, and `org.lwjgl.vulkan.*` covers
`VkDevice`.)

### `G/VulkanPipelineLayout.quorum`

Added after `SetPushConstants`:

```
    /*
    This action frees the layout. Doing it twice does nothing.
    */
    action Dispose
        if not initialized
            return now
        end
        DisposeNative(device)
        initialized = false
    end

    private system action DisposeNative(VulkanDevice device)

    /*
    This action returns true if the layout has been made and not freed.

    Attribute: Returns True if the layout exists.
    */
    action IsInitialized returns boolean
        return initialized
    end
```

### `J/VulkanPipelineLayout.java`

Change `import static org.lwjgl.vulkan.VK10.vkCreatePipelineLayout;` to
`import static org.lwjgl.vulkan.VK10.*;`. Then add:

```java
    public void DisposeNative(VulkanDevice_ quorumDevice)
    {
        if (layoutHandle == 0L)
            return;
        VulkanDevice pluginDevice = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanDevice)quorumDevice).plugin_;
        vkDestroyPipelineLayout(pluginDevice.GetDevice(), layoutHandle, null);
        layoutHandle = 0L;
    }
```

### `G/VulkanRenderPass.quorum`

`Dispose` becomes:

```
    /*
    This action frees the render pass. Doing it twice does nothing.
    Pipelines and framebuffers made with it keep working; only recording
    a new use of the pass needs it. The GPU must have finished every frame
    that used it: use VulkanGraphics:Retire unless the device is idle.
    */
    action Dispose
        if not initialized
            return now
        end
        DisposeNative(device)
        initialized = false
    end

    private system action DisposeNative(VulkanDevice device)
```

### `J/VulkanRenderPass.java`

**The import.** `import static org.lwjgl.vulkan.VK10.vkCreateRenderPass;`
becomes `import static org.lwjgl.vulkan.VK10.*;`.

**The first check** becomes:

```java
        if (quorumDescriptions == null || quorumSubpasses == null || quorumDependencies == null
                || quorumDescriptions.IsEmpty() || quorumSubpasses.IsEmpty())
        {
            return false;
        }
```

Dependencies may be empty. Every pass made today has at least one, and an
undefined array would have crashed further down.

**The stencil fix:**

```java
                if (description.GetStencilLoadOp() >= 0)
                    vkDescription.stencilLoadOp(description.GetStencilLoadOp());
                if (description.GetStencilStoreOp() >= 0)
                    vkDescription.stencilStoreOp(description.GetStencilStoreOp());
```

**The new action:**

```java
    public void DisposeNative(VulkanDevice_ quorumDevice)
    {
        if (vulkanRenderPassHandle == 0L)
            return;
        VulkanDevice pluginDevice = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanDevice)quorumDevice).plugin_;
        vkDestroyRenderPass(pluginDevice.GetDevice(), vulkanRenderPassHandle, null);
        vulkanRenderPassHandle = 0L;
    }
```

**What the stencil fix changes.** Three depth attachments set stencil ops:
- the scene depth (`VulkanPainter3D`);
- the shadow depth (`VulkanPainter3D`);
- the swapchain depth (`VulkanGraphics:MakeSwapchainSubpass`).

Each one:
- **its final layout:** from `GENERAL` (by accident) to the
  `DEPTH_STENCIL_ATTACHMENT_OPTIMAL` it asks for. Every pass starts these
  images from `UNDEFINED` and clears them, so nothing reads the old
  layout.
- **its stencil load op:** set with `ATTACHMENT_STORE_OP_DONT_CARE` (1),
  which as a *load* op means `CLEAR`. `D32_SFLOAT` has no stencil, so
  Vulkan ignores it. For clarity, the three
  `SetStencilLoadOp(constants:ATTACHMENT_STORE_OP_DONT_CARE)` lines become
  `SetStencilLoadOp(constants:ATTACHMENT_LOAD_OP_DONT_CARE)`:
  - `G/VulkanPainter3D.quorum` (scene depth and shadow depth);
  - `G/VulkanGraphics.quorum` (`MakeSwapchainSubpass`).

### `G/VulkanDescriptorSetLayout.quorum`

`Dispose` becomes:

```
    /*
    This action frees the layout. Doing it twice does nothing. Descriptor
    sets made from it must not be updated afterwards.
    */
    action Dispose
        if not initialized
            return now
        end
        DisposeNative(device)
        initialized = false
    end

    private system action DisposeNative(VulkanDevice device)
```

### `J/VulkanDescriptorSetLayout.java`

Change `import static org.lwjgl.vulkan.VK10.vkCreateDescriptorSetLayout;`
to `import static org.lwjgl.vulkan.VK10.*;`, and add:

```java
    public void DisposeNative(VulkanDevice_ quorumDevice)
    {
        if (layoutHandle == 0L)
            return;
        VulkanDevice pluginDevice = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanDevice)quorumDevice).plugin_;
        vkDestroyDescriptorSetLayout(pluginDevice.GetDevice(), layoutHandle, null);
        layoutHandle = 0L;
    }
```

### `G/VulkanSampler.quorum`

Added after `CreateNative`:

```
    /*
    This action frees the sampler. Doing it twice does nothing.
    */
    action Dispose
        if not initialized
            return now
        end
        DisposeNative(device)
        initialized = false
    end

    private system action DisposeNative(VulkanDevice device)
```

### `J/VulkanSampler.java`

Change `import static org.lwjgl.vulkan.VK10.vkCreateSampler;` to
`import static org.lwjgl.vulkan.VK10.*;`, and add:

```java
    public void DisposeNative(VulkanDevice_ quorumDevice)
    {
        if (samplerHandle == 0L)
            return;
        VulkanDevice pluginDevice = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanDevice)quorumDevice).plugin_;
        vkDestroySampler(pluginDevice.GetDevice(), samplerHandle, null);
        samplerHandle = 0L;
    }
```

### `G/VulkanDescriptorPool.quorum`

`Dispose` becomes the following. It isn't retirable: a pool is only freed
when its owner is torn down, after the device is idle.

```
    /*
    This action frees the pool, and with it every descriptor set made from
    it. Doing it twice does nothing. The device must be idle.
    */
    action Dispose
        if not initialized
            return now
        end
        DisposeNative(device)
        initialized = false
    end

    private system action DisposeNative(VulkanDevice device)
```

### `J/VulkanDescriptorPool.java`

Change `import static org.lwjgl.vulkan.VK10.vkCreateDescriptorPool;` to
`import static org.lwjgl.vulkan.VK10.*;`, and add:

```java
    public void DisposeNative(VulkanDevice_ quorumDevice)
    {
        if (poolHandle == 0L)
            return;
        VulkanDevice pluginDevice = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanDevice)quorumDevice).plugin_;
        vkDestroyDescriptorPool(pluginDevice.GetDevice(), poolHandle, null);
        poolHandle = 0L;
    }
```

### `J/VulkanBuffer.java`

`StopMapping` and `Dispose` become:

```java
    public void StopMapping()
    {
        if (!IsMapping())
            return;

        VulkanBuffer_ quorumBuffer = (VulkanBuffer_)me_;
        VulkanDevice_ quorumDevice = quorumBuffer.GetDevice();
        VulkanMemoryAllocator pluginMemoryAllocator = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanMemoryAllocator)quorumDevice.GetMemoryAllocator()).plugin_;

        // VMA unmaps by allocation, not by the mapped address.
        vmaUnmapMemory(pluginMemoryAllocator.GetAllocatorPointer(), memoryHandle);
        mappedMemoryPointer = 0L;
    }

    public void Dispose()
    {
        // A second Dispose, or one before CreateNative, does nothing.
        if (bufferHandle == 0L)
            return;

        StopMapping();

        VulkanBuffer_ quorumBuffer = (VulkanBuffer_)me_;
        VulkanDevice_ quorumDevice = quorumBuffer.GetDevice();
        VulkanMemoryAllocator pluginMemoryAllocator = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanMemoryAllocator)quorumDevice.GetMemoryAllocator()).plugin_;
        vmaDestroyBuffer(pluginMemoryAllocator.GetAllocatorPointer(), bufferHandle, memoryHandle);

        bufferHandle = 0L;
        memoryHandle = 0L;
        bufferDeviceAddress = 0L;
    }
```

Any mapped-memory wrapper (`VulkanNumber32BitMappedMemory` and the like)
made from a buffer must not be written after `StopMapping` or `Dispose`.
That is true of every caller today.

### `J/VulkanImage.java`

`Dispose` becomes:

```java
    public void Dispose()
    {
        // Images wrapped from the swapchain have no VMA memory and aren't
        // ours to free. A second Dispose does nothing.
        if (vulkanImageHandle == 0L || vulkanMemoryHandle == 0L)
            return;

        VulkanDevice_ quorumDevice = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanImage_)me_).GetDevice();
        VulkanMemoryAllocator pluginMemoryAllocator = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanMemoryAllocator)quorumDevice.GetMemoryAllocator()).plugin_;

        vmaDestroyImage(pluginMemoryAllocator.GetAllocatorPointer(), vulkanImageHandle, vulkanMemoryHandle);
        vulkanImageHandle = 0L;
        vulkanMemoryHandle = 0L;
    }
```

### `J/VulkanImageView.java`, `J/VulkanFramebuffer.java`, `J/VulkanSemaphore.java`

Each `Dispose` gains a guard first, and clears its handle at the end.
For `VulkanImageView`:

```java
    public void Dispose()
    {
        if (vulkanImageViewHandle == 0L)
            return;

        VulkanDevice_ quorumDevice = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanImageView_)me_).Get_Libraries_Game_Graphics_Vulkan_VulkanImageView__device_();
        VulkanDevice pluginDevice = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanDevice)quorumDevice).plugin_;
        VkDevice vulkanDevice = pluginDevice.GetDevice();

        vkDestroyImageView(vulkanDevice, vulkanImageViewHandle, null);
        vulkanImageViewHandle = 0L;
    }
```

The same applies to the others:
- **`VulkanFramebuffer`:** guard on `framebufferHandle == 0L`, and set it
  to `0L` after `vkDestroyFramebuffer`.
- **`VulkanSemaphore`:** guard on `semaphoreHandle == 0L`, and set it to
  `0L` after `vkDestroySemaphore`.

### `J/VulkanDrawIndirectDataMappedMemory.java`

```java
    public void Dispose()
    {
        // The memory belongs to the VulkanBuffer, which VMA frees; only the
        // view of it is dropped here.
        drawBuffer = null;
    }
```

### `J/VulkanPushConstantBuffer.java`

The Quorum class declares `system action Dispose`, but the Java class had
none. Add:

```java
    public void Dispose()
    {
        if (buffer != null)
            MemoryUtil.memFree(buffer);
        buffer = null;
    }
```

### `G/VulkanMemoryAllocator.quorum` (for the report)

Added after `Dispose`:

```
    /*
    This action returns how many bytes of GPU memory are allocated through
    the allocator right now, for buffers and images together.

    Attribute: Returns The number of bytes.
    */
    system action GetAllocatedBytes returns number

    /*
    This action returns how many buffers and images are allocated through
    the allocator right now.

    Attribute: Returns The number of allocations.
    */
    system action GetAllocationCount returns integer
```

### `J/VulkanMemoryAllocator.java`

Add `import org.lwjgl.util.vma.VmaTotalStatistics;` and:

```java
    public double GetAllocatedBytes()
    {
        try (MemoryStack stack = MemoryStack.stackPush())
        {
            VmaTotalStatistics statistics = VmaTotalStatistics.calloc(stack);
            vmaCalculateStatistics(allocatorPointer, statistics);
            return (double)statistics.total().statistics().allocationBytes();
        }
    }

    public int GetAllocationCount()
    {
        try (MemoryStack stack = MemoryStack.stackPush())
        {
            VmaTotalStatistics statistics = VmaTotalStatistics.calloc(stack);
            vmaCalculateStatistics(allocatorPointer, statistics);
            return statistics.total().statistics().allocationCount();
        }
    }
```

`VmaTotalStatistics` is in LWJGL 3.4.1's VMA, which `build.gradle` uses
(checked in the jar). `vmaCalculateStatistics` walks every allocation, so
it is for reports, not for every frame.

### `G/VulkanGraphics.quorum`

**New fields,** after `integer currentResourceIndex = -1`:

```
    // Counts frames: BeginNextFrame adds one (Item 31). Objects handed to
    // Retire are freed by frame number.
    integer frameNumber = 0

    // Objects waiting until no frame on the GPU can use them, oldest first
    // (Item 31).
    Array<VulkanRetirable> retired
```

**`BeginNextFrame`:**
- The first line `currentResourceIndex = (currentResourceIndex + 1) mod ...`
  is followed by `frameNumber = frameNumber + 1`.
- After `currentRenderFence:Wait()`, before the minimized check, add:

```
        // Frame frameNumber - N, the last to use this slot, has now
        // finished, so whatever was retired by then can be freed (Item 31).
        ReleaseRetired(false)
```

**In the 2D sample count branch,** after its `device:WaitUntilIdle()`, add
`ReleaseRetired(true)`. In `RegenerateSwapchain`, after its
`device:WaitUntilIdle()`, add the same line. Both run before this frame
records anything.

**The reset.** `currentRenderCommandBuffer:Reset()` becomes
`currentRenderCommandBuffer:Reset(false)`. The comment above it already
says the buffer should keep its memory, and the `Reset` it called asked
Vulkan to release it every frame.

**`DisplayCurrentImage`.** Both uses of
`imageRenderCompleteSemaphores:Get(currentResourceIndex)` become
`imageRenderCompleteSemaphores:Get(currentSwapchainIndex)`.
- A frame's render-complete semaphore is waited on by the *present* of
  that swapchain image. No fence covers the present.
- Chosen by frame slot, a semaphore can be signalled again while an
  earlier present still waits on it.
- Chosen by image, it is only reused once that image has been acquired
  again, which means its present has finished.
- Both arrays have one entry per swapchain image.

**New actions,** after `GetLightingProperties`:

```
    /*
    This action hands over a Vulkan object that is no longer needed, but
    that frames already recorded may still be using on the GPU. It is freed
    (its Release action) once every such frame has finished: after the
    swapchain image count's worth of frames. Retiring undefined does
    nothing. The object must not be used again after it is retired.

    Attribute: Parameter item The object to free.

    Attribute: Example
    // VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
    // graphics:Retire(oldPipeline)
    */
    action Retire(VulkanRetirable item)
        if item = undefined
            return now
        end
        integer slots = 3
        if swapchain not= undefined
            slots = swapchain:GetImageCount()
        end
        item:SetRetireFrame(frameNumber + slots)
        retired:Add(item)
    end

    /*
    This action returns how many retired objects are still waiting to be
    freed.

    Attribute: Returns The number of objects.
    */
    action GetRetiredCount returns integer
        return retired:GetSize()
    end

    /*
    This action frees retired objects, oldest first: those whose frame has
    come, or every one if the device is idle and nothing has been recorded
    this frame.

    Attribute: Parameter everything True to free every retired object.
    */
    private action ReleaseRetired(boolean everything)
        integer released = 0
        boolean releasing = true
        repeat while releasing and released < retired:GetSize()
            VulkanRetirable item = retired:Get(released)
            if everything or item:GetRetireFrame() <= frameNumber
                item:Release()
                released = released + 1
            else
                releasing = false
            end
        end

        if released = 0
            return now
        end
        if released = retired:GetSize()
            retired:Empty()
            return now
        end

        // Move the ones still waiting to the front, keeping their order.
        integer i = released
        repeat while i < retired:GetSize()
            retired:Set(i - released, retired:Get(i))
            i = i + 1
        end
        repeat released times
            retired:RemoveFromEnd()
        end
    end

    /*
    This action returns a line describing the GPU memory in use: the bytes
    and number of buffers and images allocated, and how many retired
    objects are still waiting to be freed. Later memory Items add their
    own counts.

    Attribute: Returns The report.

    Attribute: Example
    // VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
    // output graphics:GetMemoryReport()
    */
    action GetMemoryReport returns text
        VulkanMemoryAllocator allocator = device:GetMemoryAllocator()
        number megabytes = allocator:GetAllocatedBytes() / (1024.0 * 1024.0)
        megabytes = cast(integer, megabytes * 10) / 10.0
        return "GPU memory: " + megabytes + " MB in " + allocator:GetAllocationCount() +
            " allocations; waiting to be freed: " + retired:GetSize()
    end
```

### `S/VulkanShaderProgram.quorum`

**Imports.** Add:

```
use Libraries.Game.Graphics.Vulkan.VulkanGraphics
```

**`CreatePipeline`.** Its first block:

```
        if pipeline not= undefined
            pipeline:Dispose()
        end
```

becomes:

```
        // Frames already recorded may still draw with the old pipeline, so
        // it is freed once they finish (Item 31).
        if pipeline not= undefined
            GameStateManager retireState
            VulkanGraphics retireGraphics = cast(VulkanGraphics, retireState:GetGameGraphics())
            retireGraphics:Retire(pipeline)
            pipeline = undefined
        end
```

**The failure branch,** `if not success`, keeps `pipeline:Dispose()`. A
pipeline that failed to be made has no handles, so `Dispose` now does
nothing there, instead of alerting "NYI" before the real error.

## What changes when it runs

- **MSAACheck (M) and MSAA2DCheck (N):** stepping the sample count works
  without an alert. The old pipelines are freed three frames later.
- **Materials** unmap their staging buffers correctly.
- **Nothing else frees anything new yet.** `Retire` is used here only for
  pipelines. Items 32 to 35 use it for the rest.
- **Final layouts** of the three depth attachments are now the ones asked
  for. No reads depend on them.
- **The render-complete semaphores** are now chosen per swapchain image.
  The swapchain usually hands out images in slot order, so frames behave
  as before.

## `MemoryCheck.quorum` (project, `AllTerrainVehicle/SourceCode/`)

A first version, which later Items extend with their own loops:
- It draws a small lit scene.
- It prints `GetMemoryReport` and the Java heap every two seconds.
- M steps the 3D sample count, and N steps the 2D one.
- **A** turns on automatic stepping, which steps both every half second.
  That makes it easy to see whether memory settles.

```
use Libraries.Game.Game
use Libraries.Game.InputMonitor
use Libraries.Game.GameStateManager
use Libraries.Game.Graphics.Color
use Libraries.Game.Graphics.Model
use Libraries.Game.Graphics.Label
use Libraries.Game.Graphics.AmbientLight
use Libraries.Game.Graphics.DirectionalLight
use Libraries.Game.Graphics.Vulkan.VulkanGraphics
use Libraries.Interface.Events.KeyboardEvent
use Libraries.System.SystemHelper

/*
MemoryCheck watches GPU and Java memory under Vulkan while things are made
and freed (MemoryPlan.md, Items 31 onward). Every two seconds the console
shows the GPU memory report and the Java heap in use.

Keys:
- M steps the 3D MSAA sample count: 1, 2, 4, 8, and back to 1.
- N steps the 2D MSAA sample count the same way.
- A turns automatic stepping on or off: both counts step every half second.

What to see (Item 31):
1. M and N give no alert.
2. With A on, after a minute the GPU memory and allocation count go back
   and forth within a range, rather than climbing. The waiting count stays
   small. Render passes and descriptor sets still leak until Item 32, so
   a slow climb is expected for now.

Attribute: Example
// MemoryCheck is a main program: set it as the project's main file and run
// it.
*/
class MemoryCheck is Game
    Label label
    InputMonitor monitor
    KeyboardEvent keys
    DirectionalLight sun
    AmbientLight ambient
    Model ground
    Model box

    boolean mWasDown = false
    boolean nWasDown = false
    boolean aWasDown = false
    boolean automatic = false
    number timeUntilStep = 0.5
    number timeUntilReport = 2

    action Main
        SetScreenSize(1000, 600)
        UseVulkan(true)
        StartGame()
    end

    action CreateGame
        Color colors
        sun:SetColor(colors:White())
        sun:SetIntensity(2)
        sun:SetDirection(-0.5, -1, 0.7)
        Add(sun)
        ambient:SetColor(0.45, 0.45, 0.45, 1)
        SetAmbientLight(ambient)

        ground:LoadBox(20, 0.2, 20, colors:CustomColor(0.45, 0.55, 0.35, 1))
        ground:SetPosition(0, -0.1, 8)
        Add(ground)
        box:LoadBox(1.5, 1.5, 1.5, colors:Red())
        box:SetPosition(0, 1, 6)
        Add(box)

        GetCamera3D():SetPosition(0, 3, -2)
        GetCamera3D():LookAt(0, 1, 6)

        label:SetPosition(10, 10)
        label:SetText("M 3D samples, N 2D samples, A automatic stepping")
        Add(label)
    end

    action Update(number seconds)
        boolean mDown = monitor:IsKeyPressed(keys:M)
        if mDown and not mWasDown
            Step3D()
        end
        mWasDown = mDown

        boolean nDown = monitor:IsKeyPressed(keys:N)
        if nDown and not nWasDown
            Step2D()
        end
        nWasDown = nDown

        boolean aDown = monitor:IsKeyPressed(keys:A)
        if aDown and not aWasDown
            automatic = not automatic
            output "Automatic stepping: " + automatic
        end
        aWasDown = aDown

        if automatic
            timeUntilStep = timeUntilStep - seconds
            if timeUntilStep <= 0
                Step3D()
                Step2D()
                timeUntilStep = 0.5
            end
        end

        box:Rotate(0, 1, 0, 30 * seconds)

        timeUntilReport = timeUntilReport - seconds
        if timeUntilReport <= 0
            Report()
            timeUntilReport = 2
        end
    end

    private action Step3D
        integer count = GetMultisampling() * 2
        if count > 8
            count = 1
        end
        SetMultisampling(count)
    end

    private action Step2D
        integer count = GetMultisampling2D() * 2
        if count > 8
            count = 1
        end
        SetMultisampling2D(count)
    end

    private action Report
        SystemHelper helper
        number used = helper:GetTotalMemory() - helper:GetFreeMemory()
        integer heapMegabytes = cast(integer, used / (1024.0 * 1024.0))
        GameStateManager manager
        if manager:GetGameGraphics() is VulkanGraphics
            VulkanGraphics graphics = cast(VulkanGraphics, manager:GetGameGraphics())
            output graphics:GetMemoryReport() + "; Java heap: " + heapMegabytes + " MB"
        else
            output "Not running under Vulkan. Java heap: " + heapMegabytes + " MB"
        end
    end
end
```

## Test plan

1. **MSAACheck:** press M through every count, twice. There is no alert,
   and edges change as before.
2. **MSAA2DCheck:** press N and M through every count. There is no alert.
3. **DriveOpen:** drive for a minute and resize. Nothing changes on
   screen.
4. **MemoryCheck:** press A, and watch for a minute.
   - The waiting count stays under about 20.
   - GPU memory climbs only slowly (the leaks Item 32 fixes), and the
     allocation count doesn't climb.
5. **A model-heavy scene** (TerrainWalk). It runs as before. This checks
   that materials unmapping correctly changes nothing visible.

## Rollback

Revert the Item 31 changes in the files above and rebuild the library and
plugins. `VulkanRetirable.quorum` can be deleted.
