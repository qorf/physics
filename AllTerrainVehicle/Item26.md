# Item 26: the skybox on the new shader system

**Status (2026-10-19): done.** Committed in `768335de9`; confirmed (SkyboxCheck under Vulkan, the Day sky in DriveOpen).

The exact code for `SkyboxPlan.md`, with the recommended answers to its five
decisions:
1. cube maps on both renderers now; panorama and procedural skies later;
2. OpenGL cube loading stays in Java;
3. the old Java shader is retired;
4. orthographic cameras draw no sky;
5. the web stays as it is.

`VulkanChanges.md` #11. **Approved and applied on 2026-10-19** to the
`quorum-language` branch `TerrainShader`, with the camera-vector math in
`Skybox` (`UpdateView`) rather than a separate class (the user's choice).
`SourceCode/SkyboxCheck.quorum` and its test sky
(`Skyboxes/Check/*.png`, made by a script) are written. **Waiting for a
rebuild of the library and plugins, and a run.** Item 25 is still
uncommitted on the same branch.

**First run (2026-10-19): SkyboxCheck under Vulkan** started and ran with
the sky turning (R) on and off, with no errors in the console. Next:
DriveOpen with a real sky. `Skyboxes/MakeDaySky.py` makes
`Skyboxes/Day/` (a 1024 daytime sky: gradient, clouds, hazy ground,
seamless), loaded by DriveOpen's `useSkybox`. K hides or shows it.
Then SkyboxCheck under OpenGL, and BlockBreaker.

Paths are under
`quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/` for
Quorum, and
`quorum-language/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/`
for Java.

## What was learned while writing the code

Five findings change the plan's details. None changes its design.

1. **Which file goes on which cube face.** OpenGL and Vulkan pick a cube
   face, and the place on it, by the same table (OpenGL spec, cube map face
   selection; Vulkan uses the same). Worked through for Quorum's
   left-handed world (+x right, +y up, +z forward):
   - **front goes on +Z, back on -Z;** right on +X, left on -X, top on +Y,
     bottom on -Y;
   - then the camera's own direction can be used as the lookup, unchanged.
     Every side shows upright and unmirrored, and the top and bottom join
     the front along their edges.

   Today's `Skybox` puts front on **-Z** (made for the old right-handed
   world). That can't be fixed by turning the lookup direction: any turn
   that puts the front ahead either mirrors the images or swaps left and
   right. So **the desktop OpenGL load swaps the two z faces.** Vulkan loads
   in the new order from the start.
2. **The web can't be told apart from desktop OpenGL** at the painter
   level. Its JavaScript `LoadSide` still uses the old faces, and it may
   draw through `OpenGLPainter3D`. So the web keeps the old faces and the
   old `SkyboxShader`, chosen with `GetApplication() is WebApplication`
   (as `Texture` already does).
3. **So `SkyboxShader.java` can't be deleted yet** (decision 3).
   `SkyboxShader.quorum` keeps its system action for the web, and a system
   action needs its Java class for desktop builds to link. Instead:
   - desktop never creates it (today `OpenGLPainter3D` creates it for every
     painter, compiling the old GLSL);
   - it is deleted when the web moves.
4. **`Skybox.java` records which file was loaded for each side,** keyed on
   the OpenGL face. With the z faces swapped, it would record front and
   back the wrong way round. That bookkeeping moves into Quorum: **one
   small Java change, removing a `switch`.**
5. **`InvertSkybox`'s documentation** describes the old world's mismatch
   ("false: the left image will appear on the right"). With correct faces,
   the default (`true`, inverter 1) shows the sky as it is, and `false`
   mirrors it left to right. The setting keeps its meaning as data, and the
   documentation is updated.

## Files

| File | Change |
|---|---|
| `Shaders/Programs/SkyboxShaderProgram.quorum` | **New.** |
| `Shaders/OpenGL/Vertex/SkyboxVertexShaderOpenGL.quorum` | **New.** |
| `Shaders/OpenGL/Fragment/SkyboxFragmentShaderOpenGL.quorum` | **New.** |
| `Shaders/OpenGL/Mapping/SkyboxShaderMappingOpenGL.quorum` | **New.** |
| `Shaders/Vulkan/Vertex/SkyboxVertexShaderVulkan.quorum` | **New.** |
| `Shaders/Vulkan/Fragment/SkyboxFragmentShaderVulkan.quorum` | **New.** |
| `Shaders/Vulkan/Mapping/SkyboxShaderMappingVulkan.quorum` | **New.** |
| `Shaders/ShaderManager.quorum` | Names and getters. |
| `Skybox.quorum` | One place that loads a side, per renderer; the camera's sky vectors (`UpdateView`); getters; documentation. |
| `OpenGL/OpenGLPainter3D.quorum` | Draws with the new program (the web keeps the old). |
| `Vulkan/VulkanTextureManager.quorum` | `RequestCubeLoad`: six-layer cube images. |
| `Vulkan/VulkanPainter3D.quorum` | `SetSkybox`, and the sky in the result pass. |
| `Skybox.java` | The side bookkeeping is removed. |

## 1. The shaders

All four draw **one triangle that covers the screen**, made from the vertex
number, with no vertex buffer: corners (-1, -1), (3, -1) and (-1, 3). The
fragment shader works out the direction from the screen position, turns it
back by the sky's rotation, mirrors x if the sky is inverted, and reads the
cube.

**The rotation** is turned back with `direction * mat3(rotation)` (the
transpose, which undoes a rotation). That matches the old shader, which
turned the cube's corners by the rotation and read the cube at the corners'
own positions.

### `Shaders/OpenGL/Vertex/SkyboxVertexShaderOpenGL.quorum`

```
package Libraries.Game.Graphics.Shaders.OpenGL.Vertex

use Libraries.Game.GameStateManager
use Libraries.Game.Graphics.Shaders.Shader
use Libraries.Game.Graphics.Shaders.ShaderManager

/*
SkyboxVertexShaderOpenGL draws one triangle covering the screen, at the far
plane, for the sky. It needs no vertices: the corners come from the vertex
number. It passes each pixel's screen position, from -1 to 1, to the
fragment shader.

Attribute: Example
use Libraries.Game.Graphics.Shaders.OpenGL.Vertex.SkyboxVertexShaderOpenGL
SkyboxVertexShaderOpenGL shader
shader:Compile()
*/
class SkyboxVertexShaderOpenGL is Shader
    on create
        SetType(parent:Shader:VERTEX_SHADER)
        GameStateManager manager
        ShaderManager shaderManager = manager:GetShaderManager()
        SetName(shaderManager:SKYBOX_VERTEX_SHADER)
        SetCode(GetVersionHeader() + "

out vec2 v_screen;

void main()
{
    vec2 corner = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    v_screen = corner * 2.0 - 1.0;
    // Depth 1: the far plane, behind everything drawn.
    gl_Position = vec4(v_screen, 1.0, 1.0);
}
")
    end
end
```

### `Shaders/OpenGL/Fragment/SkyboxFragmentShaderOpenGL.quorum`

```
package Libraries.Game.Graphics.Shaders.OpenGL.Fragment

use Libraries.Game.GameStateManager
use Libraries.Game.Graphics.Shaders.Shader
use Libraries.Game.Graphics.Shaders.ShaderManager

/*
SkyboxFragmentShaderOpenGL colors each pixel of the sky from a cube map, in
the direction the camera looks through that pixel (see Skybox:UpdateView).

Attribute: Example
use Libraries.Game.Graphics.Shaders.OpenGL.Fragment.SkyboxFragmentShaderOpenGL
SkyboxFragmentShaderOpenGL shader
shader:Compile()
*/
class SkyboxFragmentShaderOpenGL is Shader
    on create
        SetType(parent:Shader:FRAGMENT_SHADER)
        GameStateManager manager
        ShaderManager shaderManager = manager:GetShaderManager()
        SetName(shaderManager:SKYBOX_FRAGMENT_SHADER)
        SetCode(GetVersionHeader() + "

#ifdef GL_ES
    precision mediump float;
#endif

in vec2 v_screen;
layout (location = 0) out vec4 outputColor;

uniform samplerCube u_skybox;
// The camera's directions, from Skybox:UpdateView.
uniform vec3 u_right;
uniform vec3 u_up;
uniform vec3 u_forward;
// The sky's rotation, and 1, or -1 to mirror it.
uniform mat4 u_rotation;
uniform float u_inverter;

void main()
{
    vec3 direction = u_forward + v_screen.x * u_right + v_screen.y * u_up;
    direction = direction * mat3(u_rotation);
    direction.x = direction.x * u_inverter;
    outputColor = vec4(texture(u_skybox, direction).rgb, 1.0);
}
")
    end
end
```

### `Shaders/Vulkan/Vertex/SkyboxVertexShaderVulkan.quorum`

The result pass's viewport has a negative height (as the copy pass's does),
so screen y of +1 is the top, as in OpenGL.

```
package Libraries.Game.Graphics.Shaders.Vulkan.Vertex

use Libraries.Game.GameStateManager
use Libraries.Game.Graphics.Shaders.Shader
use Libraries.Game.Graphics.Shaders.ShaderManager

/*
SkyboxVertexShaderVulkan draws one triangle covering the screen for the sky.
It needs no vertices: the corners come from the vertex number. It passes
each pixel's screen position, from -1 to 1, to the fragment shader.

Attribute: Example
use Libraries.Game.Graphics.Shaders.Vulkan.Vertex.SkyboxVertexShaderVulkan
SkyboxVertexShaderVulkan shader
shader:Compile()
*/
class SkyboxVertexShaderVulkan is Shader
    on create
        SetType(parent:Shader:VERTEX_SHADER)
        GameStateManager manager
        ShaderManager shaderManager = manager:GetShaderManager()
        SetName(shaderManager:SKYBOX_VERTEX_SHADER)
        SetCode(GetVersionHeader() + "

layout (location = 0) out vec2 v_screen;

void main()
{
    vec2 corner = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
    v_screen = corner * 2.0 - 1.0;
    gl_Position = vec4(v_screen, 0.0, 1.0);
}
")
    end
end
```

### `Shaders/Vulkan/Fragment/SkyboxFragmentShaderVulkan.quorum`

```
package Libraries.Game.Graphics.Shaders.Vulkan.Fragment

use Libraries.Game.GameStateManager
use Libraries.Game.Graphics.Shaders.Shader
use Libraries.Game.Graphics.Shaders.ShaderManager

/*
SkyboxFragmentShaderVulkan colors each pixel of the sky from a cube map, in
the direction the camera looks through that pixel (see Skybox:UpdateView). The
camera's directions, the sky's rotation and its inverter come in push
constants; the cube map in its own descriptor set.

Attribute: Example
use Libraries.Game.Graphics.Shaders.Vulkan.Fragment.SkyboxFragmentShaderVulkan
SkyboxFragmentShaderVulkan shader
shader:Compile()
*/
class SkyboxFragmentShaderVulkan is Shader
    on create
        SetType(parent:Shader:FRAGMENT_SHADER)
        GameStateManager manager
        ShaderManager shaderManager = manager:GetShaderManager()
        SetName(shaderManager:SKYBOX_FRAGMENT_SHADER)
        SetCode(GetVersionHeader() + "

layout (location = 0) in vec2 v_screen;
layout (location = 0) out vec4 outputColor;

layout (set = 0, binding = 0) uniform samplerCube u_skybox;

// 112 bytes. The right vector's w is the inverter: 1, or -1 to mirror.
layout (push_constant) uniform SkyboxConstants
{
    vec4 right;
    vec4 up;
    vec4 forward;
    mat4 rotation;
} sky;

void main()
{
    vec3 direction = sky.forward.xyz + v_screen.x * sky.right.xyz + v_screen.y * sky.up.xyz;
    direction = direction * mat3(sky.rotation);
    direction.x = direction.x * sky.right.w;
    outputColor = vec4(texture(u_skybox, direction).rgb, 1.0);
}
")
    end
end
```

## 2. The mappings and the program

### `Shaders/OpenGL/Mapping/SkyboxShaderMappingOpenGL.quorum`

```
package Libraries.Game.Graphics.Shaders.OpenGL.Mapping

use Libraries.Compute.Vector3
use Libraries.Game.GameStateManager
use Libraries.Game.Graphics.Camera
use Libraries.Game.Graphics.Skybox
use Libraries.Game.Graphics.OpenGL.OpenGLConstants
use Libraries.Game.Graphics.OpenGL.OpenGLManager
use Libraries.Game.Graphics.Shaders.ShaderMapping
use Libraries.Game.Graphics.Shaders.OpenGL.OpenGLShaderProgram
use Libraries.Game.Graphics.Shaders.Programs.ShaderProgram

/*
SkyboxShaderMappingOpenGL gives the OpenGL sky shaders what they need: the
camera's directions, the sky's rotation and inverter, and its cube map on
texture unit 0. Begin also sets the depth test so the sky only fills pixels
nothing else was drawn on. Give it the skybox with SetSkybox first.

Attribute: Example
use Libraries.Game.Graphics.Shaders.OpenGL.Mapping.SkyboxShaderMappingOpenGL
SkyboxShaderMappingOpenGL mapping
*/
class SkyboxShaderMappingOpenGL is ShaderMapping
    Skybox skybox = undefined
    OpenGLConstants constants

    /*
    This action sets the skybox the next Begin draws.

    Attribute: Parameter skybox The skybox.
    */
    action SetSkybox(Skybox skybox)
        me:skybox = skybox
    end

    /*
    This action sets the shader inputs and the graphics state for the sky.

    Attribute: Parameter program The skybox program, already begun.
    Attribute: Parameter camera The camera the sky is seen from.
    */
    action Begin(ShaderProgram program, Camera camera)
        GameStateManager manager
        OpenGLManager graphics = cast(OpenGLManager, manager:GetGameGraphics())
        OpenGLShaderProgram glProgram = cast(OpenGLShaderProgram, program:GetShaderProgramStrategy())

        skybox:UpdateView(camera)
        Vector3 right = skybox:GetViewRight()
        Vector3 up = skybox:GetViewUp()
        Vector3 forward = skybox:GetViewForward()
        glProgram:SetShaderInput("u_right", right:GetX(), right:GetY(), right:GetZ())
        glProgram:SetShaderInput("u_up", up:GetX(), up:GetY(), up:GetZ())
        glProgram:SetShaderInput("u_forward", forward:GetX(), forward:GetY(), forward:GetZ())
        glProgram:SetShaderInputMatrix("u_rotation", skybox:GetRotation())
        glProgram:SetShaderInput("u_inverter", skybox:GetInverter())

        // The cube map, on texture unit 0.
        skybox:GetCubeMap():Bind(0)
        glProgram:SetShaderInput("u_skybox", 0)

        // The triangle is at depth 1, so it only shows where nothing nearer
        // was drawn, and it doesn't write depth.
        graphics:EnableProperty(constants:GL_DEPTH_TEST)
        graphics:SetDepthFunction(constants:GL_LEQUAL)
        graphics:SetDepthMask(false)
        graphics:DisableProperty(constants:GL_CULL_FACE)
        graphics:DisableProperty(constants:GL_BLEND)
    end

    /*
    This action puts back the depth writes the sky turned off.

    Attribute: Parameter program The skybox program.
    */
    action End(ShaderProgram program)
        GameStateManager manager
        OpenGLManager graphics = cast(OpenGLManager, manager:GetGameGraphics())
        graphics:SetDepthMask(true)
    end
end
```

### `Shaders/Vulkan/Mapping/SkyboxShaderMappingVulkan.quorum`

```
package Libraries.Game.Graphics.Shaders.Vulkan.Mapping

use Libraries.Game.Graphics.Shaders.Vulkan.VulkanShaderProgram
use Libraries.Game.Graphics.Vulkan.VulkanDevice
use Libraries.Game.Graphics.Vulkan.VulkanPipelineInfo
use Libraries.Game.Graphics.Vulkan.VulkanPipelineInfoCreator
use Libraries.Game.Graphics.Vulkan.VulkanConstants
use Libraries.Game.Graphics.Vulkan.VulkanPushConstantRange

/*
SkyboxShaderMappingVulkan describes the sky's Vulkan pipeline:
- one combined cube sampler in descriptor set 0;
- 112 bytes of push constants for the fragment shader (see
  SkyboxFragmentShaderVulkan);
- no depth test, no culling, opaque blending, and a dynamic viewport.

The VulkanPainter3D fills in the data when it draws the sky.

Attribute: Example
use Libraries.Game.Graphics.Shaders.Vulkan.Mapping.SkyboxShaderMappingVulkan
SkyboxShaderMappingVulkan mapping
*/
class SkyboxShaderMappingVulkan is VulkanShaderMapping

    /*
    This action makes the pipeline description for the sky.

    Attribute: Parameter program The skybox program.
    Attribute: Parameter device The Vulkan device.
    Attribute: Returns The pipeline description.
    */
    action CreatePipelineInfo(VulkanShaderProgram program, VulkanDevice device) returns VulkanPipelineInfo
        VulkanConstants constants
        VulkanPipelineInfoCreator creator
        creator:Begin(device)

        creator:AddOpaqueColorBlendAttachmentState()
        creator:AddDynamicViewport()
        creator:AddDynamicScissor()
        creator:AddDescriptorSetLayoutBinding(constants:SHADER_STAGE_FRAGMENT_BIT, constants:DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER)

        VulkanPushConstantRange pushConstants
        pushConstants:SetSize(112)
        pushConstants:SetStage(constants:SHADER_STAGE_FRAGMENT_BIT)
        pushConstants:Create()
        creator:SetPushConstantRange(pushConstants)

        VulkanPipelineInfo info = creator:Finish()
        // The sky is drawn first in the result pass, under everything, so
        // it needs no depth.
        info:SetDepthTestEnable(false)
        info:SetDepthWriteEnable(false)
        info:SetCullMode(constants:CULL_MODE_NONE)
        return info
    end
end
```

### `Shaders/Programs/SkyboxShaderProgram.quorum`

```
package Libraries.Game.Graphics.Shaders.Programs

use Libraries.Game.GameStateManager
use Libraries.Game.Graphics.Shaders.Shader
use Libraries.Game.Graphics.Shaders.ShaderManager
use Libraries.Game.Graphics.Shaders.OpenGL.Mapping.SkyboxShaderMappingOpenGL
use Libraries.Game.Graphics.Shaders.Vulkan.Mapping.SkyboxShaderMappingVulkan

/*
SkyboxShaderProgram draws a Skybox behind a 3D scene, in OpenGL or Vulkan.
It covers the screen with one triangle and colors each pixel from the sky's
cube map, in the direction the camera looks through it. The painters use it
for a layer's skybox (Layer3D:SetSkybox); games don't need to use it
directly.

Attribute: Example
use Libraries.Game.GameStateManager
use Libraries.Game.Graphics.Shaders.ShaderManager
use Libraries.Game.Graphics.Shaders.Programs.ShaderProgram

GameStateManager gameState
ShaderManager manager = gameState:GetShaderManager()
ShaderProgram program = manager:GetSkyboxShaderProgram()
*/
class SkyboxShaderProgram is ShaderProgram
    on create
        GameStateManager gameState
        ShaderManager manager = gameState:GetShaderManager()
        SetName(manager:SKYBOX_SHADER_PROGRAM)
        Shader vertex = manager:GetSkyboxVertexShader()
        Shader fragment = manager:GetSkyboxFragmentShader()
        Add(vertex)
        Add(fragment)
        if IsVulkanProgram()
            SkyboxShaderMappingVulkan mapping
            SetShaderMapping(mapping)
        else
            SkyboxShaderMappingOpenGL mapping
            SetShaderMapping(mapping)
        end
    end
end
```

## 3. `Shaders/ShaderManager.quorum`

**New `use` lines** (with the others at the top):

```
use Libraries.Game.Graphics.Shaders.Programs.SkyboxShaderProgram
use Libraries.Game.Graphics.Shaders.OpenGL.Vertex.SkyboxVertexShaderOpenGL
use Libraries.Game.Graphics.Shaders.OpenGL.Fragment.SkyboxFragmentShaderOpenGL
use Libraries.Game.Graphics.Shaders.Vulkan.Vertex.SkyboxVertexShaderVulkan
use Libraries.Game.Graphics.Shaders.Vulkan.Fragment.SkyboxFragmentShaderVulkan
```

**New constants,** after `TWO_STAGE_SHADOW_SHADER_PROGRAM`:

```
    public constant text SKYBOX_VERTEX_SHADER = "Skybox Vertex Shader"
    public constant text SKYBOX_FRAGMENT_SHADER = "Skybox Fragment Shader"
    public constant text SKYBOX_SHADER_PROGRAM = "Skybox Shader Program"
```

**New actions,** after `GetCopyFromSamplerFragmentShader`:

```
    /*
    This action returns the program that draws a Skybox, for OpenGL or
    Vulkan, compiling it the first time.

    Attribute: Returns The skybox shader program.
    */
    action GetSkyboxShaderProgram returns ShaderProgram
        ShaderProgram program = GetShaderProgram(SKYBOX_SHADER_PROGRAM)
        if program = undefined
            SkyboxShaderProgram default
            // Compiling this program will automatically register it in the ShaderManager for future use.
            default:Compile()
            return default
        else
            return program
        end
    end

    /*
    This action returns the skybox's vertex shader for the renderer in use.

    Attribute: Returns The skybox vertex shader.
    */
    action GetSkyboxVertexShader returns Shader
        if HasShader(SKYBOX_VERTEX_SHADER) = false
            if IsVulkan()
                SkyboxVertexShaderVulkan shader
                shader:Compile()
            elseif IsOpenGL()
                SkyboxVertexShaderOpenGL shader
                shader:Compile()
            else
                alert("I couldn't create a shader because I couldn't determine what graphics library was being used!")
            end
        end

        return GetShader(SKYBOX_VERTEX_SHADER)
    end

    /*
    This action returns the skybox's fragment shader for the renderer in
    use.

    Attribute: Returns The skybox fragment shader.
    */
    action GetSkyboxFragmentShader returns Shader
        if HasShader(SKYBOX_FRAGMENT_SHADER) = false
            if IsVulkan()
                SkyboxFragmentShaderVulkan shader
                shader:Compile()
            elseif IsOpenGL()
                SkyboxFragmentShaderOpenGL shader
                shader:Compile()
            else
                alert("I couldn't create a shader because I couldn't determine what graphics library was being used!")
            end
        end

        return GetShader(SKYBOX_FRAGMENT_SHADER)
    end
```

## 4. `Skybox.quorum`

**New `use` lines:**

```
use Libraries.Containers.Array
use Libraries.Compute.Math
use Libraries.Game.GameStateManager
use Libraries.Game.WebApplication
use Libraries.Game.Graphics.Vulkan.VulkanGraphics
use Libraries.Game.Graphics.Vulkan.VulkanTextureManager
```

`Vector3` and `Matrix4` are already imported; `Camera` and
`PerspectiveCamera` are in the same package.

**The comment on the constants** (lines 9-10) becomes:

```
    // OpenGL's names for the sides of a cube map. The load actions pass
    // these as they always have (front as negative z, back as positive z,
    // from before Quorum's world was left-handed); LoadCubeSide puts each
    // file on the face the renderer needs (Item 26).
```

**New field,** after `number inverter = 1`:

```
    // Under Vulkan, each side's pixels, kept until all six are loaded and
    // the cube can be made: right, left, up, down, front, back.
    Array<PixelMap> vulkanSides

    // The camera's directions for drawing the sky, from UpdateView.
    Vector3 viewRight
    Vector3 viewUp
    Vector3 viewForward
    Math math
```

**Every load action.** In `Load(File ...)` and the six `LoadRight` to
`LoadBack` actions (those taking a `File`), the block

```
        if cubeMap = undefined
            Texture texture
            cubeMap = texture
            InitializeCubeMap(texture)
        end
```

becomes `PrepareCubeMap()`. Each `LoadSide(file, cubeMap, SIDE)` becomes
`LoadCubeSide(file, SIDE)`, with the same constant. The two "Note that
positive Z in OpenGL is negative Z in Quorum" comments are removed. So
`LoadFront` becomes:

```
    action LoadFront(File image)
        PrepareCubeMap()
        LoadCubeSide(image, GL_TEXTURE_CUBE_MAP_NEGATIVE_Z)
    end
```

**New private actions,** after the `LoadSide` declaration:

```
    /*
    This action makes the cube map's Texture the first time a side is
    loaded. Under OpenGL it becomes a GL cube texture; under Vulkan it waits
    for all six sides.
    */
    private action PrepareCubeMap
        if cubeMap not= undefined
            return now
        end
        Texture texture
        cubeMap = texture
        if UsingVulkan()
            vulkanSides:SetSize(6)
        else
            InitializeCubeMap(texture)
        end
    end

    /*
    This action loads one side, given by its OpenGL constant as the load
    actions always have, onto the face the renderer needs:
    - Vulkan: the side's pixels are kept, and once all six are in, the
      texture manager makes the cube.
    - OpenGL on the desktop: front and back are swapped onto positive and
      negative z, which Quorum's left-handed world needs; the other sides
      are unchanged.
    - The web: unchanged, since it still draws with its own skybox shader.

    Attribute: Parameter file The image file.
    Attribute: Parameter side One of the GL_TEXTURE_CUBE_MAP constants above.
    */
    private action LoadCubeSide(File file, integer side)
        GameStateManager manager
        if UsingVulkan()
            PixelMap map
            map:LoadPixelMap(file)
            vulkanSides:Set(GetVulkanLayer(side), map)
            RecordSource(file, side)
            if HasAllVulkanSides()
                VulkanGraphics graphics = cast(VulkanGraphics, manager:GetGameGraphics())
                VulkanTextureManager textureManager = graphics:GetTextureManager()
                textureManager:RequestCubeLoad(cubeMap, vulkanSides)
            end
        elseif manager:GetApplication() is WebApplication
            LoadSide(file, cubeMap, side)
        else
            integer face = side
            if side = GL_TEXTURE_CUBE_MAP_NEGATIVE_Z
                face = GL_TEXTURE_CUBE_MAP_POSITIVE_Z
            elseif side = GL_TEXTURE_CUBE_MAP_POSITIVE_Z
                face = GL_TEXTURE_CUBE_MAP_NEGATIVE_Z
            end
            LoadSide(file, cubeMap, face)
            RecordSource(file, side)
        end
    end

    /*
    This action returns a side's layer in a Vulkan cube image, whose layers
    are +x, -x, +y, -y, +z, -z: right, left, up, down, front, back.

    Attribute: Parameter side One of the GL_TEXTURE_CUBE_MAP constants above.
    Attribute: Returns The layer, 0 to 5.
    */
    private action GetVulkanLayer(integer side) returns integer
        if side = GL_TEXTURE_CUBE_MAP_POSITIVE_X
            return 0
        elseif side = GL_TEXTURE_CUBE_MAP_NEGATIVE_X
            return 1
        elseif side = GL_TEXTURE_CUBE_MAP_POSITIVE_Y
            return 2
        elseif side = GL_TEXTURE_CUBE_MAP_NEGATIVE_Y
            return 3
        elseif side = GL_TEXTURE_CUBE_MAP_NEGATIVE_Z
            return 4
        end
        return 5
    end

    /*
    This action returns true once every side's pixels are in, under Vulkan.

    Attribute: Returns True if all six sides are loaded.
    */
    private action HasAllVulkanSides returns boolean
        integer i = 0
        repeat while i < 6
            if vulkanSides:Get(i) = undefined
                return false
            end
            i = i + 1
        end
        return true
    end

    /*
    This action remembers which file a side was loaded from. (Skybox.java
    did this, by OpenGL face, before the faces were swapped.)

    Attribute: Parameter file The image file.
    Attribute: Parameter side One of the GL_TEXTURE_CUBE_MAP constants above.
    */
    private action RecordSource(File file, integer side)
        if side = GL_TEXTURE_CUBE_MAP_POSITIVE_X
            rightSource = file
        elseif side = GL_TEXTURE_CUBE_MAP_NEGATIVE_X
            leftSource = file
        elseif side = GL_TEXTURE_CUBE_MAP_POSITIVE_Y
            upSource = file
        elseif side = GL_TEXTURE_CUBE_MAP_NEGATIVE_Y
            downSource = file
        elseif side = GL_TEXTURE_CUBE_MAP_NEGATIVE_Z
            frontSource = file
        else
            backSource = file
        end
    end

    /*
    This action returns true if the game draws with Vulkan.

    Attribute: Returns True under Vulkan.
    */
    private action UsingVulkan returns boolean
        GameStateManager manager
        return manager:GetGameGraphics() is VulkanGraphics
    end
```

**New public actions,** after `IsLoaded`:

```
    /*
    This action returns the cube map texture holding the six sides. It is
    used by the painters to draw the sky.

    Attribute: Returns The cube map, or undefined if no side is loaded yet.
    */
    action GetCubeMap returns Texture
        return cubeMap
    end

    /*
    This action returns the Skybox's rotation, as set by Rotate and
    SetToRotation.

    Attribute: Returns The rotation.
    */
    action GetRotation returns Matrix4
        return transform
    end

    /*
    This action returns 1 if the sky is shown as it is, or -1 if it is
    mirrored left to right (see InvertSkybox).

    Attribute: Returns 1 or -1.
    */
    action GetInverter returns number
        return inverter
    end

    /*
    This action works out, from a camera, the three vectors the painters'
    sky shaders need to find the direction through each pixel: the camera's
    forward direction, and its right and up directions, each as long as the
    view reaches at a distance of 1. A pixel at screen position (x, y), each
    from -1 at the left or bottom to 1 at the right or top, looks along
    forward + x × right + y × up. Using the camera's directions instead of
    its matrices keeps the sky the same in every renderer, and moving the
    camera never moves the sky. The painters call it each time they draw the
    sky; read the results with GetViewRight, GetViewUp and GetViewForward.

    Attribute: Parameter camera The camera the sky is seen from.
    Attribute: Returns True if the camera can show a sky, false for an orthographic camera.

    Attribute: Example
    use Libraries.Game.Game
    use Libraries.Game.Graphics.Skybox

    class Main is Game
        Skybox skybox

        action Main
            StartGame()
        end

        action CreateGame
            skybox:Load("Skybox/right.jpg", "Skybox/left.jpg", "Skybox/top.jpg", "Skybox/bottom.jpg", "Skybox/front.jpg", "Skybox/back.jpg")
            SetSkybox(skybox)
            if skybox:UpdateView(GetCamera3D())
                output "The camera looks along z " + skybox:GetViewForward():GetZ()
            end
        end
    end
    */
    action UpdateView(Camera camera) returns boolean
        if not (camera is PerspectiveCamera)
            return false
        end
        PerspectiveCamera perspective = cast(PerspectiveCamera, camera)
        number zoom = perspective:GetZoom()
        if zoom <= 0
            zoom = 1
        end
        // The same field of view the camera's projection uses (vertical).
        number halfHeight = math:Tangent(math:DegreesToRadians(perspective:GetFieldOfView() / zoom) / 2)
        number aspect = 1
        if camera:GetHeight() > 0
            aspect = camera:GetWidth() / camera:GetHeight()
        end

        viewForward:Set(camera:GetDirection())
        viewForward:Normalize()
        // In Quorum's left-handed world, up × forward points right.
        viewRight:Set(camera:GetUp())
        viewRight:CrossProduct(viewForward)
        viewRight:Normalize()
        // Made again from the other two, in case the camera's up isn't
        // exactly square to its direction.
        viewUp:Set(viewForward)
        viewUp:CrossProduct(viewRight)
        viewUp:Normalize()

        viewRight:Scale(halfHeight * aspect)
        viewUp:Scale(halfHeight)
        return true
    end

    /*
    This action returns the camera's right direction from the last
    UpdateView, as long as the view reaches sideways at a distance of 1.

    Attribute: Returns The right vector.
    */
    action GetViewRight returns Vector3
        return viewRight
    end

    /*
    This action returns the camera's up direction from the last UpdateView,
    as long as the view reaches upward at a distance of 1.

    Attribute: Returns The up vector.
    */
    action GetViewUp returns Vector3
        return viewUp
    end

    /*
    This action returns the camera's forward direction from the last
    UpdateView, of length 1.

    Attribute: Returns The forward vector.
    */
    action GetViewForward returns Vector3
        return viewForward
    end
```

Two layers sharing one `Skybox` with different cameras is fine: each
painter calls `UpdateView` right before it reads the vectors.

**`Dispose`:** also forget the Vulkan sides. Under Vulkan, the cube image
isn't freed, like any Vulkan texture today (order 11):

```
        vulkanSides:Empty()
```

**`InvertSkybox` documentation:** the paragraph becomes:

```
    The InvertSkybox action sets whether the Skybox's images are shown as
    they are (true, the default) or mirrored left to right (false).
```

## 5. `OpenGL/OpenGLPainter3D.quorum`

**The field** `SkyboxShader skyboxShader` (line 25) becomes:

```
    // The web's own skybox shader, made only on the web (Item 26).
    SkyboxShader webSkyboxShader = undefined
```

**New `use` lines:**

```
use Libraries.Game.WebApplication
use Libraries.Game.Graphics.Shaders.OpenGL.Mapping.SkyboxShaderMappingOpenGL
```

**`End` and `Flush`:** each block

```
            OpenGLManager graphics = GetGraphics()
            OpenGLConstants constants
            graphics:EnableProperty(constants:GL_DEPTH_TEST)
            graphics:EnableProperty(constants:GL_BLEND)
            skyboxShader:Render(skybox, camera)
```

becomes `RenderSkybox()`.

**New private action:**

```
    /*
    This action draws the skybox with the SkyboxShaderProgram, behind
    everything drawn so far. Only perspective cameras show a sky. The web
    still draws with its own skybox shader.
    */
    private action RenderSkybox
        OpenGLManager graphics = GetGraphics()
        OpenGLConstants constants
        GameStateManager gameState
        if gameState:GetApplication() is WebApplication
            if webSkyboxShader = undefined
                SkyboxShader shader
                webSkyboxShader = shader
            end
            graphics:EnableProperty(constants:GL_DEPTH_TEST)
            graphics:EnableProperty(constants:GL_BLEND)
            webSkyboxShader:Render(skybox, camera)
            return now
        end
        if not (camera is PerspectiveCamera)
            return now
        end

        ShaderManager shaders = gameState:GetShaderManager()
        ShaderProgram program = shaders:GetSkyboxShaderProgram()
        SkyboxShaderMappingOpenGL mapping = cast(SkyboxShaderMappingOpenGL, program:GetShaderMapping())
        program:Begin()
        mapping:SetSkybox(skybox)
        mapping:Begin(program, camera)
        // The triangle comes from the vertex number, so no vertex inputs
        // are used; the default vertex array is enough.
        graphics:UseDefaultVertexArray()
        graphics:DrawBuffer(constants:GL_TRIANGLES, 0, 3)
        mapping:End(program)
        program:End()
    end
```

## 6. `Vulkan/VulkanTextureManager.quorum`

**New fields,** after `Array<PixelMap> pendingPixelMaps`:

```
    // Cube textures waiting to be made (Item 26), each with its six sides.
    Array<Texture> pendingCubeTextures
    Array<Array<PixelMap>> pendingCubeSides
```

**New action,** after `RequestLoad`:

```
    /*
    This action asks for a cube texture to be made from six square images of
    the same size, in the order right, left, up, down, front, back (the
    +x, -x, +y, -y, +z, -z layers). It is made during the next frame. The
    texture gets its own image view and no place in the global texture
    array; a shader reads it through its own descriptor set.

    Attribute: Parameter texture The texture to hold the cube.
    Attribute: Parameter sides The six images.
    */
    action RequestCubeLoad(Texture texture, Array<PixelMap> sides)
        if sides:GetSize() not= 6
            alert("A cube texture needs 6 images, but was given " + sides:GetSize() + ".")
        end
        Array<PixelMap> copy
        integer i = 0
        repeat while i < 6
            copy:Add(sides:Get(i))
            i = i + 1
        end
        pendingCubeTextures:Add(texture)
        pendingCubeSides:Add(copy)
    end
```

**`ProcessPendingTextures`:** the first check becomes

```
        if pendingTextures:IsEmpty() and pendingCubeTextures:IsEmpty()
            return now
        end
```

and after `pendingPixelMaps:Empty()`:

```
        i = 0
        repeat while i < pendingCubeTextures:GetSize()
            LoadCubeTexture(pendingCubeTextures:Get(i), pendingCubeSides:Get(i), commandBuffer, graphics)
            i = i + 1
        end
        pendingCubeTextures:Empty()
        pendingCubeSides:Empty()
```

**New private action:**

```
    /*
    This action makes a cube image from six sides: a six-layer image that
    can be viewed as a cube, one staging buffer and copy per side, and a
    cube view, set on the texture.

    Attribute: Parameter texture The texture to hold the cube.
    Attribute: Parameter sides The six images, right, left, up, down, front, back.
    Attribute: Parameter commandBuffer The frame's command buffer, recording.
    Attribute: Parameter graphics The Vulkan graphics.
    */
    private action LoadCubeTexture(Texture texture, Array<PixelMap> sides, VulkanCommandBuffer commandBuffer, VulkanGraphics graphics)
        VulkanDevice device = graphics:GetDevice()
        VulkanConstants constants
        BitwiseOperations bits

        integer size = sides:Get(0):GetWidth()
        integer i = 0
        repeat while i < 6
            PixelMap side = sides:Get(i)
            if side:GetWidth() not= size or side:GetHeight() not= size
                alert("A skybox's six images must be square and the same size. The first is " + size + " by " + size +
                    ", but image " + (i + 1) + " is " + side:GetWidth() + " by " + side:GetHeight() + ".")
            end
            i = i + 1
        end

        VulkanImage image
        VulkanImageInfo imageInfo
        imageInfo:SetWidth(size)
        imageInfo:SetHeight(size)
        imageInfo:SetArrayLayers(6)
        imageInfo:SetFlags(constants:IMAGE_CREATE_CUBE_COMPATIBLE_BIT)
        imageInfo:SetUsage(bits:Or(constants:IMAGE_USAGE_TRANSFER_DESTINATION_BIT, constants:IMAGE_USAGE_SAMPLED_BIT))
        imageInfo:SetFormat(constants:FORMAT_R8G8B8A8_UNORM)
        image:Create(device, imageInfo)

        VulkanImageMemoryBarrier toTransfer
        toTransfer:SetNewLayout(constants:IMAGE_LAYOUT_TRANSFER_DESTINATION_OPTIMAL)
        toTransfer:SetSourceAccessMask(0)
        toTransfer:SetDestinationAccessMask(constants:ACCESS_TRANSFER_WRITE_BIT)
        toTransfer:SetSourceStageMask(constants:PIPELINE_STAGE_TOP_OF_PIPE_BIT)
        toTransfer:SetDestinationStageMask(constants:PIPELINE_STAGE_TRANSFER_BIT)
        toTransfer:SetAspectMask(constants:IMAGE_ASPECT_COLOR_BIT)
        toTransfer:SetLayerCount(6)
        toTransfer:SetImage(image)
        PipelineBarrierCommand toTransferCommand
        toTransferCommand:SetMemoryBarrier(toTransfer)
        commandBuffer:Record(toTransferCommand)

        // One staging buffer and copy per side, into its layer.
        i = 0
        repeat while i < 6
            VulkanBuffer buffer
            buffer:CreateTransferSourceBuffer(device, size * size * 4)
            buffer:BeginMapping()
            TransferPixelData(sides:Get(i), buffer)
            stagingBuffers:Add(buffer)

            CopyBufferToImageCommand copyCommand
            copyCommand:SetImageWidth(size)
            copyCommand:SetImageHeight(size)
            copyCommand:SetAspectMask(constants:IMAGE_ASPECT_COLOR_BIT)
            copyCommand:SetBaseArrayLayer(i)
            copyCommand:SetLayerCount(1)
            copyCommand:SetSourceBuffer(buffer)
            copyCommand:SetDestinationImage(image)
            commandBuffer:Record(copyCommand)
            i = i + 1
        end

        VulkanImageMemoryBarrier toRead
        toRead:SetOldLayout(constants:IMAGE_LAYOUT_TRANSFER_DESTINATION_OPTIMAL)
        toRead:SetNewLayout(constants:IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL)
        toRead:SetSourceAccessMask(constants:ACCESS_TRANSFER_WRITE_BIT)
        toRead:SetDestinationAccessMask(constants:ACCESS_SHADER_READ_BIT)
        toRead:SetSourceStageMask(constants:PIPELINE_STAGE_TRANSFER_BIT)
        toRead:SetDestinationStageMask(constants:PIPELINE_STAGE_FRAGMENT_SHADER_BIT)
        toRead:SetAspectMask(constants:IMAGE_ASPECT_COLOR_BIT)
        toRead:SetLayerCount(6)
        toRead:SetImage(image)
        PipelineBarrierCommand toReadCommand
        toReadCommand:SetMemoryBarrier(toRead)
        commandBuffer:Record(toReadCommand)

        VulkanImageView view
        VulkanImageViewInfo viewInfo
        viewInfo:SetFormat(constants:FORMAT_R8G8B8A8_UNORM)
        viewInfo:SetViewType(constants:IMAGE_VIEW_TYPE_CUBE)
        viewInfo:SetLayerCount(6)
        view:Create(device, image, viewInfo)
        texture:SetVulkanImageView(view)
    end
```

## 7. `Vulkan/VulkanPainter3D.quorum`

**New `use` lines:**

```
use Libraries.Game.Graphics.Texture
use Libraries.Compute.Vector3
```

**New fields,** after `VulkanPushConstantBuffer shadowPushConstants = undefined`:

```
    // The layer's skybox (Item 26), drawn first in the result pass. Each
    // frame slot has its own descriptor set for the cube, linked again only
    // when the cube's view changes.
    Skybox skybox = undefined
    VulkanPushConstantBuffer skyboxPushConstants = undefined
    VulkanDescriptorSetLayout skyboxLayout = undefined
    Array<VulkanDescriptorSet> skyboxDescriptors
    Array<VulkanImageView> skyboxLinkedViews
```

**`SetSkybox`** (line 1951) becomes:

```
    action SetSkybox(Skybox skybox)
        me:skybox = skybox
    end
```

**In `End`'s result pass,** right after
`commandBuffer:Record(beginResultRender)`:

```
        // The sky goes down first. The lit image is copied over it with its
        // alpha, which is 0 where nothing was drawn, so the sky shows there.
        RecordSkybox(commandBuffer, swapchain, resourceIndex)
```

**New private actions:**

```
    /*
    This action draws the skybox, if the layer has one that is loaded and
    the camera is a perspective camera: the skybox program's full-screen
    triangle, with the camera's directions and the sky's rotation in push
    constants, and the cube in its own descriptor set.

    Attribute: Parameter commandBuffer The frame's command buffer, in the result pass.
    Attribute: Parameter swapchain The swapchain.
    Attribute: Parameter resourceIndex The frame slot.
    */
    private action RecordSkybox(VulkanCommandBuffer commandBuffer, VulkanSwapchain swapchain, integer resourceIndex)
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

        ShaderManager shaders = gameState:GetShaderManager()
        ShaderProgram program = shaders:GetSkyboxShaderProgram()
        VulkanShaderProgram strategy = cast(VulkanShaderProgram, program:GetShaderProgramStrategy())
        VulkanPipeline pipeline = strategy:GetPipeline()
        if pipeline = undefined
            strategy:CreatePipeline(resultRenderPass)
            pipeline = strategy:GetPipeline()
        end
        VulkanPipelineLayout layout = pipeline:GetInfo():GetLayout()

        BindPipelineCommand bindPipeline
        bindPipeline:SetPipeline(pipeline)
        commandBuffer:Record(bindPipeline)
        SetResultViewportAndScissor(commandBuffer, swapchain)

        BindDescriptorSetCommand bindCube
        bindCube:SetPipelineLayout(layout)
        bindCube:SetDescriptorSet(GetSkyboxDescriptor(resourceIndex, cube:GetVulkanImageView()))
        commandBuffer:Record(bindCube)

        if skyboxPushConstants = undefined
            VulkanPushConstantBuffer buffer
            buffer:Create(112)
            skyboxPushConstants = buffer
        end
        Vector3 right = skybox:GetViewRight()
        Vector3 up = skybox:GetViewUp()
        Vector3 forward = skybox:GetViewForward()
        skyboxPushConstants:ResetWritePosition()
        skyboxPushConstants:AddNumber32Bit(right:GetX())
        skyboxPushConstants:AddNumber32Bit(right:GetY())
        skyboxPushConstants:AddNumber32Bit(right:GetZ())
        skyboxPushConstants:AddNumber32Bit(skybox:GetInverter())
        skyboxPushConstants:AddNumber32Bit(up:GetX())
        skyboxPushConstants:AddNumber32Bit(up:GetY())
        skyboxPushConstants:AddNumber32Bit(up:GetZ())
        skyboxPushConstants:AddNumber32Bit(0)
        skyboxPushConstants:AddNumber32Bit(forward:GetX())
        skyboxPushConstants:AddNumber32Bit(forward:GetY())
        skyboxPushConstants:AddNumber32Bit(forward:GetZ())
        skyboxPushConstants:AddNumber32Bit(0)
        skyboxPushConstants:AddMatrix4(skybox:GetRotation())

        SetPushConstantsCommand setPushConstants
        setPushConstants:SetData(skyboxPushConstants)
        setPushConstants:SetPipelineLayout(layout)
        setPushConstants:SetStageFlags(constants:SHADER_STAGE_FRAGMENT_BIT)
        commandBuffer:Record(setPushConstants)

        DrawCommand drawSky
        drawSky:SetVertexCount(3)
        commandBuffer:Record(drawSky)
    end

    /*
    This action returns a frame slot's descriptor set for the sky's cube,
    making it the first time, and linking it to the cube's view when the
    view changes. A slot's set is only changed after its previous frame has
    finished with it.

    Attribute: Parameter resourceIndex The frame slot.
    Attribute: Parameter view The cube's image view.
    Attribute: Returns The descriptor set.
    */
    private action GetSkyboxDescriptor(integer resourceIndex, VulkanImageView view) returns VulkanDescriptorSet
        VulkanConstants constants
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        if skyboxLayout = undefined
            VulkanDescriptorSetLayout layout
            Array<VulkanDescriptorSetLayoutBinding> bindings
            VulkanDescriptorSetLayoutBinding samplerBinding
            samplerBinding:SetBinding(0)
            samplerBinding:SetDescriptorType(constants:DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER)
            samplerBinding:SetDescriptorCount(1)
            samplerBinding:SetStageFlags(constants:SHADER_STAGE_FRAGMENT_BIT)
            bindings:Add(samplerBinding)
            layout:Create(graphics:GetDevice(), bindings)
            skyboxLayout = layout
        end

        VulkanDescriptorSetManager descriptorSetManager = graphics:GetDescriptorSetManager()
        repeat while skyboxDescriptors:GetSize() <= resourceIndex
            VulkanDescriptorSet newSet = descriptorSetManager:CreateDescriptorSet(skyboxLayout)
            skyboxDescriptors:Add(newSet)
            skyboxLinkedViews:Add(undefined)
        end

        VulkanDescriptorSet set = skyboxDescriptors:Get(resourceIndex)
        if skyboxLinkedViews:Get(resourceIndex) not= view
            VulkanDescriptorResourcesInfo resources
            VulkanDescriptorImageInfo image
            image:SetImageView(view)
            image:SetSampler(resultSampler)
            image:SetImageLayout(constants:IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL)
            Array<VulkanDescriptorImageInfo> images
            images:Add(image)
            resources:SetImageInfo(images)
            resources:SetDescriptorType(constants:DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER)
            set:LinkResources(resources)
            skyboxLinkedViews:Set(resourceIndex, view)
        end
        return set
    end
```

`resultSampler` repeats at the edges, but cube lookups ignore the wrap
setting (Vulkan always filters cube faces seamlessly), so it serves.

## 8. `Skybox.java` (`QuorumPlugins` copy)

In `LoadSide`, the `switch (side)` that sets `rightSource` to
`frontSource` is removed. Quorum's `RecordSource` does it now, by the side
the game asked for, not the OpenGL face. The web's `Skybox.js` keeps its own
bookkeeping, since the web still loads the old way.

The older `Plugins/GamePlugin/JavaGame` copies of `Skybox.java` and
`SkyboxShader.java` are left alone.

## Size

- **New:** 7 small classes, about 450 lines with documentation.
- **Changed:**
  - `ShaderManager` +70;
  - `Skybox` +230 −40;
  - `OpenGLPainter3D` +40 −12;
  - `VulkanTextureManager` +130;
  - `VulkanPainter3D` +140;
  - `Skybox.java` −20.

## What changes for existing games

- **Desktop OpenGL games with a skybox** (BlockBreaker) draw it with the
  new program. Front and back are now placed for the left-handed world.
  - If the old sky showed mirrored or turned, it now shows correctly.
  - If a game worked around the old placement (by swapping its files, or
    with `InvertSkybox(false)`), its sky changes. BlockBreaker is the check.
- **Vulkan games get a skybox** for the first time.
- **The web is unchanged.**
- **Orthographic cameras** draw no sky (OpenGL drew one before, with
  meaningless directions).

## Risks and things to know

- **Face placement** comes from the spec's face table, worked through by
  hand. `SkyboxCheck` checks each face's place, upright, and not mirrored.
  If one is off, the fix is in one place (`LoadCubeSide`'s swap, or
  `GetVulkanLayer`).
- **Matrix order for the rotation:** OpenGL gets it through
  `SetShaderInputMatrix` and Vulkan through `AddMatrix4`, the same way
  other matrices go to each. If one renderer turns the sky the other way,
  that renderer's row-or-column order is the cause.
- **OpenGL with no vertex inputs:** the program has none. The default
  vertex array is bound, and meshes switch their inputs off after drawing.
  If a driver complains, a three-vertex buffer is the fallback.
- **Vulkan cube memory** isn't freed on `Dispose`, like every Vulkan
  texture today (order 11).
- **Loading a side again under Vulkan** after all six are in makes a new
  cube image. Fine for occasional sky changes.
- **MoltenVK:**
  - a six-layer, cube-compatible image with a cube view becomes a Metal
    cube texture;
  - push constants become a small buffer;
  - `samplerCube` becomes `texturecube`.

## Test plan

**`SkyboxCheck.quorum`** (project; written when this is applied). It runs
under both renderers, with one `UseVulkan` line to switch.
- **A made-up sky:** six 256 by 256 images made with `PixelMap`:
  - front red, back cyan, left green, right magenta, top white, bottom
    dark grey;
  - each with a yellow bar along its top edge and a blue square near its
    right edge, so turned or mirrored faces show.
- **Keys:**
  - arrow keys turn and tilt the camera;
  - R starts the sky turning around the vertical;
  - I switches `InvertSkybox`;
  - V adds two solid boxes and a half-transparent box in front;
  - the console says which way the camera faces.
- **Check:**
  1. at start, facing +z: red, yellow bar on top, blue square on the right;
  2. turning right shows magenta, left green, behind cyan, up white, down
     grey, each upright and unmirrored. Looking up, the white face's
     yellow bar is toward the back. Looking down, the grey face's bar is
     toward the front;
  3. moving the camera doesn't move the sky;
  4. boxes cover the sky; the half-transparent box shows the sky through
     it (Vulkan: through the lit image's alpha);
  5. no seams along the cube's edges;
  6. R turns the sky, and I mirrors it left to right;
  7. resizing the window keeps the sky's proportions.

**Then:**
- BlockBreaker (OpenGL);
- TextureUpdateCheck and DriveOpen, to make sure nothing else changed;
- a real sky set in DriveOpen.

## Rollback

Delete the seven new classes, then revert:
- `ShaderManager`, `Skybox`, `OpenGLPainter3D`, `VulkanTextureManager` and
  `VulkanPainter3D`;
- `Skybox.java`.

Then rebuild the library and plugins.
