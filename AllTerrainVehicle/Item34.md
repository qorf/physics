# Item 34: freeing textures, materials and the skybox

**Status (2026-10-19): plan, for review.** Nothing is applied yet. It
needs Item 31, and Item 33 for the blueprint hook. It is section 4 of
`MemoryPlan.md`. It uses the recommended answer to decision 3: a texture
cache with reference counts. Font atlases (decision 4) wait for later; only
a crash in their disposal is fixed here.

Vulkan only, on `TerrainShader`. **OpenGL changes:** `Texture:Dispose`
becomes a Quorum action that calls the old Java code, so OpenGL behaves
exactly as before. Paths are as in `Item31.md` and `Item33.md`.
**GR/** is `Quorum/Library/Standard/Libraries/Game/Graphics/`, and **JG/**
is `Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/`.

## What leaks today

| What | Where |
|---|---|
| Every texture's image and view, for good. `Texture:Dispose` only frees an OpenGL handle, which is always 0 under Vulkan | `JG/Texture.java` |
| Every first-load staging buffer (the full mip chain), mapped, forever: `stagingBuffers` is only added to | `VulkanTextureManager:LoadNewTexture` |
| The six cube-side staging buffers, the same way | `VulkanTextureManager:LoadCubeTexture` |
| A per-slot update staging buffer replaced by a larger one | `VulkanTextureManager:UpdateTexture` |
| A texture loaded again at a new size: a new image, view and global place each time, with the old ones kept | `LoadNewTexture` |
| A cube loaded again: the old cube image and view | `LoadCubeTexture` |
| The CPU pixels of every texture loaded from a file (`PixelMap`s are never disposed under Vulkan, though `TextureData:DisposePixelMap` says to) | `Texture:LoadFromTextureData`, `ProcessPendingTextures` |
| The native pixels of every non-RGBA file (JPG): converted, then the native copy is lost | `JG/PixelMap.java` `LoadPixelMap` |
| The skybox's six side `PixelMap`s, kept after the cube is made | `GR/Skybox.quorum` |
| Each material's staging buffer, mapped, forever | `MaterialVulkan` |
| Each material's own textures (one to three files, or a texture set's two packed textures and their two packed `PixelMap`s) | `MaterialVulkan` |
| The same image file loaded again by every material that names it | `MaterialManagerVulkan` (no cache) |

**Bugs found here and fixed:**
- **`TransferPixelData` (Java)** copies with a relative `put`, which moves
  the pixel buffer's position to its end. A second upload of the same
  `PixelMap` copies nothing (an update with unchanged pixels, or a cube
  side reused).
- **The material copy has no barrier after it.** `ModelManagerVulkan`'s
  barrier is recorded before `materialManager:ProcessPendingResources()`
  runs, so material copies aren't covered. A material could be read on the
  frame it is loaded, before its copy lands.
- **`FreeTypeStrategy:EmptyGlyphTable`** calls `imageSheet:Dispose()` even
  when no sheet was made.

## The design

**`Texture:Dispose` under Vulkan** calls
`VulkanTextureManager:ReleaseTexture`:
- It drops the texture from the waiting lists, if it hasn't been made yet.
- It retires its image and view.
- It retires its global place. The place isn't reusable while earlier
  frames may still draw with it, so it goes through `Retire` too, as a
  small `VulkanTextureIndexRelease`. When that runs:
  - the descriptor slot is pointed at the unit texture, so anything still
    naming the place reads white, never a freed view;
  - the place goes on `recycledTextureIDs`, finishing that TO-DO.
  New textures take recycled places first.

**Loading a texture again at a new size:**
- It waits for the device, frees the old image and view on the spot, and
  **keeps its place**, linking the new view there.
  - Materials bake a texture's place in once, so they keep showing the
    right texture. Today they show the old image.
  - A device wait is needed because the slot is in use by frames in
    flight. Changing it under them breaks the rule of the descriptor set's
    "update unused while pending" flag.
  - Reloading at a new size is rare (editors and resizes). The same-size
    path (Item 20) is unchanged and doesn't wait.

**Staging buffers** are retired right after their copy is recorded.

**Pixels.**
- The texture manager disposes a `PixelMap` after writing it into the
  staging buffer, when the texture read it from a file itself
  (`FileTextureData` with a file, and `DisposePixelMap` true).
- Pixels passed to `LoadFromPixelMap` are kept. OpenGL disposes them too,
  but under Vulkan, Item 20's updates and WorldTerrain's splat map reuse
  the same `PixelMap`, so the caller keeps owning them.
- Cube sides are always disposed.

**Materials:**
- **File textures come from a cache** in `MaterialManagerVulkan`.
  - The key is the path. Normal maps add `:normal`, since their mipmaps
    are made differently.
  - Each use is counted.
- **Texture sets** are cached the same way, under one key made from all
  their paths and settings. So a set is packed once, however many models
  use it.
- **`MaterialVulkan:Release`** gives back its textures through the cache,
  and retires its buffers. When a texture's count reaches 0, it is
  disposed.
- **`ModelBlueprintVulkan:Release`** (Item 33) releases its materials.
- **A texture set's two packed `PixelMap`s** are disposed once both
  textures have been written (`MaterialVulkan:Load` runs after the texture
  manager in every frame).

**Behaviour change to note.** Under Vulkan, `Texture:Dispose` now really
frees, and so do the `Dispose` actions that call it:
- `Drawable:Dispose`;
- `TextureRegion:Dispose`;
- `ImageSheet` and font sheets;
- `SharedTextureManager`.

That is what they always did under OpenGL. Code that disposed a texture
and kept drawing it worked by accident under Vulkan before. Now it draws
white, until the place is reused.

## The code

### New file `GR/Vulkan/VulkanTextureIndexRelease.quorum`

```
package Libraries.Game.Graphics.Vulkan

/*
VulkanTextureIndexRelease gives a disposed texture's place in the global
texture array back to the texture manager, once no frame on the GPU can
still be drawing with it. The texture manager hands one to
VulkanGraphics:Retire when a texture is disposed (Item 34).
*/
class VulkanTextureIndexRelease is VulkanRetirable
    VulkanTextureManager manager = undefined
    integer index = -1

    /*
    This action sets which place to give back, and to which manager.

    Attribute: Parameter manager The texture manager.
    Attribute: Parameter index The place in the global texture array.
    */
    action Set(VulkanTextureManager manager, integer index)
        me:manager = manager
        me:index = index
    end

    /*
    This action gives the place back to the texture manager.
    */
    action Release
        manager:RecycleTextureIndex(index)
    end
end
```

### `GR/Texture.quorum`

The line `system action Dispose` and its comment become:

```
    /*
    This action will release the memory used to store pixel information for this
    Texture. This frees up resources, but will make the Texture no longer usable,
    including in classes that may have loaded the Texture, such as in Drawable.
    Use this when you are completely finished with a Texture and no longer intend
    to use it.
    */
    action Dispose
        // Under Vulkan, the texture manager frees the image once no frame
        // on the GPU still draws with it (Item 34).
        if manager:GetGameGraphics() is VulkanGraphics
            VulkanGraphics graphics = cast(VulkanGraphics, manager:GetGameGraphics())
            VulkanTextureManager textureManager = graphics:GetTextureManager()
            textureManager:ReleaseTexture(me)
        end
        DisposeNative()
    end

    private system action DisposeNative
```

**`LoadFromTextureData`.** The line
`textureManager:RequestLoad(me, data:ConsumePixelMap())` becomes:

```
            // Pixels this texture read from a file itself are disposed once
            // copied (Item 34). Pixels the caller passed in (LoadFromPixelMap)
            // are kept: under Vulkan, callers such as texture updates and
            // terrain splat maps reuse them, even though OpenGL disposes them.
            boolean disposeAfter = false
            if data is FileTextureData
                FileTextureData fileData = cast(FileTextureData, data)
                disposeAfter = fileData:GetFile() not= undefined and fileData:DisposePixelMap()
            end
            textureManager:RequestLoad(me, data:ConsumePixelMap(), disposeAfter)
```

### `JG/Texture.java`

`public void Dispose()` is renamed `public void DisposeNative()`; its body
is unchanged. `ImageSheet.java` calls `texture.Dispose()` on the Quorum
interface `Texture_`, which still has `Dispose`, so it needs no change.

### `GR/Vulkan/VulkanTextureManager.quorum`

**Fields:**
- **Removed:** `Array<VulkanBuffer> stagingBuffers` and its comment.
- **Added,** after `pendingPixelMaps`:

```
    // For each waiting texture, whether its PixelMap is disposed once
    // copied (Item 34).
    Array<boolean> pendingDisposeFlags
```

- **Replaced:** the `recycledTextureIDs` comment ("TO-DO: NYI, ...")
  becomes:

```
    // Places of disposed textures, given back once no frame can still draw
    // with them (Item 34). New textures take these first.
```

**`RequestLoad`.** It becomes two actions:

```
    action RequestLoad(Texture texture, PixelMap pixelMap)
        RequestLoad(texture, pixelMap, false)
    end

    /*
    This action asks for a texture to be loaded from a PixelMap during the
    next frame.

    Attribute: Parameter texture The texture.
    Attribute: Parameter pixelMap Its pixels.
    Attribute: Parameter disposeAfter True to dispose the PixelMap once it has been copied.
    */
    action RequestLoad(Texture texture, PixelMap pixelMap, boolean disposeAfter)
        pendingTextures:Add(texture)
        pendingPixelMaps:Add(pixelMap)
        pendingDisposeFlags:Add(disposeAfter)
    end
```

**`ProcessPendingTextures`.** The first loop and the lines after it become:

```
        integer i = 0
        repeat while i < pendingTextures:GetSize()
            Texture texture = pendingTextures:Get(i)
            PixelMap pixelMap = pendingPixelMaps:Get(i)
            if CanUpdateInPlace(texture, pixelMap)
                UpdateTexture(texture, pixelMap, commandBuffer, graphics)
            else
                LoadNewTexture(texture, pixelMap, commandBuffer, graphics)
            end
            // The pixels are in a staging buffer now (Item 34).
            if pendingDisposeFlags:Get(i)
                pixelMap:Dispose()
            end
            i = i + 1
        end

        pendingTextures:Empty()
        pendingPixelMaps:Empty()
        pendingDisposeFlags:Empty()
```

**`LoadNewTexture`.**

*At the start,* after `VulkanDevice device = graphics:GetDevice()`, add:

```
        // A texture loaded again at a new size keeps its place, so
        // materials that hold it still show it. Frames in flight may be
        // drawing from that place, so wait for them before freeing the old
        // image and linking the new one there (Item 34).
        integer keptIndex = texture:GetVulkanTextureIndex()
        VulkanImageView oldView = texture:GetVulkanImageView()
        if oldView not= undefined
            device:WaitUntilIdle()
            VulkanImage oldImage = oldView:GetImage()
            oldView:Dispose()
            oldImage:Dispose()
        end
```

*The staging buffer.* The lines

```
        // We need to hold onto the buffer to be disposed after the transfer is done.
        stagingBuffers:Add(buffer)
```

become:

```
        // The copy above is the buffer's only use (Item 34).
        graphics:Retire(buffer)
```

*Choosing the place.* The block

```
        // Also store the texture in our global array and associate our resources.
        if not recycledTextureIDs:IsEmpty()
            // TO-DO: Handle this case. ...
        else
            globalTextureArray:Add(texture)
            texture:SetVulkanTextureIndex(nextTextureID)
            nextTextureID = nextTextureID + 1
        end
```

becomes:

```
        // The texture's place in the global array: its own if it had one,
        // else a given-back one, else a new one (Item 34).
        if keptIndex >= 0
            globalTextureArray:Set(keptIndex, texture)
        elseif not recycledTextureIDs:IsEmpty()
            integer recycled = recycledTextureIDs:RemoveFromFront()
            globalTextureArray:Set(recycled, texture)
            texture:SetVulkanTextureIndex(recycled)
        else
            globalTextureArray:Add(texture)
            texture:SetVulkanTextureIndex(nextTextureID)
            nextTextureID = nextTextureID + 1
        end
```

The linking after it is unchanged. It writes the new view into the
texture's slot, which is either the kept place, idle after the wait, or a
place no frame uses.

**`UpdateTexture`.** In the block making a new staging buffer, the line
`VulkanBuffer newStaging` gains, before it:

```
            // A smaller buffer from before is freed once its last copy has
            // run (Item 34).
            graphics:Retire(staging)
```

(`Retire` ignores undefined.)

**`LoadCubeTexture`.**

*At the start,* after `BitwiseOperations bits`, add:

```
        // A cube made again replaces the old one, which earlier frames may
        // still draw (Item 34).
        VulkanImageView oldCube = texture:GetVulkanImageView()
        if oldCube not= undefined
            graphics:Retire(oldCube)
            graphics:Retire(oldCube:GetImage())
        end
```

*In the side loop,* `stagingBuffers:Add(buffer)` becomes:

```
            graphics:Retire(buffer)
```

*After the loop,* before the `toRead` barrier, add:

```
        // The sides' pixels are copied, and nothing else keeps them (Item 34).
        i = 0
        repeat while i < 6
            sides:Get(i):Dispose()
            i = i + 1
        end
```

**New actions,** before `TransferPixelData`:

```
    /*
    This action frees a texture: it is taken out of the waiting lists, and
    its image, view and place in the global array are freed once no frame
    on the GPU still draws with them. Texture:Dispose calls it.

    Attribute: Parameter texture The texture.
    */
    action ReleaseTexture(Texture texture)
        integer i = pendingTextures:GetSize() - 1
        repeat while i >= 0
            if pendingTextures:Get(i) = texture
                if pendingDisposeFlags:Get(i)
                    pendingPixelMaps:Get(i):Dispose()
                end
                pendingTextures:RemoveAt(i)
                pendingPixelMaps:RemoveAt(i)
                pendingDisposeFlags:RemoveAt(i)
            end
            i = i - 1
        end
        i = pendingCubeTextures:GetSize() - 1
        repeat while i >= 0
            if pendingCubeTextures:Get(i) = texture
                Array<PixelMap> sides = pendingCubeSides:Get(i)
                integer side = 0
                repeat while side < sides:GetSize()
                    sides:Get(side):Dispose()
                    side = side + 1
                end
                pendingCubeTextures:RemoveAt(i)
                pendingCubeSides:RemoveAt(i)
            end
            i = i - 1
        end

        GameStateManager manager
        VulkanGraphics graphics = cast(VulkanGraphics, manager:GetGameGraphics())
        VulkanImageView view = texture:GetVulkanImageView()
        if view not= undefined
            graphics:Retire(view)
            graphics:Retire(view:GetImage())
            texture:SetVulkanImageView(undefined)
        end
        if updateStagingBuffers:HasKey(texture)
            Array<VulkanBuffer> buffers = updateStagingBuffers:RemoveKey(texture)
            i = 0
            repeat while i < buffers:GetSize()
                graphics:Retire(buffers:Get(i))
                i = i + 1
            end
        end
        mipLevelTable:RemoveKey(texture)

        integer index = texture:GetVulkanTextureIndex()
        if index >= 0
            VulkanTextureIndexRelease release
            release:Set(me, index)
            graphics:Retire(release)
            texture:SetVulkanTextureIndex(-1)
        end
    end

    /*
    This action gives a disposed texture's place back, once no frame can
    draw with it: its slot shows the unit texture until the place is used
    again, and the next new texture takes it. VulkanTextureIndexRelease
    calls it.

    Attribute: Parameter index The place in the global texture array.
    */
    action RecycleTextureIndex(integer index)
        SharedTextureManager shared
        Texture unit = shared:GetUnitTexture()
        VulkanImageView unitView = unit:GetVulkanImageView()
        if unitView not= undefined
            VulkanConstants constants
            VulkanDescriptorSet set = globalTextureDescriptorSets:Get(index / descriptorSetEntries)
            VulkanDescriptorResourcesInfo resourcesInfo
            resourcesInfo:SetDescriptorType(constants:DESCRIPTOR_TYPE_SAMPLED_IMAGE)
            resourcesInfo:SetDestinationArrayElement(index mod descriptorSetEntries)
            resourcesInfo:AddImageInfo(undefined, unitView, constants:IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL)
            set:LinkResources(resourcesInfo)
        end
        globalTextureArray:Set(index, undefined)
        recycledTextureIDs:AddToEnd(index)
    end

    /*
    This action returns how many textures have a place in the global array.

    Attribute: Returns The number of textures.
    */
    action GetTextureCount returns integer
        return nextTextureID - recycledTextureIDs:GetSize()
    end
```

**Uses.** Add `use Libraries.Game.Graphics.SharedTextureManager`.

**`GR/Texture.quorum`, `SetVulkanTextureIndex`.** `ReleaseTexture` sets the
index to -1. Today that would give group `-1 / n` = 0 and local index -1. The
action gains a guard, so a texture with no place has no group either:

```
    action SetVulkanTextureIndex(integer vulkanTextureIndex)
        me:vulkanTextureIndex = vulkanTextureIndex
        if vulkanTextureIndex < 0
            vulkanTextureGroupIndex = -1
            vulkanTextureLocalIndex = -1
            return now
        end

        if manager:GetGameGraphics() is VulkanGraphics
            ...unchanged...
        end
    end
```

### `JG/Vulkan/VulkanTextureManager.java`

`TransferPixelData` becomes:

```java
    public void TransferPixelData(PixelMap_ quorumMap, VulkanBuffer_ quorumBuffer)
    {
        PixelMap pluginMap = ((quorum.Libraries.Game.Graphics.PixelMap)quorumMap).plugin_;
        VulkanBuffer pluginBuffer = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanBuffer)quorumBuffer).plugin_;

        // A duplicate from the start, so the PixelMap's own position never
        // moves and the same pixels can be copied again (Item 34).
        ByteBuffer pixelBytes = pluginMap.GetPixels().duplicate();
        pixelBytes.position(0);

        ByteBuffer target = MemoryUtil.memByteBuffer(pluginBuffer.GetMappedMemoryPointer(), quorumBuffer.GetSize());
        target.put(pixelBytes);
    }
```

(The old `MemoryStack` block wrapped nothing that needed a stack. The
`flip` on the target only changed a temporary view.)

### `JG/PixelMap.java`

In `LoadPixelMap`, the conversion branch becomes:

```java
        if ((int)nativeData[3] != FORMAT_RGBA8888 && useVulkan)
        {
            int width = (int) nativeData[1];
            int height = (int) nativeData[2];
            ByteBuffer convertedBuffer = ConvertToRGBA8888(pixelPointer, (int)nativeData[3], width, height, (byte) 255);
            // The converted pixels live in Java's memory. The native ones
            // aren't used again, so free them now (Item 34).
            Free(nativeData[0]);
            LoadFromByteBuffer(convertedBuffer, width, height, FORMAT_RGBA8888);
            return;
        }
```

`ConvertToRGBA8888` doesn't keep `pixelPointer`: it reads it with
absolute `get`s into a new Java buffer (checked), so freeing the native
pixels afterwards is safe.

### `GR/Skybox.quorum`

In `LoadCubeSide`, the Vulkan branch's
`textureManager:RequestCubeLoad(cubeMap, vulkanSides)` gains, after it:

```
                // The texture manager disposes the sides once the cube is
                // made, so they're let go here. Loading one side again
                // waits for all six again (Item 34).
                integer side = 0
                repeat while side < 6
                    vulkanSides:Set(side, undefined)
                    side = side + 1
                end
```

**`RecordSource` keeps the files.** A skybox reloaded side by side still
works once all six are loaded again. **Behaviour change:** before this,
reloading one side alone remade the cube with the five old sides. Now it
waits for the other five. No code in the library or the project does that.

**`Skybox:Dispose`** already calls `cubeMap:Dispose()`, which now frees the
cube under Vulkan.

### `GR/Models/Vulkan/MaterialManagerVulkan.quorum`

**Uses.** Add:

```
use Libraries.Game.Graphics.Texture
use Libraries.Game.Graphics.Vulkan.VulkanMemoryBarrier
use Libraries.Game.Graphics.Vulkan.Commands.PipelineBarrierCommand
```

**New fields,** after `pendingMaterials`:

```
    // Textures shared by materials, by key: a file's path (with ":normal"
    // for normal maps), or a texture set's key. Each counts its users, and
    // is disposed when none is left (Item 34).
    HashTable<text, Texture> sharedTextures
    HashTable<text, integer> sharedTextureUsers
    HashTable<Texture, text> sharedTextureKeys
```

**`ProcessPendingResources`.** It becomes:

```
    action ProcessPendingResources
        if pendingMaterials:IsEmpty() = false
            GameStateManager manager
            VulkanGraphics graphics = cast(VulkanGraphics, manager:GetGameGraphics())
            VulkanCommandBuffer commandBuffer = graphics:GetCurrentRenderCommandBuffer()

            boolean copied = false
            integer i = 0
            repeat while i < pendingMaterials:GetSize()
                MaterialVulkan material = pendingMaterials:Get(i)
                if material:IsPreloaded()
                    material:Load()
                end
                if material:HasData()
                    material:TransferBuffers(commandBuffer)
                    copied = true
                end
                i = i + 1
            end
            pendingMaterials:Empty()

            // Drawing waits for the material copies (Item 34).
            if copied
                VulkanConstants constants
                VulkanMemoryBarrier afterCopy
                afterCopy:SetSourceStageMask(constants:PIPELINE_STAGE_TRANSFER_BIT)
                afterCopy:SetSourceAccessMask(constants:ACCESS_TRANSFER_WRITE_BIT)
                afterCopy:SetDestinationStageMask(constants:PIPELINE_STAGE_VERTEX_SHADER_BIT + constants:PIPELINE_STAGE_FRAGMENT_SHADER_BIT)
                afterCopy:SetDestinationAccessMask(constants:ACCESS_SHADER_READ_BIT)
                PipelineBarrierCommand afterCommand
                afterCommand:SetMemoryBarrier(afterCopy)
                commandBuffer:Record(afterCommand)
            end
        end
    end
```

**`ProcessPendingResources` while minimized.** Today it records into a
command buffer that isn't recording. The model manager returns early when
paused before reaching it, so this is safe.

**New actions,** after `GetMaterial`:

```
    /*
    This action returns a shared texture, counting one more user of it, or
    undefined if none has been added under the key.

    Attribute: Parameter key The texture's key.
    Attribute: Returns The texture, or undefined.
    */
    action UseSharedTexture(text key) returns Texture
        if not sharedTextures:HasKey(key)
            return undefined
        end
        sharedTextureUsers:Add(key, sharedTextureUsers:GetValue(key) + 1)
        return sharedTextures:GetValue(key)
    end

    /*
    This action adds a texture to share under a key, with one user.

    Attribute: Parameter key The texture's key.
    Attribute: Parameter texture The texture.
    */
    action AddSharedTexture(text key, Texture texture)
        sharedTextures:Add(key, texture)
        sharedTextureUsers:Add(key, 1)
        sharedTextureKeys:Add(texture, key)
    end

    /*
    This action counts one fewer user of a shared texture, and disposes it
    when none is left. A texture that isn't shared is disposed straight
    away.

    Attribute: Parameter texture The texture.
    */
    action ReleaseSharedTexture(Texture texture)
        if not sharedTextureKeys:HasKey(texture)
            texture:Dispose()
            return now
        end
        text key = sharedTextureKeys:GetValue(texture)
        integer users = sharedTextureUsers:GetValue(key) - 1
        if users > 0
            sharedTextureUsers:Add(key, users)
            return now
        end
        sharedTextures:RemoveKey(key)
        sharedTextureUsers:RemoveKey(key)
        sharedTextureKeys:RemoveKey(texture)
        texture:Dispose()
    end

    /*
    This action takes a material out of the waiting list, if it is there.

    Attribute: Parameter material The material.
    */
    action RemovePendingMaterial(MaterialVulkan material)
        pendingMaterials:Remove(material)
    end

    /*
    This action returns how many textures materials share.

    Attribute: Returns The number of textures.
    */
    action GetSharedTextureCount returns integer
        return sharedTextures:GetSize()
    end
```

(`HashTable:Add` with an existing key replaces the value: it calls the same
`Set` as `HashTable:Set`.)

### `GR/Models/Vulkan/MaterialVulkan.quorum`

**New fields,** after `textureGroupIndex`:

```
    // The textures this material uses that it got from the material
    // manager (files and texture sets, not the unit texture), given back
    // in Release (Item 34).
    Array<Texture> usedTextures

    // A texture set's packed pixels, disposed once both textures are
    // copied (Item 34).
    PixelMap packedAlbedoHeight = undefined
    PixelMap packedNormalRoughness = undefined

    boolean released = false
```

**`Preload`.** The three file loads go through the cache:

```
        else
            // Mipmaps keep distant models from shimmering (Item 25).
            preloadTexture = UseFileTexture(texturePath, false)
        end
```

```
        else
            // A normal map's mipmaps average directions, so far normals
            // stay real normals.
            preloadNormalMap = UseFileTexture(normalPath, true)
        end
```

```
        else
            preloadRoughMap = UseFileTexture(roughPath, false)
        end
```

New private action:

```
    /*
    This action returns the texture for an image file, shared with every
    material using the same file, loading it the first time (Item 34).

    Attribute: Parameter path The file's path.
    Attribute: Parameter packedNormals True for a normal map.
    Attribute: Returns The texture.
    */
    private action UseFileTexture(text path, boolean packedNormals) returns Texture
        ModelManagerVulkan models
        MaterialManagerVulkan materials = models:GetMaterialManager()
        text key = path
        if packedNormals
            key = path + ":normal"
        end
        Texture texture = materials:UseSharedTexture(key)
        if texture = undefined
            Texture loaded
            loaded:SetPackedNormalMipMaps(packedNormals)
            loaded:LoadFromFile(path, true)
            materials:AddSharedTexture(key, loaded)
            texture = loaded
        end
        usedTextures:Add(texture)
        return texture
    end
```

**`PreloadTextureSet`.**

*At the start,* after `textureScale = data:GetTextureScale()`, add:

```
        // A set already packed for another material is shared (Item 34).
        ModelManagerVulkan models
        MaterialManagerVulkan materials = models:GetMaterialManager()
        text setKey = "set:" + data:GetColorMapPath() + "|" + data:GetHeightMapPath() + "|" +
            data:GetNormalMapPath() + "|" + data:IsNormalMapDirectX() + "|" +
            data:GetAmbientOcclusionMapPath() + "|" + data:GetRoughnessMapPath() + "|" + data:GetRoughness()
        Texture sharedAlbedo = materials:UseSharedTexture(setKey + ":albedo")
        if sharedAlbedo not= undefined
            albedoHeightTexture = sharedAlbedo
            normalRoughnessTexture = materials:UseSharedTexture(setKey + ":normal")
            usedTextures:Add(albedoHeightTexture)
            usedTextures:Add(normalRoughnessTexture)
            preloadTexture = albedoHeightTexture
            preloadNormalMap = normalRoughnessTexture
            return now
        end
```

*At its end,* after `preloadNormalMap = normals`, add:

```
        materials:AddSharedTexture(setKey + ":albedo", albedo)
        materials:AddSharedTexture(setKey + ":normal", normals)
        usedTextures:Add(albedo)
        usedTextures:Add(normals)
        packedAlbedoHeight = albedoHeight
        packedNormalRoughness = normalRoughness
```

**`Load`.** At its end, after `stagingBuffer:StopMapping()`, add:

```
        // A texture set's packed pixels have been copied by now: the
        // texture manager runs before the material manager every frame
        // (Item 34).
        if packedAlbedoHeight not= undefined and albedoHeightTexture:GetVulkanTextureIndex() >= 0
            packedAlbedoHeight:Dispose()
            packedAlbedoHeight = undefined
        end
        if packedNormalRoughness not= undefined and normalRoughnessTexture:GetVulkanTextureIndex() >= 0
            packedNormalRoughness:Dispose()
            packedNormalRoughness = undefined
        end
```

**`TransferBuffers`.** After `dataTransferred = true`, add:

```
        // The copy is the staging buffer's only use (Item 34).
        GameStateManager gameState
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        graphics:Retire(stagingBuffer)
        stagingBuffer = undefined
```

**`HasData`.** It is unchanged. It is still true through `materialBuffer`,
and `IsReady` uses `materialBuffer`.

**New action:**

```
    /*
    This action frees the material: its GPU buffers once no frame on the
    GPU still uses them, and its textures through the material manager,
    which disposes each when no other material uses it. Its blueprint calls
    it when no model uses the blueprint any more. Doing it twice does
    nothing.
    */
    action Release
        if released
            return now
        end
        released = true
        ModelManagerVulkan models
        MaterialManagerVulkan materials = models:GetMaterialManager()
        materials:RemovePendingMaterial(me)

        GameStateManager gameState
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        graphics:Retire(stagingBuffer)
        graphics:Retire(materialBuffer)
        stagingBuffer = undefined
        materialBuffer = undefined

        integer i = 0
        repeat while i < usedTextures:GetSize()
            materials:ReleaseSharedTexture(usedTextures:Get(i))
            i = i + 1
        end
        usedTextures:Empty()

        if packedAlbedoHeight not= undefined
            packedAlbedoHeight:Dispose()
            packedAlbedoHeight = undefined
        end
        if packedNormalRoughness not= undefined
            packedNormalRoughness:Dispose()
            packedNormalRoughness = undefined
        end
        albedoHeightTexture = undefined
        normalRoughnessTexture = undefined
    end
```

**The packed `PixelMap`s.** They go through `LoadFromPixelMap`, whose
data has no file, so the texture manager keeps them, and the material
disposes them itself.

### `GR/Models/Vulkan/ModelBlueprintVulkan.quorum`

In `Release` (Item 33), before `data = undefined`, add:

```
        if materials not= undefined
            i = 0
            repeat while i < materials:GetSize()
                materials:Get(i):Release()
                i = i + 1
            end
        end
```

Each blueprint makes its own `MaterialVulkan`s (`GetMaterial` makes a new
one every time), so nothing else holds them.

### `GR/Fonts/FreeTypeStrategy.quorum`

In `EmptyGlyphTable`:

```
        // Reset the FontImageSheet as well.
        if imageSheet not= undefined
            imageSheet:Dispose()
        end
        imageSheet = undefined
```

### `GR/Vulkan/VulkanGraphics.quorum` (the report)

`GetMemoryReport`'s `return` gains textures:

```
        return "GPU memory: " + megabytes + " MB in " + allocator:GetAllocationCount() +
            " allocations; waiting to be freed: " + retired:GetSize() +
            "; model blueprints: " + modelManager:GetCachedBlueprintCount() +
            "; textures: " + textureManager:GetTextureCount()
```

## Test plan

1. **MemoryCheck, new loop T.** It loads and disposes 50 textured
   drawables, and one texture loaded again at alternating sizes, once a
   second.
   - The texture count and GPU memory go up and down within a range.
   - The Java heap stays flat.
   - The resized texture shows its new image every time.
2. **TextureUpdateCheck (Item 20)** behaves as before, with same-size
   updates.
3. **MipMapCheck, TextureSetCheck.** Same look as before, including T/B
   lighting.
4. **SkyboxCheck and DriveOpen K.** The sky shows. Disposing the skybox and
   loading another one keeps memory flat.
5. **The model loop from Item 33 (L) with a textured model file.**
   - Textures are shared: one texture per file, not 100.
   - Memory returns after each cycle.
6. **Text and the interface.** Labels with changing fonts and sizes still
   draw. Nothing goes white. The font atlases still grow, as decision 4
   leaves them.

## Rollback

Revert the Item 34 changes in the library and plugin files. Items 31 to 33
stay.
