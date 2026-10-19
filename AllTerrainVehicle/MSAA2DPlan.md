# MSAA for 2D under Vulkan (investigation)

**Status (2026-10-19): done** as `Item29.md` (option A), committed in `7ad442acb`.

Written 2026-10-19, for review, after Item 27 (MSAA for the 3D scene
pass). **Vulkan only; OpenGL is not touched.** Nothing is changed.

The resize problem noted below was confirmed (blurry after a resize) and
is fixed in `Item28.md`. **Option A, with a separate
`Game:SetMultisampling2D`, is applied as `Item29.md` (2026-10-19), waiting
for a run with `MSAA2DCheck.quorum`.**

Paths are under
`quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/`.

## Short answer

2D MSAA is possible, and one design covers every case, including 2D drawn
over 3D. But **in Quorum it would smooth fewer edges than you might
expect.** Most 2D edges are either baked into textures or computed in
shaders, and MSAA smooths neither. What it does smooth is the outer edges of
quads that are turned or scaled: sprites, images, rectangles and buttons at
an angle. I'd only do it if turned 2D items matter to a game. Details below.

## How 2D draws today

- `Vulkan/VulkanPainter2D.quorum` draws straight into the **swapchain
  image**, through `VulkanGraphics`'s framebuffers (`GetCurrentFramebuffer`),
  which hold the swapchain image and one depth image.
- **The 3D painter's result pass** (the lit image and the sky, Item 26)
  draws into the same framebuffers. Every pass that uses them must be
  compatible with `VulkanGraphics`'s render pass: the same attachments,
  formats and sample counts.
- **Layers stack in one swapchain image:**
  - the first layer's pass clears it;
  - every later layer's pass loads it (`ATTACHMENT_LOAD_OP_LOAD`) and draws
    on top. A 2D HUD over 3D is a later layer.
- **On a window resize,** `VulkanGraphics:RegenerateSwapchain` remakes the
  swapchain, its depth image and its framebuffers.
- **The 2D blend state** (`EnableDefaultTransparency`) blends color by alpha,
  but writes the source's alpha straight in (alpha factors ONE and ZERO).
- **2D pipelines** are made with `CreatePipeline(renderPass)` (line 601), so
  after Item 27 they already take their pass's sample count.

## What MSAA can and can't smooth in Quorum's 2D

| Edge | How it is made | Smoothed by MSAA? |
|---|---|---|
| Outer edge of a sprite, image or rectangle, turned or scaled | the quad's triangles | **Yes** |
| Same, straight and at its own size | pixel-aligned triangles | No change (already crisp) |
| Circles, triangles, lines (`LoadFilledCircle` and others) | drawn into a texture, then shown on a quad | **No**: the edge is inside the texture |
| Text | glyph textures with smooth edges | No (already smooth) |
| Controls, patterns, charts (`ControlFragmentShaderVulkan` and others) | computed in the fragment shader, most with `smoothstep` | No (already smooth) |

So MSAA helps 2D games that turn or scale sprites and panels. For
everything else, the edge has to be smoothed where it's made: in the texture
or the shader.

## Options

| Option | How | Covers | Cost | Verdict |
|---|---|---|---|---|
| **A. Multisample the whole swapchain stage** | `VulkanGraphics`'s framebuffers gain one multisampled color image and a multisampled depth image; every pass on them (2D, and 3D's result pass) draws into the multisampled image and resolves into the swapchain image as it ends | Every layer, including 2D over 3D | Memory: 4× color plus depth ≈ 32 bytes a pixel, about 66 MB at 1080p with one shared set (about none on Apple GPUs). Bandwidth: the multisampled image is stored and loaded between layers in a frame | **Recommended, if 2D MSAA is wanted** |
| B. First layer only | Only a 2D layer that clears the screen gets MSAA | Pure 2D games only, not a HUD over 3D | Smaller | Partial; two code paths |
| C. Draw 2D offscreen, then composite | 2D into a cleared multisampled image, resolved, then blended over the swapchain | Every layer | Needs every 2D program's alpha blending changed (ONE, ONE_MINUS_SRC_ALPHA), which changes the swapchain's alpha | Not recommended |
| D. `VK_EXT_multisampled_render_to_single_sampled` | The driver loads and resolves a single-sample image behind the scenes | Every layer | Small | **Not available on MoltenVK** (not in its extension list), so not an option on the Mac |

### Option A in more detail

- **One multisampled color image** at the swapchain's size and format, and
  **one multisampled depth image.** Both are shared by every swapchain image
  and made by `VulkanGraphics`.
- **`VulkanGraphics`'s render pass and framebuffers:** attachments are the
  swapchain image (the resolve target), the multisampled color, and the
  multisampled depth.
- **Each pass that draws on them** (`VulkanPainter2D`, and `VulkanPainter3D`'s
  result pass):
  - **The multisampled color:**
    - load op `CLEAR` for the first layer, `LOAD` for later ones;
    - store op `STORE`, so the next layer can load it.
  - **The swapchain image:** load `DONT_CARE`, store `STORE`, resolved into
    at the end of each pass.
  - **Depth:** multisampled, cleared per pass as now.
- **Later layers load the multisampled image,** not the single-sample
  swapchain image, so stacking works as today. This is what makes A cover
  2D over 3D, and why B and C have trouble.
- **Pipelines:** 2D programs, and the 3D copy and sky programs, follow the
  pass's sample count automatically (Item 27). They're remade when the
  count changes, like Item 27's scene pipelines (a `NeedsPipeline` check at
  `VulkanPainter2D` line 601 and in the result pass).
- **Turning it on or off,** or resizing: `VulkanGraphics` remakes the
  images and framebuffers, as `RegenerateSwapchain` already does, and the
  painters remake their passes.
- **The switch:**
  - either `Game:SetMultisampling` covers both 3D and 2D;
  - or a separate `Game:SetMultisampling2D`, since the costs and gains
    differ (decision 2).
- **Size:** about 150 to 200 lines in `VulkanGraphics`, `VulkanPainter2D`
  and `VulkanPainter3D`'s result pass. No Java, no OpenGL.

### Bandwidth note

The guide's best practice (transient multisampled images, resolved and
never stored) only fully works when one pass draws everything. With
several layers, the multisampled color has to be stored between them. On
tile-based GPUs that costs a write and a read of a 4× image per extra
layer. A typical game has one 3D layer and one 2D layer, so that's one
extra. It's modest, but it is why this would be its own switch.

## Something noticed while reading (3D, existing)

`RegenerateSwapchain` remakes `VulkanGraphics`'s framebuffers on a resize,
but nothing tells `VulkanPainter3D` to remake its G-buffer framebuffers.
Their passes stay "valid", so they are only made once, at the first size.

- **If so, after a resize:**
  - the G-buffer stays at the old size;
  - the 3D image may be cropped or stretched;
  - with Item 27, the multisampled images too.
- **Worth one check:** run DriveOpen, resize the window, and see whether the
  3D view still fills it correctly. If not, it's a small fix: the painter
  compares the swapchain's size with the size its framebuffers were made at,
  in `Begin`, and remakes them. That also covers Item 27's images. I can
  write it as its own item.

## Open decisions for the user

1. **Do 2D MSAA at all?** It's worth it if games turn or scale sprites and
   panels. Otherwise, smoother 2D shapes come from smoother textures
   (`LoadFilledCircle` and others), which are shared with OpenGL and would be
   a separate discussion.
2. **If yes, option A,** with a separate `Game:SetMultisampling2D`
   (recommended)? Or one switch for both 3D and 2D?
3. **The resize check** above: run it first, and fix it as its own item if
   needed?
