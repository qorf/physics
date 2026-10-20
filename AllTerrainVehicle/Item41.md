# Item 41: the sky reflected in water (water, phase 3)

**Status (2026-10-19): for review.** Nothing is applied yet. This is phase 3
of `WaterPlan.md`: the sky cube sampled along the reflected view, weighted
by fresnel, so water is nearly a mirror at low angles and clear looking
down.

**Needs Items 39 and 40 first.** It adds set 4 to Item 39's forward layout,
fills Item 39's forward scene data, and with no sky it reflects Item 40's
fog color.

**Branch:** whichever is checked out in `quorum-language` (`MakeAWish` now).
It never switches.

**Scope:** Vulkan only. **OpenGL is not touched.**

Paths: **G/** = `Quorum/Library/Standard/Libraries/Game/Graphics/`,
**P** = `G/Vulkan/VulkanPainter3D.quorum`, **W/** =
`AllTerrainVehicle/SourceCode/Worlds/`.

## The design

**Set 4 of every forward pipeline is the sky's cube:** one combined cube
sampler, with exactly the binding of the skybox's own set
(`GetSkyboxDescriptor`'s layout). So the painter binds the same per-slot
sky descriptor set the skybox draw uses. No new image, no new set.

**Which cube:**
- **The layer's skybox,** if it will be drawn this frame. The checks are
  the ones `RecordSkybox` already makes, moved into one action,
  `CanDrawSky`, so both always agree.
- **Otherwise a plain 1 × 1 cube,** made once by the painter through the
  texture manager's cube upload (Item 26's `RequestCubeLoad`). The shader
  is told there's no sky, and reflects the fog color, or the ambient light
  when there's no fog. It doesn't read the plain cube's grey; the cube is
  only there because a pipeline's sets must all be bound.
- The plain cube is uploaded with the next frame's textures. Until then
  (one frame, only in programs with no skybox) forward programs aren't
  drawn.

**Why the two never fight over the sky's descriptor set:** in a frame where
`CanDrawSky` is true, both the water and the skybox link the skybox's view.
In a frame where it's false, the skybox isn't drawn, so only the water
links the set (to the plain cube). A set is never linked twice with
different views in one frame's commands.

**The sky's rotation** goes in Item 39's forward scene data, the last 12
numbers of the push constants:

| Number | Holds |
|---|---|
| 0 to 8 | the skybox rotation's first three columns (x, y, z of each) |
| 9 | the inverter: 1, or -1 to mirror (`Skybox:GetInverter`) |
| 10 | 1 if there is a sky, 0 if not |
| 11 | spare |

The shader turns a world direction exactly as the skybox shader does:
`direction * mat3(rotation)`, then x times the inverter. In GLSL,
`direction * mat3(rotation)` is each column dotted with the direction,
so the shader needs only the three columns. `AddMatrix4` writes a
`Matrix4` column by column, the same order.

**In the water shader:**
1. `R = reflect(-V, N)`, with the ripple normal, so the reflection
   ripples.
2. `R.y` is made positive. A ripple can tilt the reflection below the
   horizon, where the cube shows the ground under the sky; the sky above
   is what water there would show.
3. **Fresnel:** `0.02 + 0.98 × (1 - N·V)^5`, times the program's reflection
   strength.
4. **Mixing:** the reflection covers the water's own color by the fresnel,
   and makes the water that much more opaque. At the shore it fades with
   the same shore fade, so there's no hard edge at low angles.
5. **From below** (camera under the surface): no reflection.

## The code: library

### 1. `G/Vulkan/VulkanPipelineInfoCreator.quorum`, `AddForwardInfo3D` (Item 39)

**The doc comment's set list.** The line

```
    - set 3: the lights (a storage buffer) and the scene data (a uniform).
```

becomes:

```
    - set 3: the lights (a storage buffer) and the scene data (a uniform);
    - set 4: the sky's cube, a combined sampler (Item 41).
```

**And** "then 12 numbers of scene data from the painter" becomes "then 12
numbers of scene data from the painter: the sky's rotation (Item 41)".

**The set itself.** The lines

```
        // Set 3: the lights and scene data, as the lighting pass's set 1.
        AddDescriptorSetLayoutBinding(constants:SHADER_STAGE_FRAGMENT_BIT, constants:DESCRIPTOR_TYPE_STORAGE_BUFFER)
        AddDescriptorSetLayoutBinding(constants:SHADER_STAGE_FRAGMENT_BIT, constants:DESCRIPTOR_TYPE_UNIFORM_BUFFER)
        FinishDescriptorSetLayout()
```

become:

```
        // Set 3: the lights and scene data, as the lighting pass's set 1.
        AddDescriptorSetLayoutBinding(constants:SHADER_STAGE_FRAGMENT_BIT, constants:DESCRIPTOR_TYPE_STORAGE_BUFFER)
        AddDescriptorSetLayoutBinding(constants:SHADER_STAGE_FRAGMENT_BIT, constants:DESCRIPTOR_TYPE_UNIFORM_BUFFER)
        FinishDescriptorSetLayout()

        // Set 4: the sky's cube (Item 41), with the same binding as the
        // skybox's own set, so the painter binds that set.
        AddDescriptorSetLayoutBinding(constants:SHADER_STAGE_FRAGMENT_BIT, constants:DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER)
        FinishDescriptorSetLayout()
```

### 2. P (`G/Vulkan/VulkanPainter3D.quorum`)

**New `use`s** (if not already there):

```
use Libraries.Game.Graphics.PixelMap
use Libraries.Game.Graphics.Format
use Libraries.Game.Graphics.Color
use Libraries.Compute.Matrix4
```

**New field,** after `Array<VulkanImageView> skyboxLinkedViews`:

```
    // A plain 1 by 1 cube, bound in place of the sky for forward programs
    // when there is no sky to draw (Item 41).
    Texture fallbackSkyCube = undefined
```

**`RecordSkybox`.** Its first checks

```
        if skybox = undefined or camera = undefined
            return now
        end
        if not skybox:IsLoaded()
            return now
        end
        Texture cube = skybox:GetCubeMap()
        if cube = undefined or cube:GetVulkanImageView() = undefined
            return now
        end
        if not skybox:UpdateView(camera)
            return now
        end
        VulkanConstants constants
```

become:

```
        if not CanDrawSky()
            return now
        end
        Texture cube = skybox:GetCubeMap()
        VulkanConstants constants
```

**New private actions,** before `RecordSkybox`:

```
    /*
    This action returns true if the sky will be drawn this frame: the layer
    has a skybox, its cube is made, and the camera is a perspective camera.
    The skybox draw and the forward programs' reflections both use it, so
    they always agree (Item 41).

    Attribute: Returns True if the sky can be drawn.
    */
    private action CanDrawSky returns boolean
        if skybox = undefined or camera = undefined
            return false
        end
        if not skybox:IsLoaded()
            return false
        end
        Texture cube = skybox:GetCubeMap()
        if cube = undefined or cube:GetVulkanImageView() = undefined
            return false
        end
        return skybox:UpdateView(camera)
    end

    /*
    This action returns the view of a plain 1 by 1 cube, bound for forward
    programs when there is no sky (Item 41). It is made the first time, and
    is ready once the texture manager has uploaded it, a frame later.

    Attribute: Returns The cube's view, or undefined until it is uploaded.
    */
    private action GetFallbackSkyView returns VulkanImageView
        if fallbackSkyCube = undefined
            VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
            Format format
            format:SetValue(format:RGBA8888)
            Color grey
            grey:SetColor(0.5, 0.5, 0.5, 1)
            Array<PixelMap> sides
            repeat 6 times
                PixelMap side
                side:CreatePixelMap(1, 1, format)
                side:Fill(grey)
                sides:Add(side)
            end
            Texture cube
            graphics:GetTextureManager():RequestCubeLoad(cube, sides)
            fallbackSkyCube = cube
        end
        return fallbackSkyCube:GetVulkanImageView()
    end

    /*
    This action adds the forward scene data to the forward push constants:
    the sky's rotation as its first three columns, the inverter, and
    whether there is a sky (Item 41). With no sky, the rotation is the
    identity.

    Attribute: Parameter hasSky True if the sky's cube is bound.
    */
    private action AddForwardSceneData(boolean hasSky)
        if hasSky
            Matrix4 rotation = skybox:GetRotation()
            forwardPushConstants:AddNumber32Bit(rotation:row0column0)
            forwardPushConstants:AddNumber32Bit(rotation:row1column0)
            forwardPushConstants:AddNumber32Bit(rotation:row2column0)
            forwardPushConstants:AddNumber32Bit(rotation:row0column1)
            forwardPushConstants:AddNumber32Bit(rotation:row1column1)
            forwardPushConstants:AddNumber32Bit(rotation:row2column1)
            forwardPushConstants:AddNumber32Bit(rotation:row0column2)
            forwardPushConstants:AddNumber32Bit(rotation:row1column2)
            forwardPushConstants:AddNumber32Bit(rotation:row2column2)
            forwardPushConstants:AddNumber32Bit(skybox:GetInverter())
            forwardPushConstants:AddNumber32Bit(1)
        else
            forwardPushConstants:AddNumber32Bit(1)
            forwardPushConstants:AddNumber32Bit(0)
            forwardPushConstants:AddNumber32Bit(0)
            forwardPushConstants:AddNumber32Bit(0)
            forwardPushConstants:AddNumber32Bit(1)
            forwardPushConstants:AddNumber32Bit(0)
            forwardPushConstants:AddNumber32Bit(0)
            forwardPushConstants:AddNumber32Bit(0)
            forwardPushConstants:AddNumber32Bit(1)
            forwardPushConstants:AddNumber32Bit(1)
            forwardPushConstants:AddNumber32Bit(0)
        end
        // Spare.
        forwardPushConstants:AddNumber32Bit(0)
    end
```

**`RecordForwardPrograms` (Item 39).** After its first lines

```
        VulkanConstants constants
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        VulkanTextureManager textureManager = graphics:GetTextureManager()
```

add:

```
        // The sky's cube for reflections (Item 41): the skybox's, if it is
        // drawn this frame, or else the plain cube. Until the plain cube is
        // uploaded, a frame after it is asked for, forward programs wait.
        boolean hasSky = CanDrawSky()
        VulkanImageView skyView = undefined
        if hasSky
            skyView = skybox:GetCubeMap():GetVulkanImageView()
        else
            skyView = GetFallbackSkyView()
        end
        if skyView = undefined
            return now
        end
```

**Binding it.** After the light data bind

```
                BindDescriptorSetCommand lightDataBind
                lightDataBind:SetPipelineLayout(layout)
                lightDataBind:SetDescriptorSet(environment:GetLightDataDescriptorSet(resourceIndex))
                lightDataBind:SetSetIndex(3)
                commandBuffer:Record(lightDataBind)
```

add:

```
                BindDescriptorSetCommand skyBind
                skyBind:SetPipelineLayout(layout)
                skyBind:SetDescriptorSet(GetSkyboxDescriptor(resourceIndex, skyView))
                skyBind:SetSetIndex(4)
                commandBuffer:Record(skyBind)
```

**The scene data.** The lines

```
                        // The forward scene data: unused until Item 41.
                        repeat FORWARD_SCENE_DATA_SIZE times
                            forwardPushConstants:AddNumber32Bit(0)
                        end
```

become:

```
                        // The forward scene data: the sky's rotation (Item 41).
                        AddForwardSceneData(hasSky)
```

`AddForwardSceneData` writes exactly `FORWARD_SCENE_DATA_SIZE` (12)
numbers, so the buffer is still filled to its 128 bytes.

## The code: project

### 3. `W/WaterFragmentShader.quorum` (after Items 39 and 40)

**The class comment.** After "every light shines and glints on the
surface." add: "The sky is reflected in it, strongly at low angles and
hardly looking down (library item 41)."

**The sky's cube,** after the `SceneInfo` block:

```glsl
// The sky's cube (library item 41), the skybox's own, or a plain one when
// there is no sky.
layout(set = 4, binding = 0) uniform samplerCube skyCube;
```

**New function,** after `rangeAttenuation`:

```glsl
// The sky seen along a world direction, turned and mirrored as the skybox
// is drawn (library item 41). With no sky, the fog's color if there is
// fog, or else the ambient light.
vec3 skyColor(vec3 direction)
{
    if (water.hasSky < 0.5)
    {
        if (sceneInfo.fogAmount > 0.0)
            return sceneInfo.fogColor;
        return sceneInfo.ambientColor * sceneInfo.ambientIntensity;
    }
    vec3 turned = vec3(dot(direction, water.skyColumn0), dot(direction, water.skyColumn1), dot(direction, water.skyColumn2));
    turned.x = turned.x * water.skyInverter;
    return texture(skyCube, turned).rgb;
}
```

**In `main`.** The lines (as Item 40 leaves them)

```glsl
    float opacity = mix(water.shallowColor.a, water.deepColor.a, 1.0 - exp(-thickness * clarity));
    // A soft edge where the water meets the shore.
    if (water.look.y > 0.0)
        opacity *= clamp(depth / water.look.y, 0.0, 1.0);
```

become:

```glsl
    float opacity = mix(water.shallowColor.a, water.deepColor.a, 1.0 - exp(-thickness * clarity));
    // A soft edge where the water meets the shore. The reflection fades
    // with it too.
    float shore = 1.0;
    if (water.look.y > 0.0)
        shore = clamp(depth / water.look.y, 0.0, 1.0);
    opacity *= shore;
```

**And** the lines

```glsl
    // The glint is added on top, and shows even on clear water: the
    // blend gives color × alpha + behind × (1 - alpha), so the color is
    // divided by the alpha here.
    float glintAlpha = clamp(max(glint.r, max(glint.g, glint.b)), 0.0, 1.0);
    float alpha = clamp(opacity + glintAlpha * (1.0 - opacity), 0.0, 1.0);
    vec3 color = (body * opacity + glint) / max(alpha, 0.0001);
```

become:

```glsl
    // The sky reflected in the water (library item 41): hardly any looking
    // straight down, nearly a mirror at a low angle (Schlick's fresnel). A
    // ripple can tilt the reflection below the horizon; the sky above is
    // what it would show there. Seen from below, there is none.
    float facing = max(dot(N, V), 0.0);
    float fresnel = WATER_REFLECTANCE + (1.0 - WATER_REFLECTANCE) * pow(1.0 - facing, 5.0);
    float reflection = fresnel * water.look.w * shore;
    if (V.y < 0.0)
        reflection = 0.0;
    vec3 R = reflect(-V, N);
    R.y = abs(R.y);
    vec3 sky = skyColor(normalize(R));

    // The reflection covers the water's own color, and makes the water as
    // opaque as it is strong. The glint is added on top, and shows even on
    // clear water. The blend gives color × alpha + behind × (1 - alpha),
    // so the color is divided by the alpha here.
    vec3 covered = body * opacity * (1.0 - reflection) + sky * reflection + glint;
    float alpha = opacity * (1.0 - reflection) + reflection;
    float glintAlpha = clamp(max(glint.r, max(glint.g, glint.b)), 0.0, 1.0);
    alpha = clamp(alpha + glintAlpha * (1.0 - alpha), 0.0, 1.0);
    vec3 color = covered / max(alpha, 0.0001);
```

The fog line after it (Item 40) stays as it is.

### 4. `SourceCode/WaterCheck.quorum` (after Items 39 and 40)

**New fields:** `boolean rWasDown = false`, `boolean kWasDown = false`,
`boolean skyShown = true`.

**In `Update`,** after the fog key:

```
        boolean rDown = monitor:IsKeyPressed(keys:R)
        if rDown and not rWasDown
            if water:GetReflectionStrength() > 0
                water:SetReflectionStrength(0)
                output "Water check: no reflection."
            else
                water:SetReflectionStrength(1)
                output "Water check: the sky is reflected."
            end
        end
        rWasDown = rDown

        boolean kDown = monitor:IsKeyPressed(keys:K)
        if kDown and not kWasDown
            if skyShown
                SetSkybox(undefined)
                skyShown = false
                output "Water check: sky hidden. The water reflects the fog color, or the ambient light."
            else
                SetSkybox(skybox)
                skyShown = true
                output "Water check: sky shown."
            end
        end
        kWasDown = kDown
```

Add "R reflection, K sky" to the label and the header's key list, and to
"What to see":
- "11. Looking across the pool at a low angle, the water shows the sky's
  colors and clouds, rippling; looking straight down it shows the floor.
  R turns the reflection off and on."
- "12. The reflected clouds are in the same places as the sky's, mirrored
  in the surface."
- "13. K hides the sky: the water reflects a flat color (the fog's, with
  F on) and is still drawn. K shows the sky again."

## What changes

**On screen:** water reflects the sky. Nothing else changes; the skybox
draws as before.

**Cost:** one cube read per water pixel, one more descriptor bind per
forward program.

**Memory:** the plain cube, six 1 × 1 pixels, in programs with water and no
sky.

## Test plan

1. **WaterCheck,** points 11 to 13, and points 1 to 10 still.
2. **SkyboxCheck:** the sky as before (`RecordSkybox` now uses
   `CanDrawSky`; R and I still turn and mirror it).
3. **WaterCheck with the sky turned** (if a key is added later, or by
   `skybox:Rotate` in `CreateGame` for a test): the reflection turns with
   the sky.
4. **With the validation layer, if available:** no messages about set 4,
   or about a descriptor set changed after it was bound.

## Rollback

Revert the Item 41 lines in the creator, P, the water shader and
WaterCheck. Item 39's zeros come back as the forward scene data.
