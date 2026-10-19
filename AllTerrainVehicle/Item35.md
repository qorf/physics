# Item 35: shadow maps

**Status (2026-10-19): plan, for review.** Nothing is applied yet. It
needs Item 31 (`Retire`). It is the shadow part of `MemoryPlan.md` section
5, with the recommended answer to decision 5: directional lights get
`cascades` layers. Sharing one set of maps across frame slots is not done
here; it is left to measure later.

Vulkan only, on `TerrainShader`. Paths are as in `Item31.md`. **SV/** is
`Quorum/Library/Standard/Libraries/Game/Graphics/Shaders/Vulkan/`, and
**MV/** is `.../Graphics/Models/Vulkan/`.

## Today

`VulkanPainter3D:EnsureShadowCubemapFramebuffers` gives every light place
(directional lights first, then point lights), in every frame slot:
- a color map: `RG32F`, 8 bytes a pixel;
- a depth map: `D32`, 4 bytes a pixel.

Each has `6 × cascades` layers of `shadowMapSize²`. **At the defaults**
(`DesktopConfiguration`: 2048, 3 cascades) **with 3 frame slots:**

| | Layers | Per slot | All 3 slots |
|---|---|---|---|
| Any light today | 18 | 576 MB + 288 MB = 864 MB | **2.6 GB** |
| A directional light after this Item | 3 | 96 MB + 48 MB = 144 MB | **432 MB** |
| A point light (unchanged) | 18 | 864 MB | 2.6 GB |

**Directional lights use only 1 face in 6.**
- The geometry shader writes `gl_Layer = cascade × 6 + face`, and loops
  one face for them (`mapSize = 1 + isPoint × 5`).
- The lighting shader reads layer `6 × cascade`.
- So five sixths of a sun's maps are made, cleared every frame, and never
  read.

**Maps are never freed.** When lights are removed, the places past the new
count keep their maps, and the shadow pass still clears them every frame
(the barrier loop runs over every framebuffer).

**Two bugs in `EnvironmentVulkan` overflow or misreport:**
- **`cascadeShadowTransferArray`** is sized `SHADOW_DATA_WORD_SIZE ×
  maxLights`. But it is filled with `lights × cascades` entries, so with 3
  cascades it overflows past a third of the maximum lights. The loop also
  doesn't stop at `maxLights`. The GPU buffer is already sized with the
  cascade count.
- **With no ambient light,** the fallback color writes red three times to
  the same index. Green and blue keep whatever was there before.

**Not in this Item.** Cascade snapping (`row3column1`) and
`lastSplitDistance` (#14 and the TerrainWalk notes) change how shadows
look, so they stay their own Item.

## The design

**Each light place's map is sized for the light now there:**
- `cascades` layers for a directional light;
- `6 × cascades` for a point light.

`EnsureShadowMaps` (renamed from `EnsureShadowCubemapFramebuffers`) runs
every frame for the frame's slot:
- **A place with no map** gets one.
- **A place whose map has the wrong layer count** (the place changed
  between a directional and a point light) gets a new map. The old
  framebuffer, both views and both images are retired.
- **Places past the light count** are freed, once they have been unused
  for 180 calls in a row. That is 60 frames per slot with 3 slots, about a
  second. So a light switched off and on doesn't remake its maps every
  time.
- **New maps are linked** into the lighting set at their place, and
  remembered in `shadowMapViews` (Item 30).
- **Freed places stay linked to their retired views.** The binding is
  partially bound (`DESCRIPTOR_BINDING_DYNAMIC`), and the lighting shader
  only reads places below the light count, so they're never read.

**The shaders choose the layer by light type.** Point lights are
unchanged.
- **Shadow geometry shader:** `gl_Layer = gl_InvocationID * (1 + isPoint * 5) + i`.
  For directional lights `i` is 0, so the layer is the cascade.
- **Two-stage shadow vertex shader** (no geometry shaders):
  `gl_Layer = int(targetCascade * (1 + pushConstants.isPointLight * 5) + targetFace)`.
  It already receives `isPointLight`.
- **Lighting fragment shader:** directional lights read
  `vec3(uv, cascadeIndex)`, not `6 * cascadeIndex`.

## The code

### `G/VulkanPainter3D.quorum`

**New field,** after `shadowMapViews`:

```
    // How many calls in a row the current slot had more shadow maps than
    // lights. Past SHADOW_MAP_KEEP_CALLS, the extra maps are freed (Item 35).
    integer extraShadowMapCalls = 0
    constant integer SHADOW_MAP_KEEP_CALLS = 180
```

**The call site.** `EnsureShadowCubemapFramebuffers(resourceIndex)` (in
`End`) becomes `EnsureShadowMaps(resourceIndex)`.

**The action itself.** `EnsureShadowCubemapFramebuffers` is replaced by:

```
    /*
    This action makes sure the frame slot has a shadow map, with its
    framebuffer, for each light, sized for the light's type: one layer per
    cascade for a directional light, six per cascade for a point light.
    Maps that no longer fit their light are replaced, and maps past the
    light count are freed once unused for a while. Old maps are freed when
    no frame still draws with them (Item 35).

    Attribute: Parameter resourceIndex The frame slot.
    */
    private action EnsureShadowMaps(integer resourceIndex)
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        VulkanLightingProperties lightProperties = graphics:GetLightingProperties()
        integer cascades = lightProperties:GetShadowMapCascadeCount()

        integer directionalCount = environment:GetDirectionalLightCount()
        integer totalLights = directionalCount + environment:GetPointLightCount()
        if totalLights > environment:GetMaxLights()
            totalLights = environment:GetMaxLights()
        end

        repeat while shadowMapViews:GetSize() <= resourceIndex
            Array<VulkanImageView> views
            shadowMapViews:Add(views)
        end
        Array<VulkanFramebuffer> framebuffers = shadowCubemapFramebuffers:Get(resourceIndex)
        Array<VulkanImageView> views = shadowMapViews:Get(resourceIndex)

        integer i = 0
        repeat while i < totalLights
            integer layers = cascades * 6
            if i < directionalCount
                layers = cascades
            end
            if i >= framebuffers:GetSize()
                VulkanFramebuffer made = MakeShadowMap(layers)
                framebuffers:Add(made)
                views:Add(made:GetImageViews():Get(0))
                LinkShadowMap(resourceIndex, i, made:GetImageViews():Get(0))
            else
                VulkanFramebuffer existing = framebuffers:Get(i)
                if existing:GetImageViews():Get(0):GetInfo():GetLayerCount() not= layers
                    RetireShadowMap(existing, graphics)
                    VulkanFramebuffer remade = MakeShadowMap(layers)
                    framebuffers:Set(i, remade)
                    views:Set(i, remade:GetImageViews():Get(0))
                    LinkShadowMap(resourceIndex, i, remade:GetImageViews():Get(0))
                end
            end
            i = i + 1
        end

        if framebuffers:GetSize() > totalLights
            extraShadowMapCalls = extraShadowMapCalls + 1
            if extraShadowMapCalls >= SHADOW_MAP_KEEP_CALLS
                repeat while framebuffers:GetSize() > totalLights
                    RetireShadowMap(framebuffers:RemoveFromEnd(), graphics)
                    views:RemoveFromEnd()
                end
            end
        else
            extraShadowMapCalls = 0
        end
    end

    /*
    This action makes one shadow map: a color image (the depth moments)
    and a depth image, each with the given number of layers, their views,
    and a framebuffer for the shadow pass. The color view comes first in
    the framebuffer.

    Attribute: Parameter layers How many layers each image has.
    Attribute: Returns The framebuffer.
    */
    private action MakeShadowMap(integer layers) returns VulkanFramebuffer
        VulkanConstants constants
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        VulkanDevice device = graphics:GetDevice()
        integer size = graphics:GetLightingProperties():GetShadowMapSize()

        VulkanImageInfo colorInfo
        colorInfo:SetWidth(size)
        colorInfo:SetHeight(size)
        colorInfo:SetFormat(constants:FORMAT_R32G32_SFLOAT)
        colorInfo:SetUsage(constants:IMAGE_USAGE_COLOR_ATTACHMENT_BIT + constants:IMAGE_USAGE_SAMPLED_BIT)
        colorInfo:SetArrayLayers(layers)
        VulkanImage colorImage
        colorImage:Create(device, colorInfo)
        VulkanImageViewInfo colorViewInfo
        colorViewInfo:SetFormat(colorInfo:GetFormat())
        colorViewInfo:SetViewType(constants:IMAGE_VIEW_TYPE_2D_ARRAY)
        colorViewInfo:SetLayerCount(layers)
        VulkanImageView colorView
        colorView:Create(device, colorImage, colorViewInfo)

        VulkanImageInfo depthInfo
        depthInfo:SetWidth(size)
        depthInfo:SetHeight(size)
        depthInfo:SetUsage(constants:IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT)
        depthInfo:SetFormat(constants:FORMAT_D32_SFLOAT)
        depthInfo:SetArrayLayers(layers)
        VulkanImage depthImage
        depthImage:Create(device, depthInfo)
        VulkanImageViewInfo depthViewInfo
        depthViewInfo:SetAspectMask(constants:IMAGE_ASPECT_DEPTH_BIT)
        depthViewInfo:SetFormat(depthInfo:GetFormat())
        depthViewInfo:SetViewType(constants:IMAGE_VIEW_TYPE_2D_ARRAY)
        depthViewInfo:SetLayerCount(layers)
        VulkanImageView depthView
        depthView:Create(device, depthImage, depthViewInfo)

        Array<VulkanImageView> attachments
        attachments:Add(colorView)
        attachments:Add(depthView)
        VulkanFramebuffer framebuffer
        framebuffer:Create(device, attachments, shadowRenderPass)
        return framebuffer
    end

    /*
    This action frees a shadow map's framebuffer, views and images once no
    frame on the GPU still uses them.

    Attribute: Parameter framebuffer The shadow map's framebuffer.
    Attribute: Parameter graphics The Vulkan graphics.
    */
    private action RetireShadowMap(VulkanFramebuffer framebuffer, VulkanGraphics graphics)
        Array<VulkanImageView> attachments = framebuffer:GetImageViews()
        graphics:Retire(framebuffer)
        integer i = 0
        repeat while i < attachments:GetSize()
            VulkanImageView view = attachments:Get(i)
            graphics:Retire(view)
            graphics:Retire(view:GetImage())
            i = i + 1
        end
    end
```

**What carries over:**
- The framebuffer is made with the current `shadowRenderPass`, as before.
  Passes made again by Item 32 are identical, so maps stay compatible
  across a resize, as Item 30 relies on.
- `VulkanFramebuffer.java` sets the framebuffer's layers to its views'
  largest layer count, so a 3-layer map gets a 3-layer framebuffer.
- **The barrier loop after the shadow pass** (`repeat while i <
  shadowFramebuffers:GetSize()`, `AttachmentWriteBarrier`) is unchanged.
  It now also covers extra maps waiting to be freed, which is harmless.

### `SV/Geometry/DefaultShadowGeometryShaderVulkan.quorum`

In the shader text,

```
				gl_Layer = gl_InvocationID * 6 + i;
```

becomes:

```
				// Point lights have six layers per cascade, one per face.
				// Directional lights have one per cascade (Item 35).
				gl_Layer = int(gl_InvocationID * (1 + isPoint * 5) + i);
```

The comments above it, "Output to the first face of each cubemap and
ignore the other 5", become "Output to the cascade's one layer."

### `SV/Vertex/TwoStageShadowVertexShaderVulkan.quorum`

```
	gl_Layer = int(targetCascade * 6 + targetFace);
```

becomes:

```
	// Six layers per cascade for a point light, one for a directional
	// light (Item 35).
	gl_Layer = int(targetCascade * (1 + pushConstants.isPointLight * 5) + targetFace);
```

### `SV/Fragment/DefaultLightingFragmentShaderVulkan.quorum`

In `calculateDirectionalVisibility`,

```
	vec2 moments = texture(nonuniformEXT(shadowSamplers[lightIndex]), vec3(uv, 6 * cascadeIndex)).rg;
```

becomes:

```
	// A directional light's map has one layer per cascade (Item 35).
	vec2 moments = texture(nonuniformEXT(shadowSamplers[lightIndex]), vec3(uv, cascadeIndex)).rg;
```

`calculatePointVisibility` is unchanged (`6 * cascadeIndex + targetFace`).

**The shadow fragment shaders** (`DefaultShadowFragmentShaderVulkan`,
`TwoStageShadowFragmentShaderVulkan`) only write moments and don't name
layers. A search of every Vulkan shader for `6 *` and `* 6` (2026-10-19)
finds only the four lines above, so nothing else needs changing.

### `MV/EnvironmentVulkan.quorum`

**`Create`.** The line
`cascadeShadowTransferArray:SetSize(SHADOW_DATA_WORD_SIZE * maxLights)`
becomes:

```
        // Every light has one entry per cascade (Item 35).
        cascadeShadowTransferArray:SetSize(SHADOW_DATA_WORD_SIZE * maxLights * lightingProperties:GetShadowMapCascadeCount())
```

**The shadow data loop.** In the frame update that fills it,
`repeat while i < directionalLights:GetSize() + pointLights:GetSize()`
becomes:

```
        integer shadowLightCount = directionalLights:GetSize() + pointLights:GetSize()
        if shadowLightCount > maxLights
            shadowLightCount = maxLights
        end
        repeat while i < shadowLightCount
```

**The ambient fallback.** The six lines writing
`AMBIENT_LIGHT_COLOR_INDEX` with 1.0 or 0.0 become:

```
                if pointLights:IsEmpty() and directionalLights:IsEmpty()
                    sceneDataMappingArray:Set(AMBIENT_LIGHT_COLOR_INDEX, 1.0)
                    sceneDataMappingArray:Set(AMBIENT_LIGHT_COLOR_INDEX + 1, 1.0)
                    sceneDataMappingArray:Set(AMBIENT_LIGHT_COLOR_INDEX + 2, 1.0)
                else
                    sceneDataMappingArray:Set(AMBIENT_LIGHT_COLOR_INDEX, 0.0)
                    sceneDataMappingArray:Set(AMBIENT_LIGHT_COLOR_INDEX + 1, 0.0)
                    sceneDataMappingArray:Set(AMBIENT_LIGHT_COLOR_INDEX + 2, 0.0)
                end
```

**Who sees a change.** Only scenes with no `AmbientLight` see a
difference:
- **with no lights at all,** they now get full white for all three
  channels, as the comment says;
- **with lights,** green and blue are now zero as intended.

The array starts at zero, so today those scenes read red-only ambient
(1, 0, 0) with no lights, which is the visible bug.

## What changes on screen

**Shadows from directional and point lights look the same.** They read
the same data from fewer, smaller layers.

**Memory drops sharply:**
- **One sun at the defaults:** 2.6 GB → 432 MB.
- **Removing lights** frees their maps after about a second.
- **A scene with no lights and no ambient light** (unusual) now shows
  white rather than red. Scenes with no `AmbientLight` but with lights
  lose a stray green and blue ambient term.

## Test plan

1. **MemoryCheck, new key S.** It adds a directional light, then a point
   light, then removes both, one step every 3 seconds.
   - The report shows about +144 MB per slot for the sun and +864 MB for
     the point light, then back down a second or so after removal.
   - This checks the expected sizes on the Mac's 3 slots.
2. **MSAACheck, TerrainWalk, DriveOpen.** The sun's shadows are unchanged,
   at all three cascade distances (move the camera near and far). Resize
   still works (Item 30).
3. **A point light scene** (a check with `PointLight`, or MemoryCheck S
   with a box near the light): shadows on all six sides.
4. **Swapping light types.** Remove the sun and add a point light (so
   place 0 changes type). Shadows are right on the next frames, and
   memory reflects the new sizes.
5. **Both shadow paths.** The Mac has no geometry shaders under MoltenVK,
   so it uses the two-stage path. Where possible, a Windows or Linux run
   checks the geometry shader path.
6. **Six or more lights with 3 cascades.** No crash (the array overflow
   fix).

## Rollback

Revert the Item 35 changes in the files above, including the three
shaders.
