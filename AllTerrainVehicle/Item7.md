# Item 7: update a mesh's vertices in place

`LibraryChangesPlan.md` order 7, `VulkanChanges.md` #3. **Approved and
applied on 2026-10-18** to the `quorum-language` branch `TerrainShader`,
along with the project-side change at the end.

**Runs:** compiled and ran on 2026-10-18 with no errors, and editing worked.
The user couldn't tell from the log whether meshes were reused, so DriveOpen's
edit message now prints "Meshes so far: N updated in place, M new". That
count hasn't been checked in a run yet.

Paths are under
`quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/`.

## Why

Today, any change to a terrain region (an E/Q brush stroke, a far model
rebuild) makes a new `ModelData`, which makes a new blueprint, new GPU
buffers and new global buffer IDs. Blueprints are cached forever and IDs are
never recycled, so every edit leaks GPU memory and an ID. A long editing
session or a long drive with streaming eventually runs out.

Terrain edits never change the vertex count or the triangle layout, only
positions, normals, tangents and texture coordinates. So the smallest useful
change is: **let an existing mesh take new vertex data of the same size**,
reusing its GPU buffers and IDs. The index buffer is untouched.

This does not fix the leak for meshes that really are new (that is item #1/#2,
freeing meshes). It just stops terrain from making new ones.

## How the current code works (the parts that matter)

- `MeshVulkan:Load` packs 14 floats per vertex into a host-visible staging
  buffer (mapped and left mapped) and creates a device-local `vertexBuffer`.
- `ModelManagerVulkan` (a `shared` class, so one instance) keeps
  `pendingMeshes`. `ProcessPendingResources` runs once per frame, right after
  `VulkanGraphics:BeginNextFrame`, and records a copy from staging to device
  buffer into **the current frame's render command buffer**. After that
  `dataTransferred` is true and the staging buffer is never touched again.
- There are several frames in flight (`swapchain:GetImageCount()`, usually 3).
  Each has its own fence and command buffer. `BeginNextFrame` waits on the
  fence of the slot it is about to reuse, so when it returns, everything that
  slot recorded last time has finished on the GPU.

## The three hazards an in-place update has to avoid

1. **Overwriting a staging buffer the GPU is still copying from.** If we wrote
   new numbers into the one existing staging buffer, a copy recorded one or
   two frames ago might still be waiting to run, and it would pick up the new
   numbers, or half of them.
2. **Overwriting the device vertex buffer while an earlier frame is still
   drawing from it** (write-after-read). Earlier frames' command buffers run
   on the same queue, earlier in submission order, so a pipeline barrier in
   the new frame's command buffer orders against them.
3. **Drawing before the copy has finished** (read-after-write). The painter
   has a transfer → vertex-input barrier, but only when it has pending
   batches (`VulkanPainter3D.quorum:1065`, recorded as #4). We should not
   depend on that.

### Hazard 1: one staging buffer per frame slot

Each mesh that gets updated gets one extra staging buffer **per frame slot**,
created lazily the first time that slot needs it. A slot's buffer is only
written inside `ProcessPendingResources`, which runs right after
`BeginNextFrame` waited on that same slot's fence. The last copy that read
from that buffer was recorded the last time this slot was used, so it is
finished. No counters, no extra fences.

I considered and rejected a frame counter ("don't reuse the staging buffer
until N frames have passed"). It breaks across paused frames (the counter
moves but the GPU doesn't), and it duplicates what the fences already
guarantee.

Checked in `VulkanGraphics.quorum:410-415`: `BeginNextFrame` advances
`currentResourceIndex`, takes that slot's command buffer and fence, and waits
on the fence before anything else (including the paused early return). So
`GetCurrentResourceIndex()` inside `ProcessPendingResources` is exactly the
slot whose previous work is known to be finished.

Cost: for a 257 by 257 region, 66,049 vertices × 56 bytes ≈ 3.7 MB per slot,
so about 11 MB per *edited* region with 3 slots. Only meshes that are actually
updated pay this. Freeing these buffers when editing stops can come later.

### Hazards 2 and 3: two global memory barriers

When at least one update copy is recorded in a frame:

- **Before** the update copies: source stages vertex input + vertex shader
  (access 0, an execution dependency is enough for write-after-read),
  destination stage transfer, access transfer write.
- **After** all copies (first loads and updates): source stage transfer,
  access transfer write; destination stages vertex input + vertex shader,
  access vertex attribute read + shader read + memory read.

The vertex shader reads vertices through buffer device addresses, which is a
shader read in the vertex shader stage, so both are listed. The "after"
barrier also makes first-time mesh loads safe on their own, fixing #4 for
meshes. The painter's barrier stays (redundant but harmless).

The masks are combined with `+`, which equals bitwise OR because each
constant is a different single bit. That avoids importing
`BitwiseOperations`.

### An existing bug this has to fix: paused frames

When the window is minimized, `BeginNextFrame` returns early, **before**
resetting and beginning the frame's command buffer. `Game` still calls
`models:ProcessPendingResources()`, so today any mesh loaded while minimized
records copy commands into a command buffer that is not recording (invalid
Vulkan usage; validation layers would flag it). Updates would hit this all the
time (streaming keeps running while minimized), so the change adds a guard:
if rendering is paused, return and keep all pending work for the next real
frame. Material and animation processing are skipped as well, since they
record into the same command buffer.

The texture manager has the same paused-frame problem. It is **not** touched
here; I will add it to `VulkanChanges.md` as its own item.

## The code changes

Two files: `Models/Vulkan/MeshVulkan.quorum` and
`Models/Vulkan/ModelManagerVulkan.quorum`. Nothing else changes, and no
existing action changes what it does for callers that don't use the new
actions (except the pause guard and the extra barrier, both of which only
make existing behavior correct).

### 1. MeshVulkan.quorum

#### 1a. New import

```quorum
use Libraries.Containers.Array
```

#### 1b. New fields (after `MaterialVulkan material = undefined`, line 46)

Before: (none)

After:

```quorum
    // The mapped staging memory for the first load, kept so an update made
    // before the first copy can write straight into it.
    VulkanNumber32BitMappedMemory vertexMapping = undefined

    // Packed vertices waiting to be copied to the GPU, or undefined if no
    // update is waiting. If several updates come in one frame, the last wins.
    Number32BitArray pendingVertices = undefined

    // One staging buffer and mapping per frame in flight, made the first time
    // a frame slot needs one. A slot's buffer is only written after that
    // slot's fence has been waited on, so the GPU is done reading it.
    Array<VulkanBuffer> updateStagingBuffers
    Array<VulkanNumber32BitMappedMemory> updateMappings
```

#### 1c. `Load`: move the packing loop into `PackVertices`, keep the mapping

Before (lines 58-108, shortened; the loop is unchanged in substance):

```quorum
        Number32BitArray vertices = data:GetVertices()
        Number32BitArray normals = data:GetNormals()
    Number32BitArray tangents = data:GetTangents()
    Number32BitArray bitangents = data:GetBitangents()
    Number32BitArray textureCoordinates = data:GetTextureCoordinates()
    Integer32BitArray indices = data:GetIndices()
        ...
        vertexCount = vertices:GetSize() / 3
        indexCount = indices:GetSize()
        
        integer vertexBufferSize = vertexCount * vertexSize
        vertexStagingBuffer:CreateTransferSourceBuffer(device, vertexBufferSize * 4)
        indexStagingBuffer:CreateTransferSourceBuffer(device, indexCount * 4)
        
        Number32BitArray vertexArray
        vertexArray:SetSize(vertexBufferSize)
        integer counter = 0
        repeat while counter < vertexCount
            ... 14 Set calls per vertex ...
            counter = counter + 1
        end
        
        VulkanNumber32BitMappedMemory vertexMapping = vertexStagingBuffer:MapToNumber32BitMemory()
        VulkanInteger32BitMappedMemory indexMapping = indexStagingBuffer:MapToInteger32BitMemory()
        
        vertexMapping:Set(vertexArray)
        indexMapping:Set(indices)
```

After:

```quorum
        Number32BitArray vertices = data:GetVertices()
        Integer32BitArray indices = data:GetIndices()
        ...
        vertexCount = vertices:GetSize() / 3
        indexCount = indices:GetSize()
        
        integer vertexBufferSize = vertexCount * vertexSize
        vertexStagingBuffer:CreateTransferSourceBuffer(device, vertexBufferSize * 4)
        indexStagingBuffer:CreateTransferSourceBuffer(device, indexCount * 4)
        
        Number32BitArray vertexArray = PackVertices(data)
        
        vertexMapping = vertexStagingBuffer:MapToNumber32BitMemory()
        VulkanInteger32BitMappedMemory indexMapping = indexStagingBuffer:MapToInteger32BitMemory()
        
        vertexMapping:Set(vertexArray)
        indexMapping:Set(indices)
```

The only differences: the loop moves to `PackVertices`, and `vertexMapping`
is the new field rather than a local. The rest of `Load` (destination
buffers, animation data, the commented-out `StopMapping` calls) is unchanged.

#### 1d. New private action `PackVertices`

The body is the existing loop, moved word for word.

```quorum
    /*
    This action packs a mesh's positions, normals, tangents, bitangents and
    texture coordinates into one array of 14 numbers per vertex, the layout the
    vertex shader reads. The texture's vertical coordinate is flipped to match
    Vulkan's image layout.

    Attribute: Parameter data The mesh data to pack.
    Attribute: Returns An array of vertexCount times 14 numbers.
    */
    private action PackVertices(MeshData data) returns Number32BitArray
        Number32BitArray vertices = data:GetVertices()
        Number32BitArray normals = data:GetNormals()
        Number32BitArray tangents = data:GetTangents()
        Number32BitArray bitangents = data:GetBitangents()
        Number32BitArray textureCoordinates = data:GetTextureCoordinates()
        
        integer count = vertices:GetSize() / 3
        Number32BitArray vertexArray
        vertexArray:SetSize(count * vertexSize)
        integer counter = 0
        repeat while counter < count
            integer arrayIndex = counter * vertexSize
            vertexArray:Set(arrayIndex, vertices:Get(counter * 3))
            vertexArray:Set(arrayIndex + 1, vertices:Get(counter * 3 + 1))
            vertexArray:Set(arrayIndex + 2, vertices:Get(counter * 3 + 2))
            
            vertexArray:Set(arrayIndex + 3, normals:Get(counter * 3))
            vertexArray:Set(arrayIndex + 4, normals:Get(counter * 3 + 1))
            vertexArray:Set(arrayIndex + 5, normals:Get(counter * 3 + 2))
            
            vertexArray:Set(arrayIndex + 6, tangents:Get(counter * 3))
            vertexArray:Set(arrayIndex + 7, tangents:Get(counter * 3 + 1))
            vertexArray:Set(arrayIndex + 8, tangents:Get(counter * 3 + 2))
            
            vertexArray:Set(arrayIndex + 9, bitangents:Get(counter * 3))
            vertexArray:Set(arrayIndex + 10, bitangents:Get(counter * 3 + 1))
            vertexArray:Set(arrayIndex + 11, bitangents:Get(counter * 3 + 2))
            
            // Invert the texture y-coordinate to match our coordinate systems.
            vertexArray:Set(arrayIndex + 12, textureCoordinates:Get(counter * 2))
            vertexArray:Set(arrayIndex + 13, 1.0 - textureCoordinates:Get(counter * 2 + 1))
            
            counter = counter + 1
        end
        return vertexArray
    end
```

#### 1e. New public actions (after `TransferBuffers`)

```quorum
    /*
    This action replaces the mesh's vertex data (positions, normals, tangents,
    bitangents and texture coordinates) without making new GPU buffers. The
    new data must have the same number of vertices, and the triangles (the
    indices) stay the same. The mesh keeps drawing its old data until the copy
    runs at the start of the next frame. If this is called several times
    before then, only the last data is copied. Animated meshes are not
    supported.

    Attribute: Parameter data The new mesh data, with the same vertex count as before.
    Attribute: Example

    use Libraries.Game.Graphics.Models.Vulkan.MeshVulkan
    use Libraries.Game.Graphics.Models.Vulkan.ModelBlueprintVulkan

    ModelBlueprintVulkan blueprint = cast(ModelBlueprintVulkan, model:GetModelBlueprint())
    MeshVulkan mesh = blueprint:GetMeshes():Get(0)
    mesh:UpdateVertices(newMeshData)
    */
    action UpdateVertices(MeshData data)
        if not HasData()
            alert("I cannot update this mesh's vertices because it was never loaded.")
        end
        if HasAnimations()
            alert("I cannot update the vertices of an animated mesh.")
        end
        if data:GetVertices():GetSize() / 3 not= vertexCount
            alert("I cannot update this mesh's vertices because the new data has " + (data:GetVertices():GetSize() / 3) + " vertices and the mesh has " + vertexCount + ".")
        end
        
        Number32BitArray packed = PackVertices(data)
        
        // Before the first copy has been recorded, nothing on the GPU reads
        // the first staging buffer yet, so the new data can go straight there.
        if not dataTransferred
            vertexMapping:Set(packed)
            return now
        end
        
        boolean alreadyWaiting = pendingVertices not= undefined
        pendingVertices = packed
        if not alreadyWaiting
            ModelManagerVulkan manager
            MeshVulkan self = me
            manager:QueueMeshUpdate(self)
        end
    end
    
    /*
    This action returns whether new vertex data is waiting to be copied.

    Attribute: Returns True if an update is waiting for the next frame.
    */
    action HasPendingUpdate returns boolean
        return pendingVertices not= undefined
    end
    
    /*
    This action records the copy of waiting vertex data into the given command
    buffer. It is called by the model manager once per frame, right after the
    frame's fence has been waited on, so this slot's staging buffer is free to
    write.

    Attribute: Parameter buffer The frame's command buffer, already recording.
    Attribute: Parameter slot The frame slot (resource index) of this frame.
    Attribute: Parameter slotCount How many frames can be in flight.
    */
    action RecordUpdate(VulkanCommandBuffer buffer, integer slot, integer slotCount)
        if pendingVertices = undefined
            return now
        end
        
        repeat while updateStagingBuffers:GetSize() < slotCount
            updateStagingBuffers:Add(undefined)
            updateMappings:Add(undefined)
        end
        
        VulkanBuffer staging = updateStagingBuffers:Get(slot)
        if staging = undefined
            VulkanBuffer newStaging
            newStaging:CreateTransferSourceBuffer(device, vertexStagingBuffer:GetSize())
            updateStagingBuffers:Set(slot, newStaging)
            updateMappings:Set(slot, newStaging:MapToNumber32BitMemory())
            staging = newStaging
        end
        
        updateMappings:Get(slot):Set(pendingVertices)
        
        CopyBufferCommand copy
        copy:SetSourceBuffer(staging)
        copy:SetDestinationBuffer(vertexBuffer)
        copy:SetSize(staging:GetSize())
        buffer:Record(copy)
        
        pendingVertices = undefined
    end
```

Notes on 1e:

- `MeshVulkan self = me` follows the handoff gotcha about passing `me`.
- `dataTransferred` stays true through an update, so `IsReady` and the
  painter keep treating the mesh as drawable with its old data. The painter
  never checks `IsReady` anyway.
- The vertex count check also guarantees the new data fits the staging and
  device buffers exactly.

### 2. ModelManagerVulkan.quorum

#### 2a. New imports

```quorum
use Libraries.Game.Graphics.Vulkan.VulkanMemoryBarrier
use Libraries.Game.Graphics.Vulkan.Commands.PipelineBarrierCommand
```

#### 2b. New field (after `Array<MeshVulkan> pendingMeshes`, line 49)

```quorum
    // Meshes that already live on the GPU and have new vertex data waiting.
    Array<MeshVulkan> pendingUpdates
```

#### 2c. New action `QueueMeshUpdate`

```quorum
    /*
    This action adds a mesh to the list of meshes whose new vertex data is
    copied at the start of the next frame. MeshVulkan:UpdateVertices calls it;
    other code should not need to.

    Attribute: Parameter mesh The mesh with waiting vertex data.
    */
    action QueueMeshUpdate(MeshVulkan mesh)
        pendingUpdates:Add(mesh)
    end
```

#### 2d. `ProcessPendingResources`

Before: lines 76-114, shown in full above in the "current code" reading
(loops `pendingMeshes`, calls `TransferBuffers`, assigns global IDs, empties
the list, then calls the material and animation managers).

After:

```quorum
    action ProcessPendingResources
        GameStateManager manager
        VulkanGraphics graphics = cast(VulkanGraphics, manager:GetGameGraphics())
        
        // While the window is minimized, the frame's command buffer is not
        // recording, so nothing can be recorded. Keep all waiting work for the
        // next frame that really draws.
        if graphics:IsRenderingPaused()
            return now
        end
        
        boolean copied = false
        VulkanConstants constants
        VulkanCommandBuffer commandBuffer = graphics:GetCurrentRenderCommandBuffer()
        
        if pendingUpdates:IsEmpty() = false
            // Earlier frames may still be drawing from these vertex buffers.
            // Make the copies wait until those reads are done.
            VulkanMemoryBarrier beforeCopy
            beforeCopy:SetSourceStageMask(constants:PIPELINE_STAGE_VERTEX_INPUT_BIT + constants:PIPELINE_STAGE_VERTEX_SHADER_BIT)
            beforeCopy:SetSourceAccessMask(0)
            beforeCopy:SetDestinationStageMask(constants:PIPELINE_STAGE_TRANSFER_BIT)
            beforeCopy:SetDestinationAccessMask(constants:ACCESS_TRANSFER_WRITE_BIT)
            PipelineBarrierCommand beforeCommand
            beforeCommand:SetMemoryBarrier(beforeCopy)
            commandBuffer:Record(beforeCommand)
            
            integer slot = graphics:GetCurrentResourceIndex()
            integer slotCount = graphics:GetSwapchain():GetImageCount()
            integer u = 0
            repeat while u < pendingUpdates:GetSize()
                pendingUpdates:Get(u):RecordUpdate(commandBuffer, slot, slotCount)
                u = u + 1
            end
            pendingUpdates:Empty()
            copied = true
        end
        
        if pendingMeshes:IsEmpty() = false
            integer i = 0
            repeat while i < pendingMeshes:GetSize()
                MeshVulkan mesh = pendingMeshes:Get(i)
                if mesh:HasData()
                    mesh:TransferBuffers(commandBuffer)
                end

                // Also store the vertex buffer in our global array and associate our resources.
                if not recycledVertexIDs:IsEmpty()
                    // TO-DO: Handle this case. This gets complicated by the question of releasing IDs that might be in use for previous frames.
                else
                    //globalVertexBufferArray:Add(mesh:GetVertexBuffer())
                    mesh:SetGlobalVertexBufferIndex(nextVertexBufferID)
                    nextVertexBufferID = nextVertexBufferID + 1
                end
                if not recycledIndexIDs:IsEmpty()
                    // TO-DO: Handle this case. This gets complicated by the question of releasing IDs that might be in use for previous frames.
                else
                    //globalIndexBufferArray:Add(mesh:GetIndexBuffer())
                    mesh:SetGlobalIndexBufferIndex(nextIndexBufferID)
                    nextIndexBufferID = nextIndexBufferID + 1
                end

                i = i + 1
            end

            pendingMeshes:Empty()
            copied = true
        end
        
        if copied
            // Drawing in this frame must wait until the copies are finished.
            VulkanMemoryBarrier afterCopy
            afterCopy:SetSourceStageMask(constants:PIPELINE_STAGE_TRANSFER_BIT)
            afterCopy:SetSourceAccessMask(constants:ACCESS_TRANSFER_WRITE_BIT)
            afterCopy:SetDestinationStageMask(constants:PIPELINE_STAGE_VERTEX_INPUT_BIT + constants:PIPELINE_STAGE_VERTEX_SHADER_BIT)
            afterCopy:SetDestinationAccessMask(constants:ACCESS_VERTEX_ATTRIBUTE_READ_BIT + constants:ACCESS_SHADER_READ_BIT + constants:ACCESS_MEMORY_READ_BIT)
            PipelineBarrierCommand afterCommand
            afterCommand:SetMemoryBarrier(afterCopy)
            commandBuffer:Record(afterCommand)
        end
        
        materialManager:ProcessPendingResources()
        animationManager:ProcessPendingResources()
    end
```

What changed compared with today, line by line:

1. The graphics lookup moved to the top (it was inside the `if`).
2. **New:** the pause guard.
3. **New:** the update block with its "before" barrier. It runs before first
   loads so a mesh can't be both loaded and updated in the wrong order (an
   update made before the first copy goes into the first staging buffer
   anyway, see 1e).
4. The first-load loop is unchanged, apart from setting `copied`.
5. **New:** the "after" barrier when anything was copied.
6. The material and animation calls are unchanged (now skipped while paused).

## Risks and things to know

- **Staging memory might not be coherent.** `CreateTransferSourceBuffer` asks
  for host-visible sequential-write memory without requiring coherent, and
  nothing flushes. This is exactly how the existing load path works, and on
  the Mac (MoltenVK) the memory is coherent. If it ever isn't on some driver,
  first loads would already be broken there too. Not made worse.
- **Animated meshes are refused.** Their vertices also go through a compute
  pass on another queue, which these barriers don't cover.
- **The blueprint's CPU copy goes stale.** `ModelBlueprintVulkan:GetData()`
  still holds the original `ModelData`. I searched the library: nothing reads
  it after loading. Bounding boxes come from the `Model` itself, so the
  terrain code must keep setting dimensions after an update (it already does
  in `PlaceInWorld`).
- **Swapchain recreation can change the image count.** `RecordUpdate` grows
  its arrays to the new count. If the count shrinks, extra buffers are just
  unused. Slot indices stay below the count, so no out-of-range access.
- **Memory:** about 3 × the vertex buffer size per updated mesh (see above).
  Released only when the mesh is (which is never, until #1/#2).
- **Paused frames:** the guard changes behavior only while minimized, and only
  by not recording invalid commands. The texture manager still has the same
  problem, to be listed separately.
- **Barrier cost:** two global barriers in frames with updates, one in frames
  with first loads, none otherwise. Negligible.

## Test plan

Turn on Vulkan validation layers for these runs if possible.

1. **Nothing broken:** run `RunWorldTests` and `RunPhysicsTests`, then a
   normal `DriveOpen` drive with streaming. Expect no change at all (no code
   uses the new actions yet).
2. **Terrain editing** after the project-side change below: E and Q raise and
   lower; holding E for several seconds stays smooth; the shape on screen
   matches the collision (drive onto a mound).
3. **No new blueprints:** a debug count of blueprints/global vertex IDs stays
   flat while editing (`DriveOpen` can print `nextVertexBufferID` through a
   small diagnostic, or just watch memory).
4. **Minimize and restore** while streaming and editing: no crash, no
   validation errors, terrain correct after restore.
5. **Many updates per frame:** a test that updates the same region's mesh
   several times in one frame; the last one wins.

## Rollback

Revert the two files on `TerrainShader`. The project-side change checks for
the new action only through the cast in one place, so it would need reverting
too (or guarding behind a flag, see below).

## Project-side change (done, not library)

- **`TerrainRegionModel`:** it keeps the blueprint it loaded, plus the grid
  columns and rows (`GetPixelWidth`, `GetPixelHeight`) and the splat
  setting it was built with. A build or rebuild with the same three calls
  `UpdateVertices` on that blueprint's mesh. Anything else loads a new mesh
  as before.
  - Columns and rows are compared, not the vertex count, because
    257 by 256 and 256 by 257 have the same count but different triangles.
    A region's grid changes size when the neighbor it reaches into is loaded
    or unloaded.
  - The splat setting is compared because it changes the material, and an
    update keeps the old material.
  - `Model:Load` sets the model's sizes from the blueprint's cached box, and
    an update doesn't reload. Without full collision, the update path
    therefore sets the height itself. With full collision,
    `ApplyCollisionShape` already sets all three sizes.
- **`TerrainRegionFarModel`:** the same, comparing the region size, the step
  and the splat setting. Its `Build` already sets its sizes after loading.
- **`WorldTerrain`:** `SetInPlaceUpdates` and `UsesInPlaceUpdates` (on by
  default) are passed to every model it makes, so the old path can be
  switched back on for comparison.
