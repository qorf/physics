# Vulkan rotation fix: code changes

> **Status, 2026-10-15: done.** These edits were applied, although the text below says otherwise.

These are the edits for the bug described in `VulkanRotationBug.md`. None of
them have been applied. They span three files and must go in together.
Fixing only `Item3D` breaks OpenGL, and fixing only OpenGL shows the reversed
turning there too.

## 1. Item3D.quorum: copy rotations without mirroring

### a. `Rotate(Vector3 vector, number degrees, boolean rotateChildren)`, about lines 1613-1623

Remove the four minus signs:

```quorum
                tempMatrix:row0column0 = rotationMatrix:row0column0 / scale:GetX()
                tempMatrix:row0column1 = rotationMatrix:row0column1 / scale:GetX()
                tempMatrix:row0column2 = rotationMatrix:row0column2 / scale:GetX()

                tempMatrix:row1column0 = rotationMatrix:row1column0 / scale:GetY()
                tempMatrix:row1column1 = rotationMatrix:row1column1 / scale:GetY()
                tempMatrix:row1column2 = rotationMatrix:row1column2 / scale:GetY()

                tempMatrix:row2column0 = rotationMatrix:row2column0 / scale:GetZ()
                tempMatrix:row2column1 = rotationMatrix:row2column1 / scale:GetZ()
                tempMatrix:row2column2 = rotationMatrix:row2column2 / scale:GetZ()
```

### b. `SetYawPitchRoll`, about lines 2044-2054

This block is identical to 1a. Make the same change.

### c. `SetScreenPositionFromPhysicsPosition`, about lines 3387-3419

Replace the comment block and the nine assignments:

```quorum
        Matrix3 tempMatrix
        tempMatrix:Set(collisionTransform:GetBasis())

        // Physics and drawing share one coordinate system, since the position
        // is copied unchanged below, so the rotation is copied unchanged too.
        Matrix4 matrix = rotationMatrix
        matrix:IdentityMatrix()
        matrix:row0column0 = tempMatrix:row0column0
        matrix:row0column1 = tempMatrix:row0column1
        matrix:row0column2 = tempMatrix:row0column2

        matrix:row1column0 = tempMatrix:row1column0
        matrix:row1column1 = tempMatrix:row1column1
        matrix:row1column2 = tempMatrix:row1column2

        matrix:row2column0 = tempMatrix:row2column0
        matrix:row2column1 = tempMatrix:row2column1
        matrix:row2column2 = tempMatrix:row2column2
```

Delete the "Conversion between left-handed coordinate system and
right-handed..." comment and the commented-out assignments under it. The
rest of the action stays as it is: `transformDirty = true`, the `me:x/y/z`
lines, and `SetOffset`.

## 2. DefaultShaderMapping3DOpenGL.quorum: remove the hidden z flips

The file is in `Game/Graphics/Shaders/OpenGL/Mapping/`.

### a. `Begin`, about line 211

Delete the `InvertViewZ` line:

```quorum
        // Set the projection-view transform
        tempMatrix4:Set(camera:GetCombinedMatrix())
        program:SetShaderInputMatrix(projectionViewTransformID, tempMatrix4)
```

### b. `MapInputs`, about lines 291-295

Delete the "lazy hack" comment and the `InvertPositionZ` line:

```quorum
        // Set the world transform.
        tempMatrix4:Set(renderable:worldTransform)
        program:SetShaderInputMatrix(worldTransformID, tempMatrix4)
```

### c. `BindLights`, about line 552

Delete:

```quorum
        tempVector3:Scale(1, 1, -1)
```

### d. `BindLights`, directional lights, about line 580

```quorum
                    glProgram:SetShaderInput(directionalLightDirectionID:Get(counter), tempVector3:GetX(), tempVector3:GetY(), tempVector3:GetZ())
```

### e. `BindLights`, point lights, about line 615

```quorum
                    glProgram:SetShaderInput(pointLightPositionID:Get(counter), position:GetX(), position:GetY(), position:GetZ())
```

### f. End of the file, about lines 698-710

`InvertPositionZ` and `InvertViewZ` are no longer called. Delete both
actions.

## 3. Vehicle.quorum: wheel visuals

The file is in `Game/Physics/Vehicles/`.

### `ToVisualRotation`, line 652

```quorum
        Matrix3 converted
        converted:Set(basis)
```

Update the action's comment so it no longer says rotations are stored with
signs flipped. For example:

```quorum
    /*
    Applies a physics rotation on top of a visual's rest rotation. Physics and
    drawing share one coordinate system, so the physics rotation is used as
    it is.
    ...
```

## 4. Nothing to change for the camera or Vulkan

- `CameraMatrix4`, `Camera`, `VulkanPainter3D` (including the negative
  viewport height) and the GLSL shaders are already correct.
- The test `DrawnRotationMatchesPhysicsTest` in PhysicsTests needs no
  changes. It should fail before these edits and pass after.

## After the change

1. Run PhysicsTests. All 28 tests should pass, including
   `DrawnRotationMatchesPhysicsTest`.
2. Run the AllTerrainVehicle physics tests.
3. Do the visual checks in `VulkanRotationBug.md` in both APIs. In OpenGL,
   specifically check that the scene is no longer mirrored and that lighting
   comes from the same sides as in Vulkan.
