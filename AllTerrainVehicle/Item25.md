# Item 25: mipmaps and anisotropic filtering

`VulkanChanges.md` #7 (no mipmaps) and #8 (anisotropic filtering off),
`LibraryChangesPlan.md` orders 8 and 10, done together as one item.
**Approved and applied on 2026-10-19** to the `quorum-language` branch
`TerrainShader`, with the recommended answers to all four decisions:
the old way's Material textures get mipmaps; the public
`LoadFromFile(text, boolean)` is added; anisotropy is capped at 16; levels
are made in Java. The project-side changes are made, and
`SourceCode/MipMapCheck.quorum` is written. **Waiting for a rebuild of the
library and plugins, and a run.**

Paths are under
`quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/` for
Quorum, and
`quorum-language/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/Vulkan/`
for Java. The branch is `TerrainShader`.

## Why

The ground shimmers and crawls as the camera moves, worst in the distance
and at low angles. Texture sets (Item 24) made it worse, since a 1K pebble
texture tiled every 2.5 units has a lot of fine detail to alias.

Three causes, all in how textures are sampled under Vulkan:

1. **Every image has one level.** `VulkanTextureManager:LoadNewTexture`
   makes images with `mipLevels = 1`. Far ground samples a 1024 by 1024
   texture where a pixel covers dozens of texels, so each frame picks
   different texels: shimmer.
2. **The sampler can't blend levels.** The one shared sampler
   (`VulkanTextureManager:Create`) uses `SAMPLER_MIPMAP_MODE_NEAREST`. With
   mipmaps, that would show bands where the level changes.
3. **Anisotropic filtering is off.** `VulkanSamplerInfo` defaults to
   `anisotropyEnable = false`. Ground seen at a low angle needs a different
   level along and across the view. Without anisotropy the sampler picks
   the blurrier one, so mipmaps alone make the middle distance blurry.

## What's there today (the parts that matter)

- **Already supported, no change needed:**
  - `VulkanImageInfo:SetMipLevels`, honored by `VulkanImage.java`;
  - `VulkanImageViewInfo:SetLevelCount`, honored by `VulkanImageView.java`;
  - `VulkanImageMemoryBarrier:SetLevelCount`, honored by
    `PipelineBarrierCommand.java`;
  - `CopyBufferToImageCommand:SetBufferOffset` and `SetMipLevel`, honored
    by its Java;
  - `VulkanSamplerInfo:SetMipMapMode`, `SetAnisotropyEnable`,
    `SetMaxAnisotropy`, all passed through by `VulkanSampler.java`. `maxLod`
    already defaults to `LOD_CLAMP_NONE`;
  - `VulkanDevice.java` already turns on the `samplerAnisotropy` device
    feature when the GPU has it. `VulkanPhysicalDeviceLimits` has
    `GetMaxSamplerAnisotropy`.
- **Texture already asks for mipmaps:** `LoadFromPixelMap(map, format,
  useMipMaps)` and the private `LoadFromFile(file, format, useMipMaps)`
  store the choice in the texture's `TextureData` (`UseMipMaps()`).
  OpenGL honors it; the Vulkan path ignores it.
- **One sampler for everything.** The immutable sampler is shared by the 2D
  and 3D pipelines (`VulkanPipelineInfoCreator`, `VulkanPainter2D`,
  `VulkanPainter3D`). It must be set before the first pipeline is made,
  which `Create` already does.

So the change is mostly in `VulkanTextureManager`, plus one Java helper to
make the smaller levels.

## The design

### Which textures get mipmaps

**Only those that ask,** through the existing `useMipMaps` flag:
- Labels, fonts, 2D drawables, the splat texture and the layer table keep
  one level. They are drawn at their own size or read texel by texel, so
  mipmaps would only cost memory and load time.
- `MaterialVulkan` asks for mipmaps for texture sets (decision 1 covers the
  old way too).
- Games can ask with `LoadFromPixelMap(map, format, true)`, or with a new
  public `LoadFromFile(text filePath, boolean useMipMaps)` (decision 2).

### Making the levels: on the CPU, in Java

Each level is half the size of the one before, down to 1 by 1. A level's
pixel is the average of the 2 by 2 pixels above it (a box filter). The
levels are made when the texture's pixels are written into the staging
buffer, all into one buffer one after another. Then one
`CopyBufferToImageCommand` per level copies each level into its place.

- **Why not the GPU** (`vkCmdBlitImage`)? Blitting would need a new
  command class (Quorum and Java). More importantly, it can only average
  plainly, which is wrong for packed normals (next section).
- **Cost:** a 1024 by 1024 texture has 11 levels and about 1.4 million
  pixels in all, a few milliseconds in Java. Memory grows by a third.
- **Updates in place** (Item 20) regenerate every level of a mipmapped
  texture. Nothing updated often uses mipmaps today; the splat texture
  doesn't.

### Packed normals average differently

A texture set's normal-roughness texture keeps ambient occlusion in the
normal's length (Item 24, Terrain3D's packing). A plain average of bumpy
normals is shorter than any of them, so far ground would read as heavily
occluded and turn darker with distance. A plain average of normals also
isn't a normal.

So a texture can be marked as holding packed normals
(`SetPackedNormalMipMaps(true)`). For those, each smaller level:
- averages the four normals' **directions** (each made length 1 first),
  then makes the result length 1;
- averages their **lengths**, so ambient occlusion is averaged, and sets
  the new normal to that length;
- averages roughness (alpha) plainly.

`MaterialVulkan` marks the normal-roughness texture of a texture set this
way. The old way's plain normal map is marked too (decision 1), so its far
normals are real normals.

### The sampler

- Mip mode **linear**: blends between the two nearest levels, so there are
  no bands. Textures with one level are unaffected, since there is nothing
  to blend.
- **Anisotropy** on when the device has it, at the device's maximum capped
  at 16. It costs a few more texture reads at low angles, on modern GPUs
  usually under a millisecond. 2D drawing is unaffected, since it isn't
  seen at an angle.

### The splat shader (project side)

Mipmaps bring one shader rule into play. The GPU picks a level from how
fast texture coordinates change between neighboring pixels. That only works
when all four pixels of a 2 by 2 group run the same `texture` call. The
splat shader's texture set path skips layers with almost no weight
(`continue`), which differs from pixel to pixel at layer edges, so those
reads could pick wild levels: sparkles along the edges between layers.

Terrain3D has the same problem and the same fix: work out how the world
position changes across the screen **once**, before any branch, and read
every layer with `textureGrad`, giving those rates scaled by the layer's
tile size. See its `main.glsl`, `base_ddx` and `id_dd`.

## Compared with Terrain3D

| Topic | Terrain3D | This item | Verdict |
|---|---|---|---|
| Mipmaps on terrain textures | required (its docs and the asset checks warn without them); Godot makes them on import | made on load, in Java | Same |
| Normal mipmaps | Godot's generic mipmaps; AO read from normal length anyway (`main.glsl`: `length(nrm.xyz) * 2.0 - 1.0`), so far ground darkens slightly | directions and lengths averaged apart, so AO holds | Better |
| Sampler | `filter_linear_mipmap_anisotropic` by default (`samplers.glsl`) | linear mip mode, anisotropy up to 16 | Same |
| Reads in branches | `textureGrad` with derivatives from the vertex, taken once | the same, in the splat shader | Same |
| Distant detail | dual scaling (a second, larger tiling far away) and macro variation | not in this item | Later, shader only |
| Compression (BC) | VRAM-compressed with mipmaps | uncompressed RGBA8 with mipmaps | Gap, as before (#9) |

## The code change

### 1. `Texture.quorum`

**New field,** after `TextureData data = undefined` (line 59):

```
    // Whether this texture holds packed normals: normals in red, green and
    // blue, with ambient occlusion in their length, as a texture set's
    // normal-roughness texture does (Item 24). Its mipmaps then average
    // the normals' directions and lengths separately (Item 25).
    boolean packedNormalMipMaps = false
```

**New actions,** after `LoadFromFile(text filePath)` (line 129):

```
    /*
    This action loads a Texture from a file path, and makes mipmaps for it
    if asked: smaller copies the renderer uses when the texture is far away
    or seen at an angle, so it doesn't shimmer. Mipmaps suit textures on 3D
    models and ground. They cost a third more memory, and are not needed
    for 2D images drawn at their own size.

    Attribute: Parameter filePath The image file's path.
    Attribute: Parameter useMipMaps True to make mipmaps.

    Attribute: Example
    use Libraries.Game.Graphics.Texture
    Texture ground
    ground:LoadFromFile("Textures/grass.png", true)
    */
    action LoadFromFile(text filePath, boolean useMipMaps)
        File file
        file:SetPath(filePath)
        LoadFromFile(file, undefined, useMipMaps)
    end

    /*
    This action returns true if the texture was loaded asking for mipmaps.

    Attribute: Returns True if the texture uses mipmaps.
    */
    action UsesMipMaps returns boolean
        if data = undefined
            return false
        end
        return data:UseMipMaps()
    end

    /*
    This action says whether the texture holds packed normals, as a texture
    set's normal-roughness texture does. If it does, its mipmaps keep each
    normal a real direction, and keep the ambient occlusion carried in the
    normals' length. Set it before loading. Only the Vulkan renderer uses
    it.

    Attribute: Parameter packed True for packed normals.
    */
    action SetPackedNormalMipMaps(boolean packed)
        packedNormalMipMaps = packed
    end

    /*
    This action returns true if the texture holds packed normals (see
    SetPackedNormalMipMaps).

    Attribute: Returns True for packed normals.
    */
    action HasPackedNormalMipMaps returns boolean
        return packedNormalMipMaps
    end
```

### 2. `Vulkan/VulkanTextureManager.quorum`

**New field,** after `HashTable<Texture, Array<VulkanBuffer>> updateStagingBuffers`:

```
    // How many mip levels each loaded texture's image has (Item 25). An
    // update in place needs the same count.
    HashTable<Texture, integer> mipLevelTable
```

**`Create`:** the sampler lines become:

```
        VulkanSampler immutableSampler
        VulkanSamplerInfo defaultInfo
        // Blend between the two nearest mip levels (Item 25). A texture
        // with one level is read as before.
        defaultInfo:SetMipMapMode(constants:SAMPLER_MIPMAP_MODE_LINEAR)
        // Anisotropic filtering keeps textures seen at a low angle, like
        // ground, sharp. VulkanDevice turns the feature on when the device
        // has it.
        VulkanPhysicalDevice physicalDevice = graphics:GetPhysicalDevice()
        VulkanPhysicalDeviceFeatures features = physicalDevice:GetFeatures()
        if features:HasSamplerAnisotropy()
            VulkanPhysicalDeviceLimits limits = physicalDevice:GetLimits()
            number anisotropy = limits:GetMaxSamplerAnisotropy()
            if anisotropy > 16
                anisotropy = 16
            end
            defaultInfo:SetAnisotropyEnable(true)
            defaultInfo:SetMaxAnisotropy(anisotropy)
        end
        immutableSampler:Create(device, defaultInfo)
        defaultSampler = immutableSampler
```

**`LoadNewTexture`:** five changes, everything else unchanged.

```
        integer pixelSize = 4
        integer levels = GetMipLevelCount(texture, width, height)

        VulkanBuffer buffer
        buffer:CreateTransferSourceBuffer(device, GetMipChainByteSize(width, height, levels))
        buffer:BeginMapping()
        WritePixels(texture, pixelMap, buffer, levels)
```

```
        imageInfo:SetFormat(constants:FORMAT_R8G8B8A8_UNORM)
        imageInfo:SetMipLevels(levels)
        image:Create(device, imageInfo)
```

`memoryBarrier` and `readTransition` each get
`...:SetLevelCount(levels)`. The single `CopyBufferToImageCommand` block
becomes:

```
        // Now copy each level from the buffer into the image.
        RecordLevelCopies(commandBuffer, buffer, image, width, height, levels)
```

```
viewInfo:SetFormat(constants:FORMAT_R8G8B8A8_UNORM)
        viewInfo:SetLevelCount(levels)
        view:Create(device, image, viewInfo)
        mipLevelTable:Add(texture, levels)
```

**`CanUpdateInPlace`:** the last line becomes:

```
        if image:GetWidth() not= pixelMap:GetWidth() or image:GetHeight() not= pixelMap:GetHeight()
            return false
        end
        // A texture that now asks for mipmaps (or no longer does) needs a
        // new image with the right number of levels.
        if not mipLevelTable:HasKey(texture)
            return false
        end
        return mipLevelTable:GetValue(texture) = GetMipLevelCount(texture, image:GetWidth(), image:GetHeight())
```

**`UpdateTexture`:**

```
        integer levels = GetMipLevelCount(texture, width, height)
        integer byteSize = GetMipChainByteSize(width, height, levels)
```

replaces `integer byteSize = width * height * 4`;
`TransferPixelData(pixelMap, staging)` becomes
`WritePixels(texture, pixelMap, staging, levels)`; `toTransfer` and `toRead`
each get `...:SetLevelCount(levels)`; and the copy block becomes
`RecordLevelCopies(commandBuffer, staging, image, width, height, levels)`.

**New private actions,** before `TransferPixelData`:

```
    /*
    This action returns how many mip levels a texture's image gets: 1 if it
    didn't ask for mipmaps, or else one for each halving of its larger side
    down to 1, plus the full size.

    Attribute: Parameter texture The texture.
    Attribute: Parameter width The full size's width.
    Attribute: Parameter height The full size's height.
    Attribute: Returns The number of levels.
    */
    private action GetMipLevelCount(Texture texture, integer width, integer height) returns integer
        if not texture:UsesMipMaps()
            return 1
        end
        integer size = width
        if height > size
            size = height
        end
        integer levels = 1
        repeat while size > 1
            size = size / 2
            levels = levels + 1
        end
        return levels
    end

    /*
    This action returns one side of a mip level: the full side halved once
    per level, but never under 1.

    Attribute: Parameter size The full size's side.
    Attribute: Parameter level The level, 0 for the full size.
    Attribute: Returns The level's side.
    */
    private action GetLevelSize(integer size, integer level) returns integer
        integer result = size
        integer i = 0
        repeat while i < level and result > 1
            result = result / 2
            i = i + 1
        end
        return result
    end

    /*
    This action returns how many bytes every level together takes, at 4
    bytes a pixel, which is the staging buffer's size.

    Attribute: Parameter width The full size's width.
    Attribute: Parameter height The full size's height.
    Attribute: Parameter levels How many levels.
    Attribute: Returns The size in bytes.
    */
    private action GetMipChainByteSize(integer width, integer height, integer levels) returns integer
        integer total = 0
        integer level = 0
        repeat while level < levels
            total = total + GetLevelSize(width, level) * GetLevelSize(height, level) * 4
            level = level + 1
        end
        return total
    end

    /*
    This action writes a texture's pixels into a staging buffer: the full
    size, then, if it has more levels, each smaller level after it.

    Attribute: Parameter texture The texture.
    Attribute: Parameter pixelMap Its pixels.
    Attribute: Parameter buffer The staging buffer, mapped, of GetMipChainByteSize bytes.
    Attribute: Parameter levels How many levels.
    */
    private action WritePixels(Texture texture, PixelMap pixelMap, VulkanBuffer buffer, integer levels)
        if levels = 1
            TransferPixelData(pixelMap, buffer)
        else
            TransferPixelDataWithMipMaps(pixelMap, buffer, levels, texture:HasPackedNormalMipMaps())
        end
    end

    /*
    This action records one copy per mip level, from where WritePixels put
    each level in the buffer into that level of the image. The image must
    be in the layout for receiving copies.

    Attribute: Parameter commandBuffer The frame's command buffer, recording.
    Attribute: Parameter buffer The staging buffer.
    Attribute: Parameter image The image.
    Attribute: Parameter width The full size's width.
    Attribute: Parameter height The full size's height.
    Attribute: Parameter levels How many levels.
    */
    private action RecordLevelCopies(VulkanCommandBuffer commandBuffer, VulkanBuffer buffer, VulkanImage image,
            integer width, integer height, integer levels)
        VulkanConstants constants
        integer offset = 0
        integer level = 0
        repeat while level < levels
            integer levelWidth = GetLevelSize(width, level)
            integer levelHeight = GetLevelSize(height, level)
            CopyBufferToImageCommand copyCommand
            copyCommand:SetImageWidth(levelWidth)
            copyCommand:SetImageHeight(levelHeight)
            copyCommand:SetAspectMask(constants:IMAGE_ASPECT_COLOR_BIT)
            copyCommand:SetBufferOffset(offset)
            copyCommand:SetMipLevel(level)
            copyCommand:SetSourceBuffer(buffer)
            copyCommand:SetDestinationImage(image)
            commandBuffer:Record(copyCommand)
            offset = offset + levelWidth * levelHeight * 4
            level = level + 1
        end
    end
```

**New system action,** after `TransferPixelData`:

```
    /*
    This action writes a texture's pixels into a staging buffer followed by
    each smaller mip level, made by averaging 2 by 2 pixels. For packed
    normals, directions and lengths are averaged separately.
    */
    private system action TransferPixelDataWithMipMaps(PixelMap pixelMap, VulkanBuffer buffer, integer levels, boolean packedNormals)
```

`use` lines to add: `VulkanPhysicalDevice`, `VulkanPhysicalDeviceFeatures`
and `VulkanPhysicalDeviceLimits` are in the same package, so none are
needed.

### 3. `VulkanTextureManager.java`

**New method,** after `TransferPixelData`:

```java
    public void TransferPixelDataWithMipMaps(PixelMap_ quorumMap, VulkanBuffer_ quorumBuffer, int levels, boolean packedNormals)
    {
        PixelMap pluginMap = ((quorum.Libraries.Game.Graphics.PixelMap)quorumMap).plugin_;
        VulkanBuffer pluginBuffer = ((quorum.Libraries.Game.Graphics.Vulkan.VulkanBuffer)quorumBuffer).plugin_;
        ByteBuffer pixelBytes = pluginMap.GetPixels();
        ByteBuffer target = MemoryUtil.memByteBuffer(pluginBuffer.GetMappedMemoryPointer(), quorumBuffer.GetSize());

        int width = quorumMap.GetWidth();
        int height = quorumMap.GetHeight();

        // The full size, read by index so the pixel buffer's position
        // doesn't matter.
        byte[] level = new byte[width * height * 4];
        for (int i = 0; i < level.length; i++)
            level[i] = pixelBytes.get(i);

        int offset = 0;
        for (int index = 0; index < levels; index++)
        {
            target.position(offset);
            target.put(level);
            offset += level.length;

            if (index + 1 < levels)
            {
                int smallerWidth = Math.max(1, width / 2);
                int smallerHeight = Math.max(1, height / 2);
                level = MakeSmallerLevel(level, width, height, smallerWidth, smallerHeight, packedNormals);
                width = smallerWidth;
                height = smallerHeight;
            }
        }
        target.position(0);
    }

    // Averages each 2 by 2 block of pixels into one. At an odd edge, the
    // last row or column is used twice.
    private static byte[] MakeSmallerLevel(byte[] source, int width, int height, int smallerWidth, int smallerHeight, boolean packedNormals)
    {
        byte[] result = new byte[smallerWidth * smallerHeight * 4];
        int[] corners = new int[4];
        for (int y = 0; y < smallerHeight; y++)
        {
            int y0 = Math.min(y * 2, height - 1);
            int y1 = Math.min(y * 2 + 1, height - 1);
            for (int x = 0; x < smallerWidth; x++)
            {
                int x0 = Math.min(x * 2, width - 1);
                int x1 = Math.min(x * 2 + 1, width - 1);
                corners[0] = (y0 * width + x0) * 4;
                corners[1] = (y0 * width + x1) * 4;
                corners[2] = (y1 * width + x0) * 4;
                corners[3] = (y1 * width + x1) * 4;
                int out = (y * smallerWidth + x) * 4;

                if (!packedNormals)
                {
                    for (int channel = 0; channel < 4; channel++)
                    {
                        int sum = 0;
                        for (int corner : corners)
                            sum += source[corner + channel] & 0xFF;
                        result[out + channel] = (byte)((sum + 2) / 4);
                    }
                    continue;
                }

                // Packed normals: average the directions and the lengths
                // (ambient occlusion) apart, and roughness plainly.
                double directionX = 0, directionY = 0, directionZ = 0, lengthSum = 0;
                int alphaSum = 0;
                for (int corner : corners)
                {
                    double normalX = (source[corner] & 0xFF) / 127.5 - 1.0;
                    double normalY = (source[corner + 1] & 0xFF) / 127.5 - 1.0;
                    double normalZ = (source[corner + 2] & 0xFF) / 127.5 - 1.0;
                    double length = Math.sqrt(normalX * normalX + normalY * normalY + normalZ * normalZ);
                    lengthSum += length;
                    if (length > 0.000001)
                    {
                        directionX += normalX / length;
                        directionY += normalY / length;
                        directionZ += normalZ / length;
                    }
                    alphaSum += source[corner + 3] & 0xFF;
                }
                double directionLength = Math.sqrt(directionX * directionX + directionY * directionY + directionZ * directionZ);
                if (directionLength < 0.000001)
                {
                    directionX = 0;
                    directionY = 0;
                    directionZ = 1;
                    directionLength = 1;
                }
                double scale = (lengthSum / 4.0) / directionLength;
                result[out] = ToByte((directionX * scale + 1.0) * 127.5);
                result[out + 1] = ToByte((directionY * scale + 1.0) * 127.5);
                result[out + 2] = ToByte((directionZ * scale + 1.0) * 127.5);
                result[out + 3] = (byte)((alphaSum + 2) / 4);
            }
        }
        return result;
    }

    private static byte ToByte(double value)
    {
        long rounded = Math.round(value);
        if (rounded < 0)
            rounded = 0;
        if (rounded > 255)
            rounded = 255;
        return (byte)rounded;
    }
```

### 4. `Models/Vulkan/MaterialVulkan.quorum`

**`PreloadTextureSet`:** the two loads ask for mipmaps, and the normals are
marked as packed:

```
        Texture albedo
        albedo:LoadFromPixelMap(albedoHeight, albedoHeight:GetFormat(), true)
        Texture normals
        normals:SetPackedNormalMipMaps(true)
        normals:LoadFromPixelMap(normalRoughness, normalRoughness:GetFormat(), true)
```

**`Preload`, the old way (decision 1):**

```
            texture:LoadFromFile(texturePath, true)
```

```
            Texture normal
            normal:SetPackedNormalMipMaps(true)
            normal:LoadFromFile(normalPath, true)
```

```
            rough:LoadFromFile(roughPath, true)
```

The unit texture (no texture path) is left alone.

### Size

About 40 lines in `Texture`, 150 in `VulkanTextureManager` (most of it new
small actions and comments), 100 lines of Java, and 6 in `MaterialVulkan`.
The plugins need rebuilding, as for Item 24.

## Project-side change (with the library change)

**`TerrainSplatFragmentShader`, texture set path:**
- Before the layer loop:
  ```glsl
      // How fast the world position changes across the screen, for
      // picking mip levels. Taken here, before any branch, since layers
      // with no weight are skipped below (Terrain3D does the same).
      vec2 positionDx = dFdx(v_position.xz);
      vec2 positionDy = dFdy(v_position.xz);
  ```
- In the loop, the two reads become `textureGrad(...,
  coordinates, positionDx / tileSize, positionDy / tileSize)` through a new
  `sampleGlobalTextureGrad(index, coordinates, dx, dy)` helper.
- The plain path reads every layer outside any branch, so it can keep
  `texture`.

**Plain textures:** the speckled dirt and sand in TerrainEditor and
DriveOpen load with `LoadFromPixelMap(map, map:GetFormat(), true)`, and
grass.png and rock.png (used when texture sets are off) with
`LoadFromFile(path, true)`.

**A check main, `MipMapCheck.quorum`:**
- two long ground planes side by side, running away from the camera, with
  the same fine checkerboard texture: left without mipmaps, right with;
- the camera slowly moving;
- the console reports each texture's level count, from
  `UsesMipMaps`.

The right plane should fade to even grey in the distance. The left one
should crawl with moiré.

## What changes for existing games

- **Nothing for 2D,** fonts or textures that don't ask for mipmaps. They
  still have one level.
- **Anisotropic filtering applies to every texture.** Textures seen at an
  angle get sharper. A texture drawn flat to the screen is read the same.
- **With decision 1, every 3D model's material textures get mipmaps.**
  Distant models stop sparkling. Loading takes a little longer, and
  textures take a third more GPU memory.

## Risks and things to know

- **Color is averaged as stored.** The renderer treats textures as linear
  (UNORM, not sRGB) throughout, so the averages match how they're drawn
  today. If the renderer moves to sRGB textures later, mipmaps should
  average in linear space.
- **Odd sizes** use their last row or column twice. A 1000 by 600 image
  gets correct, slightly uneven levels. AmbientCG sets are powers of two.
- **Load time:** packing a 1K texture set already takes a moment (Item 24).
  Mipmaps add a few milliseconds per texture.
- **The table and splat textures must not ask for mipmaps.** The table is
  read texel by texel. The splat texture's weights, mipmapped, would smear
  into neighboring regions' edges. Neither asks today.
- **MoltenVK** (the Mac) supports anisotropy and multi-level images. The
  Mac's GPUs report a maximum of 16.

## Test plan

1. **MipMapCheck:** the right plane is smooth in the distance, the left
   one shimmers. The console shows 11 levels for a 1024 texture, and 1
   without.
2. **TextureSetCheck:** the three boxes look as before up close, and stay
   steady as you back away. The texture set boxes don't get darker with
   distance (packed normal mipmaps).
3. **TerrainEditor:** far ground stops crawling as the camera turns, and
   ground at a low angle stays sharp. There are no sparkles along the edges
   between grass and rock. Painting still works (the splat texture keeps
   one level).
4. **TextureUpdateCheck and DriveOpen:** unchanged.
5. **Worlds tests:** 22 of 22.

## Rollback

All changes are in four library files and one Java file. Revert them, and
rebuild the library and plugins. The project's shader change and the
`true`s in its texture loads are harmless without mipmaps: `textureGrad`
reads level 0 when there's only one, and on the old library the two-argument
`LoadFromFile` doesn't exist, so those lines would go back too.

## Open decisions for the user

1. **The old way's Material textures get mipmaps too** (color, normal and
   metal-rough maps on every 3D model)? Recommended: yes. Models are what
   mipmaps are for, and nothing in 3D is drawn at its own size.
2. **Add the public `Texture:LoadFromFile(text filePath, boolean
   useMipMaps)`?** It's additive, and the only easy way for a game to ask
   for mipmaps on a file texture. Recommended: yes.
3. **Anisotropy cap:** 16, the usual maximum (recommended), or 8 to save a
   little time on weak GPUs?
4. **Levels made in Java** (recommended, for correct packed normals), or
   on the GPU with a new blit command?
