# Item 28: the 3D view after a window resize

**Approved and applied on 2026-10-19** (uncommitted, together with Item 27).
**Waiting for a library rebuild and a run.** Vulkan only,
one file: `Graphics/Vulkan/VulkanPainter3D.quorum`, on the
`quorum-language` branch `TerrainShader`. Path is under
`quorum-language/Quorum/Library/Standard/Libraries/Game/`.

## The problem

The user confirmed it (2026-10-19): after resizing the window, DriveOpen's
3D view is blurry.

- **What resizing does:** `VulkanGraphics:RegenerateSwapchain` makes a new
  swapchain at the new size, with its depth image and framebuffers.
- **What it misses:** nothing tells `VulkanPainter3D`. Its render passes
  stay "valid", so `RegenerateRenderPasses` never runs again. The G-buffer
  (position, albedo, normals, PBR), its depth, the lighting images, and
  with MSAA the multisampled images all stay **at the size the window first
  had**.
- **The result:**
  - the result pass stretches the old-size lit image over the new window
    (blurry when bigger, lost detail when smaller);
  - the scene pass's render area (the swapchain's size) can be larger than
    its framebuffers, which Vulkan doesn't allow (it happens to survive on
    MoltenVK).

## The fix

1. **The painter remembers the size** its framebuffers were made at. In
   `Begin`, if the swapchain's size differs, or the MSAA count changed
   (Item 27's existing check), it waits for the device and remakes its
   passes and framebuffers. That is the same path Item 27 uses.
2. **It frees the old images** when it remakes them. Today
   `RegenerateRenderPasses` disposes the old framebuffers, but never the
   images and views behind them. Each image it makes (G-buffer, depth,
   lighting, MSAA) is now kept in a list, and released when the
   framebuffers are. Without this, dragging a window edge (dozens of sizes
   in a second) would leak a few hundred megabytes per step.

   Render passes are still let go rather than disposed
   (`VulkanRenderPass:Dispose` isn't written); they are tiny.

Shadow maps don't depend on the window's size, and are left alone.

## The code

### New fields

After `integer sceneSampleCount = 1` (Item 27):

```
    // The swapchain size the framebuffers below were made at. When the
    // window is resized, the swapchain changes size and Begin makes them
    // again (Item 28).
    integer framebufferWidth = 0
    integer framebufferHeight = 0

    // Every image, and its view, made for those framebuffers (G-buffer,
    // depth, lighting, MSAA), so they can be freed when they are made again.
    Array<VulkanImage> sizedImages
    Array<VulkanImageView> sizedImageViews
```

### `Begin`

Item 27's block

```
        // If the game's MSAA sample count changed since the passes were
        // made, make them again (Item 27). Earlier frames may still be using
        // the old framebuffers, so wait for the device first. The old passes
        // are let go rather than disposed, since VulkanRenderPass:Dispose
        // isn't written yet.
        if AreRenderPassesValid() and graphics:GetUsableMultisampleCount() not= sceneSampleCount
            graphics:GetDevice():WaitUntilIdle()
            sceneRenderPass = undefined
            shadowRenderPass = undefined
            lightRenderPass = undefined
            resultRenderPass = undefined
        end
```

becomes

```
        // If the window was resized (Item 28), or the game's MSAA sample
        // count changed (Item 27), since the passes and framebuffers were
        // made, make them again at the swapchain's size. Earlier frames may
        // still be using the old framebuffers, so wait for the device first.
        // The old passes are let go rather than disposed, since
        // VulkanRenderPass:Dispose isn't written yet; their framebuffers and
        // images are freed in RegenerateRenderPasses.
        if AreRenderPassesValid()
            VulkanSwapchain currentSwapchain = graphics:GetSwapchain()
            boolean resized = currentSwapchain:GetImageWidth() not= framebufferWidth or
                currentSwapchain:GetImageHeight() not= framebufferHeight
            if resized or graphics:GetUsableMultisampleCount() not= sceneSampleCount
                graphics:GetDevice():WaitUntilIdle()
                sceneRenderPass = undefined
                shadowRenderPass = undefined
                lightRenderPass = undefined
                resultRenderPass = undefined
            end
        end
```

### `RegenerateRenderPasses`

**After the old framebuffers are disposed** (after the
`lightFramebuffers` loop, before `integer counter = 0`):

```
        // The images behind those framebuffers go too (Item 28).
        ReleaseSizedImages()
```

**Each image made for the framebuffers is kept.**

- After `positionImageView:Create(device, positionImage, positionImageViewInfo)`:

  ```
                  KeepSizedImage(positionImage, positionImageView)
  ```

- In the G-buffer loop, after `imageView:Create(device, image, imageViewInfo)`:

  ```
                  KeepSizedImage(image, imageView)
  ```

- In the depth branch (MSAA off), after
  `depthImageView:Create(device, depthImage, depthViewInfo)`:

  ```
                  KeepSizedImage(depthImage, depthImageView)
  ```

- In the lighting image block, after
  `imageView:Create(device, image, imageViewInfo)`:

  ```
                  KeepSizedImage(image, imageView)
  ```

- In `MakeMultisampledView` (Item 27), after `view:Create(device, image, viewInfo)`:

  ```
          KeepSizedImage(image, view)
  ```

**The size is remembered,** right after
`integer swapchainHeight = swapchain:GetImageHeight()`:

```
        framebufferWidth = swapchainWidth
        framebufferHeight = swapchainHeight
```

### New private actions

```
    /*
    This action remembers an image, and its view, made for the painter's
    framebuffers, so ReleaseSizedImages can free them when the framebuffers
    are made again (Item 28).

    Attribute: Parameter image The image.
    Attribute: Parameter view Its view.
    */
    private action KeepSizedImage(VulkanImage image, VulkanImageView view)
        sizedImages:Add(image)
        sizedImageViews:Add(view)
    end

    /*
    This action frees every image, and view, made for the painter's
    framebuffers: views first, then images. It is called once the
    framebuffers using them are gone, after the device has finished with
    them (Begin waits for it).
    */
    private action ReleaseSizedImages
        integer i = 0
        repeat while i < sizedImageViews:GetSize()
            sizedImageViews:Get(i):Dispose()
            i = i + 1
        end
        i = 0
        repeat while i < sizedImages:GetSize()
            sizedImages:Get(i):Dispose()
            i = i + 1
        end
        sizedImageViews:Empty()
        sizedImages:Empty()
    end
```

## What changes

- **Resizing:** the 3D view is remade at the new size and is sharp. A short
  pause on each size change while the device goes idle. While dragging an
  edge, that's a few small hitches.
- **MSAA changes** (Item 27) now also free the old images.
- **Nothing else:** no change while the size and the sample count stay the
  same.

## Risks

- **Freeing images:** `VulkanImage:Dispose` and `VulkanImageView:Dispose`
  are used here on images for the first time. They run only after
  `WaitUntilIdle` and after the framebuffers are disposed, so nothing in
  flight uses them.
- **Descriptor sets** for lighting and the result pass are linked to the
  new views every time `RegenerateRenderPasses` runs. That code is
  unchanged, so they never point at freed views.
- **Several 3D layers:** each painter checks its own size and remakes its
  own images.
- **A minimized window** (size 0): `Begin` already returns early while
  rendering is paused, before this check.

## Test plan

1. **DriveOpen:** resize the window larger and smaller, and maximize and
   restore it. The 3D view stays sharp and fills the window. Shadows,
   splatting and the sky are unchanged.
2. **MSAACheck:** the same with 4 samples, then step M a few times. No
   errors, and memory doesn't keep growing (Activity Monitor).
3. **TerrainEditor:** resize, then check that the brush follows the mouse.
4. **Minimize and restore** in DriveOpen: no crash (#23 still holds).

## Rollback

Revert `VulkanPainter3D.quorum`'s Item 28 changes and rebuild the library.
