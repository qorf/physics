# Item 32: render passes, descriptor sets and 2D batches

**Status (2026-10-19): plan, for review.** Nothing is applied yet. It
needs Item 31 (`VulkanGraphics:Retire` and safe `Dispose`). It is section 5
of `MemoryPlan.md`, apart from shadow maps, which are Item 35.

Vulkan only, on `TerrainShader`. Paths are as in `Item31.md`. **M/** is
`Quorum/Library/Standard/Libraries/Game/Graphics/Shaders/Vulkan/Mapping/`.

The decisions in `MemoryPlan.md` don't affect this Item.

## What leaks today, and what is fixed

**Every resize, and every 3D or 2D sample count change:**

| What | Where | Today | After |
|---|---|---|---|
| 4 render passes | `VulkanPainter3D:Begin` | Let go | Retired |
| 3 descriptor set layouts | `VulkanPainter3D:RegenerateRenderPasses` | Made again | Made once |
| 4 descriptor sets per frame slot | The same | Made again from the pools, which only grow | Kept, linked again |
| The 2D painter's pass | `VulkanPainter2D:Begin` (2D count only) | Let go | Retired |
| The swapchain's pass | `VulkanGraphics:MakeSwapchainFramebuffers` | Let go | Retired |
| One image-acquired semaphore per swapchain image | `VulkanGraphics:RegenerateSwapchain` (resize only) | Let go | Retired |
| The Block shaders' uniform buffers and descriptor sets | `M/BlockShaderMappingVulkan`, `M/BlockErrorShaderMappingVulkan` (on a pipeline rebuild) | A new buffer made over the old one (`Create` on the same object), and new sets | Made once |

**Also fixed here:**
- **The 2D batches' staging buffers are shared by every frame in flight.**
  - The CPU fills frame *F*'s vertices while frame *F − 1*'s copy out of
    the same buffer may not have run yet.
  - The copy into the output buffer also has no barrier against the
    previous frame's draws reading it.
  - Either can show as a flicker in 2D. Each frame slot gets its own
    staging buffer, and a barrier goes before the copies.
- **#22:** the 3D geometry and shadow loops count frame slots (usually 3),
  not texture groups.
  - Models whose textures are in group 3 or later aren't drawn.
  - Groups 0 to 2 get draw queues, about 600 KB each, even if they're
    unused.
  - The fix changes what is drawn (more, not less), so it is called out
    separately below.

**Not changed.** Descriptor set layouts made by `VulkanPipelineInfoCreator`
for a pipeline are still made again with each new pipeline (a few hundred
bytes, only on a sample count change).
- They can't safely be freed with the pipeline. Mappings and painters
  make descriptor sets from them, and Vulkan forbids updating a set
  after its layout is gone.
- They could be made once per mapping later, if this ever matters.

## The code

### `G/VulkanSemaphore.quorum`

The class line becomes `class VulkanSemaphore is VulkanRetirable`. Add,
before the final `end`:

```
    /*
    This action frees the semaphore once VulkanGraphics:Retire knows no
    frame still uses it (Item 32). It is the same as Dispose.
    */
    action Release
        Dispose()
    end
```

(Item 31 already made its Java `Dispose` safe to call twice.)

### `G/VulkanGraphics.quorum`

**`MakeSwapchainFramebuffers`.** The lines

```
        // The old pass is let go: VulkanRenderPass:Dispose isn't written yet.
        VulkanRenderPass pass
        renderPass = pass
```

become:

```
        // The old pass is freed once no frame uses it (Item 32).
        Retire(renderPass)
        VulkanRenderPass pass
        renderPass = pass
```

(`Retire` ignores undefined, which is the case the first time.)

**`RegenerateSwapchain`.** In the loop at its end, the line
`VulkanSemaphore newSemaphore` gains the old one's retirement first:

```
        i = 0
        repeat while i < swapchain:GetImageCount()
            // The old semaphore may still have a signal pending from the
            // acquire that found the swapchain out of date, so it is freed
            // a few frames later rather than now (Item 32).
            if i < imageAcquiredSemaphores:GetSize()
                Retire(imageAcquiredSemaphores:Get(i))
            end
            VulkanSemaphore newSemaphore
            success = newSemaphore:Create(device)
            imageAcquiredSemaphores:Set(i, newSemaphore)
            i = i + 1
        end
```

**Note.** `RegenerateSwapchain` assumes the new swapchain has as many
images as the old one. The command buffers, fences and semaphores are
never resized. If a platform ever changes the count on a resize, `Set`
past the end would fail. That is a separate, pre-existing issue, recorded
in `VulkanChanges.md`, and not changed here.

### `G/VulkanPainter3D.quorum`

**`Begin`.** The block that lets the passes go:

```
                graphics:GetDevice():WaitUntilIdle()
                sceneRenderPass = undefined
                shadowRenderPass = undefined
                lightRenderPass = undefined
                resultRenderPass = undefined
```

becomes:

```
                graphics:GetDevice():WaitUntilIdle()
                graphics:Retire(sceneRenderPass)
                graphics:Retire(shadowRenderPass)
                graphics:Retire(lightRenderPass)
                graphics:Retire(resultRenderPass)
                sceneRenderPass = undefined
                shadowRenderPass = undefined
                lightRenderPass = undefined
                resultRenderPass = undefined
```

The comment above it changes its last sentence. "The old passes are let
go rather than disposed, since VulkanRenderPass:Dispose isn't written yet;
their framebuffers and images are freed in RegenerateRenderPasses." becomes
"The old passes are retired (Item 32); their framebuffers and images are
freed in RegenerateRenderPasses."

**`RegenerateRenderPasses`, the top.** Its four `if ... not= undefined` /
`Dispose()` blocks (for `sceneRenderPass`, `lightRenderPass`,
`resultRenderPass` and `shadowRenderPass`) are removed. `Begin` always
retires the passes and sets them to undefined before calling this, and
the first call has none. In their place:

```
        // Begin has already retired any old passes (Item 32).
```

**The dead shadow loop.** The loop

```
        integer counter = 0
        repeat while counter < shadowCubemapFramebuffers:GetSize()
            Array<VulkanFramebuffer> framebuffers
            ...
            counter = counter + 1
        end
```

is removed. It walks a new empty array and does nothing. Shadow maps and
their framebuffers are kept across a resize on purpose (Item 30); Item 35
frees them when lights are removed.

**Keeping the descriptor sets.** The four lines

```
        shadowProjectionDescriptors:Empty()
        lightDescriptors:Empty()
        lightShadowDataDescriptors:Empty()
        resultDescriptors:Empty()
```

are replaced by:

```
        // The descriptor sets, and the layouts they're made from, are made
        // the first time only. On later calls the sets are kept, and the
        // loop below links the new images into the lighting and result
        // sets. The shadow sets don't depend on the window's size (Item 32).
```

**Why this is enough:**
- Each layout is already made inside an `if <sets>:GetSize() <
  swapchain:GetImageCount()` guard, and each set inside `if <layout> not=
  undefined`. Once the arrays stay full, later calls make neither.
- The loop already links the four G-buffer views into `lightDescriptors`
  and the light view into `resultDescriptors` on every call.
- `Begin` has waited for the device, so updating the sets is safe.
- **Item 30's re-linking at the end** (`shadowProjectionResourcesLinked =
  false`, and `LinkShadowMap` for each existing map) is now unneeded.
  Relinking what is already linked is harmless, so it stays as a safety
  net, with its comment changed to: "The shadow sets are kept (Item 32), so
  this only links again what is already linked. It is kept in case the
  sets are ever made again (Item 30)."

**#22, the geometry pass.** In `End`, the default queues' draw loop

```
        i = 0
        repeat while i < drawQueues:GetSize()
            VulkanDrawQueue3D drawQueue = GetCurrentDrawQueue(i)
            if drawQueue not= undefined and drawQueue:GetDrawCommandCount() > 0
```

becomes:

```
        // One queue per texture group used so far, with undefined for
        // groups never used (#22: this counted frame slots before).
        Array<VulkanDrawQueue3D> defaultQueues = drawQueues:Get(currentSwapchainIndex)
        i = 0
        repeat while i < defaultQueues:GetSize()
            VulkanDrawQueue3D drawQueue = defaultQueues:Get(i)
            if drawQueue not= undefined and drawQueue:GetDrawCommandCount() > 0
```

**What else changes.** The rest of the loop body is unchanged. Its
`textureManager:GetGlobalTextureDescriptorSet(i)` already uses `i` as the
texture group. Reading the array directly, rather than through
`GetCurrentDrawQueue`, stops the loop making queues for unused groups.

**#22, the shadow pass.** The list of default queues

```
        integer queueCounter = 0
        repeat while queueCounter < drawQueues:GetSize()
            shadowQueues:Add(GetCurrentDrawQueue(queueCounter))
            queueCounter = queueCounter + 1
        end
```

becomes:

```
        // This frame's default queues, one per texture group used (#22).
        VulkanGraphics queueGraphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        Array<VulkanDrawQueue3D> defaultShadowQueues = drawQueues:Get(queueGraphics:GetCurrentResourceIndex())
        integer queueCounter = 0
        repeat while queueCounter < defaultShadowQueues:GetSize()
            shadowQueues:Add(defaultShadowQueues:Get(queueCounter))
            queueCounter = queueCounter + 1
        end
```

The shadow loop already skips undefined queues. Custom programs' queues
reach it with undefined padding today.

**How the #22 fix behaves:**
- **A scene whose textures all fit in groups 0 to 2** (31 textures each on
  the Mac) draws exactly as before.
- **With more textures,** models in later groups now appear.
- **Draw queues are no longer made for unused groups 0 to 2.** For
  example, a frame slot that only uses group 0 loses two queues.

### `G/VulkanPainter2D.quorum`

**`Begin`.** In the block

```
        if IsRenderPassValid() and renderPass:GetSampleCount() not= graphics:GetSwapchainSampleCount()
            renderPass = undefined
        end
```

the line `renderPass = undefined` gains `graphics:Retire(renderPass)`
before it. The comment's last sentence, "The old pass is let go, since
VulkanRenderPass:Dispose isn't written yet.", becomes "The old pass is
retired (Item 32)."

**`RegenerateRenderPass`.** Its opening `if renderPass not= undefined` /
`renderPass:Dispose()` block is removed, with the same comment as the 3D
painter: `// Begin has already retired any old pass (Item 32).`

**`EndBatches`.** After the paused check and before the batch loop, add:

```
        // The copies below overwrite output buffers that the previous
        // frame's draws may still be reading. Make them wait for those
        // reads (Item 32).
        VulkanConstants barrierConstants
        VulkanMemoryBarrier readBarrier
        readBarrier:SetSourceStageMask(barrierConstants:PIPELINE_STAGE_VERTEX_INPUT_BIT)
        readBarrier:SetDestinationStageMask(barrierConstants:PIPELINE_STAGE_TRANSFER_BIT)
        readBarrier:SetDestinationAccessMask(barrierConstants:ACCESS_TRANSFER_WRITE_BIT)
        PipelineBarrierCommand readBarrierCommand
        readBarrierCommand:SetMemoryBarrier(readBarrier)
        commandBuffer:Record(readBarrierCommand)
```

`EndBatches` runs before the painter begins its render pass, so a barrier
is allowed there.

### `G/VulkanPainter2DBatch.quorum`

Each frame slot gets its own staging buffers. The output buffers stay
shared, protected by the barrier above and the existing barrier after the
copies.

**Uses.** Add:

```
use Libraries.Containers.Array
use Libraries.Game.GameStateManager
```

**Fields.** The four staging fields

```
    VulkanBuffer vertexStagingBuffer = undefined
    VulkanBuffer indexStagingBuffer = undefined
    ...
    VulkanNumber32BitMappedMemory vertexMappedMemory = undefined
    VulkanInteger32BitMappedMemory indexMappedMemory = undefined
```

become:

```
    // One pair of staging buffers per frame slot, so the CPU never writes a
    // buffer that an earlier frame's copy is still reading (Item 32).
    Array<VulkanBuffer> vertexStagingBuffers
    Array<VulkanBuffer> indexStagingBuffers
    ...
    Array<VulkanNumber32BitMappedMemory> vertexMappedMemories
    Array<VulkanInteger32BitMappedMemory> indexMappedMemories
```

The comments above them stay as they are.

**`Create(ShaderProgram, integer, integer)`.** It becomes:

```
    action Create(ShaderProgram program, integer vertexBufferSize, integer indexBufferSize)
        me:program = program
        VulkanShaderProgram strategy = cast(VulkanShaderProgram, program:GetShaderProgramStrategy())
        pipeline = strategy:GetPipeline()
        VulkanDevice device = pipeline:GetDevice()

        Number32BitArray vertexData
        Integer32BitArray indexData
        VulkanBuffer vertexOutputBuffer
        VulkanBuffer indexOutputBuffer
        me:vertexData = vertexData
        me:indexData = indexData
        me:vertexOutputBuffer = vertexOutputBuffer
        me:indexOutputBuffer = indexOutputBuffer

        VulkanConstants constants
        vertexData:SetSize(vertexBufferSize)
        indexData:SetSize(indexBufferSize)

        GameStateManager gameState
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        integer slot = 0
        repeat while slot < graphics:GetSwapchain():GetImageCount()
            VulkanBuffer vertexStagingBuffer
            VulkanBuffer indexStagingBuffer
            vertexStagingBuffer:CreateTransferSourceBuffer(device, vertexBufferSize * 4)
            indexStagingBuffer:CreateTransferSourceBuffer(device, indexBufferSize * 4)
            vertexStagingBuffers:Add(vertexStagingBuffer)
            indexStagingBuffers:Add(indexStagingBuffer)
            vertexMappedMemories:Add(vertexStagingBuffer:MapToNumber32BitMemory())
            indexMappedMemories:Add(indexStagingBuffer:MapToInteger32BitMemory())
            slot = slot + 1
        end

        vertexOutputBuffer:CreateTransferDestinationBuffer(device, vertexBufferSize * 4, constants:BUFFER_USAGE_VERTEX_BUFFER_BIT)
        indexOutputBuffer:CreateTransferDestinationBuffer(device, indexBufferSize * 4, constants:BUFFER_USAGE_INDEX_BUFFER_BIT)
    end
```

**`TransferBuffers`.** It becomes:

```
    action TransferBuffers(VulkanCommandBuffer buffer)
        GameStateManager gameState
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        integer slot = graphics:GetCurrentResourceIndex()

        vertexMappedMemories:Get(slot):Set(0, vertexData, 0, vertexWritePosition)
        indexMappedMemories:Get(slot):Set(0, indexData, 0, indexWritePosition)

        CopyBufferCommand vertexCopyCommand
        vertexCopyCommand:SetSourceBuffer(vertexStagingBuffers:Get(slot))
        vertexCopyCommand:SetDestinationBuffer(vertexOutputBuffer)
        vertexCopyCommand:SetSize(vertexWritePosition * 4)

        CopyBufferCommand indexCopyCommand
        indexCopyCommand:SetSourceBuffer(indexStagingBuffers:Get(slot))
        indexCopyCommand:SetDestinationBuffer(indexOutputBuffer)
        indexCopyCommand:SetSize(indexWritePosition * 4)

        buffer:Record(vertexCopyCommand)
        buffer:Record(indexCopyCommand)
    end
```

**`Dispose`.** It becomes the following. A batch is disposed only after
180 unused frames, far more than the frames in flight, so on-the-spot
disposal stays safe.

```
    action Dispose
        integer slot = 0
        repeat while slot < vertexStagingBuffers:GetSize()
            vertexMappedMemories:Get(slot):Dispose()
            indexMappedMemories:Get(slot):Dispose()
            vertexStagingBuffers:Get(slot):Dispose()
            indexStagingBuffers:Get(slot):Dispose()
            slot = slot + 1
        end
        vertexMappedMemories:Empty()
        indexMappedMemories:Empty()
        vertexStagingBuffers:Empty()
        indexStagingBuffers:Empty()
        vertexOutputBuffer:Dispose()
        indexOutputBuffer:Dispose()
    end
```

`Dispose` on a buffer unmaps it first, now correctly (Item 31), so the
separate `StopMapping` calls go.

**Memory cost:**
- Each batch's staging is about 600 KB (120,000 numbers and 30,000
  integers). With 3 frame slots that is about 1.8 MB, instead of 600 KB.
- A 2D layer normally has one or two batches.

### `M/BlockShaderMappingVulkan.quorum`

In `CreatePipelineInfo`, the resources for the notch height are made only
the first time. Everything from
`// Also initialize resources for the notch height descriptor.` through
`notchHeightDescriptorSet = descriptorManager:CreateDescriptorSet(descriptorLayout, notchResourcesInfo)`
is wrapped in:

```
        // Made the first time only. A new pipeline (a 2D sample count
        // change) uses the same buffer and set: the set's layout is
        // defined the same way, so the set works with the new pipeline
        // (Item 32).
        if notchHeightDescriptorSet = undefined
            ...the existing lines...
        end
```

### `M/BlockErrorShaderMappingVulkan.quorum`

The same wrapping applies. Everything from
`// Also initialize resources for the notch height descriptor.` through
the end of the `repeat while i < graphics:GetSwapchain():GetImageCount()`
loop that fills `uniformsDescriptorSets` goes inside:

```
        // Made the first time only (Item 32): see BlockShaderMappingVulkan.
        if notchHeightMemory = undefined
            ...the existing lines...
        end
```

(This mapping has no single set field to test, so it tests
`notchHeightMemory`, which is undefined until the first call.)

## Test plan

1. **MemoryCheck (Item 31), with A on for two minutes.** It steps both
   sample counts every half second.
   - GPU memory and allocations go up and down within a range, and don't
     climb.
   - Java heap stays flat after the first minute.
   - The waiting count stays small.
2. **Resizing.** Drag-resize DriveOpen for 20 seconds with the report
   showing (add `GetMemoryReport` to its F-key output, or run MemoryCheck
   and resize it). Memory returns to where it was once the size settles.
3. **MSAACheck and MSAA2DCheck.** Every count, then resize. Lighting,
   shadows and the sky are unchanged.
4. **2D.** A 2D-heavy screen (the Quorum interface, or `Rendering2D`
   checks) with text changing every frame. There is no flicker; there was
   rarely one before.
5. **#22.** A scene with more than 93 textures (three groups of 31 on the
   Mac), for example TextureUpdateCheck with extra textures loaded. Models
   in later groups now show. A scene with few textures looks the same.
6. **Block editor** (if a test is at hand). Change the 2D sample count;
   blocks keep drawing.

## Rollback

Revert the Item 32 changes in the files above. Item 31 stays.
