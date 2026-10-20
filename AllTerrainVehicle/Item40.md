# Item 40: distance fog (Vulkan)

**Status (2026-10-19): for review.** Nothing is applied yet. This is
`VulkanChanges.md` #17's fog half and `WaterPlan.md` decision 6 ("alongside
water"). Item 41 (the sky's reflection on water) uses the fog color when
there is no sky.

**Needs:** nothing in the library. Its water part (section 3) needs Item 39.
If Item 40 is applied first, section 3 waits for Item 39.

**Branch:** whichever is checked out in `quorum-language` (`MakeAWish` now).
It never switches.

**Scope:** Vulkan only. **OpenGL is not touched:** the fog actions are on
`EnvironmentVulkan`, not the shared `Environment`, so OpenGL games can't
call them. OpenGL fog would be part of Item 68.

Paths: **G/** = `Quorum/Library/Standard/Libraries/Game/Graphics/`,
**E** = `G/Models/Vulkan/EnvironmentVulkan.quorum`, **L** =
`G/Shaders/Vulkan/Fragment/DefaultLightingFragmentShaderVulkan.quorum`,
**W/** = `AllTerrainVehicle/SourceCode/Worlds/`.

## Why

**Far terrain ends in a hard line against the sky.** The far rings
(`SetFarRadius`) reach 200 units in DriveOpen, and past them is the sky.
Fog fades the land into a haze color as it gets far away, which:
- hides where the terrain ends;
- gives a sense of distance;
- hides the far rings' lower detail.

## The design

**Fog belongs to the environment,** beside the ambient light, and goes to
the shaders in the scene data uniform the lighting pass already reads
(set 1, binding 1). It is per layer, as lights are.

**How much fog, at a point:**
1. **By distance:** none before *start*, all of it by *end*, with a smooth
   curve between (smoothstep).
2. **By height (optional):** less fog above a base height, by
   `exp(-(height - base) × falloff)`. A falloff of 0 turns this off. It
   keeps hills clear while valleys are hazy.
3. **The most fog:** the *amount*, from 0 (no fog, the default) to 1 (far
   things are only the fog color).

The color is then `mix(lit color, fog color, fog)`.

**Where it's applied:**
- the lighting pass, to every lit pixel (all G-buffer geometry: terrain,
  models);
- the water shader (section 3), to the water's color.

**What it doesn't touch:** the sky. Pixels where nothing was drawn have
alpha 0, and the result pass shows the sky there. So pick a fog color close
to the sky's horizon, for example the Day sky's `(0.78, 0.86, 0.94)`.
Fading the land into the sky's own picture (sampling the cube) is a later
step.

**The scene data uniform** grows from 24 to 32 numbers (96 to 128 bytes).
The new words come after the view matrix, so nothing moves:

| Word | Holds |
|---|---|
| 24 to 26 | fog color (r, g, b) |
| 27 | fog start |
| 28 | fog end |
| 29 | fog amount (0 = off) |
| 30 | fog base height |
| 31 | fog height falloff (0 = off) |

The block is in scalar layout, so the new `vec3` and floats pack with no
padding.

**Names:** `end` is a reserved word, so `SetFog`'s distances are
`nearDistance` and `farDistance`.

**Changing fog** marks only the scene data dirty, not the shadows, so it
costs one 128-byte upload per frame slot.

## The code

### 1. E (`G/Models/Vulkan/EnvironmentVulkan.quorum`)

**The scene data size.** The lines

```
    constant integer SCENE_DATA_WORD_SIZE = 24
```

become:

```
    // The camera, ambient light, light count and view matrix (24 words),
    // then the fog (8 words, Item 40).
    constant integer SCENE_DATA_WORD_SIZE = 32
```

**New constants,** after `constant integer CAMERA_VIEW_MATRIX_INDEX = 8`:

```
    constant integer FOG_COLOR_INDEX = 24
    constant integer FOG_START_INDEX = 27
    constant integer FOG_END_INDEX = 28
    constant integer FOG_AMOUNT_INDEX = 29
    constant integer FOG_BASE_HEIGHT_INDEX = 30
    constant integer FOG_HEIGHT_FALLOFF_INDEX = 31
```

**New fields,** after `VulkanDescriptorSetLayout lightDataDescriptorSetLayout = undefined`:

```
    // Distance fog (Item 40). An amount of 0 is no fog.
    Color fogColor = undefined
    number fogStart = 50
    number fogEnd = 300
    number fogAmount = 0
    number fogBaseHeight = 0
    number fogHeightFalloff = 0
```

`Color` is already used in E (`ambientLight:GetColor()`); if the `use` is
missing, add `use Libraries.Game.Graphics.Color`.

**Writing it.** In `UpdateBuffers`, the scene data block's last lines

```
            sceneDataMappingArray:Set(CAMERA_VIEW_MATRIX_INDEX + 15, matrix:row3column3)
            
            sceneDataMemory:Set(sceneDataMappingArray)
```

become:

```
            sceneDataMappingArray:Set(CAMERA_VIEW_MATRIX_INDEX + 15, matrix:row3column3)

            // The fog (Item 40). With no color set, it is off.
            if fogColor not= undefined and fogAmount > 0
                sceneDataMappingArray:Set(FOG_COLOR_INDEX, fogColor:GetRed())
                sceneDataMappingArray:Set(FOG_COLOR_INDEX + 1, fogColor:GetGreen())
                sceneDataMappingArray:Set(FOG_COLOR_INDEX + 2, fogColor:GetBlue())
                sceneDataMappingArray:Set(FOG_AMOUNT_INDEX, fogAmount)
            else
                sceneDataMappingArray:Set(FOG_COLOR_INDEX, 0)
                sceneDataMappingArray:Set(FOG_COLOR_INDEX + 1, 0)
                sceneDataMappingArray:Set(FOG_COLOR_INDEX + 2, 0)
                sceneDataMappingArray:Set(FOG_AMOUNT_INDEX, 0)
            end
            sceneDataMappingArray:Set(FOG_START_INDEX, fogStart)
            sceneDataMappingArray:Set(FOG_END_INDEX, fogEnd)
            sceneDataMappingArray:Set(FOG_BASE_HEIGHT_INDEX, fogBaseHeight)
            sceneDataMappingArray:Set(FOG_HEIGHT_FALLOFF_INDEX, fogHeightFalloff)

            sceneDataMemory:Set(sceneDataMappingArray)
```

**New actions,** after `GetAmbientLight`:

```
    /*
    This action turns on distance fog: things fade into the fog color as
    they get farther from the camera, from none at the start distance to
    all of it at the end distance. The sky isn't fogged, so a color close
    to the sky's horizon looks best. Vulkan only (Item 40).

    Attribute: Parameter color The fog's color.
    Attribute: Parameter nearDistance The distance where fog begins.
    Attribute: Parameter farDistance The distance where fog is thickest. It must be more than the near distance.

    Attribute: Example
    use Libraries.Game.Game
    use Libraries.Game.Graphics.Color
    use Libraries.Game.Graphics.Environment
    use Libraries.Game.Graphics.Models.Vulkan.EnvironmentVulkan

    class Main is Game
        action Main
            StartGame()
        end

        action CreateGame
            Environment environment = GetCurrentLayer3D():GetEnvironment()
            if environment is EnvironmentVulkan
                EnvironmentVulkan vulkanEnvironment = cast(EnvironmentVulkan, environment)
                Color haze
                haze:SetColor(0.78, 0.86, 0.94, 1)
                vulkanEnvironment:SetFog(haze, 60, 260)
            end
        end
    end
    */
    action SetFog(Color color, number nearDistance, number farDistance)
        if farDistance <= nearDistance
            alert("The fog's far distance must be more than its near distance, but was given " + nearDistance + " and " + farDistance + ".")
        end
        fogColor = color
        fogStart = nearDistance
        fogEnd = farDistance
        if fogAmount <= 0
            fogAmount = 1
        end
        SetFogDirty()
    end

    /*
    This action sets the most fog anything gets, from 0 (no fog) to 1 (the
    farthest things are only the fog color).

    Attribute: Parameter amount The most fog, from 0 to 1.
    */
    action SetFogAmount(number amount)
        if amount < 0
            amount = 0
        elseif amount > 1
            amount = 1
        end
        fogAmount = amount
        SetFogDirty()
    end

    /*
    This action makes the fog thinner higher up: above the base height it
    fades by the falloff for each unit of height, so valleys are hazy and
    hilltops clear. A falloff of 0 makes the fog the same at every height,
    the default.

    Attribute: Parameter baseHeight The height below which the fog is thickest.
    Attribute: Parameter falloff How quickly the fog thins above it, 0 or more.
    */
    action SetFogHeight(number baseHeight, number falloff)
        if falloff < 0
            falloff = 0
        end
        fogBaseHeight = baseHeight
        fogHeightFalloff = falloff
        SetFogDirty()
    end

    /*
    This action turns the fog off. SetFog turns it back on.
    */
    action RemoveFog
        fogAmount = 0
        SetFogDirty()
    end

    /*
    This action returns true if there is fog.

    Attribute: Returns True if fog is on.
    */
    action HasFog returns boolean
        return fogColor not= undefined and fogAmount > 0
    end

    /*
    This action returns the fog's color.

    Attribute: Returns The fog's color, or undefined if SetFog hasn't been called.
    */
    action GetFogColor returns Color
        return fogColor
    end

    /*
    This action returns the distance where fog begins.

    Attribute: Returns The fog's start.
    */
    action GetFogStart returns number
        return fogStart
    end

    /*
    This action returns the distance where fog is thickest.

    Attribute: Returns The fog's end.
    */
    action GetFogEnd returns number
        return fogEnd
    end

    /*
    This action returns the most fog anything gets.

    Attribute: Returns The fog amount, from 0 to 1.
    */
    action GetFogAmount returns number
        return fogAmount
    end

    /*
    This action returns the height below which the fog is thickest.

    Attribute: Returns The fog's base height.
    */
    action GetFogBaseHeight returns number
        return fogBaseHeight
    end

    /*
    This action returns how quickly the fog thins above its base height.

    Attribute: Returns The fog's height falloff.
    */
    action GetFogHeightFalloff returns number
        return fogHeightFalloff
    end
```

**New private action,** after `SetSceneDataDirty`:

```
    /*
    This action marks the scene data of every frame slot to be written
    again, for a fog change. Unlike SetSceneDataDirty, the shadows don't
    need working out again (Item 40).
    */
    private action SetFogDirty
        integer i = 0
        repeat while i < sceneDataDirty:GetSize()
            sceneDataDirty:Set(i, true)
            i = i + 1
        end
    end
```

`sceneDataDirty` is empty until `Create`, so fog set before the first
frame is simply written on the first frame (every slot starts dirty).

### 2. L (`G/Shaders/Vulkan/Fragment/DefaultLightingFragmentShaderVulkan.quorum`)

**The scene data block.** The block

```glsl
layout(scalar, set = 1, binding = 1) uniform SceneInfo
{
	vec3 cameraPosition;
	float ambientIntensity;
	vec3 ambientColor;
	uint lightsCount;
	mat4 cameraViewMatrix;
} sceneInfo;
```

becomes:

```glsl
layout(scalar, set = 1, binding = 1) uniform SceneInfo
{
	vec3 cameraPosition;
	float ambientIntensity;
	vec3 ambientColor;
	uint lightsCount;
	mat4 cameraViewMatrix;
	// Distance fog (Item 40). An amount of 0 is no fog.
	vec3 fogColor;
	float fogStart;
	float fogEnd;
	float fogAmount;
	float fogBaseHeight;
	float fogHeightFalloff;
} sceneInfo;
```

**New function,** before `void main()`:

```glsl
// Fades a color into the fog by its distance from the camera, and less
// above the fog's base height (Item 40).
vec3 applyFog(vec3 color, vec3 worldPosition)
{
	if (sceneInfo.fogAmount <= 0.0)
		return color;
	float distance = length(worldPosition - sceneInfo.cameraPosition);
	float fog = smoothstep(sceneInfo.fogStart, sceneInfo.fogEnd, distance);
	if (sceneInfo.fogHeightFalloff > 0.0)
	{
		float above = max(worldPosition.y - sceneInfo.fogBaseHeight, 0.0);
		fog *= exp(-above * sceneInfo.fogHeightFalloff);
	}
	return mix(color, sceneInfo.fogColor, fog * sceneInfo.fogAmount);
}
```

**In `main`.** The lines

```glsl
    vec3 color = ambient + Lo;

	outputColor = vec4(color.rgb, rawAlbedo.a);
```

become:

```glsl
    vec3 color = ambient + Lo;
    color = applyFog(color, worldPosition);

	outputColor = vec4(color.rgb, rawAlbedo.a);
```

`worldPosition` there is already divided by coverage (Item 27), so MSAA
edges are fogged by their real distance. Sky pixels have alpha 0, so their
fogged color never shows.

### 3. Water: `W/WaterFragmentShader.quorum` (after Item 39)

**The scene data block** gets the same six fields as in L:

```glsl
layout(scalar, set = 3, binding = 1) uniform SceneInfo
{
	vec3 cameraPosition;
	float ambientIntensity;
	vec3 ambientColor;
	uint lightsCount;
	mat4 cameraViewMatrix;
	// Distance fog (library item 40). An amount of 0 is no fog.
	vec3 fogColor;
	float fogStart;
	float fogEnd;
	float fogAmount;
	float fogBaseHeight;
	float fogHeightFalloff;
} sceneInfo;
```

**The same `applyFog` function as in L,** before `void main()`.

**In `main`.** The lines

```glsl
    vec3 color = (body * opacity + glint) / max(alpha, 0.0001);
    outputColor = vec4(color, alpha);
```

become:

```glsl
    vec3 color = (body * opacity + glint) / max(alpha, 0.0001);
    // Far water fades into the fog like the land (library item 40). The
    // ground behind was already fogged by the lighting pass.
    color = applyFog(color, surface);
    outputColor = vec4(color, alpha);
```

### 4. Project: DriveOpen fog (`SourceCode/DriveOpen.quorum`)

**New `use`s:**

```
use Libraries.Game.Graphics.Environment
use Libraries.Game.Graphics.Models.Vulkan.EnvironmentVulkan
```

**New fields,** after `number nightSunIntensity = 0.08`:

```
    // Distance fog (library item 40), Vulkan only. F turns it on or off.
    // By day it matches the Day sky's horizon; by night it is nearly black.
    boolean useFog = true
    boolean fogOn = false
    boolean fWasDown = false
    number fogStart = 60
    number fogEnd = 260
```

**In `CreateGame`,** after the skybox block (`if useSkybox ... end`), add:

```
        if useFog
            SetFog(true)
        end
```

**In `Update`,** after the `nWasDown = nDown` line, add:

```
        boolean fDown = monitor:IsKeyPressed(keys:F)
        if fDown and not fWasDown
            SetFog(not fogOn)
        end
        fWasDown = fDown
```

**The night toggle.** The lines

```
            if night
                sunlight:SetIntensity(nightSunIntensity)
                output "Night: the sun is dimmed. K hides the sky for a dark background."
            else
                sunlight:SetIntensity(daySunIntensity)
                output "Day."
            end
```

become:

```
            if night
                sunlight:SetIntensity(nightSunIntensity)
                output "Night: the sun is dimmed. K hides the sky for a dark background."
            else
                sunlight:SetIntensity(daySunIntensity)
                output "Day."
            end
            // The fog's color follows the time of day.
            if fogOn
                SetFog(true)
            end
```

**New action,** after `SetHeadlights`:

```
    /*
    This action turns the distance fog on or off (library item 40). Its
    color is the Day sky's horizon by day, and nearly black by night. It
    needs Vulkan; under OpenGL it does nothing.

    Attribute: Parameter switchOn True to turn the fog on.
    */
    action SetFog(boolean switchOn)
        Environment environment = GetCurrentLayer3D():GetEnvironment()
        if not (environment is EnvironmentVulkan)
            return now
        end
        EnvironmentVulkan vulkanEnvironment = cast(EnvironmentVulkan, environment)
        fogOn = switchOn
        if not fogOn
            vulkanEnvironment:RemoveFog()
            output "Fog: off."
            return now
        end
        Color haze
        if night
            haze:SetColor(0.02, 0.025, 0.04, 1)
        else
            haze:SetColor(0.78, 0.86, 0.94, 1)
        end
        vulkanEnvironment:SetFog(haze, fogStart, fogEnd)
        vulkanEnvironment:SetFogAmount(0.85)
        output "Fog: on, from " + fogStart + " to " + fogEnd + " units. F turns it off."
    end
```

`F` is free in DriveOpen (taken: W A S D H N K R E Q P C).

### 5. Project: WaterCheck fog (`SourceCode/WaterCheck.quorum`, after Item 39)

**New `use`s:**

```
use Libraries.Game.Graphics.Environment
use Libraries.Game.Graphics.Models.Vulkan.EnvironmentVulkan
```

**New field:** `boolean fWasDown = false`.

**In `Update`,** after `mWasDown = mDown`:

```
        boolean fDown = monitor:IsKeyPressed(keys:F)
        if fDown and not fWasDown
            Environment environment = GetCurrentLayer3D():GetEnvironment()
            if environment is EnvironmentVulkan
                EnvironmentVulkan vulkanEnvironment = cast(EnvironmentVulkan, environment)
                if vulkanEnvironment:HasFog()
                    vulkanEnvironment:RemoveFog()
                    output "Water check: fog off."
                else
                    Color haze
                    haze:SetColor(0.78, 0.86, 0.94, 1)
                    // Short distances, so the pool's far side is fogged.
                    vulkanEnvironment:SetFog(haze, 10, 60)
                    output "Water check: fog on, from 10 to 60. The far side of the pool should fade, water and floor alike."
                end
            end
        end
        fWasDown = fDown
```

Add "F fog" to the label and the header's key list, and to "What to see":
"10. F: the far side of the pool and the posts fade into a pale haze;
the water fades the same as the ground beside it."

## What changes

**On screen:** nothing until a program calls `SetFog`. DriveOpen turns it
on at start (F turns it off).

**Cost:** one `length`, one `smoothstep` and one `mix` per lit pixel, and
the same per water pixel. With fog off, one comparison.

**Memory:** 32 more bytes of scene data per frame slot.

## Test plan

1. **DriveOpen:**
   - the far rings fade into the haze, and the edge of the map no longer
     shows a hard line against the sky;
   - F turns it off and on;
   - N (night) turns the fog nearly black, and N again gives the pale haze
     back;
   - the car and near ground look as before.
2. **DriveOpen with MSAA:** no halos at the edges of far hills.
3. **WaterCheck** (after Item 39): F, as above.
4. **SkyboxCheck, SpotlightCheck, TerrainWalk:** no change (no fog set).
5. **With the validation layer, if available:** no uniform-size mismatch
   messages for set 1, binding 1.

## Rollback

Revert the library changes in E and L, the water shader's section 3, and
DriveOpen's and WaterCheck's fog lines.
