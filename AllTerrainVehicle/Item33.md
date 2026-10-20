# Item 33: freeing models (meshes, blueprints, batches)

**Status (2026-10-19): committed** (`b1d8e1a8e` on `TerrainShader`, with
Items 32 to 35). MemoryCheck and DriveOpen ran correctly and looked normal. It is section
3 of `MemoryPlan.md`, with the recommended answers to decisions 1 and 2:
- `Model:Dispose` frees under Vulkan; removing a model from a layer
  doesn't.
- Primitive blueprints stay cached.

The project changes (WorldTerrain, TerrainRegionModel) are applied too.
"As applied", just before the test plan, lists the small differences from the text.

Vulkan only, on `TerrainShader`. Paths are as in `Item31.md`. **MV/** is
`Quorum/Library/Standard/Libraries/Game/Graphics/Models/Vulkan/`.

## What leaks today

**Every file model, every `ModelData` blueprint (all of WorldTerrain's
region and far models, and the brush ring), and every primitive is kept
forever.** In detail:

**For each mesh:**
- its vertex and index buffers on the GPU;
- with animation, the animation data buffer;
- its three staging buffers. They stay mapped forever after the first
  copy, kept only to read their size.
- with Item 7 updates, one update staging buffer per frame slot.

**For each blueprint:**
- its animation frames' buffers and staging buffers;
- its `ModelData`, the CPU copy of every vertex;
- its place in `ModelManagerVulkan`'s cache.

**For each animated model:** one vertex buffer per mesh, the result of
animating. Loading a different blueprint makes a new set and drops the old
one. Loading a non-animated blueprint keeps the stale set.

**For each 3D painter:** one batch per blueprint, in four tables, kept
forever. Their `age` can't be used to remove them: it is only advanced for
batches drawn this frame, so an unused batch stays at 1.

**So in WorldTerrain:**
- **Rebuilding a region at a new grid size** loads a new blueprint, and
  the old one is kept.
- **The brush ring** is rebuilt the same way, and every old ring is kept.
- **`Build` and `UpdateRegionModels`** drop models without freeing them.
- **Streaming** keeps every region model ever built (by design, as a
  cache), so memory grows with the area explored.

## The design

**Reference counts on Vulkan blueprints:**
- `Model:Load(blueprint, matrix)` is the one place every `Load` reaches. It
  adds a user to the new blueprint, and removes one from the model's
  previous blueprint if it had a different one.
- **`Model:Dispose`** removes one too. Today it is `Item:Dispose`, which
  does nothing and is meant for exactly this ("free up any additional
  memory... for purposes such as graphics"). Nothing in the library calls
  it automatically (checked).
  - Under OpenGL it keeps today's behaviour, which is none.
  - After `Dispose`, the model draws nothing until it is loaded again.
- **When a blueprint's users reach 0,** `ModelManagerVulkan` takes it out of
  the cache and releases it. This applies unless it is a primitive, whose
  key starts with `:PRIMITIVE:`; primitives stay cached (decision 2).
  - Releasing retires every GPU buffer it owns and drops its `ModelData`.
  - It also takes its meshes and frames out of the pending lists, in case
    they were never copied.
- **A blueprint that no model ever loaded** keeps today's behaviour: it is
  never released.

**Staging buffers** are retired as soon as their copy is recorded. Meshes
keep only their device buffers.

**Batches.** The model manager counts releases. Each 3D painter checks the
count in `End`. When it has changed, the painter removes the batches whose
blueprint was released from all four tables. The `age` field is left as it
is (unused).

**Materials** are released with their blueprint in Item 34, which adds
`MaterialVulkan:Release`. Until then they keep leaking: a small uniform
buffer each, plus any textures they loaded.

## The code

### `MV/MeshVulkan.quorum`

**Uses.** Add:

```
use Libraries.Game.GameStateManager
use Libraries.Game.Graphics.Vulkan.VulkanGraphics
```

**`Load`.** Its ending comment and commented-out calls

```
        //TODO: These cause a crash in some cases, for reasons unclear. Go back and figure this out later.
        //vertexStagingBuffer:StopMapping()
        //indexStagingBuffer:StopMapping()
        //animationDataStagingBuffer:StopMapping()
```

are replaced by:

```
        // The staging buffers stay mapped until their copy is recorded;
        // TransferBuffers then retires them (Item 33).
```

**`HasData`.** It becomes:

```
    action HasData returns boolean
        return vertexBuffer not= undefined
    end
```

(`Load` makes the device buffer and the staging buffer together, so this
is the same test today. It stays true after the staging buffers are
retired.)

**`HasAnimations`.** It becomes:

```
    action HasAnimations returns boolean
        return animationDataBuffer not= undefined
    end
```

**`TransferBuffers`.** After `dataTransferred = true`, add:

```
        // The copies above are the staging buffers' only use. They are
        // freed once this frame has finished on the GPU (Item 33).
        GameStateManager gameState
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        graphics:Retire(vertexStagingBuffer)
        graphics:Retire(indexStagingBuffer)
        graphics:Retire(animationDataStagingBuffer)
        vertexStagingBuffer = undefined
        indexStagingBuffer = undefined
        animationDataStagingBuffer = undefined
        vertexMapping = undefined
```

**`RecordUpdate`.** The line
`newStaging:CreateTransferSourceBuffer(device, vertexStagingBuffer:GetSize())`
becomes:

```
            newStaging:CreateTransferSourceBuffer(device, vertexBuffer:GetSize())
```

**`GetVertexBufferSize` and `GetIndexBufferSize`.** They become:

```
    /*Returns the size of the vertex buffer in bytes.*/
    action GetVertexBufferSize returns integer
        if vertexBuffer = undefined
            return 0
        end
        return vertexBuffer:GetSize()
    end

    /*Returns the size of the index buffer in bytes.*/
    action GetIndexBufferSize returns integer
        if indexBuffer = undefined
            return 0
        end
        return indexBuffer:GetSize()
    end
```

(Each device buffer is made the same size as its staging buffer.)

**New action,** before the final `end`:

```
    /*
    This action frees the mesh's GPU buffers once no frame on the GPU still
    uses them. The model manager calls it when the mesh's blueprint is no
    longer used by any model. The mesh can't be drawn or updated afterwards.
    */
    action Release
        GameStateManager gameState
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        graphics:Retire(vertexStagingBuffer)
        graphics:Retire(indexStagingBuffer)
        graphics:Retire(animationDataStagingBuffer)
        graphics:Retire(vertexBuffer)
        graphics:Retire(indexBuffer)
        graphics:Retire(animationDataBuffer)
        integer i = 0
        repeat while i < updateStagingBuffers:GetSize()
            graphics:Retire(updateStagingBuffers:Get(i))
            i = i + 1
        end
        updateStagingBuffers:Empty()
        updateMappings:Empty()
        vertexStagingBuffer = undefined
        indexStagingBuffer = undefined
        animationDataStagingBuffer = undefined
        vertexBuffer = undefined
        indexBuffer = undefined
        animationDataBuffer = undefined
        vertexMapping = undefined
        pendingVertices = undefined
    end
```

### `MV/AnimationFrameVulkan.quorum`

**Uses.** Add `use Libraries.Game.GameStateManager` and
`use Libraries.Game.Graphics.Vulkan.VulkanGraphics`.

**`Create`.** Its commented `StopMapping` lines are replaced by
`// TransferBuffers retires the staging buffer (Item 33).`

**`HasData`.** It becomes `return dataBuffer not= undefined`.

**`TransferBuffers`.** After `dataTransferred = true`, add:

```
        // The copy is the staging buffer's only use (Item 33).
        GameStateManager gameState
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        graphics:Retire(stagingBuffer)
        stagingBuffer = undefined
```

**New action:**

```
    /*
    This action frees the frame's GPU buffers once no frame on the GPU
    still uses them. Its blueprint calls it when no model uses the
    blueprint any more.
    */
    action Release
        GameStateManager gameState
        VulkanGraphics graphics = cast(VulkanGraphics, gameState:GetGameGraphics())
        graphics:Retire(stagingBuffer)
        graphics:Retire(dataBuffer)
        stagingBuffer = undefined
        dataBuffer = undefined
    end
```

### `MV/ModelBlueprintVulkan.quorum`

**New fields,** after `BoundingBox boundingBox`:

```
    // How many models have this blueprint loaded (Item 33).
    integer userCount = 0

    // True once the blueprint's GPU memory has been freed (Item 33).
    boolean released = false
```

**New actions,** before the final `end`:

```
    /*
    This action counts one more model using the blueprint. Model:Load calls
    it through the model manager.
    */
    action AddUser
        userCount = userCount + 1
    end

    /*
    This action counts one fewer model using the blueprint.

    Attribute: Returns How many models still use it.
    */
    action RemoveUser returns integer
        if userCount > 0
            userCount = userCount - 1
        end
        return userCount
    end

    /*
    This action returns how many models use the blueprint.

    Attribute: Returns The number of models.
    */
    action GetUserCount returns integer
        return userCount
    end

    /*
    This action returns true once the blueprint's GPU memory has been
    freed. A released blueprint can't be drawn or loaded into a model.

    Attribute: Returns True if released.
    */
    action IsReleased returns boolean
        return released
    end

    /*
    This action frees the GPU memory of the blueprint's meshes and
    animation frames, once no frame on the GPU still uses it, and lets go
    of its model data. The model manager calls it when no model uses the
    blueprint any more. Doing it twice does nothing.
    */
    action Release
        if released
            return now
        end
        released = true

        integer i = 0
        if meshes not= undefined
            repeat while i < meshes:GetSize()
                meshes:Get(i):Release()
                i = i + 1
            end
        end
        if animationFrames not= undefined
            i = 0
            repeat while i < animationFrames:GetSize()
                Array<AnimationFrameVulkan> frames = animationFrames:Get(i)
                integer j = 0
                repeat while j < frames:GetSize()
                    frames:Get(j):Release()
                    j = j + 1
                end
                i = i + 1
            end
        end
        if bindPoseAnimationFrame not= undefined
            bindPoseAnimationFrame:Release()
        end
        data = undefined
    end
```

### `MV/ModelResourcesVulkan.quorum`

**`SetFromBlueprint`.** Its first lines, before
`// If the blueprint has animations, ...`, become:

```
    action SetFromBlueprint(ModelBlueprint schematic)
        // Buffers made for a previous blueprint go first (Item 33).
        Release()
```

**New action:**

```
    /*
    This action frees the model's own GPU buffers (the vertices of an
    animated model after animation) once no frame on the GPU still uses
    them. Model:Dispose calls it, and so does loading another blueprint.
    */
    action Release
        if postAnimationVertexBuffers = undefined
            return now
        end
        GameStateManager manager
        VulkanGraphics graphics = cast(VulkanGraphics, manager:GetGameGraphics())
        integer i = 0
        repeat while i < postAnimationVertexBuffers:GetSize()
            graphics:Retire(postAnimationVertexBuffers:Get(i))
            i = i + 1
        end
        postAnimationVertexBuffers = undefined
    end
```

### `MV/AnimationManagerVulkan.quorum`

New action, so a released blueprint's frames aren't copied:

```
    /*
    This action takes a frame out of the list waiting to be copied, if it
    is there (Item 33).

    Attribute: Parameter frame The frame.
    */
    action RemovePendingAnimationFrame(AnimationFrameVulkan frame)
        pendingFrames:Remove(frame)
    end
```

### `MV/ModelManagerVulkan.quorum`

**New field,** after `pendingUpdates`:

```
    // How many blueprints have been released. Painters compare it with the
    // count they last saw, to drop batches for released blueprints (Item 33).
    integer releaseCount = 0
```

**New actions,** before `GetMaterialManager`:

```
    /*
    This action counts a model as using a blueprint. Model:Load calls it.

    Attribute: Parameter blueprint The blueprint the model loaded.
    */
    action AddUser(ModelBlueprintVulkan schematic)
        blueprint:AddUser()
    end

    /*
    This action counts one fewer model using a blueprint. When no model
    uses it, it is taken out of the cache and its GPU memory is freed, once
    no frame on the GPU still uses it. Primitive blueprints (boxes, planes,
    spheres and cylinders) stay cached, since they are small and often used
    again. Model:Load and Model:Dispose call it.

    Attribute: Parameter blueprint The blueprint a model no longer uses.
    */
    action RemoveUser(ModelBlueprintVulkan blueprint)
        if blueprint:RemoveUser() > 0 or blueprint:IsReleased()
            return now
        end
        text key = blueprint:GetKey()
        if key not= undefined and key:StartsWith(PRIMITIVE_KEY)
            return now
        end

        if key not= undefined and cachedBlueprints:HasKey(key) and cachedBlueprints:GetValue(key) = blueprint
            cachedBlueprints:RemoveKey(key)
        end

        // Meshes and frames never copied must not be copied now.
        Array<MeshVulkan> meshes = blueprint:GetMeshes()
        if meshes not= undefined
            integer i = 0
            repeat while i < meshes:GetSize()
                pendingMeshes:Remove(meshes:Get(i))
                pendingUpdates:Remove(meshes:Get(i))
                i = i + 1
            end
        end
        Array<Array<AnimationFrameVulkan>> allFrames = blueprint:GetAnimationFrames()
        if allFrames not= undefined
            integer k = 0
            repeat while k < allFrames:GetSize()
                Array<AnimationFrameVulkan> frames = allFrames:Get(k)
                integer j = 0
                repeat while j < frames:GetSize()
                    animationManager:RemovePendingAnimationFrame(frames:Get(j))
                    j = j + 1
                end
                k = k + 1
            end
        end
        if blueprint:GetBindPoseAnimationFrame() not= undefined
            animationManager:RemovePendingAnimationFrame(blueprint:GetBindPoseAnimationFrame())
        end

        blueprint:Release()
        releaseCount = releaseCount + 1
    end

    /*
    This action returns how many blueprints have been released so far.

    Attribute: Returns The number of released blueprints.
    */
    action GetReleaseCount returns integer
        return releaseCount
    end

    /*
    This action returns how many blueprints are cached.

    Attribute: Returns The number of cached blueprints.
    */
    action GetCachedBlueprintCount returns integer
        return cachedBlueprints:GetSize()
    end
```

### `G/../Model.quorum` (`Quorum/Library/Standard/Libraries/Game/Graphics/Model.quorum`)

**`Load(ModelBlueprint loader, Matrix4 matrix)`.** It becomes:

```
    action Load(ModelBlueprint loader, Matrix4 matrix)
        ModelBlueprint previous = modelBlueprint
        SetModelBlueprint(loader)
        if matrix not= undefined
            GetTransform():Set(matrix)
        end

        resources:SetFromBlueprint(loader)

        // Under Vulkan, blueprints count the models using them, so one no
        // model uses can be freed (Item 33).
        if previous not= loader
            if loader is ModelBlueprintVulkan
                ModelManagerVulkan modelManager = GetModelManager()
                modelManager:AddUser(cast(ModelBlueprintVulkan, loader))
            end
            if previous not= undefined and previous is ModelBlueprintVulkan
                ModelManagerVulkan previousManager = GetModelManager()
                previousManager:RemoveUser(cast(ModelBlueprintVulkan, previous))
            end
        end

        SetDimensions(GetCachedDimensions(loader))
    end
```

The new user is added before the old one is removed, so loading the same
file again never frees it in between.

**`Dispose` (new; it overrides `Item:Dispose`).** Added after `Load`:

```
    /*
    This action frees the graphics memory this model uses. Under Vulkan,
    the model's own buffers are freed, and its blueprint (the meshes loaded
    from a file or made from model data) is freed too once no other model
    uses it. Boxes, planes, spheres and cylinders stay cached for reuse.
    Under OpenGL it does nothing yet.

    Remove the model from the game first. A disposed model draws nothing
    until it is loaded again.

    Attribute: Example
    use Libraries.Game.Game
    use Libraries.Game.Graphics.Model

    class Main is Game
        Model car

        action Main
            StartGame()
        end

        action CreateGame
            car:Load("Models/Car.obj")
            Add(car)
        end

        action Update(number seconds)
            // When the car is no longer needed:
            // Remove(car)
            // car:Dispose()
        end
    end
    */
    action Dispose
        if resources is ModelResourcesVulkan
            ModelResourcesVulkan vulkanResources = cast(ModelResourcesVulkan, resources)
            vulkanResources:Release()
            if modelBlueprint not= undefined and modelBlueprint is ModelBlueprintVulkan
                ModelManagerVulkan modelManager = GetModelManager()
                modelManager:RemoveUser(cast(ModelBlueprintVulkan, modelBlueprint))
            end
            modelBlueprint = undefined
            resources = undefined
        end
        parent:Item3D:Dispose()
    end
```

**After `Dispose`:**
- `VulkanPainter3D:Render` already ignores a model with no blueprint.
- `SetModelBlueprint` makes fresh resources on the next `Load`.

### `G/VulkanPainter3D.quorum`

**New field,** after `programTransparentBatches`:

```
    // The model manager's release count when batches were last checked
    // for released blueprints (Item 33).
    integer releasesSeen = 0
```

**In `End`,** before
`Array<VulkanPainter3DBatch> currentBatches = pendingBatches`:

```
        // Drop batches whose blueprint no model uses any more (Item 33).
        ModelManagerVulkan releaseManager = graphics:GetModelManager()
        if releaseManager:GetReleaseCount() not= releasesSeen
            releasesSeen = releaseManager:GetReleaseCount()
            RemoveReleasedBatches()
        end
```

(`graphics` is already defined in `End`, where `ComputeAnimations(graphics)`
uses it.)

**New private actions:**

```
    /*
    This action removes, from every batch table, the batches whose
    blueprint has been released (Item 33).
    */
    private action RemoveReleasedBatches
        RemoveReleasedBatches(batches)
        RemoveReleasedBatches(transparentBatches)
        Iterator<HashTable<ModelBlueprint, VulkanPainter3DBatch>> tables = programBatches:GetValueIterator()
        repeat while tables:HasNext()
            RemoveReleasedBatches(tables:Next())
        end
        tables = programTransparentBatches:GetValueIterator()
        repeat while tables:HasNext()
            RemoveReleasedBatches(tables:Next())
        end
    end

    /*
    This action removes, from one batch table, the batches whose blueprint
    has been released.

    Attribute: Parameter table A table of batches by blueprint.
    */
    private action RemoveReleasedBatches(HashTable<ModelBlueprint, VulkanPainter3DBatch> table)
        Array<ModelBlueprint> released
        Iterator<ModelBlueprint> keys = table:GetKeyIterator()
        repeat while keys:HasNext()
            ModelBlueprint key = keys:Next()
            if key is ModelBlueprintVulkan
                ModelBlueprintVulkan vulkanKey = cast(ModelBlueprintVulkan, key)
                if vulkanKey:IsReleased()
                    released:Add(key)
                end
            end
        end
        integer i = 0
        repeat while i < released:GetSize()
            VulkanPainter3DBatch batch = table:RemoveKey(released:Get(i))
            if batch not= undefined
                batch:Dispose()
            end
            i = i + 1
        end
    end
```

**What a released batch can't do.** A released blueprint can't have a
pending batch this frame: its last model was disposed, and disposed models
aren't rendered.

### `G/VulkanGraphics.quorum` (the report)

`GetMemoryReport` (Item 31) gains the blueprint count. Its `return` becomes:

```
        return "GPU memory: " + megabytes + " MB in " + allocator:GetAllocationCount() +
            " allocations; waiting to be freed: " + retired:GetSize() +
            "; model blueprints: " + modelManager:GetCachedBlueprintCount()
```

## Project changes (`AllTerrainVehicle/SourceCode/Worlds/`)

**Free automatically, with no project change:**
- regions rebuilt at a new grid size;
- far models rebuilt;
- the brush ring rebuilt.

In each case the model loads its new blueprint, and `Load` frees the old
one.

**`WorldTerrain.quorum`:**
- **`Build`.** Before `regionModels:Empty()`, add:

```
        // Models from an earlier build are freed (Item 33).
        integer old = 0
        repeat while old < regionModels:GetSize()
            regionModels:Get(old):Dispose()
            old = old + 1
        end
```

  Its comment's last paragraph ("The renderer cannot yet free a model's
  mesh, ...") becomes "Their meshes are freed, so remove them from the game
  first."
- **`StartStreaming`.** The same loop goes before its
  `regionModels:Empty()`. Those are models from `Build`, which streaming
  replaces.
- **`UpdateRegionModels`.** After `layer:Remove(kept)`, add
  `kept:Dispose()`.
- **Streaming cache limit (new).** Today every region model built while
  streaming stays in `modelMap`. A new private action frees cached models
  that are out of the layer and far from the target. `UpdateDrawnModels`
  calls it at its end when `changed` is true:

```
    /*
    This action frees cached region models that aren't being drawn and are
    more than twice the draw radius from the target. They are built again
    if the target comes back (Item 33).

    Attribute: Parameter targetX The target's position along x, in world units.
    Attribute: Parameter targetZ The target's position along z, in world units.
    */
    private action FreeFarCachedModels(number targetX, number targetZ)
        number keepRadius = drawRadius * 2 + streamer:GetRegionWorldSize()
        integer i = 0
        repeat while i < modelMap:GetSize()
            TerrainRegionModel cached = modelMap:Get(i)
            if cached not= undefined and activeMap:Get(i) = 0
                TerrainRegion region = cached:GetTerrainRegion()
                if streamer:GetDistanceToRegion(region:GetLocationX(), region:GetLocationZ(), targetX, targetZ) > keepRadius
                    cached:Dispose()
                    modelMap:Set(i, undefined)
                end
            end
            i = i + 1
        end
    end
```

  Far models are small and stay cached.
- **`TerrainRegionModel.Rebuild`.** Its comment's sentence "and the
  renderer cannot yet free the old one. See VulkanChanges.md." becomes
  "and the old one is freed."

## As applied (2026-10-19)

- **`ModelBlueprintVulkan:HasAnimations`** also returns false when `data`
  is undefined. A released blueprint drops its data, and nothing should ask
  it, but this keeps a stray call from crashing.
- **`Model:Load`, `Model:Dispose` and `ModelManagerVulkan:RemoveUser`**
  write `x not= undefined and x is ...` as two nested `if`s. The meaning is
  the same.
- **`ModelManagerVulkan:AddUser` and `RemoveUser`** name their parameter
  `schematic`, not `blueprint`, which is a reserved word in Quorum. The
  second build failed on that (2026-10-19).
- **`Model:Dispose`** doesn't call `parent:Item3D:Dispose()`. `Item3D`
  doesn't define `Dispose` (only `Item` does, and it's empty), so the call
  was dropped to avoid a compile error (2026-10-19).
- **The MemoryCheck loop L** (model load and dispose) isn't added yet. The
  file has only Item 31's keys. The test plan below needs it before step 1.

## Test plan

**MemoryCheck gains a loop (key L).** It loads and disposes 100 models
from a file once a second.

```
    // In MemoryCheck: fields
    Array<Model> loadedModels
    boolean lWasDown = false
    boolean loading = false
    number timeUntilLoad = 1

    // In Update:
        boolean lDown = monitor:IsKeyPressed(keys:L)
        if lDown and not lWasDown
            loading = not loading
            output "Model loop: " + loading
        end
        lWasDown = lDown
        if loading
            timeUntilLoad = timeUntilLoad - seconds
            if timeUntilLoad <= 0
                CycleModels()
                timeUntilLoad = 1
            end
        end

    private action CycleModels
        integer i = 0
        repeat while i < loadedModels:GetSize()
            Remove(loadedModels:Get(i))
            loadedModels:Get(i):Dispose()
            i = i + 1
        end
        loadedModels:Empty()
        i = 0
        repeat while i < 100
            Model model
            model:Load("Car/Car.obj")
            model:SetPosition((i mod 10) * 2 - 10, 0, 10 + (i / 10) * 2)
            Add(model)
            loadedModels:Add(model)
            i = i + 1
        end
    end
```

The path `Car/Car.obj` stands for any model file the project has; the
apply step uses one that exists under `AllTerrainVehicle`.

**The checks:**
1. **MemoryCheck, L on for two minutes.**
   - GPU memory, allocations and blueprints go up and down within a range.
   - The blueprint count goes 0 → 1 → 0 between cycles, shown as 1 at
     most.
2. **DriveOpen,** driving across 20+ regions with streaming.
   - GPU memory levels off once the cache limit is reached, rather than
     climbing with distance.
   - Coming back to a freed area rebuilds it with no visible change.
3. **TerrainEditor.**
   - The brush ring changes size without the memory climbing.
   - Region add/remove (`UpdateRegionModels`), undo and rebuild all draw
     correctly.
4. **TerrainWalk and MSAACheck** (primitives only) look and run as before.
   The blueprint count stays flat.
5. **Animated models** (any animated file): load one, then load a static
   model into the same `Model`. Nothing is drawn wrong, and the animated
   buffers are freed.

## Rollback

Revert the Item 33 changes in the library and project files. Item 31 and
Item 32 stay.
