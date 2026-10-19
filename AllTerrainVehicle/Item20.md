# Item 20: update a texture in place

`VulkanChanges.md` #20, with the texture half of #21 (`LibraryChangesPlan.md`
order 14) folded in, since it is the same action. **Approved and applied on
2026-10-19** to the `quorum-language` branch `TerrainShader`, with the
project-side `WorldTerrain` change at the end.

**Confirmed working (2026-10-19).** In-place updates show in 2D and 3D, with
texture overrides too (`TextureUpdateCheck.quorum`). In TerrainEditor, paint
shows under the brush, and the splat texture stays at index 5.

Paint first looked broken for two reasons outside this item, both fixed in
the project:
- the splat map was mirrored along z;
- PixelMap's default blending wiped splat pixels with alpha 0 (see
  `TierFour.md` and `VulkanChanges.md` E).

Paths are under
`quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/`.

## Why

In `TerrainEditor`, painting turns the whole ground grey. The editor's
"Splat texture check" confirmed why (2026-10-18):

- The splat texture made at startup gets renderer index 5, in texture group
  0.
- Every paint stroke makes the splat texture again. By the first stroke,
  about 66 other textures exist (very likely the labels' glyph textures), so
  the new one lands at index 72 and up, in group 2.
- The splat shader finds the splat texture and the four ground textures by
  index within the bound group. Outside group 0 it reads the wrong textures,
  everywhere.

Reloading can't help today: `VulkanTextureManager:ProcessPendingTextures`
gives every load a new image, a new view and the next index, even when the
same `Texture` object is loaded again at the same size. Old images, views,
indices and staging buffers are never freed. This is #20: "a texture can't
be updated, and texture places are never reused".

The fix: **when a texture that already has an index is loaded again at the
same size, copy the new pixels into its existing image.** It keeps its
index, view and descriptor. Then:
- the splat texture stays at index 5 for good, and painting shows;
- painting no longer uses up texture places or leaks images.

## How texture loading works now (the parts that matter)

- `Texture:LoadFromPixelMap` (via `LoadFromTextureData`, Texture.quorum
  about line 612) calls `VulkanTextureManager:RequestLoad(texture,
  pixelMap)`, which queues the pair.
- `Game` calls `ProcessPendingTextures` once per frame, right after
  `VulkanGraphics:BeginNextFrame` and before the models' resources (Game.quorum
  about line 799). For each pending texture it:
  1. makes a host-visible staging buffer, maps it, and copies the pixels in
     (Java `TransferPixelData`);
  2. makes a new image (RGBA8, transfer destination and sampled);
  3. records into the frame's command buffer: a transition to transfer
     destination, the buffer-to-image copy, and a transition to shader
     read-only;
  4. keeps the staging buffer in `stagingBuffers`, forever;
  5. makes a new image view and gives it to the texture;
  6. gives the texture the next global index, and writes the view into the
     group's descriptor set at the texture's place in the group.
- **Shaders read textures only in the fragment stage** (the binding is
  `SHADER_STAGE_FRAGMENT_BIT`).

## The hazards of writing into an image that's in use

The same three as mesh updates (`Item7.md`):

1. **Overwriting a staging buffer the GPU is still copying from.** Solved
   the same way: one staging buffer per frame slot, per updated texture,
   written only right after that slot's fence was waited on.
2. **Writing the image while earlier frames still read it** (write after
   read). The update is recorded in this frame's command buffer, on the same
   queue as earlier frames. So a barrier from the fragment shader stage
   (shader reads) to the transfer stage (transfer writes) makes the copy wait
   for their reads. It also changes the layout from shader read-only to
   transfer destination.
3. **Reading before the copy is done** (read after write). The same
   transition back to shader read-only that a first load already records:
   transfer writes to fragment shader reads.

Both transitions are image barriers on this one image, so other textures
aren't held up.

### Paused frames (#21, for textures)

While the window is minimized, `BeginNextFrame` returns before the frame's
command buffer starts recording, but `Game` still calls
`ProcessPendingTextures`. Today a texture loaded while minimized is recorded
into a command buffer that isn't recording, which is invalid Vulkan use. The
same guard as the model manager got in Item 7: if rendering is paused,
return and keep the pending textures for the next real frame.

## The code change

One file: `Vulkan/VulkanTextureManager.quorum`. No Java, no shader, and no
change to `Texture`.

### 1. New field (after `Array<VulkanBuffer> stagingBuffers`, line 23)

```quorum
    // Staging buffers for textures loaded again after their first load: for
    // each texture, one per frame in flight. A frame slot's buffer is only
    // written after that slot's fence has been waited on, so the GPU is done
    // copying from it. They are reused while the texture's size stays the
    // same.
    HashTable<Texture, Array<VulkanBuffer>> updateStagingBuffers
```

### 2. `ProcessPendingTextures`

Before: lines 102-214, one loop whose body loads every pending texture as a
new one (shown in full in the file).

After: the loop body moves, word for word, into `LoadNewTexture`. The loop
chooses between that and `UpdateTexture`, and the pause guard is added.

```quorum
    action ProcessPendingTextures
        if pendingTextures:IsEmpty()
            return now
        end
        GameStateManager manager
        VulkanGraphics graphics = cast(VulkanGraphics, manager:GetGameGraphics())

        // While the window is minimized, the frame's command buffer is not
        // recording, so nothing can be recorded. Keep the waiting textures
        // for the next frame that really draws.
        if graphics:IsRenderingPaused()
            return now
        end

        VulkanCommandBuffer commandBuffer = graphics:GetCurrentRenderCommandBuffer()
        integer i = 0
        repeat while i < pendingTextures:GetSize()
            Texture texture = pendingTextures:Get(i)
            PixelMap pixelMap = pendingPixelMaps:Get(i)
            if CanUpdateInPlace(texture, pixelMap)
                UpdateTexture(texture, pixelMap, commandBuffer, graphics)
            else
                LoadNewTexture(texture, pixelMap, commandBuffer, graphics)
            end
            i = i + 1
        end

        pendingTextures:Empty()
        pendingPixelMaps:Empty()
    end
```

### 3. New private action `LoadNewTexture`

Today's loop body (lines 113-208), unchanged except:
- `device`, `constants` and `bits` are made at its top, as they were above
  the loop;
- `i = i + 1` stays in the loop.

```quorum
    /*
    This action loads a texture into a new image: a staging buffer, a copy,
    a view, the next global index, and its place in the descriptor set. This
    is how every load worked before textures could be updated in place.

    Attribute: Parameter texture The texture.
    Attribute: Parameter pixelMap Its pixels.
    Attribute: Parameter commandBuffer The frame's command buffer, recording.
    Attribute: Parameter graphics The Vulkan graphics.
    */
    private action LoadNewTexture(Texture texture, PixelMap pixelMap, VulkanCommandBuffer commandBuffer, VulkanGraphics graphics)
        VulkanDevice device = graphics:GetDevice()
        VulkanConstants constants
        BitwiseOperations bits

        integer width = pixelMap:GetWidth()
        ... (lines 117-206 of today's file, unchanged) ...
        globalTextureDescriptorSet:LinkResources(resourcesInfo)
    end
```

### 4. New private actions `CanUpdateInPlace` and `UpdateTexture`

```quorum
    /*
    This action returns true if a texture can take new pixels in its existing
    image: it was loaded before (it has an index and a view), and the new
    pixels are the same size.

    Attribute: Parameter texture The texture.
    Attribute: Parameter pixelMap The new pixels.
    Attribute: Returns True to update in place, false to load as a new texture.
    */
    private action CanUpdateInPlace(Texture texture, PixelMap pixelMap) returns boolean
        if texture:GetVulkanTextureIndex() < 0
            return false
        end
        VulkanImageView view = texture:GetVulkanImageView()
        if view = undefined
            return false
        end
        VulkanImage image = view:GetImage()
        return image:GetWidth() = pixelMap:GetWidth() and image:GetHeight() = pixelMap:GetHeight()
    end

    /*
    This action copies new pixels into a texture's existing image. The
    texture keeps its image, view, index and place in the descriptor set, so
    nothing that refers to it changes. Earlier frames may still be reading
    the image, so the copy waits for their fragment shaders first, and this
    frame's drawing waits for the copy.

    Attribute: Parameter texture The texture, already loaded at this size.
    Attribute: Parameter pixelMap The new pixels.
    Attribute: Parameter commandBuffer The frame's command buffer, recording.
    Attribute: Parameter graphics The Vulkan graphics.
    */
    private action UpdateTexture(Texture texture, PixelMap pixelMap, VulkanCommandBuffer commandBuffer, VulkanGraphics graphics)
        VulkanDevice device = graphics:GetDevice()
        VulkanConstants constants
        integer width = pixelMap:GetWidth()
        integer height = pixelMap:GetHeight()
        integer byteSize = width * height * 4

        // This frame slot's staging buffer for the texture. The slot's fence
        // was waited on at the start of the frame, so the GPU is done with it.
        integer slot = graphics:GetCurrentResourceIndex()
        VulkanSwapchain swapchain = graphics:GetSwapchain()
        integer slotCount = swapchain:GetImageCount()
        Array<VulkanBuffer> buffers = undefined
        if updateStagingBuffers:HasKey(texture)
            buffers = updateStagingBuffers:GetValue(texture)
        else
            Array<VulkanBuffer> newBuffers
            updateStagingBuffers:Add(texture, newBuffers)
            buffers = newBuffers
        end
        repeat while buffers:GetSize() < slotCount
            buffers:Add(undefined)
        end
        VulkanBuffer staging = buffers:Get(slot)
        if staging = undefined or staging:GetSize() not= byteSize
            VulkanBuffer newStaging
            newStaging:CreateTransferSourceBuffer(device, byteSize)
            newStaging:BeginMapping()
            buffers:Set(slot, newStaging)
            staging = newStaging
        end
        TransferPixelData(pixelMap, staging)

        VulkanImage image = texture:GetVulkanImageView():GetImage()

        // Earlier frames may still be reading the image in their fragment
        // shaders. Wait for them, and change the layout for the copy.
        VulkanImageMemoryBarrier toTransfer
        toTransfer:SetOldLayout(constants:IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL)
        toTransfer:SetNewLayout(constants:IMAGE_LAYOUT_TRANSFER_DESTINATION_OPTIMAL)
        toTransfer:SetSourceAccessMask(constants:ACCESS_SHADER_READ_BIT)
        toTransfer:SetDestinationAccessMask(constants:ACCESS_TRANSFER_WRITE_BIT)
        toTransfer:SetSourceStageMask(constants:PIPELINE_STAGE_FRAGMENT_SHADER_BIT)
        toTransfer:SetDestinationStageMask(constants:PIPELINE_STAGE_TRANSFER_BIT)
        toTransfer:SetAspectMask(constants:IMAGE_ASPECT_COLOR_BIT)
        toTransfer:SetImage(image)
        PipelineBarrierCommand toTransferCommand
        toTransferCommand:SetMemoryBarrier(toTransfer)
        commandBuffer:Record(toTransferCommand)

        CopyBufferToImageCommand copyCommand
        copyCommand:SetImageWidth(width)
        copyCommand:SetImageHeight(height)
        copyCommand:SetAspectMask(constants:IMAGE_ASPECT_COLOR_BIT)
        copyCommand:SetSourceBuffer(staging)
        copyCommand:SetDestinationImage(image)
        commandBuffer:Record(copyCommand)

        // Then back to the layout for reading, and this frame's drawing waits
        // for the copy, exactly as after a first load.
        VulkanImageMemoryBarrier toRead
        toRead:SetOldLayout(constants:IMAGE_LAYOUT_TRANSFER_DESTINATION_OPTIMAL)
        toRead:SetNewLayout(constants:IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL)
        toRead:SetSourceAccessMask(constants:ACCESS_TRANSFER_WRITE_BIT)
        toRead:SetDestinationAccessMask(constants:ACCESS_SHADER_READ_BIT)
        toRead:SetSourceStageMask(constants:PIPELINE_STAGE_TRANSFER_BIT)
        toRead:SetDestinationStageMask(constants:PIPELINE_STAGE_FRAGMENT_SHADER_BIT)
        toRead:SetAspectMask(constants:IMAGE_ASPECT_COLOR_BIT)
        toRead:SetImage(image)
        PipelineBarrierCommand toReadCommand
        toReadCommand:SetMemoryBarrier(toRead)
        commandBuffer:Record(toReadCommand)
    end
```

`VulkanSwapchain`, `VulkanImage`, `VulkanImageView` and
`VulkanImageMemoryBarrier` are in the same package, so no new `use` lines
are needed. `HashTable` and `Array` are already imported.

### Size

About 15 lines changed in `ProcessPendingTextures` and about 110 added,
most of them doc comments and the barrier setup.

## What changes for existing games

- **A texture loaded only once:** nothing changes.
- **Loading a different `Texture` object:** nothing changes. It gets a new
  image and index, as now.
- **Loading the same `Texture` object again at the same size:** today it
  gets a new image, view and index, and the old ones leak. After this
  change, it keeps its image, view and index, and the pixels are copied in.
  Anything drawing with it shows the new pixels from that frame on, as
  before. This is the only behavior change.
- **Loading the same `Texture` object again at a different size:** a new
  image and index, as now (and still leaking the old ones).
- **Textures loaded while minimized:** loaded on the next real frame,
  instead of being recorded into a command buffer that isn't recording.

## Risks and things to know

- **Only the fragment stage is waited for.** That is the only stage the
  texture binding allows (`SHADER_STAGE_FRAGMENT_BIT`). If vertex-stage
  texture reads are added later (#10), this barrier must include the vertex
  shader stage.
- **The same PixelMap loaded twice.** Java's `TransferPixelData` copies from
  the PixelMap's byte buffer with `put`, which may move that buffer's
  position. A PixelMap loaded a second time might copy nothing. This is
  already true for first loads. `WorldTerrain` makes a new PixelMap each
  time, so it's unaffected. To check if it matters elsewhere.
- **Staging memory:**
  - Per updated texture: frame slots × width × height × 4 bytes. For the
    513 by 513 splat texture, about 3 MB with 3 slots.
  - A buffer replaced because the size changed is left as is (the first-load
    staging buffers already leak), since freeing buffers needs #1.
- **Non-coherent staging memory:** as with first loads and Item 7, nothing
  flushes. The Mac is coherent.
- **Two loads of one texture in one frame:** the first makes the image (or
  updates it), the second updates it after, in order. Correct, just wasted
  work.
- **Mipmaps (#7):** there are none today. If mipmaps are added, an update
  must regenerate them.
- **#13 and #19 are unchanged.** A texture still can't be used from outside
  group 0 by the splat shader. This change just stops the splat texture from
  ever leaving group 0.

## Test plan

Validation layers on, if possible.

1. **Nothing broken:** `RunWorldTests`, `RunPhysicsTests`, DriveOpen
   (splatting, car, labels), and the editor's normal use.
2. **Painting in TerrainEditor:**
   - every paint stroke shows, with no grey;
   - the "Splat texture check" line appears once at startup (index 5) and
     not after each stroke, since no new texture is made;
   - 50 or more strokes in a row still show;
   - undo and redo of paint show too.
3. **Minimize and restore** while painting, then paint again.
4. **DriveOpen painting (P):** paint shows after each release of P, with no
   new splat textures counted.

## Rollback

Revert `VulkanTextureManager.quorum`. The project change below works with or
without the library change, so it can stay.

## Project-side change (with the library change, not library)

`WorldTerrain:MakeSplatTexture` today makes a new `Texture` object for every
splat rebuild. It would instead load into the same `Texture` object while the
splat area's size is unchanged, and make a new one only when the size
changes (new regions outside the area).

- With this library change, that updates in place and keeps index 5.
- Without it, the same `Texture` object just gets a new index each time,
  exactly as today, so this part is safe either way.

`GetSplatTextureCount` would count new splat textures only. A new
`GetSplatUpdateCount` counts updates. The editor's and DriveOpen's "about 25
strokes" warnings then fall away on their own.
