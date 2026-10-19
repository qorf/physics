# Item 36: objects made every frame

**Status (2026-10-19): plan, for review.** Nothing is applied yet. It
doesn't depend on Items 31 to 35. It is section 6 of `MemoryPlan.md`, with
the recommended answer to decision 6: shared classes (`Layer3D`, `Item3D`)
are included, with behaviour kept identical.

These aren't leaks: Java collects them. But they make garbage every
frame, which costs collector time and shows as hitches. #28 (boxing in
`VulkanPainter3DBatch`) was one such case. **It is applied in four parts,
each measured on its own (the frame-time and heap columns in MemoryCheck):
36a to 36d.** Paths are as in `Item31.md`.

## The rule all four parts use

**Commands are recorded immediately.**
- `VulkanCommandBuffer:Record(command)` calls `command:Record(me)`, a
  `system action` that issues the `vkCmd*` call there and then (checked
  for every class in `G/Commands/`).
- Nothing keeps the command object afterwards. So a command, barrier or
  submit object can be a **field, set again and recorded again** every
  frame.

**One field per use site, never one per type.**
- A reused object keeps every setting from its last use.
- Two sites sharing one `BindDescriptorSetCommand`, where only one calls
  `SetSetIndex(1)`, would leak that setting into the other.
- So each declaration listed below becomes its own field, with the name
  given. Its uses stay exactly as they are; only the declaration line is
  deleted from the action.
- **Inside a loop,** the one field is set again in full every pass (the
  same lines run each time), so it can be shared by the passes.

## 36a: `VulkanGraphics:DisplayCurrentImage`

**Today, every frame:** one `VulkanSubmitInfo`, four `Array`s, and a boxed
`integer` (`waitDestinationStageMasks`), as its own TO-DO says.

**New fields,** after `currentRenderFence`:

```
    // Reused every frame to submit the frame's commands (Item 36).
    VulkanSubmitInfo frameSubmitInfo
    Array<VulkanCommandBuffer> frameCommandBuffers
    Array<VulkanSemaphore> frameSignalSemaphores
    Array<VulkanSemaphore> frameWaitSemaphores
    Array<integer> frameWaitStageMasks
```

**`DisplayCurrentImage`.** From the TO-DO comment through
`submitInfo:SetFence(currentRenderFence)`, it becomes:

```
        // The submit description and its arrays are reused every frame
        // (Item 36). The stage mask never changes, so it is added once.
        if frameWaitStageMasks:IsEmpty()
            frameWaitStageMasks:Add(constants:PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT)
            frameSubmitInfo:SetWaitDestinationStageMasks(frameWaitStageMasks)
            frameSubmitInfo:SetCommandBuffers(frameCommandBuffers)
            frameSubmitInfo:SetSignalSemaphores(frameSignalSemaphores)
            frameSubmitInfo:SetWaitSemaphores(frameWaitSemaphores)
        end
        frameCommandBuffers:Empty()
        frameSignalSemaphores:Empty()
        frameWaitSemaphores:Empty()
        frameCommandBuffers:Add(currentRenderCommandBuffer)
        frameSignalSemaphores:Add(imageRenderCompleteSemaphores:Get(currentSwapchainIndex))
        frameWaitSemaphores:Add(imageAcquiredSemaphores:Get(currentResourceIndex))
        frameSubmitInfo:SetFence(currentRenderFence)

        graphicsQueue:SubmitCommands(frameSubmitInfo)
```

The `DisplayCurrentImageNative` line is unchanged. It uses
`currentSwapchainIndex` for the render-complete semaphore after Item 31.

`VulkanSubmitInfo`'s setters keep the arrays by reference, and
`VulkanQueue.java`'s `SubmitCommands` reads them at submit time into stack
memory (checked). So setting them once and refilling them each frame is
safe.

**The animation compute submit** in `VulkanPainter3D:ComputeAnimations`
(`VulkanSubmitInfo submitInfo`, `Array<VulkanCommandBuffer>
commandBuffers`) gets the same treatment: the fields
`animationSubmitInfo` and `animationCommandBuffers` in `VulkanPainter3D`.

## 36b: `VulkanPainter3D:End` and its helpers

Each declaration below becomes a field of `VulkanPainter3D` with the new
name, and every use in that action is renamed to match. The fields go
together after `releasesSeen` (Item 33), under the comment
`// Commands and barriers reused every frame; see Item36.md.`

| Action (line on 2026-10-19) | Declaration today | Field |
|---|---|---|
| `End` (1388) | `VulkanMemoryBarrier memoryBarrier` | `copyBarrier` |
| `End` (1394) | `PipelineBarrierCommand barrierCommand` | `copyBarrierCommand` |
| `End` (1477) | `BeginRenderPassCommand beginRenderPass` | `beginScenePass` |
| `End` (1484) | `BindPipelineCommand bindPipeline` | `bindScenePipeline` |
| `End` (1500) | `BindVertexBufferCommand bindVertex` | `bindDummyVertex` |
| `End` (1517) | `BindDescriptorSetCommand cameraBind` | `sceneCameraBind` |
| `End` (1526) | `BindDescriptorSetCommand texturesBind` | `sceneTexturesBind` |
| `End` (1535) | `SetPushConstantsCommand setPushConstants` | `scenePushConstants` |
| `End` (1542) | `DrawIndirectCommand drawCommand` | `sceneDraw` |
| `End` (1565) | `BindPipelineCommand bindProgramPipeline` | `bindProgramPipeline` |
| `End` (1569) | `BindDescriptorSetCommand programCameraBind` | `programCameraBind` |
| `End` (1578) | `BindDescriptorSetCommand programTexturesBind` | `programTexturesBind` |
| `End` (1586) | `SetPushConstantsCommand programPushConstants` | `programPushConstantsCommand` |
| `End` (1592) | `DrawIndirectCommand programDraw` | `programDraw` |
| `End` (1604) | `EndRenderPassCommand endRenderPass` | `endScenePass` |
| `End` (1638) | `Array<VulkanDrawQueue3D> shadowQueues` | `shadowQueues` (emptied at the start of each use) |
| `End` (1661) | `BeginRenderPassCommand beginShadowPass` | `beginShadowPass` |
| `End` (1668) | `BindPipelineCommand bindShadowPipeline` | `bindShadowPipeline` |
| `End` (1672) | `SetViewportCommand setViewport` | `shadowViewport` |
| `End` (1677) | `SetScissorCommand setScissor` | `shadowScissor` |
| `End` (1686) | `BindDescriptorSetCommand shadowDescriptorBind` | `shadowDescriptorBind` |
| `End` (1722) | `BindDescriptorSetCommand shadowTextureDescriptorBind` | `shadowTextureDescriptorBind` |
| `End` (1733) | `SetPushConstantsCommand setPushConstants` | `shadowPushConstantsCommand` |
| `End` (1748) | `DrawIndirectCommand drawCommand` | `shadowDraw` |
| `End` (1765) | `EndRenderPassCommand endShadowRenderPass` | `endShadowPass` |
| `End` (1794) | `BeginRenderPassCommand beginLightRender` | `beginLightPass` |
| `End` (1808) | `BindPipelineCommand bindLightPipeline` | `bindLightPipeline` |
| `End` (1819) | `BindDescriptorSetCommand lightDescriptorBind` | `lightDescriptorBind` |
| `End` (1824) | `BindDescriptorSetCommand lightDataDescriptorBind` | `lightDataDescriptorBind` |
| `End` (1830) | `BindDescriptorSetCommand lightShadowDescriptorBind` | `lightShadowDescriptorBind` |
| `End` (1836) | `DrawCommand lightDrawCommand` | `lightDraw` |
| `End` (1841) | `EndRenderPassCommand endLightRenderPass` | `endLightPass` |
| `End` (1853) | `BeginRenderPassCommand beginResultRender` | `beginResultPass` |
| `End` (1873) | `BindPipelineCommand bindResultPipeline` | `bindResultPipeline` |
| `End` (1884) | `BindDescriptorSetCommand resultDescriptorBind` | `resultDescriptorBind` |
| `End` (1889) | `DrawCommand resultDrawCommand` | `resultDraw` |
| `End` (1894) | `EndRenderPassCommand endResultRenderPass` | `endResultPass` |
| `ComputeAnimations` (1911) | `VulkanMemoryBarrier memoryBarrier` | `animationBarrier` |
| `ComputeAnimations` (1916) | `PipelineBarrierCommand barrierCommand` | `animationBarrierCommand` |
| `ComputeAnimations` (1920) | `BindComputePipelineCommand bindPipelineCommand` | `bindAnimationPipeline` |
| `ComputeAnimations` (1953) | `SetPushConstantsCommand setPushConstants` | `animationPushConstantsCommand` |
| `ComputeAnimations` (1960) | `ComputeShaderDispatchCommand dispatch` | `animationDispatch` |
| `AttachmentWriteBarrier` (2024) | `VulkanImageMemoryBarrier barrier` | `attachmentBarrier` |
| `AttachmentWriteBarrier` (2036) | `PipelineBarrierCommand barrierCommand` | `attachmentBarrierCommand` |
| the viewport helper (2042, 2049) | `SetViewportCommand setViewport`, `SetScissorCommand setScissor` | `fullViewport`, `fullScissor` |
| the second viewport helper (2056, 2063) | the same | `fullViewport2`, `fullScissor2` |
| `DrawSkybox` (2217) | `BindPipelineCommand bindPipeline` | `bindSkyPipeline` |
| `DrawSkybox` (2222) | `BindDescriptorSetCommand bindCube` | `bindSkyCube` |
| `DrawSkybox` (2250) | `SetPushConstantsCommand setPushConstants` | `skyPushConstantsCommand` |
| `DrawSkybox` (2256) | `DrawCommand drawSky` | `drawSky` |

**Before converting, check each field for a set-once value.** Any
setting made only on some passes of a loop (`if ... SetX(...)`) must be
set on every pass, or reset at the top of the loop. Two such cases came up
in the audit, both in the shadow loop:
- the push constants' write position, already reset with
  `ResetWritePosition()` each pass;
- `shadowTextureDescriptorBind`'s set index, which is always set.

Any other case found while applying gets an explicit reset line, noted in
the applied Item.

**Expected saving:**
- About 50 objects a frame in a simple scene.
- Several hundred with many lights and texture groups. The two-stage
  shadow path multiplies the draw commands by lights × cascades × faces,
  and the Mac uses it.

## 36c: `VulkanPainter2D:End` and `EnvironmentVulkan`

**`VulkanPainter2D:End`.** The same rule applies to the declarations at
lines:
- 367/373: `copyBarrier`, `copyBarrierCommand`;
- 390: `beginPass`;
- 417: `bindPipelineCommand`;
- 431/456: `viewportCommand`, `scissorCommand`;
- 467/471: `vertexBind`, `indexBind`;
- 482/489: `descriptorBind`, `texturesBind`;
- 504: `endPass`.

Item 32's `readBarrier` and `readBarrierCommand` in `EndBatches` become
fields too.

**`DrawIndexedCommand` per flush (line 621)** is kept in
`pendingDrawCommands` until `End`, so it can't be a single field. It comes
from a pool:
- **New field:** `Array<DrawIndexedCommand> drawCommandPool`, with
  `integer drawCommandsUsed = 0`.
- **At 621,** `DrawIndexedCommand drawCommand` becomes:

```
        DrawIndexedCommand drawCommand = undefined
        if drawCommandsUsed < drawCommandPool:GetSize()
            drawCommand = drawCommandPool:Get(drawCommandsUsed)
        else
            DrawIndexedCommand newCommand
            drawCommandPool:Add(newCommand)
            drawCommand = newCommand
        end
        drawCommandsUsed = drawCommandsUsed + 1
```

- **At the end of `End`,** where `pendingDrawCommands` is emptied, add
  `drawCommandsUsed = 0`.
- **The clip `Vector4` at 630** gets the same pool:
  `Array<Vector4> clipValuePool`, with `integer clipValuesUsed`.

**`EnvironmentVulkan:CalculateShadowProjections`.** It runs when the
camera moves, which is most frames. Its locals become fields, under
`// Scratch values reused by CalculateShadowProjections (Item 36).`
- **Line 570:** `Matrix4 inverseCamera` becomes `shadowInverseCamera`.
- **Line 585:** `Array<number> cascadeSplits` becomes a
  `Number32BitArray shadowCascadeSplits`. It is sized `SetSize(CASCADE_COUNT)`
  once, and `Set(i, ...)` replaces `Add`. **This one also removes boxing:**
  each `Add` on `Array<number>` boxes a `Number`.
- **Line 624:** `Array<Vector3> frustumCorners` becomes `shadowFrustumCorners`,
  filled once with 8 `Vector3`s, then set in place.
- **Each `Vector3`/`Vector4` local** at lines 607, 641, 651, 657, 661–664,
  683, 688, 699, 701, 704, 706, 720, 725, 727, 785, 786 and 808 becomes a
  field named after its local with a `shadow` prefix (for example
  `shadowFrustumCenter`).
  - Where the same name is declared in two blocks (`calc` at 664, 688 and
    704), each gets its own field: `shadowCalcFar`, `shadowCalcUp`,
    `shadowCalcExtents`.
  - Each field is set with `Set` or `SetX/Y/Z` before use, as the locals
    are today. The exact lines are written out when this part is applied,
    after Item 35, which also touches this file.

**Overlap with #14.** Cascade snapping (#14) also changes this action.
Whichever lands second is rebased onto the first.

## 36d: physics (`Layer3D`, `Item3D`), shared with OpenGL

**Behaviour stays identical.** Only where objects come from changes.

**`Layer3D:SynchronizeTransforms`.**
- **Today,** about 8 objects per awake body per step. Its result
  (`predictedTransform`) is never used: the one line using it is
  commented out.
- **Change:** the body of the `if` is removed. The action keeps its name
  and loop, with a comment:

```
    action SynchronizeTransforms
        // This predicted each awake body's next transform, but nothing used
        // the result (the line applying it was commented out), so the work
        // is gone (Item 36). The drawn-position blending from the
        // TerrainWalk findings would go here.
    end
```

- **Check before applying:** search for callers that read anything it
  set. None was found on 2026-10-19; it only wrote locals.

**`Layer3D:ApplyGravity`.** `Vector3 force` moves above the loop: one per
call instead of one per body. `ApplyForceToCenter` copies the vector
(checked: it adds it into the body's total force).

**`Item3D:SynchronizeNodes` and `SetScreenPositionFromPhysicsPosition`.**
- Their scratch objects become fields of a new shared class:
  - `PhysicsPosition3D xf1` and `Vector3 origin`;
  - `Vector3 vector` and `Matrix3 tempMatrix`.
- **Why a shared class:** it is one instance for the program, so adding
  fields costs nothing per item. As fields on `Item3D` they would cost
  memory for every item, including thousands of terrain collision pieces.
- **Recursion is safe.** `SynchronizeNodes` recurses into children only
  after it has finished with `xf1` and `origin`.

New file `Quorum/Library/Standard/Libraries/Interface/Item3DScratch.quorum`:

```
package Libraries.Interface

use Libraries.Compute.Vector3
use Libraries.Compute.Matrix3
use Libraries.Game.Physics.PhysicsPosition3D

/*
Item3DScratch holds values that Item3D's physics actions use for a moment
while they work, so they don't make new objects for every item on every
physics step (Item 36). There is one for the whole program.
*/
shared class Item3DScratch
    PhysicsPosition3D nodePosition
    Vector3 nodeOrigin
    Vector3 scaling
    Matrix3 basis

    action GetNodePosition returns PhysicsPosition3D
        return nodePosition
    end

    action GetNodeOrigin returns Vector3
        return nodeOrigin
    end

    action GetScaling returns Vector3
        return scaling
    end

    action GetBasis returns Matrix3
        return basis
    end
end
```

In `SynchronizeNodes`, `PhysicsPosition3D xf1` and `Vector3 origin` become:

```
        Item3DScratch scratch
        PhysicsPosition3D xf1 = scratch:GetNodePosition()
        Vector3 origin = scratch:GetNodeOrigin()
```

In `SetScreenPositionFromPhysicsPosition`, the `Vector3 vector` and
`Matrix3 tempMatrix` declarations become:

```
        Item3DScratch scratch
        Vector3 vector = scratch:GetScaling()
        Matrix3 tempMatrix = scratch:GetBasis()
```

**Check before applying:** that `PhysicsPosition3D:Set(basis, origin)`
copies rather than keeps the objects. If it keeps them, `xf1` must stay a
new object, and only `origin` moves. The same goes for `GetLocalScaling`
filling `vector` in place, which its signature suggests.

**Does a shared-class declaration allocate?** In Quorum, a local of a
shared class refers to the one instance; `ModelManagerVulkan manager` is
used that way all over the Vulkan code. If the compiler makes a new
object for it, a field holding the instance on `Layer3D` (passed in) is
the fallback.

## Measuring

MemoryCheck gains a line every two seconds:
- the average frame time;
- the Java heap's growth per second (`SystemHelper` total minus free,
  sampled every frame, summed over the rises between collections).

**For each part:**
1. Run DriveOpen's scene (MSAA off, one sun) and TerrainWalk for 30
   seconds before and after.
2. Compare the heap growth per second and the collector pauses, through
   VisualVM as in `profile.sh`.
3. Write the numbers into the applied Item.

**Expected,** from the audit's counts at 60 frames a second:
- 36a and 36c: a few hundred objects a second each;
- 36b: thousands with the two-stage shadow path;
- 36d: about 16 objects per awake body per step.

## Rollback

Each part reverts on its own.
