# MSAA for the Vulkan renderer (plan)

**Status (2026-10-19): done** as `Item27.md`, committed in `7ad442acb`.

Written 2026-10-19. **Approved with the recommended answers; the exact code
is in `Item27.md`.** **Vulkan only; OpenGL is not touched.** It
can be turned on or off. Nothing is changed yet; once the design is settled,
the exact code goes in an `ItemN.md` (Item 27) for review.

Source: the Khronos sample "MSAA (Multisample anti-aliasing)",
https://docs.vulkan.org/samples/latest/samples/performance/msaa/README.html

Paths are under
`quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/`.

## What the guide recommends

- **MSAA** tests coverage at several points per pixel (4 is the sweet
  spot), but runs the fragment shader **once per pixel**. Edges get smooth
  steps, at far less cost than supersampling. It doesn't smooth the inside
  of a triangle; mipmaps (Item 25) do that.
- **Turn it on:**
  1. pick a sample count the device supports
     (`VkPhysicalDeviceLimits::framebufferColorSampleCounts` and
     `framebufferDepthSampleCounts`);
  2. make the attachments with that count;
  3. set `rasterizationSamples` in each pipeline that draws into them.
- **Resolve inside the render pass:** point the subpass's
  `pResolveAttachments` at single-sample images, so the samples are
  averaged as the tile is written out. **Avoid `vkCmdResolveImage`.** It
  writes all the samples out and reads them back, which costs several times
  the bandwidth.
- **Keep the multisampled attachments transient:**
  - store op `DONT_CARE`;
  - usage `TRANSIENT_ATTACHMENT`;
  - `LAZILY_ALLOCATED` memory.

  On tile-based GPUs (every Apple GPU, and phones) the extra samples then
  never leave the chip.
- Depth only needs resolving if something reads it afterward
  (`VK_KHR_depth_stencil_resolve`).

## Quorum's Vulkan frame today

From `Vulkan/VulkanPainter3D.quorum` (`RegenerateRenderPasses`, `End`):

| Pass | Draws | Attachments | Geometry edges? |
|---|---|---|---|
| Shadow | casters into cascades and cube faces | moments RG32F, depth | Not on screen (soft shadows) |
| **Scene (G-buffer)** | every 3D model, including the terrain's splat program | position RGBA32F, albedo RGBA16F, normal RGBA16F, PBR RGBA16F, depth D32F | **Yes: all of them** |
| Lighting | one full-screen triangle, reading the G-buffer with `sampler2D` | color RGBA16F | No |
| Result | the sky (Item 26), then the lit image copied over it with its alpha | the swapchain image, and a depth attachment | No |
| 2D (`VulkanPainter2D`) | labels, drawables | the swapchain image | 2D edges (fonts already have smooth edges) |

The G-buffer images are made once per swapchain image (one framebuffer
each). The scene pass clears all four to (0, 0, 0, 0), so wherever nothing
was drawn, position's w is 0 and albedo's alpha is 0. Geometry writes a
position with w = 1 (`worldPosition = modelTransform * vec4(inPos, 1.0)`).

**So MSAA belongs on the scene pass only.** It's the only pass where 3D
edges are made.

### What already exists

- `VulkanAttachmentDescription:SetSamples`, `VulkanImageInfo:SetSamples`,
  `VulkanPipelineInfo:SetRasterizationSamples`, all passed to Vulkan by the
  Java side.
- `VulkanSubpassDescription:SetResolveAttachments`, and `VulkanRenderPass.java`
  fills in `pResolveAttachments`.
- `VulkanPhysicalDeviceLimits:HasFrameBufferColorSampleSupport(count)` and
  `HasFrameBufferDepthSampleSupport(count)`.
- Constants: `SAMPLE_COUNT_1/2/4/8_BIT`, `IMAGE_USAGE_TRANSIENT_ATTACHMENT_BIT`,
  `MEMORY_USAGE_GPU_LAZILY_ALLOCATED`.

**No Java change is needed.**

## The difficulty: MSAA and deferred rendering

In a forward renderer, the resolve averages final colors, which is exactly
right. In a deferred renderer, the resolve averages the **G-buffer**:
positions, normals and material values. Lighting then runs once on those
averages. At an edge pixel:

- **Against the sky:** the background samples are zeros. Averaging a model
  with the background gives half its albedo, half its position (pulled
  toward the origin), and alpha 0.5. Lit as it is, that pixel is too dark
  and its shadow lookup is in the wrong place. Then the result pass blends
  it onto the sky by alpha 0.5 a second time, which leaves **a dark halo
  around every silhouette**.
- **Between two models:** position, normal and roughness are averages of
  two surfaces. The edge pixel is lit as if it were in between. That is
  usually a mild error (a soft step), sometimes a slightly wrong shadow
  pixel.

There are four ways to deal with this:

| Option | What | Correctness | Cost |
|---|---|---|---|
| **A. Resolve the G-buffer in the scene pass, coverage-aware lighting** | Multisampled, transient G-buffer and depth; resolve attachments write today's single-sample G-buffer; the lighting shader undoes the averaging with the background (below) | Exact against the sky; a blend between models | Small: the guide's best practice, almost free on Apple GPUs |
| B. Per-sample lighting | Keep the G-buffer multisampled and stored; lighting reads `sampler2DMS` and lights each sample (or only edge pixels), then averages | Exact everywhere | Large: the G-buffer stored at 4×, about 160 bytes a pixel, plus lighting up to 4× at edges |
| C. Custom resolve subpass | Like A, but a second subpass reads the samples as input attachments and resolves each value its own way (nearest position, renormalized normal) | Better than A between models | Medium: a second subpass and pipeline in the scene pass |
| D. Post-process AA (FXAA or SMAA), not MSAA | One more full-screen pass on the lit image | Approximate, but also smooths shading and alpha-cut leaves | Small; a little blurry |

**Recommended: A now.** It follows the guide exactly, and fixes the edges
that matter most outdoors: terrain, vehicles and trees against the sky.
C can follow if edges between models look wrong. D is a good companion
later for foliage and specular sparkle, which MSAA never fixes.

### Undoing the averaging against the background

The scene pass clears the background to zeros, and geometry writes position
w = 1. After the resolve, an edge pixel's **position w is the share of
samples covered by geometry**. Call it the coverage `c`. Every value
averaged with the background has been multiplied by `c`. So in the lighting
shader:

```glsl
vec4 rawWorldPosition = texture(positionSampler, uv);
float coverage = rawWorldPosition.w;          // 1 inside, 0 background, between at edges
float inverse = coverage > 0.0001 ? 1.0 / coverage : 0.0;
vec3 worldPosition = rawWorldPosition.xyz * inverse;
vec3 albedo = rawAlbedo.rgb * inverse;
vec3 pbr = rawPbr.rgb * inverse;
vec3 N = normalize(normal);                   // scaling doesn't change its direction
...
outputColor = vec4(color, rawAlbedo.a);       // unchanged: coverage × the model's alpha
```

- **With MSAA off,** coverage is exactly 1 or 0, so nothing changes.
- **Against the sky,** the pixel is lit with the model's exact values, and
  the result pass blends it onto the sky by its coverage. The edge is
  smooth with no halo.
- **Between two models,** coverage is 1, and the values stay averaged
  (option A's known limit).

## The design (option A)

### 1. Render passes know their sample count

- **`VulkanRenderPass`:** a new `integer sampleCount = 1`, set in `Create`
  to the largest `samples` among its attachments, with `GetSampleCount`.
- **`Shaders/Vulkan/VulkanShaderProgram:CreatePipeline`:** after the
  mapping makes the info, `info:SetRasterizationSamples(renderPass:GetSampleCount())`.

Every pipeline then matches the pass it's made for: the default 3D program,
custom programs like the terrain's splat program, the shadow, lighting,
copy and sky programs, and 2D. Passes other than the scene pass stay at 1,
so nothing else changes.

### 2. The scene pass with MSAA on

When the sample count `n` is more than 1:

- **Five multisampled attachments:**
  - position, albedo, normal, PBR and depth, in today's formats, with
    `samples = n`;
  - load op `CLEAR`, store op `DONT_CARE`;
  - images with usage `COLOR_ATTACHMENT | TRANSIENT_ATTACHMENT` (depth:
    `DEPTH_STENCIL_ATTACHMENT | TRANSIENT_ATTACHMENT`) and memory
    `GPU_LAZILY_ALLOCATED`.
- **Today's four single-sample G-buffer images become the resolve
  targets:** load op `DONT_CARE`, store op `STORE`. They're still sampled
  by the lighting pass exactly as now.
- **The subpass:**
  - color references point at the four multisampled attachments;
  - `SetResolveAttachments` points at the four single-sample ones;
  - depth points at the multisampled depth.

  Depth isn't resolved; nothing reads it afterward.
- **The framebuffer:** nine views (four multisampled, four single-sample,
  one depth).
- **One set of multisampled images for all frames,** rather than one per
  swapchain image:
  - They're transient, and each frame's scene pass waits for the previous
    one's attachment writes (the pass's external dependency gains
    `COLOR_ATTACHMENT_WRITE` in its source access).
  - This keeps memory down on GPUs without lazy memory (see Memory).
- **With MSAA off (`n` = 1):** exactly today's pass, attachments and
  framebuffers.

**The result pass** today reuses the scene's depth description. It gets its
own single-sample one, since the scene's may now be multisampled.

### 3. The lighting shader

`Shaders/Vulkan/Fragment/DefaultLightingFragmentShaderVulkan.quorum` gets
the coverage-aware reads above, about 8 lines. Nothing else in lighting
changes.

The sky's result pass is unchanged. It already blends the lit image by its
alpha.

### 4. Turning it on and off

- **`VulkanPainter3D:SetSampleCount(integer samples)` and
  `GetSampleCount`.** 1 means off; 2, 4 or 8 mean on.
  - The count is checked against the device:
    `HasFrameBufferColorSampleSupport` and
    `HasFrameBufferDepthSampleSupport`.
  - If the count isn't supported, it falls to the highest supported count
    below it, and says so once in the console.
- **Changing it at any time:**
  - marks the render passes for rebuilding (`RegenerateRenderPasses`
    already does this when the window is resized);
  - the scene pipelines are made again the next time they're used. The
    painter remembers the sample count each program's pipeline was made
    with, and remakes any that differ.
- **A game-level way in** (decision 2), for example
  `Game:SetMultisampling(integer samples)`:
  - it passes the count to every `Layer3D`'s painter when it's a
    `VulkanPainter3D`, and does nothing under OpenGL;
  - or the setting lives on `VulkanGraphics`, and every 3D painter reads it.
- **The default stays off,** so nothing changes until a game asks.

### 5. Test main: `MSAACheck.quorum` (project)

- A scene that aliases badly: thin posts and wires, boxes turning slowly,
  and the terrain's silhouette against the Item 26 sky.
- **M** steps the sample count through 1, 2, 4 and 8 (as supported). The
  console reports the count asked for, the count used, and the frame time.
- **What to see:**
  - stair-stepped edges become smooth at 4;
  - no dark halo against the sky;
  - edges between models soften without bright or dark fringes;
  - shadows unchanged;
  - switching counts doesn't stall for long or leak.
- Then TerrainEditor and DriveOpen with it on.

## Memory and speed

| GPU | Multisampled attachments | Extra memory at 1920×1080, 4× |
|---|---|---|
| Apple (M-series), phones | `LAZILY_ALLOCATED` becomes Metal's memoryless storage (MoltenVK does this on Apple GPUs); the samples live in tile memory only | About none. The tiles get smaller, a small speed cost |
| Desktop GPUs without lazy memory (most Windows and Linux) | Really allocated | 4 G-buffer targets (40 bytes a pixel) plus depth (4) = 44 bytes × 4 samples ≈ 365 MB with one shared set; at 2× about 180 MB. (One set per swapchain image would triple this, so the plan shares one.) |

- **Bandwidth:** with the resolve in the pass, the G-buffer is written out
  once at 1× as now. Only the resolve's own read is extra, and that stays
  on-chip on tilers.
- **Lighting cost is unchanged:** it still runs once per pixel.

## MoltenVK (the Mac)

Checked in its source:
- **Multisampled RGBA32F (the position buffer):**
  - it resolves natively when the GPU reports `supports32BitMSAA` (current
    Apple Silicon);
  - otherwise MoltenVK resolves it with a compute shader. That is correct
    but slower (`MVKPixelFormats.mm`, around line 650).
- **RGBA16F:** resolves natively everywhere.
- **`LAZILY_ALLOCATED` memory:** on Apple GPUs it becomes memoryless
  (`MVKDevice.mm`, around line 3451).
- **Resolve attachments** become Metal's `MultisampleResolve` store action,
  which is the in-pass resolve the guide recommends.

## What MSAA won't fix

- **Shading aliasing:** sparkling specular highlights, and noisy normal
  maps far away. Mipmaps (Item 25) handle most of it. Post-process AA or
  TAA handle the rest.
- **Alpha-cut edges** (leaves and grass made by `discard`): MSAA sees the
  whole quad. `alphaToCoverage` in the pipeline's multisample state is the
  usual fix, for when foliage (Tier 5) arrives.
- **Inside triangles:** textures are already filtered.

## Compared with others

- **Godot:** offers MSAA 2×, 4× and 8× in its forward renderers (where
  Terrain3D runs), plus FXAA and TAA. It has no deferred G-buffer, so it
  doesn't face the averaging problem.
- **Unreal and GRW-era deferred engines:** mostly use TAA, since MSAA on
  a G-buffer is expensive (option B).

Option A is the cheap middle ground that most deferred renderers that
support MSAA at all use.

## Files (option A)

| File | Change |
|---|---|
| `Vulkan/VulkanRenderPass.quorum` | `sampleCount`, `GetSampleCount` |
| `Shaders/Vulkan/VulkanShaderProgram.quorum` | pipelines take the pass's sample count |
| `Vulkan/VulkanPainter3D.quorum` | `SetSampleCount` / `GetSampleCount`; multisampled scene attachments and resolve targets; one shared multisampled set; the result pass's own depth description; pipelines made again when the count changes |
| `Shaders/Vulkan/Fragment/DefaultLightingFragmentShaderVulkan.quorum` | coverage-aware G-buffer reads |
| Possibly `Game.quorum` or `Vulkan/VulkanGraphics.quorum` | the game-level switch (decision 2) |

No Java, and nothing in OpenGL. About 200 lines.

## Open decisions for the user

1. **Option A now** (recommended), with C and/or D (FXAA) as later items?
   Or go straight to B for exact edges between models, at its memory cost?
2. **Where the switch lives:**
   - only on `VulkanPainter3D` (`SetSampleCount`);
   - on `VulkanGraphics`, for every 3D painter;
   - or also a `Game:SetMultisampling(samples)` that OpenGL ignores
     (recommended for ease of use; it is the one change in a shared,
     non-OpenGL file).
3. **The default:** off (recommended), or 4 when the device supports it?
4. **Share one multisampled set across frames** (recommended, for memory)?
   Or one per swapchain image, like the G-buffer today?
