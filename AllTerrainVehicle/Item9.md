# Item 9: draw a 3D model with its own shader program

`LibraryChangesPlan.md` order 9, `VulkanChanges.md` #6. **Approved and
applied on 2026-10-18** to the `quorum-language` branch `TerrainShader`,
along with the project-side switch to Route 2.

**Runs:** compiled and ran on 2026-10-18. The splat program compiled and
the splat textures became ready. The run then crashed after the window was
minimized and restored. That was an older painter bug, not this change: it is
`VulkanChanges.md` #23, now fixed (library order 12). Waiting for a rerun to
check the look, the car and shadows.

Paths are under
`quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/`.

## Why

`Model:SetShaderProgram` exists, but the Vulkan 3D painter ignores it: every
model is drawn with the one default program
(`Vulkan/VulkanPainter3D.quorum:1098`, "TO-DO: Support custom shaders for
3D"). The 2D Vulkan painter already honors a drawable's program
(`VulkanPainter2D.quorum:593`), so this brings 3D in line with 2D.

For us, it replaces the splat prototype's trick (Route 1 in
`TextureSplattingPlan.md`):
- Today, `TerrainSplatShaderProgram:InstallAsDefault` compiles the splat
  shader under the default program's name, so **every** model in the game is
  drawn with it.
- Terrain is told apart by a marker: a metallic value of -1.

After this change, only the terrain models get the splat program, through
`SetShaderProgram`, and the default shader is left alone.

## How 3D drawing works now (the parts that matter)

- **Batches.** `Render(model)` puts each model into a
  `VulkanPainter3DBatch`. There is one batch per blueprint (one table for
  opaque, one for transparent), so all instances of one blueprint are drawn
  together.
- **Draw queues.** At `End`, each batch writes its instances into a
  `VulkanDrawQueue3D`:
  - A queue holds per-instance data (104 bytes each) and indirect draw
    commands, one per mesh, each covering a run of instances.
  - There is one queue per texture group, and one set of queues per frame
    in flight (`drawQueues`).
  - `GetCurrentDrawQueue(group)` picks the queue.
- **Geometry pass.** It binds the default pipeline and the camera
  descriptor set. Then, for each queue, it binds that group's textures
  (set 1), pushes the queue's instance-buffer address as a push constant,
  and draws indirect.
- **Shadow pass.** For each light, it binds the shadow pipeline and draws
  each queue's shadow draw commands, using the same instance buffer.
- **Pipelines** are made lazily from a program's strategy:
  `VulkanShaderProgram:CreatePipeline(renderPass)`, with the layout coming
  from its shader mapping. `DefaultShaderMapping3DVulkan` makes the default
  3D layout (`AddDefaultInfo3D`) and sets the existing flag
  `UsesDefaultResources3D()` to true. Nothing reads that flag today.

## The design

**One rule for custom programs:** the program's shader mapping must use the
default 3D resources (`UsesDefaultResources3D()`), which in practice means a
`DefaultShaderMapping3DVulkan`. Then:
- its pipeline layout matches the default one (camera at set 0, textures
  at set 1, an 8-byte push constant);
- it reads the same instance data and vertices;
- it writes the same four G-buffer outputs (position, color, normal, PBR),
  so lighting and shadows keep working.

The painter checks the flag the first time it sees a program and gives a
clear alert if it's wrong, rather than letting a mismatched layout misbehave
on the GPU.

The changes:

1. **Batches are kept per program.** Models with no program, or with the
   default program, use the existing tables exactly as now. A model with
   another program goes into a batch keyed by (program, blueprint), and the
   batch remembers its program.
2. **Draw queues are kept per program.** The default program keeps
   `drawQueues`, unchanged. Each custom program gets its own set, laid out
   the same way (per frame slot, then per texture group), made the first
   time the program is used. A batch asks
   `GetCurrentDrawQueue(program, group)`; with no program, that is the
   existing `GetCurrentDrawQueue(group)`.
3. **Geometry pass:** after the default queues are drawn, as now, each
   custom program in turn:
   - its pipeline is made if needed, against the scene render pass, the
     same way the default one is;
   - it is bound, and the camera descriptor set is bound again for its
     layout;
   - its queues are drawn exactly like the default ones (texture set,
     push constant, draw indirect).
4. **Shadow pass:** unchanged pipeline (shadows use the default shadow
   program for everything, as the plan says). It now draws the custom
   programs' queues too, so terrain still casts shadows. To avoid copying
   the long shadow loop, it walks one list of queues: the default ones, in
   the same order as today, then the custom ones. It takes the texture group
   from `queue:GetTextureGroupID()` instead of the loop counter, which is
   the same number for the default queues.

Custom programs are drawn in the order they were first used, so the order
is the same every frame.

### What does not change

- Models without a custom program: same batches, same queues, same commands
  in the same order. The only extra work is one `GetShaderProgram()` check
  in `GetBatch`.
- The lighting pass, the result pass, the animation compute pass, and the
  barriers.
- OpenGL. This is only the Vulkan 3D painter.

## The code changes

Two files: `Vulkan/VulkanPainter3DBatch.quorum` and
`Vulkan/VulkanPainter3D.quorum`.

### 1. VulkanPainter3DBatch.quorum

#### 1a. New import

```quorum
use Libraries.Game.Graphics.Shaders.Programs.ShaderProgram
```

#### 1b. New field (after `boolean isTransparent = false`, line 21)

```quorum
    // The shader program this batch's models are drawn with, or undefined
    // for the default program.
    ShaderProgram program = undefined
```

#### 1c. `Create`: a second version that takes the program

Before (lines 31-43): `action Create(ModelBlueprintVulkan schematic, boolean isTransparent)`.

After: the existing action calls the new one, so its behavior is unchanged.

```quorum
    action Create(ModelBlueprintVulkan schematic, boolean isTransparent)
        Create(schematic, isTransparent, undefined)
    end
    
    /*
    This action sets up the batch for one blueprint, drawn with the given
    shader program.

    Attribute: Parameter schematic The blueprint whose models this batch draws.
    Attribute: Parameter isTransparent True if the models have transparency.
    Attribute: Parameter program The shader program to draw with, or undefined for the default.
    */
    action Create(ModelBlueprintVulkan schematic, boolean isTransparent, ShaderProgram program)
        me:schematic = schematic
        me:isTransparent = isTransparent
        me:program = program
        
        Array<MeshVulkan> meshes = schematic:GetMeshes()
        meshesPerModel = meshes:GetSize()
        
        integer i = 0
        repeat while i < meshesPerModel
            totalVertices = totalVertices + meshes:Get(i):GetVertexCount()
            i = i + 1
        end
    end
    
    /*
    This action returns the shader program the batch is drawn with.

    Attribute: Returns The program, or undefined for the default program.
    */
    action GetProgram returns ShaderProgram
        return program
    end
```

#### 1d. `ProcessBatch`: ask for the program's queues

Five calls change from `painter:GetCurrentDrawQueue(x)` to
`painter:GetCurrentDrawQueue(program, x)`. They are at lines 123, 125, 155,
158 and 169. Nothing else in the action changes. For example:

Before:

```quorum
                        queue = painter:GetCurrentDrawQueue(textureOverride:GetVulkanTextureGroupIndex())
```

After:

```quorum
                        queue = painter:GetCurrentDrawQueue(program, textureOverride:GetVulkanTextureGroupIndex())
```

With `program` undefined (every batch today), the new call returns exactly
what the old one did.

### 2. VulkanPainter3D.quorum

#### 2a. New fields

After `Array<VulkanPainter3DBatch> pendingTransparentBatches` (line 87):

```quorum
    // Batches for models drawn with their own shader program instead of the
    // default one. There is one table per program, keyed by blueprint like
    // batches and transparentBatches.
    HashTable<ShaderProgram, HashTable<ModelBlueprint, VulkanPainter3DBatch>> programBatches
    HashTable<ShaderProgram, HashTable<ModelBlueprint, VulkanPainter3DBatch>> programTransparentBatches
```

After `Array<Array<VulkanDrawQueue3D>> drawQueues` (line 91):

```quorum
    // Draw queues for models drawn with their own shader program. For each
    // program there is one array per swapchain image, laid out like
    // drawQueues. customPrograms keeps the programs in the order they were
    // first used, so they are drawn in the same order every frame.
    HashTable<ShaderProgram, Array<Array<VulkanDrawQueue3D>>> programDrawQueues
    Array<ShaderProgram> customPrograms
```

#### 2b. `GetBatch`: send models with their own program elsewhere

Before (lines 864-886): it looks up the batch by blueprint in `batches`
or `transparentBatches`.

After: two lines added at the top. The rest is unchanged.

```quorum
    private action GetBatch(Model model) returns VulkanPainter3DBatch
        ShaderProgram program = GetCustomProgram(model)
        if program not= undefined
            return GetProgramBatch(model, program)
        end
        
        boolean isTransparent = model:HasTransparency()
        ... (unchanged) ...
    end
```

#### 2c. New private actions for batches

```quorum
    /*
    This action returns the shader program a model asks to be drawn with,
    or undefined if it should be drawn with the default program. A model
    given the default program itself is drawn with the default batches.

    Attribute: Parameter model The model being drawn.
    Attribute: Returns The model's own program, or undefined for the default.
    */
    private action GetCustomProgram(Model model) returns ShaderProgram
        ShaderProgram program = model:GetShaderProgram()
        if program = undefined
            return undefined
        end
        ShaderProgram defaultOne = GetDefaultProgram()
        if program = defaultOne
            return undefined
        end
        return program
    end
    
    /*
    This action finds or makes the batch for a model drawn with its own
    shader program. The first time a program is seen, it is checked.

    Attribute: Parameter model The model being drawn.
    Attribute: Parameter program The model's own shader program.
    Attribute: Returns The batch for the model's blueprint and program.
    */
    private action GetProgramBatch(Model model, ShaderProgram program) returns VulkanPainter3DBatch
        boolean isTransparent = model:HasTransparency()
        ModelBlueprintVulkan schematic = cast(ModelBlueprintVulkan, model:GetModelBlueprint())
        
        HashTable<ShaderProgram, HashTable<ModelBlueprint, VulkanPainter3DBatch>> tables = programBatches
        if isTransparent
            tables = programTransparentBatches
        end
        
        HashTable<ModelBlueprint, VulkanPainter3DBatch> table = undefined
        if tables:HasKey(program)
            table = tables:GetValue(program)
        else
            CheckCustomProgram(program)
            HashTable<ModelBlueprint, VulkanPainter3DBatch> newTable
            tables:Add(program, newTable)
            table = newTable
        end
        
        if table:HasKey(schematic)
            return table:GetValue(schematic)
        end
        VulkanPainter3DBatch batch
        batch:Create(schematic, isTransparent, program)
        table:Add(schematic, batch)
        return batch
    end
    
    /*
    This action makes sure a custom program can draw 3D models: it is
    compiled, and its shader mapping uses the default 3D resources, so its
    layout matches what the painter binds.

    Attribute: Parameter program The program to check.
    */
    private action CheckCustomProgram(ShaderProgram program)
        if not program:IsCompiled()
            program:Compile()
        end
        VulkanShaderProgram strategy = cast(VulkanShaderProgram, program:GetShaderProgramStrategy())
        if not strategy:GetShaderMapping():UsesDefaultResources3D()
            alert("I can't draw 3D models with the shader program " + program:GetName() + " because its shader mapping doesn't use the default 3D resources. A DefaultShaderMapping3DVulkan does.")
        end
    end
```

#### 2d. `GetCurrentDrawQueue`: a program version, and a shared helper

Before (lines 1658-1687): one public action that finds the current frame's
array and makes the group's queue if needed.

After: the public action keeps its name and behavior. Its body moves into
`GetQueueForGroup`, word for word, apart from taking the array as a
parameter.

```quorum
    action GetCurrentDrawQueue(integer textureGroupID) returns VulkanDrawQueue3D
        GameStateManager manager
        VulkanGraphics graphics = cast(VulkanGraphics, manager:GetGameGraphics())
        integer resourceIndex = graphics:GetCurrentResourceIndex()
        return GetQueueForGroup(drawQueues:Get(resourceIndex), textureGroupID)
    end
    
    /*
    This action returns this frame's draw queue for a shader program and a
    texture group, making it if needed.

    Attribute: Parameter program The shader program, or undefined for the default.
    Attribute: Parameter textureGroupID The texture group the queue draws from.
    Attribute: Returns The draw queue.
    */
    action GetCurrentDrawQueue(ShaderProgram program, integer textureGroupID) returns VulkanDrawQueue3D
        if program = undefined
            return GetCurrentDrawQueue(textureGroupID)
        end
        return GetQueueForGroup(GetCurrentProgramQueues(program), textureGroupID)
    end
    
    /*
    This action returns this frame's array of draw queues for a custom
    shader program, indexed by texture group. The first time a program is
    used, its arrays are made and it is added to customPrograms.

    Attribute: Parameter program A custom shader program.
    Attribute: Returns The program's draw queues for this frame.
    */
    private action GetCurrentProgramQueues(ShaderProgram program) returns Array<VulkanDrawQueue3D>
        GameStateManager manager
        VulkanGraphics graphics = cast(VulkanGraphics, manager:GetGameGraphics())
        integer resourceIndex = graphics:GetCurrentResourceIndex()
        
        Array<Array<VulkanDrawQueue3D>> perImage = undefined
        if programDrawQueues:HasKey(program)
            perImage = programDrawQueues:GetValue(program)
        else
            Array<Array<VulkanDrawQueue3D>> newPerImage
            programDrawQueues:Add(program, newPerImage)
            customPrograms:Add(program)
            perImage = newPerImage
        end
        
        repeat while perImage:GetSize() <= resourceIndex
            Array<VulkanDrawQueue3D> queueArray
            perImage:Add(queueArray)
        end
        return perImage:Get(resourceIndex)
    end
    
    /*
    This action returns the draw queue for a texture group from one frame's
    array of queues, making it if needed. Missing entries before it are
    filled with undefined.

    Attribute: Parameter array One frame's draw queues, indexed by texture group.
    Attribute: Parameter textureGroupID The texture group the queue draws from.
    Attribute: Returns The draw queue.
    */
    private action GetQueueForGroup(Array<VulkanDrawQueue3D> array, integer textureGroupID) returns VulkanDrawQueue3D
        GameStateManager manager
        VulkanGraphics graphics = cast(VulkanGraphics, manager:GetGameGraphics())
        VulkanDevice device = graphics:GetDevice()
        
        // Elements are indexed in the array to match their texture group index.
        ... (the rest of today's body, unchanged) ...
        return array:Get(textureGroupID)
    end
    
    /*
    This action returns true if any queue in the array has draw commands.

    Attribute: Parameter queues One frame's draw queues.
    Attribute: Returns True if there is something to draw.
    */
    private action HasDrawCommands(Array<VulkanDrawQueue3D> queues) returns boolean
        integer i = 0
        repeat while i < queues:GetSize()
            VulkanDrawQueue3D queue = queues:Get(i)
            if queue not= undefined and queue:GetDrawCommandCount() > 0
                return true
            end
            i = i + 1
        end
        return false
    end
```

#### 2e. `End`: reset the custom queues each frame

After the existing loop that calls `queue:Begin()` on every default queue
(lines 1108-1120), add:

```quorum
        // Also reset this frame's queues for custom shader programs.
        integer programIndex = 0
        repeat while programIndex < customPrograms:GetSize()
            Array<VulkanDrawQueue3D> programQueues = GetCurrentProgramQueues(customPrograms:Get(programIndex))
            integer queueIndex = 0
            repeat while queueIndex < programQueues:GetSize()
                VulkanDrawQueue3D programQueue = programQueues:Get(queueIndex)
                if programQueue not= undefined
                    programQueue:Begin()
                end
                queueIndex = queueIndex + 1
            end
            programIndex = programIndex + 1
        end
```

Only the current frame's custom queues are reset, since those are the only
ones written this frame. (The existing loop resets every frame's default
queues. That only resets counters, so it's harmless, and it's left alone.)

#### 2f. `End`: draw the custom programs in the geometry pass

Inserted after the default draw loop (it ends at line 1212) and before
`EndRenderPassCommand endRenderPass`:

```quorum
        // Then draw the models that have their own shader programs, one
        // program at a time. Their layout matches the default program's, so
        // the same camera, textures and push constant are used.
        programIndex = 0
        repeat while programIndex < customPrograms:GetSize()
            ShaderProgram program = customPrograms:Get(programIndex)
            Array<VulkanDrawQueue3D> programQueues = GetCurrentProgramQueues(program)
            if HasDrawCommands(programQueues)
                VulkanShaderProgram programStrategy = cast(VulkanShaderProgram, program:GetShaderProgramStrategy())
                if programStrategy:GetPipeline() = undefined
                    programStrategy:CreatePipeline(sceneRenderPass)
                end
                VulkanPipeline programPipeline = programStrategy:GetPipeline()
                VulkanPipelineLayout programLayout = programPipeline:GetInfo():GetLayout()
                
                BindPipelineCommand bindProgramPipeline
                bindProgramPipeline:SetPipeline(programPipeline)
                commandBuffer:Record(bindProgramPipeline)
                
                BindDescriptorSetCommand programCameraBind
                programCameraBind:SetPipelineLayout(programLayout)
                programCameraBind:SetDescriptorSet(currentCameraDescriptor)
                commandBuffer:Record(programCameraBind)
                
                integer group = 0
                repeat while group < programQueues:GetSize()
                    VulkanDrawQueue3D programQueue = programQueues:Get(group)
                    if programQueue not= undefined and programQueue:GetDrawCommandCount() > 0
                        BindDescriptorSetCommand programTexturesBind
                        programTexturesBind:SetPipelineLayout(programLayout)
                        programTexturesBind:SetDescriptorSet(textureManager:GetGlobalTextureDescriptorSet(group))
                        programTexturesBind:SetSetIndex(1)
                        commandBuffer:Record(programTexturesBind)
                        
                        pushConstants:ResetWritePosition()
                        pushConstants:AddBufferPointer(programQueue:GetInstanceDataBuffer())
                        SetPushConstantsCommand programPushConstants
                        programPushConstants:SetData(pushConstants)
                        programPushConstants:SetPipelineLayout(programPipeline:GetLayout())
                        programPushConstants:SetStageFlags(constants:SHADER_STAGE_VERTEX_BIT + constants:SHADER_STAGE_FRAGMENT_BIT)
                        commandBuffer:Record(programPushConstants)
                        
                        DrawIndirectCommand programDraw
                        programDraw:SetDrawCommands(programQueue:GetDrawCommandBuffer())
                        programDraw:SetDrawCount(programQueue:GetDrawCommandCount())
                        commandBuffer:Record(programDraw)
                    end
                    group = group + 1
                end
            end
            programIndex = programIndex + 1
        end
```

This is the default loop's body with the program's pipeline and layout in
place of the default ones. The viewport, scissor and dummy vertex buffer
are already set for the render pass, and binding a pipeline doesn't clear
them.

#### 2g. `End`: shadows for the custom programs' queues

Before the light loop (just after `integer shadowMapSize = ...`, line
1246), build the list of queues to draw:

```quorum
        // The queues the shadow pass draws: the default ones, in the same
        // order as before, then each custom program's. Every model casts
        // shadows with the default shadow program, whatever program draws it.
        Array<VulkanDrawQueue3D> shadowQueues
        integer queueCounter = 0
        repeat while queueCounter < drawQueues:GetSize()
            shadowQueues:Add(GetCurrentDrawQueue(queueCounter))
            queueCounter = queueCounter + 1
        end
        programIndex = 0
        repeat while programIndex < customPrograms:GetSize()
            Array<VulkanDrawQueue3D> programQueues = GetCurrentProgramQueues(customPrograms:Get(programIndex))
            queueCounter = 0
            repeat while queueCounter < programQueues:GetSize()
                shadowQueues:Add(programQueues:Get(queueCounter))
                queueCounter = queueCounter + 1
            end
            programIndex = programIndex + 1
        end
```

(`Array` has no action to add a whole array at once, hence the inner loop.
Undefined entries are copied too, and the shadow loop already skips them.)

Then, in the inner shadow loop (lines 1309-1352), three lines change:

Before:

```quorum
                    repeat while j < drawQueues:GetSize()
                    VulkanDrawQueue3D drawQueue = GetCurrentDrawQueue(j)
            if drawQueue not= undefined and drawQueue:GetShadowDrawCommandCount() > 0
                ...
            shadowTextureDescriptorBind:SetDescriptorSet(textureManager:GetGlobalTextureDescriptorSet(j))
```

After:

```quorum
                    repeat while j < shadowQueues:GetSize()
                    VulkanDrawQueue3D drawQueue = shadowQueues:Get(j)
            if drawQueue not= undefined and drawQueue:GetShadowDrawCommandCount() > 0
                ...
            shadowTextureDescriptorBind:SetDescriptorSet(textureManager:GetGlobalTextureDescriptorSet(drawQueue:GetTextureGroupID()))
```

For the default queues, `shadowQueues:Get(j)` is the same queue as
`GetCurrentDrawQueue(j)`, and its texture group ID is `j`. So the default
shadow drawing is exactly as before. The existing `not= undefined` check
already skips the gaps in the custom arrays.

### Summary of the size

About 25 lines changed in `VulkanPainter3DBatch` and about 170 added in
`VulkanPainter3D`, most of it doc comments and the copied draw loop. No
Java. No shader changes.

## Something found while reading (not part of this change)

**The default geometry and shadow loops count frames, not texture groups.**
Both loop `i < drawQueues:GetSize()`, but `drawQueues` has one entry per
frame in flight (usually 3), not one per texture group. So:
- only texture groups 0 to 2 are ever drawn;
- a model whose textures are in group 3 or later is silently not drawn;
- groups 0 to 2 get queues made for them even when unused.

This fits what we saw: textures are grouped 31 at a time (#19), and models
"vanished" once there were enough textures. In our last run the car was in
group 2, just inside the limit.

The fix is small: loop over `drawQueues:Get(resourceIndex):GetSize()`
instead. It changes which models are drawn, though, so I'd make it its own
item (#22), reviewed and tested on its own, right after this one. The new
custom-program loops above already loop over texture groups correctly.

## Risks and things to know

- **Nested generics.** `HashTable<ShaderProgram, Array<Array<VulkanDrawQueue3D>>>`
  ends in `>>>`. `Array<Array<...>>` already compiles in this file, so it
  should be fine. If the compiler objects, a space between the brackets
  fixes it.
- **Comparing programs.** `program = defaultOne` compares the two objects.
  `ShaderProgram` doesn't override `Equals` or `GetHashCode`, so this is
  identity, which is what we want. It also makes programs safe as hash keys.
- **Compiling during drawing.** If a model's program isn't compiled yet,
  the first frame that draws it compiles it (shaderc at run time), which can
  stall that frame. Compiling it up front (`InstallAsProgram` in
  `CreateGame`) avoids this. The default program works the same way today.
- **The pipeline is made against the first painter's scene render pass**,
  and never remade, exactly like the default pipeline. With several Layer3D
  painters, both work for the same reason: their render passes are
  compatible.
- **Memory per program:** one queue per texture group per frame slot. Each
  is about 0.85 MB of instance data plus 2 × 160 KB of draw commands, so
  about 3.5 MB for one program and one group with 3 frames. Never freed,
  like the default queues and like batches (#15).
- **Transparency order:** custom programs' transparent models are drawn
  after all default-program models. There's no transparency sorting today
  anyway, so nothing that works now gets worse.
- **Layout check is by flag.** A program whose mapping claims the default 3D
  resources but uses a different layout can't be caught. All library
  mappings that set the flag use `AddDefaultInfo3D`.
- **Custom programs and picking or other passes:** only the geometry and
  shadow passes draw models. The lighting and result passes don't, so
  nothing else needs to know about programs.

## Test plan

Validation layers on, if possible.

1. **Nothing broken** (before the project change): `RunWorldTests`,
   `RunPhysicsTests`, and DriveOpen with splatting as it is now (Route 1).
   Everything should look and behave the same: no model has a custom
   program yet, so every path is the default one.
2. **Route 2** after the project change below:
   - the terrain is splatted;
   - the car and every other model look like the plain default shader;
   - the terrain still casts and receives shadows;
   - painting (P) and editing (E/Q) still work.
3. **Resize the window, and minimize and restore.**
4. **A model given the default program** (`SetShaderProgram` with the
   default) draws exactly as one without a program.
5. **A program with the wrong mapping** gives the alert, not a crash.

## Rollback

Revert the two files. The project change below would also need reverting,
or switching back to `InstallAsDefault`.

## Project-side change (done, first step)

- DriveOpen compiles a `TerrainSplatShaderProgram` with `InstallAsProgram`
  in `CreateGame` and passes it to `WorldTerrain:SetSplatProgram`.
- `WorldTerrain` gives it to each region and far model right after it's
  built (`ApplyProgram`), or clears it when not splatting.
- The splat shader and the metallic -1 marker are unchanged for this first
  run, as planned.

The original follow-up list, for the remaining steps:


- **`TerrainSplatShaderProgram`:** DriveOpen calls
  `InstallAsProgram(layerRepeat)` instead of `InstallAsDefault`, and gives
  the program to `WorldTerrain` (for example
  `terrain:SetSplatProgram(program)`).
- **`WorldTerrain`:** gives every region model and far model that program
  with `SetShaderProgram` when splatting is on.
- **`TerrainSplatFragmentShader`:** the non-terrain branch (the copy of the
  default shader for every other model) can go, since only terrain uses it
  now. The metallic -1 marker can go too, and terrain materials can use a
  real metallic of 0. That can be a second step, after the first run shows
  Route 2 working with the shader unchanged.
- `InstallAsDefault` stays for now, as a fallback, and is removed once
  Route 2 has been run.
