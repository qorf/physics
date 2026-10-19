# Item 24: materials from texture sets (Vulkan)

**Status (2026-10-19): done.** Committed in `3e6fde7e0`; confirmed on boxes and on the terrain.

`VulkanChanges.md` #24, `LibraryChangesPlan.md` order 16. Step 1 of
`TerrainMaterialsPlan.md`. **Approved and applied on
2026-10-19** to the `quorum-language` branch `TerrainShader`, with the
project's splat shader writing AO 1.0 (change 7). **First runs (2026-10-19):**
- 16-bit PNGs didn't load (see Risks); the assets were converted.
- After that, **TextureSetCheck shows only a grey window** (no boxes, no
  label), though its CreateGame finishes. **Correction:** TextureUpdateCheck
  and the other programs work with Item 24. An answer was misread as
  TextureUpdateCheck being grey too, which led to removing Item 24 to
  bisect. It was **reapplied unchanged** the same day from the patches in
  `Item24Shaders/`, which are kept as a backup.
- **Next:** TextureSetCheck now starts with only a label and a sun, and adds
  the plain box (P), the GL set box (G), the DX set box (D) and ambient light
  (A) one key at a time, with a heartbeat every 2 seconds, to find which part
  blanks the window.
- **Result:** nothing shows even before any box is added, though frames keep
  running (heartbeat) and every box loads without error. DriveOpen,
  TerrainEditor and TextureUpdateCheck all draw normally with Item 24. So
  the blank window is not caused by texture sets.
  - The one thing only TextureSetCheck does is aim its sun again **every
    frame** (`DirectionalLight:SetDirection` in `Update`).
  - Now the sun holds still until **L** is pressed, and a red 2D square
    shows whether 2D drawing works. If the window shows until L and then
    blanks, a moving sun is the cause: a separate library bug.
- **Result:** the red square shows (2D works), but no box shows, not even
  the plain old-way box, with the sun still. So it's not the sun, and not
  texture sets: the hand-built boxes (`ModelBuilder:CreateBox`, own
  `Material`, `GetModelBlueprint`, `Load`) don't appear, while
  `Model:LoadBox` boxes do in TextureUpdateCheck. **Next:** an orange
  reference box made with `LoadBox` from the start, and each box's position,
  size and showing state written to the console.
- **Result** (after a stale build in Studio was cleared):
  - the orange reference box shows, and lighting changes with A and L, as
    expected;
  - the hand-built boxes have the right positions and sizes, and are
    showing, yet aren't seen.

  **Likely cause: texture groups (`VulkanChanges.md` #22).** Only groups 0 to
  2 are drawn. The boxes' textures were loaded after the label's glyph
  textures, so they probably landed in group 3 or later. **Next:** the boxes
  are now made in CreateGame before the label, and the heartbeat prints each
  box's texture group.

Test main: `SourceCode/TextureSetCheck.quorum`.

Note: the Java change (`PixelMap.java`) means the plugins must be rebuilt as
well as the standard library.

Paths: library Quorum under
`quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/`; Java
under
`quorum-language/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/`.

## What it does

Quorum's `Material` can describe a material **the old way** (texture,
normal map, glTF metal-rough map) **or the new way**: a texture set of
separate maps, as AmbientCG and Poly Haven give them (color, normal,
roughness, ambient occlusion, height). Under Vulkan:
- a texture set is packed on load into Terrain3D's two textures:
  - albedo + height;
  - normal (with AO folded in) + roughness;
- the default 3D shader draws it, with tangent-space normals, roughness, and
  AO;
- the lighting pass applies AO to ambient light.

Old-way materials look exactly as before. OpenGL is untouched: it never
reads the new fields.

The terrain's use of this (step 2 of the plan) is project work afterward.

## The changes, by file

| # | File | Kind | What |
|---|---|---|---|
| 1 | `Models/Data/Material.quorum` | Quorum | Texture set fields, getters and setters, `SetTextureSet`, `UsesTextureSet` |
| 2 | `PixelMap.quorum` and `PixelMap.java` | Quorum + Java | Five channel helpers, working on the pixel bytes that are uploaded |
| 3 | `Models/Vulkan/MaterialVulkan.quorum` | Quorum | Packs a texture set into two textures; the record grows from 8 to 12 words |
| 4 | `Shaders/Vulkan/Fragment/DefaultFragmentShader3DVulkan.quorum` | GLSL | The texture-set path; AO into the PBR channel that is unused today |
| 5 | `Shaders/Vulkan/Fragment/DefaultShadowFragmentShaderVulkan.quorum`, `TwoStageShadowFragmentShaderVulkan.quorum` | GLSL | Skip the alpha test for texture sets (their alpha is height) |
| 6 | `Shaders/Vulkan/Fragment/DefaultLightingFragmentShaderVulkan.quorum` | GLSL | Ambient light × AO |
| 7 | project `Worlds/TerrainSplatFragmentShader.quorum` | GLSL (project) | Writes AO 1.0 instead of 0.5, so the terrain's ambient isn't halved |

## 1. `Models/Data/Material.quorum`

### New import

```quorum
use Libraries.System.File
```

### New fields (after `number refractiveIndex = 1.0`)

```quorum
    // The new way: a texture set, separate maps that each hold one property,
    // as AmbientCG and Poly Haven give them. Only the Vulkan renderer reads
    // these. The color map's path being set is what marks a texture set.
    text colorMapPath = ""
    text roughnessMapPath = ""
    text ambientOcclusionMapPath = ""
    text heightMapPath = ""
    boolean normalMapIsDirectX = false
    number textureScale = 1.0
```

The texture set reuses the existing `normalMapPath` for its normal map.

### New actions (at the end of the class)

```quorum
    /*
    This action returns the path of the texture set's color (albedo) map.

    Attribute: Returns The path, or "" if the material doesn't use a texture set.
    */
    action GetColorMapPath returns text
        return colorMapPath
    end

    /*
    This action sets the path of the texture set's color (albedo) map. Setting
    it makes the material a texture set, which the Vulkan renderer draws with
    the set's normal, roughness, ambient occlusion and height maps, instead
    of the texture path and metal-rough map.

    Attribute: Parameter path The color map's file path.
    */
    action SetColorMapPath(text path)
        colorMapPath = path
    end

    /*
    This action returns the path of the texture set's roughness map.

    Attribute: Returns The path, or "" if none.
    */
    action GetRoughnessMapPath returns text
        return roughnessMapPath
    end

    /*
    This action sets the path of the texture set's roughness map: a gray
    image, black for smooth and white for rough. Without one, the roughness
    factor is used everywhere.

    Attribute: Parameter path The roughness map's file path.
    */
    action SetRoughnessMapPath(text path)
        roughnessMapPath = path
    end

    /*
    This action returns the path of the texture set's ambient occlusion map.

    Attribute: Returns The path, or "" if none.
    */
    action GetAmbientOcclusionMapPath returns text
        return ambientOcclusionMapPath
    end

    /*
    This action sets the path of the texture set's ambient occlusion map: a
    gray image, darker where little surrounding light reaches, such as in
    cracks. It darkens only ambient light.

    Attribute: Parameter path The ambient occlusion map's file path.
    */
    action SetAmbientOcclusionMapPath(text path)
        ambientOcclusionMapPath = path
    end

    /*
    This action returns the path of the texture set's height map.

    Attribute: Returns The path, or "" if none.
    */
    action GetHeightMapPath returns text
        return heightMapPath
    end

    /*
    This action sets the path of the texture set's height map (often called
    displacement): a gray image, lighter where the surface stands higher. It
    doesn't move the surface; terrain uses it to blend materials, so stones
    show through sand.

    Attribute: Parameter path The height map's file path.
    */
    action SetHeightMapPath(text path)
        heightMapPath = path
    end

    /*
    This action sets whether the normal map uses the DirectX convention,
    where green points down, rather than the OpenGL convention, where green
    points up. Texture sets often come with both, named NormalDX and
    NormalGL. The default is OpenGL.

    Attribute: Parameter directX True for a DirectX normal map.
    */
    action SetNormalMapDirectX(boolean directX)
        normalMapIsDirectX = directX
    end

    /*
    This action returns true if the normal map uses the DirectX convention.

    Attribute: Returns True for DirectX, false for OpenGL.
    */
    action IsNormalMapDirectX returns boolean
        return normalMapIsDirectX
    end

    /*
    This action returns how many world units one tile of the material covers
    when it is laid on terrain by world position.

    Attribute: Returns The size of one tile, in world units.
    */
    action GetTextureScale returns number
        return textureScale
    end

    /*
    This action sets how many world units one tile of the material covers
    when it is laid on terrain by world position. Models use their own
    texture coordinates and ignore it.

    Attribute: Parameter size The size of one tile, in world units. It must be more than 0.
    */
    action SetTextureScale(number size)
        if size <= 0
            alert("A material's texture scale must be more than 0, but was given " + size + ".")
        end
        textureScale = size
    end

    /*
    This action returns true if the material is a texture set (the new way),
    which is true once a color map is set.

    Attribute: Returns True for a texture set.
    */
    action UsesTextureSet returns boolean
        return colorMapPath not= ""
    end

    /*
    This action fills in a texture set from a folder of maps named the way
    AmbientCG and Poly Haven name them: name_Color.png, name_NormalGL.png
    (or name_NormalDX.png), name_Roughness.png, name_AmbientOcclusion.png
    and name_Displacement.png. Maps that aren't there are left out. The
    color map must be there.

    Attribute: Parameter folder The folder holding the maps.
    Attribute: Parameter name The start of the maps' file names, such as "Rocks002_1K-PNG".

    Attribute: Example
    use Libraries.Game.Graphics.Models.Data.Material

    Material rock
    rock:SetTextureSet("Textures/Rocks002_1K-PNG", "Rocks002_1K-PNG")
    */
    action SetTextureSet(text folder, text name)
        text start = folder + "/" + name + "_"
        if not FileExists(start + "Color.png")
            alert("I couldn't find the texture set's color map, " + start + "Color.png.")
        end
        SetColorMapPath(start + "Color.png")
        if FileExists(start + "NormalGL.png")
            SetNormalMapPath(start + "NormalGL.png")
            SetNormalMapDirectX(false)
        elseif FileExists(start + "NormalDX.png")
            SetNormalMapPath(start + "NormalDX.png")
            SetNormalMapDirectX(true)
        end
        if FileExists(start + "Roughness.png")
            SetRoughnessMapPath(start + "Roughness.png")
        end
        if FileExists(start + "AmbientOcclusion.png")
            SetAmbientOcclusionMapPath(start + "AmbientOcclusion.png")
        end
        if FileExists(start + "Displacement.png")
            SetHeightMapPath(start + "Displacement.png")
        end
    end

    /*
    This action returns true if a file exists.

    Attribute: Parameter path The file's path.
    Attribute: Returns True if it exists.
    */
    private action FileExists(text path) returns boolean
        File file
        file:SetPath(path)
        return file:Exists()
    end
```

## 2. PixelMap channel helpers

### Why Java, and why these bytes

- Under Vulkan, `PixelMap:LoadPixelMap` converts every image to RGBA8888 in
  a Java byte buffer (`pixelPointer`), and that buffer is what is uploaded
  (`TransferPixelData`).
- For converted images, `GetPixel` and `SetPixel` still act on the original
  native image, not on that buffer.
- So packing must work on `pixelPointer` itself, in Java. That is also
  thousands of times faster than Quorum loops over a 1024 by 1024 image,
  and doesn't involve blending.
- **Gray images arrive as (255, 255, 255, v), RGB gray images as
  (v, v, v, 255).** The gray-value rule below reads both correctly: alpha
  when red, green and blue are all 255, and red otherwise.

### `PixelMap.quorum`: new system actions (after `SetPixel`, about line 365)

```quorum
    /*
    This action copies one channel of another PixelMap of the same size into
    one channel of this one, pixel by pixel. Channels are 0 red, 1 green,
    2 blue and 3 alpha. Both PixelMaps must be in the RGBA8888 format, which
    all loaded images are when using the Vulkan renderer. Nothing is blended.

    Attribute: Parameter source The PixelMap to copy from.
    Attribute: Parameter sourceChannel The channel to copy, 0 to 3.
    Attribute: Parameter destinationChannel The channel to copy into, 0 to 3.
    */
    system action CopyChannel(PixelMap source, integer sourceChannel, integer destinationChannel)

    /*
    This action copies the gray value of another PixelMap of the same size
    into one channel of this one. A gray image's value is read from alpha
    when its red, green and blue are all full (how a one-channel image is
    loaded), and from red otherwise. Both must be RGBA8888. Nothing is
    blended.

    Attribute: Parameter source The gray PixelMap to copy from.
    Attribute: Parameter destinationChannel The channel to copy into, 0 to 3.
    */
    system action CopyGrayValue(PixelMap source, integer destinationChannel)

    /*
    This action sets one channel of every pixel to the same value. This
    PixelMap must be RGBA8888. Nothing is blended.

    Attribute: Parameter channel The channel to set, 0 to 3.
    Attribute: Parameter value The value, 0 to 255.
    */
    system action SetChannel(integer channel, integer value)

    /*
    This action replaces one channel of every pixel with 255 minus its
    value, such as to turn a DirectX normal map into an OpenGL one by
    inverting green. This PixelMap must be RGBA8888.

    Attribute: Parameter channel The channel to invert, 0 to 3.
    */
    system action InvertChannel(integer channel)

    /*
    This action treats this PixelMap as a normal map and folds an ambient
    occlusion map into it, Terrain3D's way: each normal is made unit length
    and then scaled by the square root of the occlusion times one half, plus
    one half. A shader reads the occlusion back as twice the normal's length
    minus one, and the direction by normalizing. Only red, green and blue
    change. Both must be RGBA8888 and the same size.

    Attribute: Parameter occlusion The gray ambient occlusion PixelMap.
    */
    system action ScaleNormalsByOcclusion(PixelMap occlusion)
```

### `PixelMap.java`: new methods (after `SetPixel`, about line 155)

```java
    // Channel helpers, working on the RGBA8888 bytes in pixelPointer, which is
    // what the Vulkan texture manager uploads. Converted images keep their
    // pixels here rather than in the native pixmap.

    public void CopyChannel(quorum.Libraries.Game.Graphics.PixelMap_ quorumSource, int sourceChannel, int destinationChannel)
    {
        PixelMap source = ((quorum.Libraries.Game.Graphics.PixelMap) quorumSource).plugin_;
        CheckChannel(sourceChannel);
        CheckChannel(destinationChannel);
        CheckSameRGBA(source);
        int count = width * height;
        for (int i = 0; i < count; i++)
            pixelPointer.put(i * 4 + destinationChannel, source.pixelPointer.get(i * 4 + sourceChannel));
    }

    public void CopyGrayValue(quorum.Libraries.Game.Graphics.PixelMap_ quorumSource, int destinationChannel)
    {
        PixelMap source = ((quorum.Libraries.Game.Graphics.PixelMap) quorumSource).plugin_;
        CheckChannel(destinationChannel);
        CheckSameRGBA(source);
        int count = width * height;
        for (int i = 0; i < count; i++)
            pixelPointer.put(i * 4 + destinationChannel, (byte) source.GetGrayValue(i));
    }

    public void SetChannel(int channel, int value)
    {
        CheckChannel(channel);
        CheckRGBA();
        byte b = (byte) Math.max(0, Math.min(255, value));
        int count = width * height;
        for (int i = 0; i < count; i++)
            pixelPointer.put(i * 4 + channel, b);
    }

    public void InvertChannel(int channel)
    {
        CheckChannel(channel);
        CheckRGBA();
        int count = width * height;
        for (int i = 0; i < count; i++)
        {
            int value = pixelPointer.get(i * 4 + channel) & 0xFF;
            pixelPointer.put(i * 4 + channel, (byte) (255 - value));
        }
    }

    public void ScaleNormalsByOcclusion(quorum.Libraries.Game.Graphics.PixelMap_ quorumOcclusion)
    {
        PixelMap occlusion = ((quorum.Libraries.Game.Graphics.PixelMap) quorumOcclusion).plugin_;
        CheckSameRGBA(occlusion);
        int count = width * height;
        for (int i = 0; i < count; i++)
        {
            double x = (pixelPointer.get(i * 4) & 0xFF) / 255.0 * 2.0 - 1.0;
            double y = (pixelPointer.get(i * 4 + 1) & 0xFF) / 255.0 * 2.0 - 1.0;
            double z = (pixelPointer.get(i * 4 + 2) & 0xFF) / 255.0 * 2.0 - 1.0;
            double length = Math.sqrt(x * x + y * y + z * z);
            if (length < 0.000001)
            {
                x = 0; y = 0; z = 1; length = 1;
            }
            double ao = occlusion.GetGrayValue(i) / 255.0;
            double scale = (Math.sqrt(ao) * 0.5 + 0.5) / length;
            pixelPointer.put(i * 4, ToByte(x * scale));
            pixelPointer.put(i * 4 + 1, ToByte(y * scale));
            pixelPointer.put(i * 4 + 2, ToByte(z * scale));
        }
    }

    // A pixel's gray value: alpha when red, green and blue are all 255 (how
    // a one-channel image is converted), red otherwise.
    private int GetGrayValue(int pixel)
    {
        int r = pixelPointer.get(pixel * 4) & 0xFF;
        int g = pixelPointer.get(pixel * 4 + 1) & 0xFF;
        int b = pixelPointer.get(pixel * 4 + 2) & 0xFF;
        if (r == 255 && g == 255 && b == 255)
            return pixelPointer.get(pixel * 4 + 3) & 0xFF;
        return r;
    }

    // Turns a value from -1 to 1 into a byte from 0 to 255.
    private static byte ToByte(double value)
    {
        long level = Math.round((value * 0.5 + 0.5) * 255.0);
        return (byte) Math.max(0, Math.min(255, level));
    }

    private void CheckChannel(int channel)
    {
        if (channel < 0 || channel > 3)
            throw new GameRuntimeError("A PixelMap channel must be from 0 to 3, but was given " + channel + ".");
    }

    private void CheckRGBA()
    {
        if (pixelPointer == null)
            throw new GameRuntimeError("The PixelMap wasn't initialized yet! Use LoadPixelMap() or CreatePixelMap() first.");
        if (format != FORMAT_RGBA8888)
            throw new GameRuntimeError("This PixelMap action needs the RGBA8888 format, which loaded images have when using Vulkan.");
    }

    private void CheckSameRGBA(PixelMap other)
    {
        CheckRGBA();
        other.CheckRGBA();
        if (other.width != width || other.height != height)
            throw new GameRuntimeError("The two PixelMaps must be the same size, but one is " + width + " by " + height +
                " and the other " + other.width + " by " + other.height + ".");
    }
```

`format`, `width`, `height` and `pixelPointer` are the class's existing
fields.
- **Checked:** on the converted path, `LoadPixelMap` calls
  `LoadFromByteBuffer(..., FORMAT_RGBA8888)`, which sets `format`, `width`
  and `height`. So `CheckRGBA` works for converted images, and for maps from
  `CreatePixelMap`.
- **Found while checking (a latent bug, recorded as F in
  `VulkanChanges.md`):** on that converted path, `basePointer` is never set
  (it stays -1), so `GetPixel` and `SetPixel` on a converted image (any gray
  or RGB file under Vulkan) call the native code with an invalid pointer.
  These helpers avoid it by working on `pixelPointer`.

## 3. `Models/Vulkan/MaterialVulkan.quorum`

### New imports

```quorum
use Libraries.Game.Graphics.PixelMap
use Libraries.Game.Graphics.Format
use Libraries.Game.Graphics.Color
use Libraries.System.File
use Libraries.Compute.Math
```

### The record: from 8 to 12 words

Before (lines 25-43): eight words, `MATERIAL_BYTE_SIZE = 4 * 8`.

After: the same eight, then four more. **Added at the end**, so the shadow
shaders' and anything else's view of the first eight is unchanged.

```quorum
    /*The buffer for an individual material holds this data:
Diffuse color (RGBA8888, 4 bytes)
Texture index (uint, 4 bytes); for a texture set, its albedo-height texture
Has Normal Map? (uint, 4 bytes, 0 or 1 for boolean logic)
Has Rough Map? (uint, 4 bytes, 0 or 1 for boolean logic)
Normal map index (uint, 4 bytes); for a texture set, its normal-roughness texture
Rough map index (uint, 4 bytes)
Roughness Factor (float, 4 bytes)
Metallic Factor (float, 4 bytes)
Flags (uint, 4 bytes): 1 if the material is a texture set
Texture scale (float, 4 bytes): world units per tile, for terrain
Two reserved words (uint, 4 bytes each), 0*/
    constant integer DIFFUSE_INDEX = 0
    constant integer TEXTURE_INDEX = 1
    constant integer HAS_NORMAL_MAP_INDEX = 2
    constant integer HAS_ROUGH_MAP_INDEX = 3
    constant integer NORMAL_MAP_INDEX = 4
    constant integer ROUGH_MAP_INDEX = 5
    constant integer ROUGH_FACTOR_INDEX = 6
    constant integer METALLIC_FACTOR_INDEX = 7
    constant integer FLAGS_INDEX = 8
    constant integer TEXTURE_SCALE_INDEX = 9
    constant integer RESERVED_INDEX_1 = 10
    constant integer RESERVED_INDEX_2 = 11

    constant integer TEXTURE_SET_FLAG = 1

    constant integer MATERIAL_BYTE_SIZE = 4 * 12
```

### New fields (after `Texture preloadRoughMap = undefined`)

```quorum
    // For a texture set: whether this material is one, and its two packed
    // textures, kept after loading so terrain can find their places.
    boolean usesTextureSet = false
    Texture albedoHeightTexture = undefined
    Texture normalRoughnessTexture = undefined
    number textureScale = 1
```

### `Preload`: a texture set takes the new path

Before (line 58): `action Preload(VulkanDevice device, Material data)`,
starting with `me:device = device` and `preloadData = data`.

After: two lines added after those, then the rest unchanged.

```quorum
    action Preload(VulkanDevice device, Material data)
        me:device = device
        preloadData = data

        if data:UsesTextureSet()
            PreloadTextureSet(data)
            return now
        end

        text texturePath = data:GetTexturePath()
        ... (unchanged) ...
```

### New private action `PreloadTextureSet`

```quorum
    /*
    This action packs a texture set into two textures, as Terrain3D does,
    and sends them to the texture manager:
    - albedo-height: the color map's red, green and blue, and the height
      map's gray in alpha (middle gray if there's none);
    - normal-roughness: the normal map (flat if there's none, and turned to
      the OpenGL convention if it's DirectX), with the ambient occlusion map
      folded into the normals' length, and the roughness map's gray in alpha
      (the roughness factor if there's none).
    All maps must be the same size as the color map.

    Attribute: Parameter data The material, a texture set.
    */
    private action PreloadTextureSet(Material data)
        usesTextureSet = true
        textureScale = data:GetTextureScale()

        PixelMap albedoHeight = LoadMap(data:GetColorMapPath())
        integer width = albedoHeight:GetWidth()
        integer height = albedoHeight:GetHeight()

        if data:GetHeightMapPath() = ""
            albedoHeight:SetChannel(3, 128)
        else
            PixelMap heights = LoadMatchingMap(data:GetHeightMapPath(), width, height)
            albedoHeight:CopyGrayValue(heights, 3)
            heights:Dispose()
        end

        PixelMap normalRoughness = undefined
        if data:GetNormalMapPath() = ""
            PixelMap flat
            Format format
            format:SetValue(format:RGBA8888)
            flat:CreatePixelMap(width, height, format)
            Color color
            flat:Fill(color:CustomColor(128 / 255.0, 128 / 255.0, 1, 1))
            normalRoughness = flat
        else
            normalRoughness = LoadMatchingMap(data:GetNormalMapPath(), width, height)
            if data:IsNormalMapDirectX()
                normalRoughness:InvertChannel(1)
            end
        end

        if data:GetAmbientOcclusionMapPath() not= ""
            PixelMap occlusion = LoadMatchingMap(data:GetAmbientOcclusionMapPath(), width, height)
            normalRoughness:ScaleNormalsByOcclusion(occlusion)
            occlusion:Dispose()
        end

        if data:GetRoughnessMapPath() = ""
            Math math
            normalRoughness:SetChannel(3, cast(integer, math:Round(math:Clamp(data:GetRoughness(), 0, 1) * 255)))
        else
            PixelMap roughness = LoadMatchingMap(data:GetRoughnessMapPath(), width, height)
            normalRoughness:CopyGrayValue(roughness, 3)
            roughness:Dispose()
        end

        Texture albedo
        albedo:LoadFromPixelMap(albedoHeight)
        Texture normals
        normals:LoadFromPixelMap(normalRoughness)
        albedoHeightTexture = albedo
        normalRoughnessTexture = normals
        preloadTexture = albedo
        preloadNormalMap = normals
    end

    /*
    This action loads an image file into a PixelMap.

    Attribute: Parameter path The file's path.
    Attribute: Returns The PixelMap.
    */
    private action LoadMap(text path) returns PixelMap
        File file
        file:SetPath(path)
        if not file:Exists()
            alert("I couldn't find the texture set map " + path + ".")
        end
        PixelMap map
        map:LoadPixelMap(file)
        return map
    end

    /*
    This action loads an image file into a PixelMap, and checks it is the
    expected size.

    Attribute: Parameter path The file's path.
    Attribute: Parameter width The width it must have.
    Attribute: Parameter height The height it must have.
    Attribute: Returns The PixelMap.
    */
    private action LoadMatchingMap(text path, integer width, integer height) returns PixelMap
        PixelMap map = LoadMap(path)
        if map:GetWidth() not= width or map:GetHeight() not= height
            alert("The texture set map " + path + " is " + map:GetWidth() + " by " + map:GetHeight() +
                ", but the color map is " + width + " by " + height + ". All maps in a set must be the same size.")
        end
        return map
    end
```

### `Load`: the four new words

Before: lines 157-158 set the roughness and metallic factors, then the record
is copied to the staging buffer.

After: the four new words are set between them.

```quorum
        dataArray:Set(ROUGH_FACTOR_INDEX, data:GetRoughness())
        dataArray:Set(METALLIC_FACTOR_INDEX, data:GetMetallic())
        if usesTextureSet
            dataArray:Set(FLAGS_INDEX, utility:EncodeIntegerAsNumber(TEXTURE_SET_FLAG))
        else
            dataArray:Set(FLAGS_INDEX, utility:EncodeIntegerAsNumber(0))
        end
        dataArray:Set(TEXTURE_SCALE_INDEX, data:GetTextureScale())
        dataArray:Set(RESERVED_INDEX_1, utility:EncodeIntegerAsNumber(0))
        dataArray:Set(RESERVED_INDEX_2, utility:EncodeIntegerAsNumber(0))
```

For a texture set, the existing code above this already writes:
- the albedo-height texture's place as the texture index;
- "has normal map" with the normal-roughness texture's place as the normal
  map index (since `preloadNormalMap` is that texture);
- "no rough map".

So old readers of the record see a sensible color texture and normal map.
`MATERIAL_BYTE_SIZE` already sizes the staging buffer, the array and the GPU
buffer.

### New actions (at the end of the class)

```quorum
    /*
    This action returns true if the material was loaded from a texture set.

    Attribute: Returns True for a texture set.
    */
    action UsesTextureSet returns boolean
        return usesTextureSet
    end

    /*
    This action returns a texture set's packed albedo-height texture: color
    in red, green and blue, height in alpha.

    Attribute: Returns The texture, or undefined if the material isn't a texture set.
    */
    action GetAlbedoHeightTexture returns Texture
        return albedoHeightTexture
    end

    /*
    This action returns a texture set's packed normal-roughness texture:
    the normal in red, green and blue (its length carrying ambient
    occlusion), roughness in alpha.

    Attribute: Returns The texture, or undefined if the material isn't a texture set.
    */
    action GetNormalRoughnessTexture returns Texture
        return normalRoughnessTexture
    end

    /*
    This action returns how many world units one tile of the material covers
    on terrain.

    Attribute: Returns The size of one tile, in world units.
    */
    action GetTextureScale returns number
        return textureScale
    end
```

## 4. `DefaultFragmentShader3DVulkan.quorum`

### The `Material` struct

Before:

```glsl
struct Material {
	uint diffuseColor;
	uint textureIndex;
	uint hasNormalMap;
	uint hasRoughMap;
	uint normalMapIndex;
	uint roughMapIndex;
	float roughness;
	float metallic;
};
```

After: the same, plus four fields.

```glsl
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
```

### `main`: the texture set path, and AO

Before: color, the alpha test, position, normal from `calculateNormal`, and
PBR = (0.5, roughness, metallic).

After:

```glsl
void main()
{
	// Calculate albedo.
   Instances instances = pushConstants.instances;
   InstanceData instanceData = instances.data[v_entityID];
   Materials materials = instanceData.materials;
   Material material = materials.data;
   // A texture set keeps height in its albedo's alpha, and its normal,
   // ambient occlusion and roughness together in the normal map.
   bool textureSet = (material.flags & 1u) != 0u;

   uint textureIndex = material.textureIndex;
	if (v_hasTextureOverride == 1)
		textureIndex = v_textureOverrideIndex;

	vec4 diffuse = unpackUnorm4x8(material.diffuseColor);
	if (v_hasDiffuseOverride == 1)
		diffuse = unpackUnorm4x8(v_diffuseOverride);

    outputColor = texture(nonuniformEXT(sampler2D(globalTextures[textureIndex], immutableSampler)), v_textureCoords) * diffuse;

	if (textureSet)
	{
		// Alpha is height, not opacity.
		outputColor.a = diffuse.a;
	}
	// If the color is less than half of the base transparency (i.e. transparent pixels in the texture), discard the fragment.
	else if (outputColor.a < (diffuse.a / 2.0))
	{
		discard;
	}

	// Set position.
	outputPosition = v_position;

	vec3 newNormal;
	float roughnessFactor = 0.0f;
    float metallicFactor = material.metallic;
	float ambientOcclusion = 1.0f;
	if (textureSet)
	{
		vec4 normalRoughness = texture(nonuniformEXT(sampler2D(globalTextures[material.normalMapIndex], immutableSampler)), v_textureCoords);
		vec3 packedNormal = normalRoughness.rgb * 2.0 - 1.0;
		// Terrain3D's packing: the normal's length carries ambient occlusion.
		ambientOcclusion = clamp(length(packedNormal) * 2.0 - 1.0, 0.0, 1.0);
		newNormal = normalize(v_tangentBitangentNormal * normalize(packedNormal));
		roughnessFactor = normalRoughness.a;
	}
	else
	{
		// Calculate and set normal.
		newNormal = calculateNormal(material, v_tangentBitangentNormal, v_textureCoords);

		// Calculate PBR properties.
		if (material.hasRoughMap > 0)
		{
			vec4 pbrValues = texture(nonuniformEXT(sampler2D(globalTextures[material.roughMapIndex], immutableSampler)), v_textureCoords);
			roughnessFactor = pbrValues.g;
			metallicFactor = pbrValues.b;
		}
		else
		{
			roughnessFactor = material.roughness;
		}
	}
	outputNormal = vec4(newNormal, 1.0);

	// The first channel, unused before, carries ambient occlusion: 1 for none.
	outputPBR = vec4(ambientOcclusion, roughnessFactor, metallicFactor, 1.0);
}
```

For old-way materials, the only difference in output is the first PBR
channel: 1.0 where it was 0.5. Nothing read it before.

## 5. The two shadow fragment shaders

In both `DefaultShadowFragmentShaderVulkan.quorum` and
`TwoStageShadowFragmentShaderVulkan.quorum`:

**The `Material` struct** gets the same four fields as above.

**The alpha test.**

Before:

```glsl
			// If the color is mostly transparent, discard the fragment.
			if (sampledColor.a < 0.5)
			{
				discard;
			}
```

After:

```glsl
			// If the color is mostly transparent, discard the fragment. A
			// texture set's alpha is height, not opacity, so it is never
			// discarded.
			if ((material.flags & 1u) == 0u && sampledColor.a < 0.5)
			{
				discard;
			}
```

Without this, the low parts of a texture set would cast no shadow.

## 6. `DefaultLightingFragmentShaderVulkan.quorum`

Before (line 303):

```glsl
    vec3 ambient = sceneInfo.ambientColor * albedo * sceneInfo.ambientIntensity;
```

After:

```glsl
    // The PBR image's first channel is ambient occlusion (1 for none), so
    // cracks and hollows get less ambient light. Direct light is unchanged.
    vec3 ambient = sceneInfo.ambientColor * albedo * sceneInfo.ambientIntensity * pbr.r;
```

Pixels where nothing was drawn have 0 there, but they're also fully
transparent (the output takes the albedo's alpha), so nothing changes on
screen.

## 7. Project: the splat shader writes AO 1.0

`TerrainSplatFragmentShader` writes the PBR image too, with 0.5 first, in
both its branches. With change 6 that would halve the terrain's ambient
light, so it changes to 1.0 in the same step. Its copy of the `Material`
struct gets the four new fields, for consistency. Its texture-set support is
step 2 of `TerrainMaterialsPlan.md`.

## Size

| File | Lines |
|---|---|
| `Material.quorum` | about 190 added (mostly doc comments) |
| `PixelMap.quorum` and `PixelMap.java` | about 50 + 110 added |
| `MaterialVulkan.quorum` | about 150 added, 15 changed |
| `DefaultFragmentShader3DVulkan.quorum` | struct + about 40 changed |
| Shadow shaders (2) | struct + 1 line each |
| `DefaultLightingFragmentShaderVulkan.quorum` | 1 line |

## Risks and things to know

- **Both packed textures must land in the same texture group.**
  - The record stores places within a group, and the draw queue follows the
    color texture's group.
  - They load one after the other, so they're split only if the group fills
    exactly between them.
  - Loading sets early (before labels) keeps them in group 0. The texture
    group problems (#19, #22) are unchanged.
- **The normal map convention.** OpenGL is assumed, as the existing shader
  does. Quorum's world is left-handed, and `MeshVulkan` turns v into 1 − v,
  so a lit test must confirm GL is right for models; DX is the switch if
  not. Terrain samples by world position, which may need the other one.
  That's a terrain-shader matter for step 2.
- **Load time.** Each set loads up to five 1024 by 1024 images and packs
  them in Java: a fraction of a second per set, mostly PNG decoding.
- **Memory.** Two RGBA8 textures per set: 8 MB at 1024. There are no
  mipmaps (#7), so detailed textures shimmer at a distance. Mipmaps are the
  recommended next library item.
- **16-bit PNGs don't load at all (found in the first run, 2026-10-19).**
  This proposal assumed the loader cuts them to 8 bits; it doesn't. The
  native loader fails with "decoder init failed for stream" on the 16-bit
  displacement (and so would on the 16-bit normal maps). Options:
  - convert the assets to 8-bit (ffmpeg is on the machine);
  - a library change: `PixelMap.java` falls back to Java's ImageIO when the
    native loader fails (recorded as G in `VulkanChanges.md`).

  **Done (user's choice):** the nine 16-bit PNGs in the three sets (normals
  and displacement) were converted to 8-bit with ffmpeg. The originals are
  kept in each set's `Original16bit/` folder. Other texture sets will need
  the same until G is fixed.
- **Gray-value rule.** A gray image that's pure white in RGB with alpha
  below 255 would be misread. That doesn't happen with gray PNGs, which load
  as (255, 255, 255, v) or (v, v, v, 255).
- **The material cache is off** (`MaterialManagerVulkan:GetCachedMaterial`
  returns undefined). Each `GetMaterial` call packs again. Fine for a few
  terrain layers; models that share a set should share the `MaterialVulkan`.
- **OpenGL:** ignores texture sets entirely. A texture-set-only material
  draws with no texture there (its texture path is empty). To document.

## Test plan

1. **Nothing broken:**
   - `RunWorldTests`, `RunPhysicsTests`;
   - DriveOpen: the car, boxes, splatting and shadows look as before;
   - ambient light on old materials is unchanged (AO 1.0).
2. **A model with a texture set,** in a small test main next to
   `TextureUpdateCheck`:
   - one box with `SetTextureSet("Textures/Rocks002_1K-PNG", ...)`, one
     plain box, and a directional light that moves;
   - the rock box shows bumps that follow the light, and rougher, less
     shiny highlights;
   - cracks are darker in ambient light;
   - no holes in its shadow;
   - swap to `SetNormalMapDirectX(true)` with NormalDX and compare (to
     settle the convention).
3. **Missing maps:** a set with only a color map draws like a plain
   texture, with a flat normal and the roughness factor.
4. **Wrong sizes:** a map of another size gives the alert.

## Rollback

Revert the files above. Old-way materials are unaffected in any case.

## Results (2026-10-19)

TextureSetCheck, with Rocks002 1K (8-bit PNGs):

- All three boxes draw, in texture group 0. They first drew see-through
  because a new Material's diffuse is (0, 0, 0, 0), not undefined
  (VulkanChanges.md, H); the test now sets a white diffuse.
- The color map shows (grey stones, as the set is).
- The texture set boxes (GL map, and DX map with `SetNormalMapDirectX(true)`)
  show individual stones that catch the light and move with the sun. The
  plain box stays flat.
- Grazing light from above (T) and below (B): both set boxes look lit from
  the side the light comes from. Each pairs its file with the right flag, so
  this is the expected result.
- No holes or stray dark patches. A black square and a shadow on one box
  were the shadows of other cubes in the test.

Not yet shown: a negative control (a GL map with the DirectX flag on,
which should look lit from the wrong side), and roughness on its own.
