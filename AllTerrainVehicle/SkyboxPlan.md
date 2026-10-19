# Skybox on the new shader system (plan)

**Status (2026-10-19): done** as `Item26.md`, committed in `768335de9`. Panorama and procedural skies are still later options.

Written 2026-10-19. **Approved with the recommended answers; the exact code
is in `Item26.md`,** which also records five details the code changed
(front and back faces, the web, `SkyboxShader.java`, side bookkeeping,
`InvertSkybox`'s wording). `VulkanChanges.md` #11 ("Skybox not
implemented"), and item 15 in `OpenWorldsHandoff.md`'s priority list.
Nothing is changed yet. Once this design is settled, the exact code goes in
`Item26.md` for review, as with Items 20, 24 and 25.

Paths are under
`quorum-language/Quorum/Library/Standard/Libraries/Game/` for Quorum, and
`quorum-language/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/`
for Java.

## The goal

- **One skybox** that draws the same under OpenGL and Vulkan.
- **Written in Quorum's shader system:** a `ShaderProgram` with OpenGL and
  Vulkan shaders and mappings, like every other program. No hand-written
  Java shader.
- **Right for the left-handed world.** The current code was written before
  the matrix conversion.
- **Today's `Skybox` API keeps working:** `Load` with six sides, `Rotate`,
  `SetToRotation`, `InvertSkybox`, `Dispose`, the scene editor's saved
  skyboxes, and `Game:SetSkybox` / `Layer3D:SetSkybox`. Games like
  BlockBreaker shouldn't need to change.

## What's there today

| Piece | Where | What it does |
|---|---|---|
| `Skybox` | `Graphics/Skybox.quorum` (1025 lines, mostly docs) | Holds `Texture cubeMap`, a rotation `Matrix4 transform`, `inverter` (1 or -1), six loaded flags and six source files. Loading goes through two **system actions**: `InitializeCubeMap(Texture)` and `LoadSide(File, Texture, side)`. The side constants are OpenGL's, with a note that Quorum's +z is OpenGL's -z, so `LoadFront` loads `GL_TEXTURE_CUBE_MAP_NEGATIVE_Z`. |
| `Skybox.java` | Java plugin (two copies: `QuorumPlugins` and the older `GamePlugin/JavaGame`) | Makes a GL cube texture (linear, clamp to edge) and loads each side with `glTexImage2D`. OpenGL only. |
| `SkyboxShader` | `Graphics/Shaders/SkyboxShader.quorum` | One line: `system action Render(Skybox, Camera)`. Its comment says: "Replace this with a proper Quorum implementation that uses our normal shader system." |
| `SkyboxShader.java` | Java plugin (both copies) | Its own GLSL 410 shaders and a 36-vertex cube buffer, both outside Quorum's shader system. It builds the view matrix by hand from the camera's, **flipping signs on some entries**, and zeroes part of the projection. It draws with `gl_Position = pos.xyww`, so the sky sits at the far plane. |
| `OpenGLPainter3D` | `Graphics/OpenGL/OpenGLPainter3D.quorum` | Calls `skyboxShader:Render` after opaque models and before the first blended one (or at `End`), with the depth test on. |
| `VulkanPainter3D:SetSkybox` | `Graphics/Vulkan/VulkanPainter3D.quorum:1951` | Empty: the "NYI" lines are commented out. **Under Vulkan, no skybox is drawn.** |
| Plumbing | `Game`, `Layer3D`, `Painter3D` (blueprint), `Scenes/DefaultSceneManager`, `SceneProperties` | `SetSkybox` passes it down to the layer's painter. Scenes save and load the six files. |
| Web | `Plugins/javascript/.../Skybox.js`, `Painter3D.js` | The web has its own JavaScript painter and skybox. |

### Why the current one is wrong, or at least fragile

1. **Hand-flipped matrices.** `SkyboxShader.java` negates the first column
   and part of the third row of the view matrix to undo the old
   handedness. The left-handed conversion (`Done/VulkanRotationFix.md`,
   `Done/OrthographicMigration.md`) changed the camera's matrices, so
   these flips now likely mirror or turn the sky.
2. **Outside the shader system.** It has its own GLSL, its own buffer and
   its own uniform handling, so it can't be shared with Vulkan, and doesn't
   follow the shader manager's version header or reloading after a lost
   context.
3. **No Vulkan at all,** and Vulkan has no cube textures. The renderer's
   bindless texture array holds only 2D textures (`texture2D
   globalTextures[]`).

## What the Vulkan side already has

- Images with several layers (`VulkanImageInfo:SetArrayLayers`), image
  flags (`SetFlags`, passed through by `VulkanImage.java`), and view types
  (`VulkanImageViewInfo:SetViewType`, passed through by
  `VulkanImageView.java`). The constants `IMAGE_CREATE_CUBE_COMPATIBLE_BIT`
  and `IMAGE_VIEW_TYPE_CUBE` exist. Point-light shadows already make
  six-layer images.
- `CopyBufferToImageCommand:SetBaseArrayLayer`, for copying each side into
  its layer.
- A full-screen pass to copy from: `CopyFromSamplerShaderProgram`. It draws
  one triangle with no vertex buffer (`gl_VertexIndex`), reads one combined
  image sampler from its own descriptor set, and **blends by alpha** onto
  the screen.
- Push constants (`VulkanPipelineInfoCreator:SetPushConstantRange`,
  `SetPushConstantsCommand`).

## The design

### One technique for both renderers: a full-screen sky

Draw **one triangle that covers the screen**, at the far plane. For each
pixel, the shader works out the direction the camera looks through that
pixel, and reads the cube map in that direction.

- **No cube mesh and no vertex buffer.** Both shaders make the triangle from
  the vertex index, as Vulkan's copy pass already does.
- **No matrices from the camera.** The CPU passes three vectors: the
  camera's forward direction, and its right and up directions, each scaled
  by how far the view reaches at a distance of 1 (from the field of view
  and the screen's aspect). The direction through a pixel at screen
  position (x, y), from -1 to 1, is then `forward + x × right + y × up`.
  - This avoids the matrix conventions that broke the old sky. It works the
    same in both APIs, with or without `y` flipped, since the vectors come
    from `Camera:GetDirection` and `GetUp`.
  - Moving the camera never moves the sky, since only its direction is
    used.
- **Rotation and inversion** stay: the `Skybox`'s rotation (as a 3 by 3
  matrix) turns the direction, and the inverter flips x, as today.
- **The face convention** (which file is "front") is applied in one place:
  the shader maps Quorum's direction to the cube map's, flipping z like the
  current note says. The test main checks it face by face (below).

### The shader program: `SkyboxShaderProgram`

New classes, following `DefaultShaderProgram3D` and `CopyFromSampler`:

| Class | Package (under `Graphics/Shaders/`) |
|---|---|
| `SkyboxShaderProgram is ShaderProgram` | `Programs` |
| `SkyboxVertexShaderOpenGL`, `SkyboxFragmentShaderOpenGL` | `OpenGL/Vertex`, `OpenGL/Fragment` |
| `SkyboxVertexShaderVulkan`, `SkyboxFragmentShaderVulkan` | `Vulkan/Vertex`, `Vulkan/Fragment` |
| `SkyboxShaderMappingOpenGL is ShaderMapping` | `OpenGL/Mapping` |
| `SkyboxShaderMappingVulkan is VulkanShaderMapping` | `Vulkan/Mapping` |

`ShaderManager` gets the names (`SKYBOX_SHADER_PROGRAM` and the four
shaders) and getters, like the lighting program's. The program picks its
shaders and mapping by `IsVulkanProgram()`, like `DefaultShaderProgram3D`.

**What each mapping passes:**

- **OpenGL:** uniforms through `OpenGLShaderProgram:SetShaderInput`: the
  three camera vectors, the rotation (`SetShaderInputMatrix` with a
  `Matrix3`), the inverter, and the cube texture on unit 0.
- **Vulkan:** a push constant block of 3 vectors, a 3 by 3 rotation and the
  inverter (about 96 bytes; every device allows at least 128). It also has
  **its own descriptor set with one combined `samplerCube`**, like the copy
  pass's. Its pipeline:
  - draws no depth;
  - blends opaque;
  - uses a dynamic viewport and scissor.

### Cube textures

**OpenGL:** loading stays as it is: `InitializeCubeMap` and `LoadSide`
remain system actions in `Skybox.java`. They only make a GL cube texture,
which is right for OpenGL and isn't what's broken. (Decision 2: move them
into Quorum too.)

**Vulkan (new):**
- `Skybox`'s load actions, under Vulkan, load each side into a `PixelMap`
  and keep it. Once all six are in, they ask the texture manager for a cube.
- New `VulkanTextureManager:RequestCubeLoad(Texture, Array<PixelMap>)`,
  handled in `ProcessPendingTextures` like other loads. It makes:
  - an image with 6 layers and the `CUBE_COMPATIBLE` flag, RGBA8, one
    level;
  - six copies, one per layer (`SetBaseArrayLayer`);
  - a `CUBE` view, set on the texture with `SetVulkanImageView`.

  The cube does **not** go in the bindless 2D array, so it uses no texture
  place and isn't affected by texture groups (#22). The sky's descriptor set
  points straight at its view.
- The sides must be square and the same size, as cube maps require. A clear
  error says so otherwise.

### Where it's drawn

**OpenGL** (forward rendering): the same place as today, after opaque
models and before the first blended one. The depth test is on with
less-or-equal, depth writes are off, and the triangle sits at depth 1. Only
pixels no model covered show sky.

**Vulkan** (deferred rendering): in the **result pass**, just before the lit
image is copied to the screen.
- The lighting pass clears its image to transparent black (alpha 0), and
  writes the albedo's alpha (1 for solid models) where there is geometry.
- The copy pass already blends by that alpha.
- So drawing the sky first and the lit image over it shows sky exactly where
  nothing was drawn, and edges blend smoothly. No depth test, no change to
  the G-buffer, lighting or shadow passes.
- Only a layer with a skybox draws one. With several `Layer3D`s, a later
  layer's sky would cover earlier layers, the same as OpenGL.

### Old code

- `SkyboxShader.quorum`'s system `Render` is replaced by the new program.
  `OpenGLPainter3D` calls the program in its place.
- `SkyboxShader.java` (both plugin copies) is no longer used. It is deleted
  once the new one is checked (decision 3).
- **The web is untouched.** It has its own JavaScript painter and skybox.
  Moving it is a separate task.

## Later options (not in this item)

These fit the same full-screen pass, with a different fragment shader or
texture. They matter more for open worlds than cube maps do.

- **Panorama skies:** one equirectangular image, the format HDRI skies come
  in (Poly Haven, AmbientCG). The direction becomes a longitude and
  latitude. It is one 2D texture, so it fits the bindless array (with
  mipmaps from Item 25).
- **A procedural sky:**
  - a gradient from horizon to zenith;
  - a sun disk that follows the scene's `DirectionalLight`;
  - simple atmospheric scattering (Godot's `ProceduralSkyMaterial`, and
    GRW's sky).

  It pairs naturally with fog (#17): the fog's color can be the sky's color
  at the horizon, which hides the world's far edge.
- **Sky lighting:** using the sky as ambient light and reflections
  (image-based lighting). Larger; it needs filtered cube maps.

## Compared with others

| | Godot (Terrain3D's host) | GRW | This plan |
|---|---|---|---|
| How it's drawn | full-screen sky pass at the far plane | sky dome, drawn last | full-screen pass |
| Sources | panorama, procedural, physical sky | procedural atmosphere | cube map now; panorama and procedural later |
| With fog | fog color from the sky | aerial perspective | later, with #17 |
| Lighting from sky | yes (radiance maps) | yes | later |

## Size

Library, Quorum:
- 7 new small classes (about 400 lines with docs);
- `Skybox` changes (about 60);
- `ShaderManager` (about 60);
- `VulkanTextureManager` (`RequestCubeLoad`, about 120);
- `VulkanPainter3D` (`SetSkybox` and the draw in the result pass, about 60);
- `OpenGLPainter3D` (about 10).

No new Java, apart from deleting `SkyboxShader.java`.

## Risks and things to know

- **Attribute-less drawing on OpenGL.** The triangle comes from
  `gl_VertexID`, which needs a vertex array object bound in core profile
  (the Mac). `DesktopOpenGL.java` makes and binds one. To check in the
  first run; if it's a problem, a 3-vertex buffer is the fallback.
- **Orthographic cameras** have no field of view. The sky is skipped for
  them (or shows one color in the camera's direction). Decision 4.
- **Face order and mirroring** are easy to get wrong, which is likely what
  happened to the old sky. The test main is built to catch it.
- **MoltenVK:** cube images and `samplerCube` map directly to Metal's
  `texturecube`. Push constants become a small buffer. Both are ordinary
  uses.
- **Resizing** changes the aspect. The vectors are made every frame, so
  that's automatic.
- **Scene files** keep working: they save the six file names, which don't
  change.

## Test plan

**`SkyboxCheck.quorum`** (project), for both renderers (one `UseVulkan`
line to switch):
- A **made-up test sky:** six square images made with `PixelMap`, each a
  different color:
  - front red, back cyan, left green, right magenta, up white, down
    black;
  - each with a yellow bar along its top edge and a small square near its
    right edge, so turned or mirrored sides show.
- **Keys:** arrow keys turn and tilt the camera, R starts the sky
  rotating, I inverts it, and V toggles a few boxes and a half-transparent
  box in front.
- **What to see:**
  1. at start, facing forward: red, with its yellow bar on top and its
     square on the right;
  2. turning right shows magenta, left green, behind cyan, up white, down
     black, each upright and unmirrored;
  3. moving the camera doesn't move the sky;
  4. boxes cover the sky; the half-transparent box shows the sky through it;
  5. no seams at the cube's edges;
  6. R turns the sky, and I mirrors it left to right.

**Then:** BlockBreaker (example-games, OpenGL, its `LightBlue` sky) should
look as it did, and DriveOpen or TerrainEditor gets a real sky (a free
cube-map sky set, added to `AllTerrainVehicle/Skyboxes/`).

## Open decisions for the user

1. **Scope:** cube-map skyboxes on both renderers now, with panorama and
   procedural skies later (recommended)? Or start with the procedural sky,
   which suits open worlds best but doesn't fix `Skybox`?
2. **OpenGL cube loading:** keep `InitializeCubeMap` and `LoadSide` as Java
   system actions (recommended: they work and aren't the broken part), or
   move them into Quorum through `Texture`'s GL upload?
3. **Old Java shader:** delete `SkyboxShader.java` (both plugin copies) once
   the new one is checked (recommended), or leave it unused?
4. **Orthographic cameras:** skip the sky (recommended), or fill with the
   color in the camera's direction?
5. **The web** stays on its JavaScript skybox for now (recommended)?
