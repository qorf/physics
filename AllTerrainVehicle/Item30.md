# Item 30: shadows after the 3D passes are remade

**Approved and applied on 2026-10-19** (uncommitted, with Items 27-29).
**Waiting for a library rebuild and a run.** Vulkan only,
one file: `Graphics/Vulkan/VulkanPainter3D.quorum`, on `TerrainShader`.
Path is under `quorum-language/Quorum/Library/Standard/Libraries/Game/`.

## The problem

Reported by the user (2026-10-19): with 3D MSAA on, resizing the window
turns every lit model black and stops it rendering. The sky still shows.

It isn't MSAA. It happens whenever `RegenerateRenderPasses` runs a second
time, which before Item 28 never happened. Now it runs on a resize (Item 28)
and when a sample count changes (Items 27 and 29). Each time it makes **new
descriptor sets** for the lighting pass's shadow data (set 2:
`lightShadowDataDescriptors`), and for the shadow pass
(`shadowProjectionDescriptors`). Two things that should fill them never run
again:

1. **The cascade matrices.** `Begin` links the shadow projection buffers
   into both kinds of set only `if not shadowProjectionResourcesLinked`.
   That flag is set to true the first time and never cleared.
2. **The shadow maps.** They are linked into the lighting sets only in
   `EnsureShadowCubemapFramebuffers`, as each light's shadow framebuffer is
   made. That action returns early once every light has a framebuffer.
   `RegenerateRenderPasses` tries to throw the old framebuffers away, but
   its loop walks a new empty array instead of the real ones
   (`Array<VulkanFramebuffer> framebuffers` rather than
   `shadowCubemapFramebuffers:Get(counter)`), so nothing is thrown away and
   nothing is linked again.

The lighting pass then reads unlinked shadow data. MoltenVK returns zeros,
or values that turn into NaN, so every lit pixel comes out black. The sky is
drawn in the result pass without lighting, so it still shows.

## The fix

- **Clear the flag** when the descriptor sets are remade, so `Begin` links
  the projection buffers into the new sets.
- **Remember each light's shadow map view,** and link the ones that exist
  into the new lighting sets after they're made.

The shadow maps and their framebuffers don't depend on the window's size,
so they are **kept, not remade.** Remaking them on every resize step would
waste time, and leak large images, since nothing frees them. Their
framebuffers were made with the old shadow render pass. The new one is
identical, so they stay compatible.

The broken disposal loop is left as it is. It does nothing, and with this
fix nothing needs it. Making it dispose the framebuffers would force the
maps to be remade, and leaked.

## The code

### New field

After `Array<Array<VulkanFramebuffer>> shadowCubemapFramebuffers`:

```
    // For each frame slot, each light's shadow map view, in light order,
    // so the maps can be linked into new lighting descriptor sets when the
    // passes are made again (Item 30).
    Array<Array<VulkanImageView>> shadowMapViews
```

### `EnsureShadowCubemapFramebuffers`

The linking at the end of the loop, from
`// Also link up the shadow stage attachment as a descriptor input to the lighting stage.`
through `shadowProjectionSet:LinkResources(shadowOutputResources)`, becomes:

```
            // Remember the map, and link it into the lighting stage's
            // descriptor set (Item 30).
            repeat while shadowMapViews:GetSize() <= resourceIndex
                Array<VulkanImageView> views
                shadowMapViews:Add(views)
            end
            shadowMapViews:Get(resourceIndex):Add(shadowImageView)
            LinkShadowMap(resourceIndex, i, shadowImageView)
```

### `RegenerateRenderPasses`

At the end, before `return true`:

```
        // The descriptor sets above are new. Link the shadow projection
        // buffers into them again (Begin does it while this is false), and
        // the shadow maps that already exist (Item 30).
        shadowProjectionResourcesLinked = false
        integer slot = 0
        repeat while slot < shadowMapViews:GetSize() and slot < lightShadowDataDescriptors:GetSize()
            Array<VulkanImageView> views = shadowMapViews:Get(slot)
            integer light = 0
            repeat while light < views:GetSize()
                LinkShadowMap(slot, light, views:Get(light))
                light = light + 1
            end
            slot = slot + 1
        end
```

### New private action

```
    /*
    This action links one light's shadow map into a frame slot's lighting
    descriptor set (set 2, binding 1, at the light's place in the array).

    Attribute: Parameter resourceIndex The frame slot.
    Attribute: Parameter lightIndex The light's place.
    Attribute: Parameter view The light's shadow map view.
    */
    private action LinkShadowMap(integer resourceIndex, integer lightIndex, VulkanImageView view)
        VulkanConstants constants
        VulkanDescriptorSet shadowProjectionSet = lightShadowDataDescriptors:Get(resourceIndex)

        VulkanDescriptorResourcesInfo shadowOutputResources
        VulkanDescriptorImageInfo shadowOutputInfo
        shadowOutputInfo:SetImageView(view)
        shadowOutputInfo:SetSampler(shadowSampler)
        shadowOutputInfo:SetImageLayout(constants:IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL)
        Array<VulkanDescriptorImageInfo> shadowOutputImages
        shadowOutputImages:Add(shadowOutputInfo)
        shadowOutputResources:SetImageInfo(shadowOutputImages)
        shadowOutputResources:SetDescriptorType(constants:DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER)
        shadowOutputResources:SetDestinationBinding(1)
        shadowOutputResources:SetDestinationArrayElement(lightIndex)
        shadowProjectionSet:LinkResources(shadowOutputResources)
    end
```

## What changes

- **The first time,** nothing changes: the same links, made through
  `LinkShadowMap`.
- **After a resize or a sample count change,** shadows and lighting work
  again, with or without MSAA.

## Test plan

1. **DriveOpen, MSAA off:** resize the window. Models stay lit and shadowed.
2. **MSAACheck at 4:** resize, and press M through every count. Models stay
   lit, with shadows.
3. **MSAA2DCheck:** step N and M, and resize.
4. **A scene with more lights** (point lights) after a resize: every
   light's shadows still show.

## Rollback

Revert the Item 30 changes in `VulkanPainter3D.quorum` and rebuild the
library.
