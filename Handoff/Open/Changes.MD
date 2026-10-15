# Changes: vulkan-rotations compared to vulkan-3D

> **Status, 2026-10-15: a record of the vulkan-3D...vulkan-rotations diff.** Its "What to check by hand" list at the end is still partly open.

Generated on 2026-10-12 with:

```bash
git diff --stat --patch vulkan-3D...vulkan-rotations
```

The three dots compare `vulkan-rotations` (cf04997e5) with the point where it last met `vulkan-3D` (f511a505f), so only the work done on `vulkan-rotations` is shown. This is the quorum-language repository only. The GroundFlightTactics changes are in example-games.

~~~~diff
 .../Game/Graphics/Models/Data/ModelLoader.java     |   9 +-
 .../Game/Graphics/OpenGL/DesktopOpenGL.java        |   2 +-
 .../Game/Graphics/Shaders/SPIRVShaderCompiler.java |   2 +-
 .../Standard/Libraries/Compute/Matrix4.quorum      | 400 ++-----------------
 .../Standard/Libraries/Game/Graphics/Camera.quorum |  36 +-
 .../Libraries/Game/Graphics/CameraMatrix4.quorum   | 444 +++++++++++++++++++++
 .../Game/Graphics/DeviceCoordinates.quorum         |  39 ++
 .../Libraries/Game/Graphics/GraphicsManager.quorum |   6 +
 .../Libraries/Game/Graphics/MeshBuilder.quorum     |  23 +-
 .../Game/Graphics/ModelLoaders/ModelReader.quorum  |   6 +-
 .../WavefrontConverterListener.quorum              |   7 +-
 .../Models/Vulkan/EnvironmentVulkan.quorum         |   7 +-
 .../Game/Graphics/OpenGL/OpenGLPainter2D.quorum    |   4 +-
 .../Game/Graphics/OrthographicCamera.quorum        |  71 +---
 .../Game/Graphics/PerspectiveCamera.quorum         |  25 +-
 .../Mapping/DefaultShaderMapping3DOpenGL.quorum    |  28 +-
 .../Game/Graphics/Vulkan/VulkanGraphics.quorum     |   5 +
 .../Game/Graphics/Vulkan/VulkanPainter3D.quorum    |  15 +
 .../Libraries/Game/Physics/Vehicles/Vehicle.quorum |   9 +-
 .../Game/Scenes/DefaultSceneManager.quorum         |  43 +-
 .../Libraries/Game/Scenes/SceneProperties.quorum   |   5 +-
 .../Standard/Libraries/Interface/Item3D.quorum     |  45 +--
 .../Math/Pass/Matrix4SetToOrthographic.quorum      |  12 +-
 23 files changed, 696 insertions(+), 547 deletions(-)

diff --git a/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/Models/Data/ModelLoader.java b/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/Models/Data/ModelLoader.java
index 25aff8c71..c775582ce 100644
--- a/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/Models/Data/ModelLoader.java
+++ b/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/Models/Data/ModelLoader.java
@@ -46,14 +46,19 @@ public class ModelLoader {
         aiReleaseImport(aiSceneCheck);
 
         boolean vulkanLoading = quorumLoader.IsUsingLeftHandedCoordinates();
+        // Most model files are right-handed and the world is left-handed, so z is
+        // flipped and each triangle's winding reversed, which keeps front faces
+        // clockwise. aiProcess_ConvertToLeftHanded is not used because it also
+        // flips texture v, which ProcessTextureCoordinates already does.
+        int leftHanded = vulkanLoading ? (aiProcess_MakeLeftHanded | aiProcess_FlipWindingOrder) : 0;
         if(hasAnimations) {
             flags = aiProcess_GenSmoothNormals | aiProcess_JoinIdenticalVertices |
                     aiProcess_Triangulate | aiProcess_FixInfacingNormals | aiProcess_CalcTangentSpace | aiProcess_LimitBoneWeights |
-                    (vulkanLoading ? aiProcess_ConvertToLeftHanded : 0);
+                    leftHanded;
         } else {
             flags = aiProcess_GenSmoothNormals | aiProcess_JoinIdenticalVertices |
                     aiProcess_Triangulate | aiProcess_FixInfacingNormals | aiProcess_CalcTangentSpace | aiProcess_LimitBoneWeights |
-                    aiProcess_PreTransformVertices | (vulkanLoading ? aiProcess_ConvertToLeftHanded : 0);
+                    aiProcess_PreTransformVertices | leftHanded;
         }
         AIScene aiScene = aiImportFile(path, flags);
         if (aiScene == null) {
diff --git a/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/OpenGL/DesktopOpenGL.java b/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/OpenGL/DesktopOpenGL.java
index a16d5e976..515a88e33 100644
--- a/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/OpenGL/DesktopOpenGL.java
+++ b/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/OpenGL/DesktopOpenGL.java
@@ -199,7 +199,7 @@ public class DesktopOpenGL implements OpenGLManager {
 
     public void DeleteBuffer(int bufferID)
     {
-        glDeleteBuffer(bufferID);
+        //glDeleteBuffer(bufferID);
     }
     
     public void SetBuffer(int purpose, Number32BitBuffer_ buffer, int option)
diff --git a/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/Shaders/SPIRVShaderCompiler.java b/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/Shaders/SPIRVShaderCompiler.java
index d1fb9f9b9..a15c70039 100644
--- a/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/Shaders/SPIRVShaderCompiler.java
+++ b/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/Shaders/SPIRVShaderCompiler.java
@@ -26,7 +26,7 @@ public class SPIRVShaderCompiler
 
             // Note: For tricky shader debugging, disabling optimization can prevent the compiler from stripping out
             // code that doesn't contribute to final outputs or removing intermediate values that would be easier to debug.
-            //Shaderc.shaderc_compile_options_set_optimization_level(optionsHandle, 0);
+            Shaderc.shaderc_compile_options_set_optimization_level(optionsHandle, 0);
 
             long result = Shaderc.shaderc_compile_into_spv(compilerHandle, code, shaderType, shaderName, "main", optionsHandle);
 
diff --git a/Quorum/Library/Standard/Libraries/Compute/Matrix4.quorum b/Quorum/Library/Standard/Libraries/Compute/Matrix4.quorum
index 849dc45f2..4679c637d 100644
--- a/Quorum/Library/Standard/Libraries/Compute/Matrix4.quorum
+++ b/Quorum/Library/Standard/Libraries/Compute/Matrix4.quorum
@@ -1380,340 +1380,6 @@ result = result + "|" + row3column0 + ", " + row3column1 + ", " + row3column2 +
                row0column2 * row1column1 * row2column0
     end
 
-    /*
-    This action sets the matrix to a projection matrix with the near and far
-    planes, the field of view height, and the aspect ratio. 
-
-    Attribute: Author Amanda Austin
-
-    Attribute: Parameter nearPlane The near plane
-    Attribute: Parameter farPlane The far plane
-    Attribute: Parameter fieldOfViewHeight The height of the field of view
-    Attribute: Parameter aspectRatio the aspect ratio
-
-    Attribute: Returns The matrix as a projection matrix
-
-    Attribute: Example
-
-    use Libraries.Compute.Matrix4
-
-    Matrix4 matrix
-
-    matrix:SetToProjection(0, 1, 10, 2)
-    
-    number row0column0 = matrix:row0column0
-    number row0column1 = matrix:row0column1
-    number row0column2 = matrix:row0column2
-    number row0column3 = matrix:row0column3
-    number row1column0 = matrix:row1column0
-    number row1column1 = matrix:row1column1
-    number row1column2 = matrix:row1column2
-    number row1column3 = matrix:row1column3
-    number row2column0 = matrix:row2column0
-    number row2column1 = matrix:row2column1
-    number row2column2 = matrix:row2column2
-    number row2column3 = matrix:row2column3
-    number row3column0 = matrix:row3column0
-    number row3column1 = matrix:row3column1
-    number row3column2 = matrix:row3column2
-    number row3column3 = matrix:row3column3
-
-    output "The new matrix is:"
-    output "|" + row0column0 + ", " + row0column1 + ", " + row0column2 + ", " + row0column3 + "|"
-    output "|" + row1column0 + ", " + row1column1 + ", " + row1column2 + ", " + row1column3 + "|"
-    output "|" + row2column0 + ", " + row2column1 + ", " + row2column2 + ", " + row2column3 + "|"
-    output "|" + row3column0 + ", " + row3column1 + ", " + row3column2 + ", " + row3column3 + "|"
-
-    */
-    action SetToProjection(number nearPlane, number farPlane, number fieldOfViewHeight, number aspectRatio) returns Matrix4
-        number l_fd = 1.0 / math:Tangent((fieldOfViewHeight * (math:pi / 180)) / 2.0)
-        number l_a1 = (farPlane + nearPlane) / (nearPlane - farPlane)
-        number l_a2 = (2 * farPlane * nearPlane) / (nearPlane - farPlane)
-
-        row0column0 = l_fd / aspectRatio
-        row1column0 = 0
-        row2column0 = 0
-        row3column0 = 0
-
-        row0column1 = 0
-        row1column1 = l_fd
-        row2column1 = 0
-        row3column1 = 0
-
-        row0column2 = 0
-        row1column2 = 0
-        row2column2 = l_a1
-        row3column2 = -1
-
-        row0column3 = 0
-        row1column3 = 0
-        row2column3 = l_a2
-        row3column3 = 0
-
-        return me
-    end
-
-    /*
-    Sets the matrix to a projection matrix with a near/far plane, and left, bottom, 
-    right and top specifying the points on the near plane that are mapped to the 
-    lower left and upper right corners of the viewport. This allows a projection
-    matrix to be created with an off-center vanishing point.
-
-    Attribute: Author Amanda Austin
-
-    Attribute: Parameter left The left point of the near plane
-    Attribute: Parameter right The right point of the near plane
-    Attribute: Parameter bottom The bottom of the near plane
-    Attribute: Parameter top The top of the near plane
-    Attribute: Parameter near The near plane
-    Attribute: Parameter far The far plane
-
-    Attribute: Returns The matrix as a projection matrix
-
-    Attribute: Example
-
-    use Libraries.Compute.Matrix4
-
-    Matrix4 matrix
-
-    matrix:SetToProjection(0, 10, 0, 10, 0, 1)
-
-    number row0column0 = matrix:row0column0
-    number row0column1 = matrix:row0column1
-    number row0column2 = matrix:row0column2
-    number row0column3 = matrix:row0column3
-    number row1column0 = matrix:row1column0
-    number row1column1 = matrix:row1column1
-    number row1column2 = matrix:row1column2
-    number row1column3 = matrix:row1column3
-    number row2column0 = matrix:row2column0
-    number row2column1 = matrix:row2column1
-    number row2column2 = matrix:row2column2
-    number row2column3 = matrix:row2column3
-    number row3column0 = matrix:row3column0
-    number row3column1 = matrix:row3column1
-    number row3column2 = matrix:row3column2
-    number row3column3 = matrix:row3column3
-
-    output "The new matrix is:"
-    output "|" + row0column0 + ", " + row0column1 + ", " + row0column2 + ", " + row0column3 + "|"
-    output "|" + row1column0 + ", " + row1column1 + ", " + row1column2 + ", " + row1column3 + "|"
-    output "|" + row2column0 + ", " + row2column1 + ", " + row2column2 + ", " + row2column3 + "|"
-    output "|" + row3column0 + ", " + row3column1 + ", " + row3column2 + ", " + row3column3 + "|"
-
-    */
-    action SetToProjection(number left, number right, number bottom, number top, number near, number far) returns Matrix4
-        number x = 2.0 * near / (right - left)
-        number y = 2.0 * near / (top - bottom)
-        number a = (right + left) / (right - left)
-        number b = (top + bottom) / (top - bottom)
-        number l_a1 = (far + near) / (near - far)
-        number l_a2 = (2 * far * near) / (near - far)
-        
-        row0column0 = x
-        row1column0 = 0
-        row2column0 = 0
-        row3column0 = 0
-
-        row0column1 = 0
-        row1column1 = y
-        row2column1 = 0
-        row3column1 = 0
-
-        row0column2 = a
-        row1column2 = b
-        row2column2 = l_a1
-        row3column2 = -1
-
-        row0column3 = 0
-        row1column3 = 0
-        row2column3 = l_a2
-        row3column3 = 0
-
-        return me
-    end
-
-    /*
-    This action sets the matrix to an orthographic projection matrix with an
-    origin at (x, y) with the given width and height. The near and far plane
-    are set to 0 and 1, respectively.
-
-    Attribute: Author Amanda Austin
-
-    Attribute: Parameter x The x-coordinate of the origin
-    Attribute: Parameter y The y-coordinate of the origin
-    Attribute: Parameter width The width
-    Attribute: Parameter height The height
-
-    Attribute: Returns The matrix as a 2D orthographic projection matrix
-
-    Attribute: Example
-
-    use Libraries.Compute.Matrix4
-
-    Matrix4 matrix
-
-    matrix:SetToOrthographic2D(0, 0, 100, 100)
-
-    number row0column0 = matrix:row0column0
-    number row0column1 = matrix:row0column1
-    number row0column2 = matrix:row0column2
-    number row0column3 = matrix:row0column3
-    number row1column0 = matrix:row1column0
-    number row1column1 = matrix:row1column1
-    number row1column2 = matrix:row1column2
-    number row1column3 = matrix:row1column3
-    number row2column0 = matrix:row2column0
-    number row2column1 = matrix:row2column1
-    number row2column2 = matrix:row2column2
-    number row2column3 = matrix:row2column3
-    number row3column0 = matrix:row3column0
-    number row3column1 = matrix:row3column1
-    number row3column2 = matrix:row3column2
-    number row3column3 = matrix:row3column3
-
-    output "The new matrix is:"
-    output "|" + row0column0 + ", " + row0column1 + ", " + row0column2 + ", " + row0column3 + "|"
-    output "|" + row1column0 + ", " + row1column1 + ", " + row1column2 + ", " + row1column3 + "|"
-    output "|" + row2column0 + ", " + row2column1 + ", " + row2column2 + ", " + row2column3 + "|"
-    output "|" + row3column0 + ", " + row3column1 + ", " + row3column2 + ", " + row3column3 + "|"
-
-    */
-    action SetToOrthographic2D(number x, number y, number width, number height) returns Matrix4
-        return SetToOrthographic(x, x + width, y, y + height, 0, 1)
-    end
-
-    /*
-    This action sets the matrix to an orthographic projection matrix with an
-    origin at (x, y) with the given width and height and the given near and
-    far planes.
-
-    Attribute: Author Amanda Austin
-
-    Attribute: Parameter x The x-coordinate of the origin
-    Attribute: Parameter y The y-coordinate of the origin
-    Attribute: Parameter width The width
-    Attribute: Parameter height The height
-    Attribute: Parameter near The near plane
-    Attribute: Parameter far The far plane
-
-    Attribute: Returns The matrix as a 2D orthographic projection matrix
-
-    Attribute: Example
-
-    use Libraries.Compute.Matrix4
-
-    Matrix4 matrix
-
-    matrix:SetToOrthographic2D(0, 0, 100, 100, 0, 1)
-
-    number row0column0 = matrix:row0column0
-    number row0column1 = matrix:row0column1
-    number row0column2 = matrix:row0column2
-    number row0column3 = matrix:row0column3
-    number row1column0 = matrix:row1column0
-    number row1column1 = matrix:row1column1
-    number row1column2 = matrix:row1column2
-    number row1column3 = matrix:row1column3
-    number row2column0 = matrix:row2column0
-    number row2column1 = matrix:row2column1
-    number row2column2 = matrix:row2column2
-    number row2column3 = matrix:row2column3
-    number row3column0 = matrix:row3column0
-    number row3column1 = matrix:row3column1
-    number row3column2 = matrix:row3column2
-    number row3column3 = matrix:row3column3
-
-    output "The new matrix is:"
-    output "|" + row0column0 + ", " + row0column1 + ", " + row0column2 + ", " + row0column3 + "|"
-    output "|" + row1column0 + ", " + row1column1 + ", " + row1column2 + ", " + row1column3 + "|"
-    output "|" + row2column0 + ", " + row2column1 + ", " + row2column2 + ", " + row2column3 + "|"
-    output "|" + row3column0 + ", " + row3column1 + ", " + row3column2 + ", " + row3column3 + "|"
-
-    */
-    action SetToOrthographic2D(number x, number y, number width, number height, number near, number far) returns Matrix4
-        return SetToOrthographic(x, x + width, y, y + height, near, far)
-    end
-
-    /*
-    This action sets the matrix to an orthographic projection matrix.
-
-    Attribute: Author Amanda Austin
-    
-    Attribute: Parameter left The left clipping plane   
-    Attribute: Parameter right The right clipping plane
-    Attribute: Parameter bottom The bottom clipping plane
-    Attribute: Parameter top The top clipping plane
-    Attribute: Parameter near The near plane
-    Attribute: Parameter far The far plane
-
-    Attribute: Returns The matrix as an orthographic projection matrix
-    
-    Attribute: Example
-
-    use Libraries.Compute.Matrix4
-    
-    Matrix4 matrix
-
-    matrix:SetToOrthographic(0, 1, 0, 1, 0, 1)
-
-    number row0column0 = matrix:row0column0
-    number row0column1 = matrix:row0column1
-    number row0column2 = matrix:row0column2
-    number row0column3 = matrix:row0column3
-    number row1column0 = matrix:row1column0
-    number row1column1 = matrix:row1column1
-    number row1column2 = matrix:row1column2
-    number row1column3 = matrix:row1column3
-    number row2column0 = matrix:row2column0
-    number row2column1 = matrix:row2column1
-    number row2column2 = matrix:row2column2
-    number row2column3 = matrix:row2column3
-    number row3column0 = matrix:row3column0
-    number row3column1 = matrix:row3column1
-    number row3column2 = matrix:row3column2
-    number row3column3 = matrix:row3column3
-
-    output "The new matrix is:"
-    output "|" + row0column0 + ", " + row0column1 + ", " + row0column2 + ", " + row0column3 + "|"
-    output "|" + row1column0 + ", " + row1column1 + ", " + row1column2 + ", " + row1column3 + "|"
-    output "|" + row2column0 + ", " + row2column1 + ", " + row2column2 + ", " + row2column3 + "|"
-    output "|" + row3column0 + ", " + row3column1 + ", " + row3column2 + ", " + row3column3 + "|"
-
-    */
-    action SetToOrthographic(number left, number right, number bottom, number top, number near, number far) returns Matrix4    
-        IdentityMatrix()
-        number x_orth = 2 / (right - left)
-        number y_orth = 2 / (top - bottom)
-        number z_orth = -2 / (far - near)
-
-        number tx = -1 * (right + left) / (right - left)
-        number ty = -1 * (top + bottom) / (top - bottom)
-        number tz = -1 * (far + near) / (far - near)
-
-        row0column0 = x_orth
-        row1column0 = 0
-        row2column0 = 0
-        row3column0 = 0
-
-        row0column1 = 0
-        row1column1 = y_orth
-        row2column1 = 0
-        row3column1 = 0
-
-        row0column2 = 0
-        row1column2 = 0
-        row2column2 = z_orth
-        row3column2 = 0
-
-        row0column3 = tx
-        row1column3 = ty
-        row2column3 = tz
-        row3column3 = 1
-
-        return me
-    end
-
     /*
     This action sets the translational component of the matrix to the given
     translation vector.
@@ -2629,26 +2295,26 @@ result = result + "|" + row3column0 + ", " + row3column1 + ", " + row3column2 +
     output "|" + row3column0 + ", " + row3column1 + ", " + row3column2 + ", " + row3column3 + "|"
 
     */
-    action SetToLookAt(Vector3 direction, Vector3 up) returns Matrix4
-        l_vez:Set(direction):Normalize()
-        l_vex:Set(direction):Normalize()
-        l_vex:CrossProduct(up):Normalize()
-        l_vey:Set(l_vex):CrossProduct(l_vez):Normalize()
-
-        IdentityMatrix()
-
-        row0column0 = l_vex:GetX()
-        row0column1 = l_vex:GetY()
-        row0column2 = l_vex:GetZ()
-        row1column0 = l_vey:GetX()
-        row1column1 = l_vey:GetY()
-        row1column2 = l_vey:GetZ()
-        row2column0 = -1 * l_vez:GetX()
-        row2column1 = -1 * l_vez:GetY()
-        row2column2 = -1 * l_vez:GetZ()
-
-        return me
-    end
+    //action SetToLookAt(Vector3 direction, Vector3 up) returns Matrix4
+        //l_vez:Set(direction):Normalize()
+        //l_vex:Set(direction):Normalize()
+        //l_vex:CrossProduct(up):Normalize()
+        //l_vey:Set(l_vex):CrossProduct(l_vez):Normalize()
+//
+        //IdentityMatrix()
+//
+        //row0column0 = l_vex:GetX()
+        //row0column1 = l_vex:GetY()
+        //row0column2 = l_vex:GetZ()
+        //row1column0 = l_vey:GetX()
+        //row1column1 = l_vey:GetY()
+        //row1column2 = l_vey:GetZ()
+        //row2column0 = -1 * l_vez:GetX()
+        //row2column1 = -1 * l_vez:GetY()
+        //row2column2 = -1 * l_vez:GetZ()
+//
+        //return me
+    //end
 
 
     /*
@@ -2704,19 +2370,19 @@ result = result + "|" + row3column0 + ", " + row3column1 + ", " + row3column2 +
     output "|" + row3column0 + ", " + row3column1 + ", " + row3column2 + ", " + row3column3 + "|"
 
     */
-    action SetToLookAt(Vector3 position, Vector3 target, Vector3 up) returns Matrix4
-        tmpVec:Set(target):Subtract(position)
-        SetToLookAt(tmpVec, up)
-
-        if tmpMat = undefined
-            Matrix4 newMatrix
-            tmpMat = newMatrix
-        end
-
-        me:Multiply(tmpMat:SetToTranslation(-1 * position:GetX(), -1 * position:GetY(), -1 * position:GetZ()))
-
-        return me
-    end
+    //action SetToLookAt(Vector3 position, Vector3 target, Vector3 up) returns Matrix4
+        //tmpVec:Set(target):Subtract(position)
+        //SetToLookAt(tmpVec, up)
+//
+        //if tmpMat = undefined
+            //Matrix4 newMatrix
+            //tmpMat = newMatrix
+        //end
+//
+        //me:Multiply(tmpMat:SetToTranslation(-1 * position:GetX(), -1 * position:GetY(), -1 * position:GetZ()))
+//
+        //return me
+    //end
 
     /*
     This action sets the matrix to a world with the given position, forward, and
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/Camera.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/Camera.quorum
index c1dfa38a9..71ceea226 100644
--- a/Quorum/Library/Standard/Libraries/Game/Graphics/Camera.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/Camera.quorum
@@ -28,22 +28,22 @@ class Camera
     /*
     The projection matrix of the camera.
     */
-    Matrix4 projection
+    CameraMatrix4 projection
 
     /*
     The view matrix of the camera.
     */
-    Matrix4 view
+    CameraMatrix4 view
 
     /*
     The combined projection and view matrix of the camera.
     */
-    Matrix4 combined
+    CameraMatrix4 combined
 
     /*
     The inverse of the combined projection and view matrix.
     */
-    Matrix4 inverseProjectionView
+    CameraMatrix4 inverseProjectionView
 
     /*
     The distance to the near clipping plane. Objects whose distance to the
@@ -78,7 +78,9 @@ class Camera
     private Math math
 
     on create
-        direction:Set(0, 0, -1)
+        // The world is left-handed, so a camera that has not been aimed looks
+        // into the screen, along +z.
+        direction:Set(0, 0, 1)
         up:Set(0, 1, 0)
 
         GameStateManager manager
@@ -1412,7 +1414,7 @@ class Camera
 
     use Libraries.Game.Game
     use Libraries.Game.Graphics.Camera
-    use Libraries.Compute.Matrix4
+    use Libraries.Game.Graphics.CameraMatrix4
 
     class Main is Game
 
@@ -1422,7 +1424,7 @@ class Camera
 
         action CreateGame
             Camera cam = GetCamera3D()
-            Matrix4 projection = cam:GetProjectionMatrix()
+            CameraMatrix4 projection = cam:GetProjectionMatrix()
         end
 
         action Update(number seconds)
@@ -1431,7 +1433,7 @@ class Camera
     end
 
     */
-    action GetProjectionMatrix returns Matrix4
+    action GetProjectionMatrix returns CameraMatrix4
         return projection
     end
 
@@ -1445,7 +1447,7 @@ class Camera
 
     use Libraries.Game.Game
     use Libraries.Game.Graphics.Camera
-    use Libraries.Compute.Matrix4
+    use Libraries.Game.Graphics.CameraMatrix4
 
     class Main is Game
 
@@ -1456,7 +1458,7 @@ class Camera
         action CreateGame
 
             Camera cam = GetCamera3D()
-            Matrix4 view = cam:GetViewMatrix()
+            CameraMatrix4 view = cam:GetViewMatrix()
         end
 
         action Update(number seconds)
@@ -1465,7 +1467,7 @@ class Camera
     end
 
     */
-    action GetViewMatrix returns Matrix4
+    action GetViewMatrix returns CameraMatrix4
         return view
     end
 
@@ -1480,7 +1482,7 @@ class Camera
 
     use Libraries.Game.Game
     use Libraries.Game.Graphics.Camera
-    use Libraries.Compute.Matrix4
+    use Libraries.Game.Graphics.CameraMatrix4
 
     class Main is Game
 
@@ -1491,7 +1493,7 @@ class Camera
         action CreateGame
 
             Camera cam = GetCamera3D()
-            Matrix4 combined = cam:GetCombinedMatrix()
+            CameraMatrix4 combined = cam:GetCombinedMatrix()
         end
 
         action Update(number seconds)
@@ -1500,7 +1502,7 @@ class Camera
     end
 
     */
-    action GetCombinedMatrix returns Matrix4
+    action GetCombinedMatrix returns CameraMatrix4
         return combined
     end
 
@@ -1515,7 +1517,7 @@ class Camera
 
     use Libraries.Game.Game
     use Libraries.Game.Graphics.Camera
-    use Libraries.Compute.Matrix4
+    use Libraries.Game.Graphics.CameraMatrix4
 
     class Main is Game
 
@@ -1526,7 +1528,7 @@ class Camera
         action CreateGame
 
             Camera cam = GetCamera3D()
-            Matrix4 inverse = cam:GetInverseCombinedMatrix()
+            CameraMatrix4 inverse = cam:GetInverseCombinedMatrix()
         end
 
         action Update(number seconds)
@@ -1535,7 +1537,7 @@ class Camera
     end
 
     */
-    action GetInverseCombinedMatrix returns Matrix4
+    action GetInverseCombinedMatrix returns CameraMatrix4
         return inverseProjectionView
     end
 
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/CameraMatrix4.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/CameraMatrix4.quorum
new file mode 100644
index 000000000..9620ad1a9
--- /dev/null
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/CameraMatrix4.quorum
@@ -0,0 +1,444 @@
+package Libraries.Game.Graphics
+
+use Libraries.Compute.Matrix4
+use Libraries.Game.GameStateManager
+use Libraries.Compute.Math
+use Libraries.Compute.Vector3
+
+class CameraMatrix4 is Matrix4
+    
+    GameStateManager manager
+    Math math
+    
+    /*
+    This action sets the matrix to a projection matrix with the near and far
+    planes, the field of view height, and the aspect ratio. 
+
+    Attribute: Author Amanda Austin
+
+    Attribute: Parameter nearPlane The near plane
+    Attribute: Parameter farPlane The far plane
+    Attribute: Parameter fieldOfViewHeight The height of the field of view
+    Attribute: Parameter aspectRatio the aspect ratio
+
+    Attribute: Returns The matrix as a projection matrix
+
+    Attribute: Example
+
+    use Libraries.Compute.Matrix4
+
+    Matrix4 matrix
+
+    matrix:SetToProjection(0, 1, 10, 2)
+    
+    number row0column0 = matrix:row0column0
+    number row0column1 = matrix:row0column1
+    number row0column2 = matrix:row0column2
+    number row0column3 = matrix:row0column3
+    number row1column0 = matrix:row1column0
+    number row1column1 = matrix:row1column1
+    number row1column2 = matrix:row1column2
+    number row1column3 = matrix:row1column3
+    number row2column0 = matrix:row2column0
+    number row2column1 = matrix:row2column1
+    number row2column2 = matrix:row2column2
+    number row2column3 = matrix:row2column3
+    number row3column0 = matrix:row3column0
+    number row3column1 = matrix:row3column1
+    number row3column2 = matrix:row3column2
+    number row3column3 = matrix:row3column3
+
+    output "The new matrix is:"
+    output "|" + row0column0 + ", " + row0column1 + ", " + row0column2 + ", " + row0column3 + "|"
+    output "|" + row1column0 + ", " + row1column1 + ", " + row1column2 + ", " + row1column3 + "|"
+    output "|" + row2column0 + ", " + row2column1 + ", " + row2column2 + ", " + row2column3 + "|"
+    output "|" + row3column0 + ", " + row3column1 + ", " + row3column2 + ", " + row3column3 + "|"
+
+    */
+    action PerspectiveProjection(number nearPlane, number farPlane, number fieldOfViewHeight, number aspectRatio) returns Matrix4
+        if manager:GetGameGraphics() not= undefined
+            DeviceCoordinates ndc = manager:GetGameGraphics():GetDeviceCoordinates()
+            PerspectiveProjection(nearPlane, farPlane, fieldOfViewHeight, aspectRatio, ndc:GetDefaultCoordinateSpace(), ndc:GetDefaultDepthRange())
+        end
+        return me
+    end
+    
+    /*
+    This action sets the matrix to a projection matrix with the near and far
+    planes, the field of view height, and the aspect ratio. The coordinate system and
+    depth range used are defined by constants available in MatrixCoordinateSpace. 
+
+    Attribute: Parameter nearPlane The near plane
+    Attribute: Parameter farPlane The far plane
+    Attribute: Parameter fieldOfViewHeight The height of the field of view
+    Attribute: Parameter aspectRatio the aspect ratio
+    Attribute: Parameter coordinateSystem A constant from MatrixCoordinateSpace indicating which coordinate system the matrix is projecting to.
+    Attribute: Parameter depthRange A constant from MatrixCoordinateSpace indicating the depth range the matrix will project to.
+
+    Attribute: Returns The matrix as a projection matrix
+
+    Attribute: Example
+
+    use Libraries.Compute.Matrix4
+    use Libraries.Game.Graphics.MatrixCoordinateSpace
+
+    Matrix4 matrix
+    MatrixCoordinateSpace space
+
+    matrix:SetToProjection(0, 1, 10, 2, space:LEFT_HANDED, space:DEPTH_ZERO_TO_ONE)
+    
+    number row0column0 = matrix:row0column0
+    number row0column1 = matrix:row0column1
+    number row0column2 = matrix:row0column2
+    number row0column3 = matrix:row0column3
+    number row1column0 = matrix:row1column0
+    number row1column1 = matrix:row1column1
+    number row1column2 = matrix:row1column2
+    number row1column3 = matrix:row1column3
+    number row2column0 = matrix:row2column0
+    number row2column1 = matrix:row2column1
+    number row2column2 = matrix:row2column2
+    number row2column3 = matrix:row2column3
+    number row3column0 = matrix:row3column0
+    number row3column1 = matrix:row3column1
+    number row3column2 = matrix:row3column2
+    number row3column3 = matrix:row3column3
+
+    output "The new matrix is:"
+    output "|" + row0column0 + ", " + row0column1 + ", " + row0column2 + ", " + row0column3 + "|"
+    output "|" + row1column0 + ", " + row1column1 + ", " + row1column2 + ", " + row1column3 + "|"
+    output "|" + row2column0 + ", " + row2column1 + ", " + row2column2 + ", " + row2column3 + "|"
+    output "|" + row3column0 + ", " + row3column1 + ", " + row3column2 + ", " + row3column3 + "|"
+
+    */
+    action PerspectiveProjection(number nearPlane, number farPlane, number fieldOfViewHeight, number aspectRatio, integer coordinateSystem, integer depthRange) returns Matrix4
+        DeviceCoordinates ndc = undefined
+        if manager:GetGameGraphics() not= undefined
+            ndc = manager:GetGameGraphics():GetDeviceCoordinates()
+        else
+            DeviceCoordinates coords
+            ndc = coords
+        end
+        
+        number l_fd = 1.0 / math:Tangent((fieldOfViewHeight * (math:pi / 180)) / 2.0)
+        number l_a1 = (farPlane + nearPlane) / (nearPlane - farPlane)
+        number l_a2 = (2 * farPlane * nearPlane) / (nearPlane - farPlane)
+
+        // Set the entries in the column that are the same across the different coordinate systems first.
+        //parent:Matrix4:row0column0 = -l_fd / aspectRatio
+        parent:Matrix4:row0column0 = l_fd / aspectRatio
+        parent:Matrix4:row1column0 = 0
+        parent:Matrix4:row2column0 = 0
+        parent:Matrix4:row3column0 = 0
+
+        parent:Matrix4:row0column1 = 0
+        parent:Matrix4:row1column1 = l_fd
+        parent:Matrix4:row2column1 = 0
+        parent:Matrix4:row3column1 = 0
+
+        parent:Matrix4:row0column2 = 0
+        parent:Matrix4:row1column2 = 0
+        
+        parent:Matrix4:row0column3 = 0
+        parent:Matrix4:row1column3 = 0
+        parent:Matrix4:row3column3 = 0
+        
+        number numerator1 = 0
+        number numerator2 = 0
+        number denominator = 0
+        if coordinateSystem = ndc:RIGHT_HANDED
+            //parent:Matrix4:row0column0 = -l_fd / aspectRatio
+            //parent:Matrix4:row0column0 = -l_fd / aspectRatio
+            denominator = farPlane - nearPlane
+            parent:Matrix4:row3column2 = 1
+            //denominator = nearPlane - farPlane
+            //parent:Matrix4:row3column2 = -1
+        else
+            //parent:Matrix4:row0column0 = l_fd / aspectRatio
+            denominator = farPlane - nearPlane
+            parent:Matrix4:row3column2 = 1
+        end
+        if depthRange = ndc:DEPTH_NEGATIVE_ONE_TO_ONE
+            numerator1 = farPlane + nearPlane
+            numerator2 = -2 * farPlane * nearPlane
+        else
+            numerator1 = farPlane
+            numerator2 = -farPlane * nearPlane
+        end
+        
+        parent:Matrix4:row2column2 = numerator1 / denominator
+        parent:Matrix4:row2column3 = numerator2 / denominator
+
+        return me
+    end
+    
+    /*
+    This action sets the matrix to an orthographic projection, which shows
+    everything at the same size however far away it is. The box between left
+    and right, bottom and top, and the near and far planes is mapped to the
+    screen. The coordinate system and depth range are the game's defaults,
+    from DeviceCoordinates.
+
+    Attribute: Parameter left The left edge of the visible area
+    Attribute: Parameter right The right edge of the visible area
+    Attribute: Parameter bottom The bottom edge of the visible area
+    Attribute: Parameter top The top edge of the visible area
+    Attribute: Parameter nearPlane The near plane
+    Attribute: Parameter farPlane The far plane
+    Attribute: Returns The matrix as an orthographic projection matrix
+
+    Attribute: Example
+
+    use Libraries.Game.Graphics.CameraMatrix4
+
+    CameraMatrix4 matrix
+    matrix:OrthographicProjection(0, 100, 0, 100, 0, 1)
+    */
+    action OrthographicProjection(number left, number right, number bottom, number top, number nearPlane, number farPlane) returns Matrix4
+        DeviceCoordinates ndc = undefined
+        if manager:GetGameGraphics() not= undefined
+            ndc = manager:GetGameGraphics():GetDeviceCoordinates()
+        else
+            DeviceCoordinates coords
+            ndc = coords
+        end
+        return OrthographicProjection(left, right, bottom, top, nearPlane, farPlane, ndc:GetDefaultCoordinateSpace(), ndc:GetDefaultDepthRange())
+    end
+
+    /*
+    This action sets the matrix to an orthographic projection with the given
+    coordinate system and depth range, using the constants in
+    DeviceCoordinates. In a left-handed system the camera looks along +z, so
+    depth grows as z grows. In a right-handed system it looks along -z, so
+    depth grows as z shrinks. The depth range is the range the near and far
+    planes are mapped to: 0 to 1 (Vulkan) or -1 to 1 (OpenGL).
+
+    Attribute: Parameter left The left edge of the visible area
+    Attribute: Parameter right The right edge of the visible area
+    Attribute: Parameter bottom The bottom edge of the visible area
+    Attribute: Parameter top The top edge of the visible area
+    Attribute: Parameter nearPlane The near plane
+    Attribute: Parameter farPlane The far plane
+    Attribute: Parameter coordinateSystem LEFT_HANDED or RIGHT_HANDED, from DeviceCoordinates
+    Attribute: Parameter depthRange DEPTH_ZERO_TO_ONE or DEPTH_NEGATIVE_ONE_TO_ONE, from DeviceCoordinates
+    Attribute: Returns The matrix as an orthographic projection matrix
+
+    Attribute: Example
+
+    use Libraries.Game.Graphics.CameraMatrix4
+    use Libraries.Game.Graphics.DeviceCoordinates
+
+    CameraMatrix4 matrix
+    DeviceCoordinates ndc
+    matrix:OrthographicProjection(0, 100, 0, 100, 0, 1, ndc:LEFT_HANDED, ndc:DEPTH_ZERO_TO_ONE)
+    */
+    action OrthographicProjection(number left, number right, number bottom, number top, number nearPlane, number farPlane,
+            integer coordinateSystem, integer depthRange) returns Matrix4
+        DeviceCoordinates ndc
+        IdentityMatrix()
+        parent:Matrix4:row0column0 = 2 / (right - left)
+        parent:Matrix4:row1column1 = 2 / (top - bottom)
+        parent:Matrix4:row0column3 = -1 * (right + left) / (right - left)
+        parent:Matrix4:row1column3 = -1 * (top + bottom) / (top - bottom)
+
+        number facing = 1
+        if coordinateSystem = ndc:RIGHT_HANDED
+            facing = -1
+        end
+
+        if depthRange = ndc:DEPTH_ZERO_TO_ONE
+            parent:Matrix4:row2column2 = facing / (farPlane - nearPlane)
+            parent:Matrix4:row2column3 = -1 * nearPlane / (farPlane - nearPlane)
+        else
+            parent:Matrix4:row2column2 = facing * 2 / (farPlane - nearPlane)
+            parent:Matrix4:row2column3 = -1 * (farPlane + nearPlane) / (farPlane - nearPlane)
+        end
+        return me
+    end
+
+    /*
+    This action sets the matrix to look at another matrix with a direction and
+    an up vector. When multiplied with a translation matrix, we get a camera
+    model view matrix.
+
+    Attribute: Author Amanda Austin
+    
+    Attribute: Parameter direction The direction vector
+    Attribute: Parameter up The up vector
+
+    Attribute: Returns the matrix
+
+    Attribute: Example
+
+    use Libraries.Compute.Matrix4
+    use Libraries.Compute.Vector3
+
+    Matrix4 matrix
+    Vector3 direction
+    Vector3 up
+
+    direction:Set(0, 0, 1)
+    up:Set(0, 1, 0)
+
+    matrix:SetToLookAt(direction, up)
+
+    number row0column0 = matrix:row0column0
+    number row0column1 = matrix:row0column1
+    number row0column2 = matrix:row0column2
+    number row0column3 = matrix:row0column3
+    number row1column0 = matrix:row1column0
+    number row1column1 = matrix:row1column1
+    number row1column2 = matrix:row1column2
+    number row1column3 = matrix:row1column3
+    number row2column0 = matrix:row2column0
+    number row2column1 = matrix:row2column1
+    number row2column2 = matrix:row2column2
+    number row2column3 = matrix:row2column3
+    number row3column0 = matrix:row3column0
+    number row3column1 = matrix:row3column1
+    number row3column2 = matrix:row3column2
+    number row3column3 = matrix:row3column3
+
+    output "The new matrix is:"
+    output "|" + row0column0 + ", " + row0column1 + ", " + row0column2 + ", " + row0column3 + "|"
+    output "|" + row1column0 + ", " + row1column1 + ", " + row1column2 + ", " + row1column3 + "|"
+    output "|" + row2column0 + ", " + row2column1 + ", " + row2column2 + ", " + row2column3 + "|"
+    output "|" + row3column0 + ", " + row3column1 + ", " + row3column2 + ", " + row3column3 + "|"
+
+    */
+    action SetToLookAt(Vector3 direction, Vector3 up) returns Matrix4
+        DeviceCoordinates ndc = undefined
+        if manager:GetGameGraphics() not= undefined
+            ndc = manager:GetGameGraphics():GetDeviceCoordinates()
+        else
+            DeviceCoordinates coords
+            ndc = coords
+        end
+        
+        Vector3 l_vex = parent:Matrix4:l_vex
+        Vector3 l_vey = parent:Matrix4:l_vey
+        Vector3 l_vez = parent:Matrix4:l_vez
+        
+        l_vez:Set(direction):Normalize()
+        
+        //if ndc:GetDefaultDepthRange() = ndc:DEPTH_ZERO_TO_ONE
+            //l_vex:Set(up):Normalize()
+        //l_vex:CrossProduct(direction):Normalize()
+            //l_vey:Set(l_vez):CrossProduct(l_vex):Normalize()
+        //else
+            //l_vex:Set(direction):Normalize()
+        //l_vex:CrossProduct(up):Normalize()
+            //l_vey:Set(l_vex):CrossProduct(l_vez):Normalize()
+        //end
+        l_vex:Set(up):Normalize()
+        l_vex:CrossProduct(direction):Normalize()
+            l_vey:Set(l_vez):CrossProduct(l_vex):Normalize()
+        
+
+        IdentityMatrix()
+
+        // TO-DO: Invert z axis for other-handed systems. Inverted order of elements in cross product can also potentially achieve this.
+        
+        parent:Matrix4:row0column0 = l_vex:GetX()
+        parent:Matrix4:row0column1 = l_vex:GetY()
+        parent:Matrix4:row0column2 = l_vex:GetZ()
+        parent:Matrix4:row1column0 = l_vey:GetX()
+        parent:Matrix4:row1column1 = l_vey:GetY()
+        parent:Matrix4:row1column2 = l_vey:GetZ()
+        //if ndc:GetDefaultCoordinateSpace() = ndc:RIGHT_HANDED
+            //parent:Matrix4:row2column0 = -1 * l_vez:GetX()
+        //parent:Matrix4:row2column1 = -1 * l_vez:GetY()
+        //parent:Matrix4:row2column2 = -1 * l_vez:GetZ()
+        //else
+            //parent:Matrix4:row2column0 = l_vez:GetX()
+        //parent:Matrix4:row2column1 = l_vez:GetY()
+        //parent:Matrix4:row2column2 = l_vez:GetZ()
+        //end
+        parent:Matrix4:row2column0 = l_vez:GetX()
+        parent:Matrix4:row2column1 = l_vez:GetY()
+        parent:Matrix4:row2column2 = l_vez:GetZ()
+
+        return me
+    end
+
+
+    /*
+    This action sets the matrix to look at another matrix with a direction,
+    target, and up vector. When multiplied with a translation matrix, we get a 
+    camera model view matrix.
+
+    Attribute: Author Amanda Austin
+    
+    Attribute: Parameter direction The direction vector
+    Attribute: Parameter target The target vector
+    Attribute: Parameter up The up vector
+
+    Attribute: Returns the matrix
+
+    Attribute: Example
+
+    use Libraries.Compute.Matrix4
+    use Libraries.Compute.Vector3
+
+    Matrix4 matrix
+    Vector3 direction
+    Vector3 target
+    Vector3 up
+
+    direction:Set(0, 0, 1)
+    target:Set(0, 0, 3)
+    up:Set(0, 1, 0)
+
+    matrix:SetToLookAt(direction, target, up)
+
+    number row0column0 = matrix:row0column0
+    number row0column1 = matrix:row0column1
+    number row0column2 = matrix:row0column2
+    number row0column3 = matrix:row0column3
+    number row1column0 = matrix:row1column0
+    number row1column1 = matrix:row1column1
+    number row1column2 = matrix:row1column2
+    number row1column3 = matrix:row1column3
+    number row2column0 = matrix:row2column0
+    number row2column1 = matrix:row2column1
+    number row2column2 = matrix:row2column2
+    number row2column3 = matrix:row2column3
+    number row3column0 = matrix:row3column0
+    number row3column1 = matrix:row3column1
+    number row3column2 = matrix:row3column2
+    number row3column3 = matrix:row3column3
+
+    output "The new matrix is:"
+    output "|" + row0column0 + ", " + row0column1 + ", " + row0column2 + ", " + row0column3 + "|"
+    output "|" + row1column0 + ", " + row1column1 + ", " + row1column2 + ", " + row1column3 + "|"
+    output "|" + row2column0 + ", " + row2column1 + ", " + row2column2 + ", " + row2column3 + "|"
+    output "|" + row3column0 + ", " + row3column1 + ", " + row3column2 + ", " + row3column3 + "|"
+
+    */
+    action SetToLookAt(Vector3 position2, Vector3 target2, Vector3 up2) returns Matrix4
+        Vector3 position
+        //position:Set(-position2:GetX(), position2:GetY(), -position2:GetZ())
+        position:Set(position2)
+        Vector3 target
+        //target:Set(-target2:GetX(), target2:GetY(), -target2:GetZ())
+        target:Set(target2)
+        Vector3 up
+        //up:Set(-up2:GetX(), up2:GetY(), -up2:GetZ())
+        up:Set(up2)
+        
+        Vector3 tmpVec = parent:Matrix4:tmpVec
+        tmpVec:Set(target):Subtract(position)
+        SetToLookAt(tmpVec, up)
+
+        if parent:Matrix4:tmpMat = undefined
+            Matrix4 newMatrix
+            parent:Matrix4:tmpMat = newMatrix
+        end
+
+        me:Multiply(parent:Matrix4:tmpMat:SetToTranslation(-1 * position:GetX(), -1 * position:GetY(), -1 * position:GetZ()))
+
+        return me
+    end
+    
+    
+end
\ No newline at end of file
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/DeviceCoordinates.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/DeviceCoordinates.quorum
new file mode 100644
index 000000000..2ffab8084
--- /dev/null
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/DeviceCoordinates.quorum
@@ -0,0 +1,39 @@
+package Libraries.Game.Graphics
+
+/*This class manages the default NDC (normalized device coordinates) used by the Game when
+performing projection calculations. Different graphics systems
+use different coordinate systems when translating world coordinates to screen space.
+When the CameraMatrix4 class calculates projections, if no coordinate system or depth range
+is specified, it uses the default NDC stored here.
+
+By default, OpenGL uses a right handed coordinate system for calculations, and Vulkan
+uses a left handed coordinate system. OpenGL maps its depth range from -1 to 1, and
+Vulkan maps its depth range from 0 to 1. These values are automatically set when a Game
+is created, so most users will never need to use this class directly.*/
+class DeviceCoordinates
+    
+    public constant integer LEFT_HANDED = 0
+    public constant integer RIGHT_HANDED = 1
+    public constant integer DEPTH_NEGATIVE_ONE_TO_ONE = 2
+    public constant integer DEPTH_ZERO_TO_ONE = 3
+    
+    integer defaultCoordinateSpace = LEFT_HANDED
+    integer defaultDepthRange = DEPTH_NEGATIVE_ONE_TO_ONE
+    
+    action GetDefaultCoordinateSpace returns integer
+        return defaultCoordinateSpace
+    end
+
+    action SetDefaultCoordinateSpace(integer defaultCoordinateSpace)
+        me:defaultCoordinateSpace = defaultCoordinateSpace
+    end
+
+    action GetDefaultDepthRange returns integer
+        return defaultDepthRange
+    end
+
+    action SetDefaultDepthRange(integer defaultDepthRange)
+        me:defaultDepthRange = defaultDepthRange
+    end
+
+end
\ No newline at end of file
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/GraphicsManager.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/GraphicsManager.quorum
index 9e4eb4288..6dd7193ce 100644
--- a/Quorum/Library/Standard/Libraries/Game/Graphics/GraphicsManager.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/GraphicsManager.quorum
@@ -5,6 +5,8 @@ use Libraries.Game.Graphics.Shaders.Programs.ShaderProgramStrategy
 
 class GraphicsManager
     
+    DeviceCoordinates deviceCoordinates
+    
     /*This action sets the background color of the window. This is the color used to clear
 the screen between each frame of animation. 
 Attribute: Parameter red The red component of the color, as a number between 0.0 (no red) and 1.0 (full red).
@@ -273,4 +275,8 @@ blueprint action CreateShaderProgram(ShaderProgramStrategy program) returns inte
     */
 //    blueprint action SetVertexInputInformation(integer inputID, integer size, integer type, boolean normalize, integer stride, Number32BitBuffer buffer)
     
+    action GetDeviceCoordinates returns DeviceCoordinates
+        return deviceCoordinates
+    end
+
 end
\ No newline at end of file
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/MeshBuilder.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/MeshBuilder.quorum
index daf38ffb3..eea18f6d9 100644
--- a/Quorum/Library/Standard/Libraries/Game/Graphics/MeshBuilder.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/MeshBuilder.quorum
@@ -972,14 +972,17 @@ begin(createAttributes(attributes), primitiveType);
     LINES, or TRIANGLES - otherwise, an error will be thrown.
     */
     action BuildRectangle(Vector3 corner00, Vector3 corner10, Vector3 corner11, Vector3 corner01, Vector3 normal)
+        // The world is left-handed, so u runs from corner10 to corner00:
+        // left to right when the rectangle is seen from the side its normal
+        // points to.
         vertTemp1:Set(corner00, normal, undefined, undefined)
-        vertTemp1:SetTextureCoordinates(0, 1)
+        vertTemp1:SetTextureCoordinates(1, 1)
         vertTemp2:Set(corner10, normal, undefined, undefined)
-        vertTemp2:SetTextureCoordinates(1, 1)
+        vertTemp2:SetTextureCoordinates(0, 1)
         vertTemp3:Set(corner11, normal, undefined, undefined)
-        vertTemp3:SetTextureCoordinates(1, 0)
+        vertTemp3:SetTextureCoordinates(0, 0)
         vertTemp4:Set(corner01, normal, undefined, undefined)
-        vertTemp4:SetTextureCoordinates(0, 0)
+        vertTemp4:SetTextureCoordinates(1, 0)
         BuildRectangle(vertTemp1, vertTemp2, vertTemp3, vertTemp4)
     end
 
@@ -1311,7 +1314,8 @@ begin(createAttributes(attributes), primitiveType);
         integer counter = 0
         repeat while counter <= divisions
             angle = startAngle + step * counter
-            u = 1.0 - divisionStep * counter
+            // u grows with the angle, which is left to right seen from outside.
+            u = divisionStep * counter
             current1:SetPosition(math:Cosine(angle) * halfWidth, 0, math:Sine(angle) * halfDepth)
             current1:SetNormal(tempVector8:Set(current1:GetPosition()):Normalize())
             current1:GetPosition():SetY(-halfHeight)
@@ -1510,7 +1514,9 @@ begin(createAttributes(attributes), primitiveType);
             currEx:SetPosition(centerX, centerY, centerZ)
             currEx:GetPosition():Add(sxEx:GetX() * x + syEx:GetX() * y, sxEx:GetY() * x + syEx:GetY() * y,
                 sxEx:GetZ() * x + syEx:GetZ() * y)
-            currEx:SetTextureCoordinates(0.5 + 0.5 * x, 0.5 + 0.5 * y)
+            // u runs against the tangent, so the ellipse is not mirrored in the
+            // left-handed world.
+            currEx:SetTextureCoordinates(0.5 - 0.5 * x, 0.5 + 0.5 * y)
 
             i1 = AddVertex(currEx)
             
@@ -1528,7 +1534,7 @@ begin(createAttributes(attributes), primitiveType);
                 currIn:SetPosition(centerX, centerY, centerZ)
                 currIn:GetPosition():Add(sxIn:GetX() * x + syIn:GetX() * y, sxIn:GetY() * x + syIn:GetY() * y,
                     sxIn:GetZ() * x + syIn:GetZ() * y)
-                currIn:SetTextureCoordinates(0.5 + us * x, 0.5 + vs * y)
+                currIn:SetTextureCoordinates(0.5 - us * x, 0.5 + vs * y)
 
                 i2 = i1
                 i1 = AddVertex(currIn)
@@ -1594,7 +1600,8 @@ begin(createAttributes(attributes), primitiveType);
             integer iu = 0
             repeat while iu <= divisionsU
                 angleU = auo + stepU * iu
-                u = 1.0 - us * iu
+                // u grows with the angle, which is left to right seen from outside.
+                u = us * iu
 
                 curr1:GetPosition():Set(math:Cosine(angleU) * halfWidth * t, h, math:Sine(angleU) * halfDepth * t)
                 curr1:GetNormal():Set(curr1:GetPosition()):Normalize()
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/ModelLoaders/ModelReader.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/ModelLoaders/ModelReader.quorum
index b6fe29663..72399d51f 100644
--- a/Quorum/Library/Standard/Libraries/Game/Graphics/ModelLoaders/ModelReader.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/ModelLoaders/ModelReader.quorum
@@ -402,7 +402,11 @@ class ModelReader
                     schematic3:SetTextureCoordinates(textures:Get(newPoint:GetTexture() - 1):GetVector():GetX(), textures:Get(newPoint:GetTexture() - 1):GetVector():GetY())
                 end
 
-                meshBuilder:AddTriangle(schematic1, schematic2, schematic3)
+                // Flipping z on load leaves the file's front faces winding
+                // counterclockwise on screen. Swapping the second and third
+                // corners makes them clockwise, the front in the left-handed
+                // world.
+                meshBuilder:AddTriangle(schematic1, schematic3, schematic2)
 
                 facePartCounter = facePartCounter + 1
             end
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/ModelLoaders/WavefrontObject/WavefrontConverterListener.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/ModelLoaders/WavefrontObject/WavefrontConverterListener.quorum
index 530517329..2ceb54b3a 100644
--- a/Quorum/Library/Standard/Libraries/Game/Graphics/ModelLoaders/WavefrontObject/WavefrontConverterListener.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/ModelLoaders/WavefrontObject/WavefrontConverterListener.quorum
@@ -160,8 +160,10 @@ class WavefrontConverterListener is WavefrontObjectListener
                 Vector3 vector = currentPosition:GetVector()
                 vector:SetY(cast(number, terminal:value))
             elseif positionIndex = 2
+                // OBJ files are right-handed and the world is left-handed, so z
+                // is flipped as it is read.
                 Vector3 vector = currentPosition:GetVector()
-                vector:SetZ(cast(number, terminal:value))
+                vector:SetZ(-1 * cast(number, terminal:value))
             elseif positionIndex = 3
                 currentPosition:SetWidth(cast(number, terminal:value))
             end
@@ -174,8 +176,9 @@ class WavefrontConverterListener is WavefrontObjectListener
                 Vector3 vector = currentNormal:GetVector()
                 vector:SetY(cast(number, terminal:value))
             elseif normalIndex = 2
+                // Normals are flipped the same way as positions.
                 Vector3 vector = currentNormal:GetVector()
-                vector:SetZ(cast(number, terminal:value))
+                vector:SetZ(-1 * cast(number, terminal:value))
             end
             normalIndex = normalIndex + 1
         elseif isVertexTexture
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/Models/Vulkan/EnvironmentVulkan.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/Models/Vulkan/EnvironmentVulkan.quorum
index 7808bb572..3ba1bdfdf 100644
--- a/Quorum/Library/Standard/Libraries/Game/Graphics/Models/Vulkan/EnvironmentVulkan.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/Models/Vulkan/EnvironmentVulkan.quorum
@@ -38,6 +38,7 @@ use Libraries.Game.Graphics.Vulkan.VulkanImageViewInfo
 use Libraries.Game.Graphics.Vulkan.VulkanRenderPass
 use Libraries.Game.Graphics.Vulkan.VulkanSampler
 use Libraries.Game.Graphics.Vulkan.VulkanSamplerInfo
+use Libraries.Game.Graphics.CameraMatrix4
 
 class EnvironmentVulkan is Environment
     
@@ -715,7 +716,7 @@ cascadeSplits:Add((d - nearClip) / clipRange)
                     up:Set(0, 0, 1)
                 end
                 
-                Matrix4 lightViewMatrix
+                CameraMatrix4 lightViewMatrix
                 lightViewMatrix:SetToLookAt(shadowCameraPosition, frustumCenter, up)
                 Matrix4 lightOrthoMatrix
                 ProjectionToVulkanOrthographic(lightOrthoMatrix, minExtents:GetX(), maxExtents:GetX(), minExtents:GetY(), maxExtents:GetY(), 0.0, maxExtents:GetZ() - minExtents:GetZ())
@@ -788,9 +789,9 @@ number d = 0.95 * (log - uniform) + uniform
             end
                 
                 //output "Last split distance = " + lastSplitDistance + ", maxDistance = " + maxDistance + ", distanceRange = " + distanceRange + ", minDistance = " + minDistance
-                Matrix4 shadowProjection
+                CameraMatrix4 shadowProjection
                 //shadowProjection:SetToProjection(lastSplitDistance * maxDistance, splitDistance * maxDistance, 90, 1)
-                shadowProjection:SetToProjection(minDistance * maxDistance, splitDistance * maxDistance, 90, 1)
+                shadowProjection:PerspectiveProjection(minDistance * maxDistance, splitDistance * maxDistance, 90, 1)
                 //SetToVulkanProjection(shadowProjection, lastSplitDistance * maxDistance, splitDistance * maxDistance, 90, 1)
                 
                 /*We need to set all six faces of our cubemap for point lights. To do this, we'll create a matrix that points to
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/OpenGL/OpenGLPainter2D.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/OpenGL/OpenGLPainter2D.quorum
index d8743ba59..d6491eab2 100644
--- a/Quorum/Library/Standard/Libraries/Game/Graphics/OpenGL/OpenGLPainter2D.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/OpenGL/OpenGLPainter2D.quorum
@@ -133,7 +133,7 @@ class OpenGLPainter2D is Painter2D
     Camera camera = undefined
 
     // Projection matrix, taken from the Camera. Allows us to translate world coordinates to screen coordinates.
-    Matrix4 projectionMatrix
+    CameraMatrix4 projectionMatrix
 
     // If this boolean is true, we can safely batch together Drawables to be rendered together for performance.
     // Otherwise, each Drawable has to be rendered separately, because a custom shader program/mapping might need different values on a per-Drawable basis.
@@ -381,7 +381,7 @@ class OpenGLPainter2D is Painter2D
             alert("I couldn't create the Painter2D because the display hasn't been initialized!")
         end
 
-        projectionMatrix:SetToOrthographic2D(0, 0, display:GetWidth(), display:GetHeight())
+        projectionMatrix:OrthographicProjection(0, display:GetWidth(), 0, display:GetHeight(), 0, 1)
 
         defaultProgram = GetDefaultShaders()
     end
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/OrthographicCamera.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/OrthographicCamera.quorum
index 061c0ec2e..129652c14 100644
--- a/Quorum/Library/Standard/Libraries/Game/Graphics/OrthographicCamera.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/OrthographicCamera.quorum
@@ -5,14 +5,10 @@ use Libraries.Compute.Vector3
 use Libraries.Game.GameStateManager
 use Libraries.Compute.Matrix4
 use Libraries.Containers.Array
-use Libraries.Game.Graphics.Vulkan.VulkanGraphics
 
 class OrthographicCamera is Camera
     
     number zoom = 1
-    
-    boolean isVulkan = false
-    boolean isVulkanCached = false
 
     on create
         SetFar(20000)
@@ -32,35 +28,16 @@ class OrthographicCamera is Camera
         Update()
     end
     
-    private action CheckIfVulkan
-        GameStateManager manager
-        GraphicsManager graphics = manager:GetGameGraphics()
-        if graphics not= undefined
-            isVulkan = (graphics is VulkanGraphics)
-            isVulkanCached = true
-        else
-            isVulkan = false
-            isVulkanCached = false
-        end
-    end
-
     /*
     This action recalculates the camera's position and data. This should be used
     after the camera has been manipulated in any way.
     */
     action Update
-        if not isVulkanCached
-            CheckIfVulkan()
-        end
-        
-        if isVulkan
-            ProjectionToVulkanOrthographic(parent:Camera:projection, -parent:Camera:viewportWidth/(2 * zoom), parent:Camera:viewportWidth/(2 * zoom),
-            -parent:Camera:viewportHeight/(2 * zoom), parent:Camera:viewportHeight/(2 * zoom), parent:Camera:near, parent:Camera:far)
-        else
-            parent:Camera:projection:SetToOrthographic(-parent:Camera:viewportWidth/(2 * zoom), parent:Camera:viewportWidth/(2 * zoom),
-            -parent:Camera:viewportHeight/(2 * zoom), parent:Camera:viewportHeight/(2 * zoom), parent:Camera:near, parent:Camera:far)
-        end
-            
+        number halfWidth = parent:Camera:viewportWidth / (2 * zoom)
+        number halfHeight = parent:Camera:viewportHeight / (2 * zoom)
+        parent:Camera:projection:OrthographicProjection(-halfWidth, halfWidth, -halfHeight, halfHeight,
+            parent:Camera:near, parent:Camera:far)
+
         parent:Camera:view:SetToLookAt(parent:Camera:position, calcVector:Set(parent:Camera:position):Add(parent:Camera:direction), parent:Camera:up)
         
         parent:Camera:combined:Set(parent:Camera:projection)
@@ -70,39 +47,6 @@ class OrthographicCamera is Camera
         parent:Camera:inverseProjectionView:Inverse()
         parent:Camera:frustum:Update(parent:Camera:inverseProjectionView)
     end
-    
-    private action ProjectionToVulkanOrthographic(Matrix4 matrix, number left, number right, number bottom, number top, number near, number far)
-        matrix:IdentityMatrix()
-        number x_orth = 2 / (right - left)
-        number y_orth = 2 / (top - bottom)
-        //number z_orth = -2 / (far - near)
-        number z_orth = -1 / (far - near)
-
-        number tx = -1 * (right + left) / (right - left)
-        number ty = -1 * (top + bottom) / (top - bottom)
-        //number tz = -1 * (far + near) / (far - near)
-        number tz = -1 * (near) / (far - near)
-
-        matrix:row0column0 = x_orth
-        matrix:row1column0 = 0
-        matrix:row2column0 = 0
-        matrix:row3column0 = 0
-
-        matrix:row0column1 = 0
-        matrix:row1column1 = y_orth
-        matrix:row2column1 = 0
-        matrix:row3column1 = 0
-
-        matrix:row0column2 = 0
-        matrix:row1column2 = 0
-        matrix:row2column2 = z_orth
-        matrix:row3column2 = 0
-
-        matrix:row0column3 = tx
-        matrix:row1column3 = ty
-        matrix:row2column3 = tz
-        matrix:row3column3 = 1
-    end
 
     /*
     This action will set the camera to an orthographic projection using a
@@ -118,9 +62,10 @@ class OrthographicCamera is Camera
     viewport of the given width and height.
     */
     action SetToOrthographic(number viewportWidth, number viewportHeight)
-        // libGDX code originally has a boolean for yDown. We assume it was false.
+        // The world is left-handed, so the camera looks into the screen,
+        // along +z.
         parent:Camera:up:Set(0, 1, 0)
-        parent:Camera:direction:Set(0, 0, -1)
+        parent:Camera:direction:Set(0, 0, 1)
         
         parent:Camera:position:Set(viewportWidth/(2.0 * zoom), viewportHeight/(2.0 * zoom), 0)
         parent:Camera:viewportWidth = viewportWidth
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/PerspectiveCamera.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/PerspectiveCamera.quorum
index 100804803..cbf42c9c2 100644
--- a/Quorum/Library/Standard/Libraries/Game/Graphics/PerspectiveCamera.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/PerspectiveCamera.quorum
@@ -59,16 +59,17 @@ class PerspectiveCamera is Camera
         end
         
         number aspect = GetWidth() / GetHeight()
-        GetProjectionMatrix():SetToProjection(math:AbsoluteValue(GetNear()), math:AbsoluteValue(GetFar()), fieldOfView / zoom, aspect)
+        GetProjectionMatrix():PerspectiveProjection(math:AbsoluteValue(GetNear()), math:AbsoluteValue(GetFar()), fieldOfView / zoom, aspect)
         
         /*Due to differences in coordinate systems, we need to set the view differently between OpenGL and Vulkan.
 OpenGL uses the original Matrix4 calculations, while Vulkan uses a different implementation of SetToLookAt
 that inverts the order of cross products to flip the handedness.*/
-        if isVulkan
-            SetToLookAt(GetViewMatrix(), GetPosition(), calcVector:Set(GetPosition()):Add(GetDirection()), GetUp())
-        else
-            GetViewMatrix():SetToLookAt(GetPosition(), calcVector:Set(GetPosition()):Add(GetDirection()), GetUp())
-        end
+        //if isVulkan
+            //SetToLookAt(GetViewMatrix(), GetPosition(), calcVector:Set(GetPosition()):Add(GetDirection()), GetUp())
+        //else
+            //GetViewMatrix():SetToLookAt(GetPosition(), calcVector:Set(GetPosition()):Add(GetDirection()), GetUp())
+        //end
+        GetViewMatrix():SetToLookAt(GetPosition(), calcVector:Set(GetPosition()):Add(GetDirection()), GetUp())
         
         GetCombinedMatrix():Set(GetProjectionMatrix())
         GetCombinedMatrix():Multiply(GetViewMatrix())
@@ -174,12 +175,12 @@ that inverts the order of cross products to flip the handedness.*/
         matrix:row1column0 = vY:GetX()
         matrix:row1column1 = vY:GetY()
         matrix:row1column2 = vY:GetZ()
-        matrix:row2column0 = -1 * vZ:GetX()
-        matrix:row2column1 = -1 * vZ:GetY()
-        matrix:row2column2 = -1 * vZ:GetZ()
-        //matrix:row2column0 = vZ:GetX()
-        //matrix:row2column1 = vZ:GetY()
-        //matrix:row2column2 = vZ:GetZ()
+        //matrix:row2column0 = -1 * vZ:GetX()
+        //matrix:row2column1 = -1 * vZ:GetY()
+        //matrix:row2column2 = -1 * vZ:GetZ()
+        matrix:row2column0 = vZ:GetX()
+        matrix:row2column1 = vZ:GetY()
+        matrix:row2column2 = vZ:GetZ()
 
         return matrix
     end
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/Shaders/OpenGL/Mapping/DefaultShaderMapping3DOpenGL.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/Shaders/OpenGL/Mapping/DefaultShaderMapping3DOpenGL.quorum
index 8a837ea81..b20fbb408 100644
--- a/Quorum/Library/Standard/Libraries/Game/Graphics/Shaders/OpenGL/Mapping/DefaultShaderMapping3DOpenGL.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/Shaders/OpenGL/Mapping/DefaultShaderMapping3DOpenGL.quorum
@@ -208,7 +208,6 @@ class DefaultShaderMapping3DOpenGL is ShaderMapping
 
         // Set the projection-view transform
         tempMatrix4:Set(camera:GetCombinedMatrix())
-        InvertViewZ(tempMatrix4)
         program:SetShaderInputMatrix(projectionViewTransformID, tempMatrix4)
 
         // Set the camera position
@@ -288,10 +287,8 @@ class DefaultShaderMapping3DOpenGL is ShaderMapping
 
         // Setting uniform values for the shaders.
 
-        // Set the world transform. The z value is inverted as a lazy hack to invert from a right-handed system to a left-handed one. 
-        // This may change in the future.
+        // Set the world transform.
         tempMatrix4:Set(renderable:worldTransform)
-        InvertPositionZ(tempMatrix4)
         program:SetShaderInputMatrix(worldTransformID, tempMatrix4)
     end
 
@@ -367,7 +364,7 @@ if graphics is OpenGLManager
                 OpenGLManager openGL = cast(OpenGLManager, graphics)
 openGL:SetCullFace(cullFace)
                 
-if cullFace = 0
+if cullFace = 0 or true
                 openGL:DisableProperty(constants:GL_CULL_FACE)
             else
                 openGL:EnableProperty(constants:GL_CULL_FACE)
@@ -549,7 +546,6 @@ openGL:SetDepthMask(mask)
         end
 
         tempVector3 = renderable:worldTransform:GetTranslation()
-        tempVector3:Scale(1, 1, -1)
         if attributes:HasAttribute(colorAttribute:GetAmbientLightValue())
             ColorAttribute ambientAttribute = cast(ColorAttribute, attributes:GetAttribute(colorAttribute:GetAmbientLightValue()))
             ambientCubemap:SetColor(ambientAttribute:color)
@@ -578,7 +574,7 @@ openGL:SetDepthMask(mask)
                 
                 if counter < max
                     glProgram:SetShaderInput(directionalLightColorID:Get(counter), color:GetRed(), color:GetGreen(), color:GetBlue())
-                    glProgram:SetShaderInput(directionalLightDirectionID:Get(counter), tempVector3:GetX(), tempVector3:GetY(), -tempVector3:GetZ())
+                    glProgram:SetShaderInput(directionalLightDirectionID:Get(counter), tempVector3:GetX(), tempVector3:GetY(), tempVector3:GetZ())
                 else
                     ambientCubemap:Add(color, tempVector3)
                 end
@@ -612,7 +608,7 @@ openGL:SetDepthMask(mask)
 
                 if counter < max
                     glProgram:SetShaderInput(pointLightColorID:Get(counter), color:GetRed() * intensity, color:GetGreen() * intensity, color:GetBlue() * intensity)
-                    glProgram:SetShaderInput(pointLightPositionID:Get(counter), position:GetX(), position:GetY(), -position:GetZ())
+                    glProgram:SetShaderInput(pointLightPositionID:Get(counter), position:GetX(), position:GetY(), position:GetZ())
                 else
                     ambientCubemap:Add(color, position, tempVector3, intensity)
                 end
@@ -694,18 +690,4 @@ OpenGLShaderProgram glProgram = cast(OpenGLShaderProgram, program:GetShaderProgr
             glProgram:SetShaderInput(enableAlphaTestID, enable)
         end
     end
-
-    private action InvertPositionZ(Matrix4 matrix)
-        matrix:row2column3 = -matrix:row2column3
-    end
-    
-    private action InvertViewZ(Matrix4 matrix)
-        matrix:row0column0 = -matrix:row0column0
-        matrix:row0column1 = -matrix:row0column1
-        matrix:row0column3 = -matrix:row0column3
-
-        matrix:row1column2 = -matrix:row1column2
-        matrix:row2column2 = -matrix:row2column2
-        matrix:row3column2 = -matrix:row3column2
-    end
-end
\ No newline at end of file
+end
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/Vulkan/VulkanGraphics.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/Vulkan/VulkanGraphics.quorum
index 8e40da08e..62c026588 100644
--- a/Quorum/Library/Standard/Libraries/Game/Graphics/Vulkan/VulkanGraphics.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/Vulkan/VulkanGraphics.quorum
@@ -12,6 +12,7 @@ use Libraries.Containers.Array
 use Libraries.Game.GameDisplay
 use Libraries.Game.Graphics.Models.Vulkan.ModelManagerVulkan
 use Libraries.Game.Graphics.Models.Vulkan.MaterialManagerVulkan
+use Libraries.Game.Graphics.DeviceCoordinates
 
 class VulkanGraphics is GraphicsManager
     
@@ -393,6 +394,10 @@ VulkanImageInfo imageInfo
         textureManager:Create(device, me)
         modelManager:Create(device, me)
         lightingProperties:Create(device, gameState:GetGame():GetDesktopConfiguration())
+        
+        DeviceCoordinates ndc = GetDeviceCoordinates()
+        ndc:SetDefaultCoordinateSpace(ndc:LEFT_HANDED)
+        ndc:SetDefaultDepthRange(ndc:DEPTH_ZERO_TO_ONE)
 
         return true
     end
diff --git a/Quorum/Library/Standard/Libraries/Game/Graphics/Vulkan/VulkanPainter3D.quorum b/Quorum/Library/Standard/Libraries/Game/Graphics/Vulkan/VulkanPainter3D.quorum
index 48b479efd..6de3be327 100644
--- a/Quorum/Library/Standard/Libraries/Game/Graphics/Vulkan/VulkanPainter3D.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Graphics/Vulkan/VulkanPainter3D.quorum
@@ -1169,6 +1169,17 @@ Number32BitArray projectionViewMatrix = MatrixToArray(camera:GetCombinedMatrix()
         
         VulkanPipelineLayout pipelineLayout = currentPipeline:GetInfo():GetLayout()
                 
+        //output "Binding camera. View: 
+//" + camera:GetViewMatrix():ToText() + "
+//
+//Projection: 
+//" + camera:GetProjectionMatrix():ToText() + "
+//
+//Combined: 
+//" + camera:GetCombinedMatrix():ToText() + "
+//
+//---"
+        
 BindDescriptorSetCommand cameraBind
             cameraBind:SetPipelineLayout(pipelineLayout)
             cameraBind:SetDescriptorSet(currentCameraDescriptor)
@@ -1620,6 +1631,8 @@ BindDescriptorSetCommand resultDescriptorBind
         SetViewportCommand setViewport
             setViewport:SetPosition(viewportX, swapchain:GetImageHeight() - viewportY)
             setViewport:SetSize(viewportWidth, -viewportHeight)
+        //setViewport:SetPosition(viewportX, viewportY)
+            //setViewport:SetSize(viewportWidth, viewportHeight)
             commandBuffer:Record(setViewport)
         
         SetScissorCommand setScissor
@@ -1632,6 +1645,8 @@ BindDescriptorSetCommand resultDescriptorBind
         SetViewportCommand setViewport
             setViewport:SetPosition(0, swapchain:GetImageHeight())
             setViewport:SetSize(swapchain:GetImageWidth(), -swapchain:GetImageHeight())
+        //setViewport:SetPosition(0, 0)
+            //setViewport:SetSize(swapchain:GetImageWidth(), swapchain:GetImageHeight())
             commandBuffer:Record(setViewport)
         
         SetScissorCommand setScissor
diff --git a/Quorum/Library/Standard/Libraries/Game/Physics/Vehicles/Vehicle.quorum b/Quorum/Library/Standard/Libraries/Game/Physics/Vehicles/Vehicle.quorum
index f1c32cb81..6f690351c 100644
--- a/Quorum/Library/Standard/Libraries/Game/Physics/Vehicles/Vehicle.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Physics/Vehicles/Vehicle.quorum
@@ -639,17 +639,16 @@ chassis from the layer also removes the vehicle.*/
     end
 
     /*
-    Converts a physics rotation to Item3D's rotation convention and applies it
-    on top of a visual's rest rotation. Item3D stores rotations with the
-    signs of m02, m12, m20, and m21 flipped compared with the physics basis,
-    the same conversion Item3D uses when it copies a physics rotation.
+    Applies a physics rotation on top of a visual's rest rotation. Physics and
+    drawing share one coordinate system, so the physics rotation is used as
+    it is.
     Attribute: Parameter basis The rotation in physics space
     Attribute: Parameter rest The item's rotation when it was given to the wheel
     Attribute: Parameter result The matrix that receives the item's rotation
 */
     private action ToVisualRotation(Matrix3 basis, Matrix4 rest, Matrix4 result)
         Matrix3 converted
-        converted:Set(basis:row0column0, basis:row0column1, -basis:row0column2, basis:row1column0, basis:row1column1, -basis:row1column2, -basis:row2column0, -basis:row2column1, basis:row2column2)
+        converted:Set(basis)
         Matrix3 restBasis
         restBasis:Set(rest:row0column0, rest:row0column1, rest:row0column2, rest:row1column0, rest:row1column1, rest:row1column2, rest:row2column0, rest:row2column1, rest:row2column2)
         Matrix3 product
diff --git a/Quorum/Library/Standard/Libraries/Game/Scenes/DefaultSceneManager.quorum b/Quorum/Library/Standard/Libraries/Game/Scenes/DefaultSceneManager.quorum
index 9816f9232..8656aba65 100644
--- a/Quorum/Library/Standard/Libraries/Game/Scenes/DefaultSceneManager.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Scenes/DefaultSceneManager.quorum
@@ -35,10 +35,21 @@ class DefaultSceneManager is SceneManager
     GameStateManager gameState
     HashTable<text, Texture> loadedTextures
 
+    // True while loading a scene saved before version 2, which needs its
+    // rotations and 2D cameras converted to the left-handed world.
+    boolean convertFromRightHanded = false
+
     action Load(Scene scene)
         Game game = gameState:GetGame()
         SceneProperties properties
 
+        number version = 1.0
+        JavaScriptObjectNotation data = scene:GetData()
+        if data:HasValue(properties:VERSION)
+            version = data:GetNumber(properties:VERSION)
+        end
+        convertFromRightHanded = version < 2.0
+
         // Modify any application-level properties.
         JavaScriptObjectNotation application = scene:GetApplicationProperties()
         if application not= undefined
@@ -196,13 +207,13 @@ class DefaultSceneManager is SceneManager
                 // Don't check the keys if it was handled by custom loading.
             elseif key = properties:POSITION
                 Number32BitArray position = ConvertToNumber32BitArray(json:GetObject(key))
-                camera:SetPosition(position:Get(0), position:Get(1), position:Get(2))
+                camera:SetPosition(position:Get(0), position:Get(1), CameraZ(camera, position:Get(2)))
             elseif key = properties:DIRECTION
                 Number32BitArray direction = ConvertToNumber32BitArray(json:GetObject(key))
-                camera:SetDirection(direction:Get(0), direction:Get(1), direction:Get(2))
+                camera:SetDirection(direction:Get(0), direction:Get(1), CameraZ(camera, direction:Get(2)))
             elseif key = properties:UP
                 Number32BitArray up = ConvertToNumber32BitArray(json:GetObject(key))
-                camera:SetUp(up:Get(0), up:Get(1), up:Get(2))
+                camera:SetUp(up:Get(0), up:Get(1), CameraZ(camera, up:Get(2)))
             elseif key = properties:SIZE
                 Number32BitArray size = ConvertToNumber32BitArray(json:GetObject(key))
                 camera:SetWidth(size:Get(0))
@@ -223,6 +234,20 @@ class DefaultSceneManager is SceneManager
         end
     end
 
+    /*
+    This action returns a z value for a camera being loaded. A 2D camera from a
+    scene saved before version 2 looks along -z, which the left-handed world
+    mirrors, so it is mirrored through the z = 0 plane, where 2D items are
+    drawn. The picture is the same from either side, so it only stops being
+    mirrored. 3D cameras are loaded as saved.
+    */
+    private action CameraZ(Camera camera, number z) returns number
+        if convertFromRightHanded and camera is OrthographicCamera
+            return -z
+        end
+        return z
+    end
+
     /*
     This action can be used to override a portion of the default camera loading.
     */
@@ -710,6 +735,17 @@ number restitution = 0
         end
 
         if transform not= undefined
+            if convertFromRightHanded
+                // Scenes saved before version 2 were placed while OpenGL drew
+                // the world mirrored in z. Mirroring the rotation once, by
+                // flipping the signs of m02, m12, m20, and m21, makes the item
+                // face the way it did when it was placed.
+                transform:Set(2, -transform:Get(2))
+                transform:Set(6, -transform:Get(6))
+                transform:Set(8, -transform:Get(8))
+                transform:Set(9, -transform:Get(9))
+            end
+
             Matrix4 matrix = item:GetRotationTransform()
             matrix:row0column0 = transform:Get(0)
             matrix:row0column1 = transform:Get(1)
@@ -829,6 +865,7 @@ number restitution = 0
     action Save(Array<Layer> layers) returns Scene
         SceneProperties properties
         JavaScriptObjectNotation json
+        json:Add(properties:VERSION, properties:LASTEST_VERSION)
         json:Add(properties:LAYERS, SaveLayers(layers))
         Scene scene
         scene:SetData(json)
diff --git a/Quorum/Library/Standard/Libraries/Game/Scenes/SceneProperties.quorum b/Quorum/Library/Standard/Libraries/Game/Scenes/SceneProperties.quorum
index 3125a2734..a6e34865b 100644
--- a/Quorum/Library/Standard/Libraries/Game/Scenes/SceneProperties.quorum
+++ b/Quorum/Library/Standard/Libraries/Game/Scenes/SceneProperties.quorum
@@ -7,7 +7,10 @@ text values which are used by the Scene system.
 shared class SceneProperties
 
     public constant text VERSION = "Version"
-    public constant number LASTEST_VERSION = 1.0
+    // Version 2 scenes are saved in the left-handed world. Scenes without a
+    // version were saved while OpenGL drew the world mirrored in z, and are
+    // converted when they are loaded.
+    public constant number LASTEST_VERSION = 2.0
 
     /*
     The following generic properties are used by a variety of elements of a scene.
diff --git a/Quorum/Library/Standard/Libraries/Interface/Item3D.quorum b/Quorum/Library/Standard/Libraries/Interface/Item3D.quorum
index 9c3806894..1b406aab1 100644
--- a/Quorum/Library/Standard/Libraries/Interface/Item3D.quorum
+++ b/Quorum/Library/Standard/Libraries/Interface/Item3D.quorum
@@ -1612,14 +1612,14 @@ class Item3D is Item
                 Matrix3 tempMatrix
                 tempMatrix:row0column0 = rotationMatrix:row0column0 / scale:GetX()
                 tempMatrix:row0column1 = rotationMatrix:row0column1 / scale:GetX()
-                tempMatrix:row0column2 = -rotationMatrix:row0column2 / scale:GetX()
+                tempMatrix:row0column2 = rotationMatrix:row0column2 / scale:GetX()
 
                 tempMatrix:row1column0 = rotationMatrix:row1column0 / scale:GetY()
                 tempMatrix:row1column1 = rotationMatrix:row1column1 / scale:GetY()
-                tempMatrix:row1column2 = -rotationMatrix:row1column2 / scale:GetY()
+                tempMatrix:row1column2 = rotationMatrix:row1column2 / scale:GetY()
 
-                tempMatrix:row2column0 = -rotationMatrix:row2column0 / scale:GetZ()
-                tempMatrix:row2column1 = -rotationMatrix:row2column1 / scale:GetZ()
+                tempMatrix:row2column0 = rotationMatrix:row2column0 / scale:GetZ()
+                tempMatrix:row2column1 = rotationMatrix:row2column1 / scale:GetZ()
                 tempMatrix:row2column2 = rotationMatrix:row2column2 / scale:GetZ()
                 collisionTransform:GetBasis():Set(tempMatrix)
             end
@@ -2043,14 +2043,14 @@ class Item3D is Item
                 Matrix3 tempMatrix
                 tempMatrix:row0column0 = rotationMatrix:row0column0 / scale:GetX()
                 tempMatrix:row0column1 = rotationMatrix:row0column1 / scale:GetX()
-                tempMatrix:row0column2 = -rotationMatrix:row0column2 / scale:GetX()
+                tempMatrix:row0column2 = rotationMatrix:row0column2 / scale:GetX()
 
                 tempMatrix:row1column0 = rotationMatrix:row1column0 / scale:GetY()
                 tempMatrix:row1column1 = rotationMatrix:row1column1 / scale:GetY()
-                tempMatrix:row1column2 = -rotationMatrix:row1column2 / scale:GetY()
+                tempMatrix:row1column2 = rotationMatrix:row1column2 / scale:GetY()
 
-                tempMatrix:row2column0 = -rotationMatrix:row2column0 / scale:GetZ()
-                tempMatrix:row2column1 = -rotationMatrix:row2column1 / scale:GetZ()
+                tempMatrix:row2column0 = rotationMatrix:row2column0 / scale:GetZ()
+                tempMatrix:row2column1 = rotationMatrix:row2column1 / scale:GetZ()
                 tempMatrix:row2column2 = rotationMatrix:row2column2 / scale:GetZ()
                 collisionTransform:GetBasis():Set(tempMatrix)
             end
@@ -3386,37 +3386,20 @@ class Item3D is Item
         Matrix3 tempMatrix
         tempMatrix:Set(collisionTransform:GetBasis())
 
-        // Conversion between left-handed coordinate system and right-handed
-        // coordinate system rotation matrices is achieved via the following:
-        //    If the matrix M = [mij], 0 <= i <= 2, 0 <= j <= 2, is a rotation
-        //    in a left- (right-) handed coordinate system, then to convert it
-        //    to a right- (left-) handed coordinate system, change the signs of
-        //    m02, m12, m20, m21.
-        // Source: http://answers.unity3d.com/storage/temp/12048-lefthandedtorighthanded.pdf
+        // Physics and drawing share one coordinate system, since the position
+        // is copied unchanged below, so the rotation is copied unchanged too.
         Matrix4 matrix = rotationMatrix
         matrix:IdentityMatrix()
-//        matrix:row0column0 = tempMatrix:row0column0// * vector:GetX()
-//        matrix:row0column1 = tempMatrix:row0column1// * vector:GetX()
-//        matrix:row0column2 = -tempMatrix:row0column2// * vector:GetX()
-//
-//        matrix:row1column0 = tempMatrix:row1column0// * vector:GetY()
-//        matrix:row1column1 = tempMatrix:row1column1// * vector:GetY()
-//        matrix:row1column2 = -tempMatrix:row1column2// * vector:GetY()
-//
-//        matrix:row2column0 = -tempMatrix:row2column0// * vector:GetZ()
-//        matrix:row2column1 = -tempMatrix:row2column1// * vector:GetZ()
-//        matrix:row2column2 = tempMatrix:row2column2// * vector:GetZ()
-
         matrix:row0column0 = tempMatrix:row0column0
         matrix:row0column1 = tempMatrix:row0column1
-        matrix:row0column2 = -tempMatrix:row0column2
+        matrix:row0column2 = tempMatrix:row0column2
 
         matrix:row1column0 = tempMatrix:row1column0
         matrix:row1column1 = tempMatrix:row1column1
-        matrix:row1column2 = -tempMatrix:row1column2
+        matrix:row1column2 = tempMatrix:row1column2
 
-        matrix:row2column0 = -tempMatrix:row2column0
-        matrix:row2column1 = -tempMatrix:row2column1
+        matrix:row2column0 = tempMatrix:row2column0
+        matrix:row2column1 = tempMatrix:row2column1
         matrix:row2column2 = tempMatrix:row2column2
 
 //        matrix:row0column3 = collisionTransform:GetOrigin():GetX()
diff --git a/Quorum/Library/Tests/Math/Pass/Matrix4SetToOrthographic.quorum b/Quorum/Library/Tests/Math/Pass/Matrix4SetToOrthographic.quorum
index 65ff768f4..c4ef94cf1 100644
--- a/Quorum/Library/Tests/Math/Pass/Matrix4SetToOrthographic.quorum
+++ b/Quorum/Library/Tests/Math/Pass/Matrix4SetToOrthographic.quorum
@@ -1,10 +1,12 @@
-use Libraries.Compute.Matrix4
+use Libraries.Game.Graphics.CameraMatrix4
+use Libraries.Game.Graphics.DeviceCoordinates
 
 class Matrix4SetToOrthographic 
     action Main
-        Matrix4 matrix
+        CameraMatrix4 matrix
+        DeviceCoordinates ndc
 
-        matrix:SetToOrthographic2D(0, 0, 100, 100)
+        matrix:OrthographicProjection(0, 100, 0, 100, 0, 1, ndc:RIGHT_HANDED, ndc:DEPTH_NEGATIVE_ONE_TO_ONE)
 
         number row0column0 = matrix:row0column0
         number row0column1 = matrix:row0column1
@@ -29,7 +31,7 @@ class Matrix4SetToOrthographic
         output "|" + row2column0 + ", " + row2column1 + ", " + row2column2 + ", " + row2column3 + "|"
         output "|" + row3column0 + ", " + row3column1 + ", " + row3column2 + ", " + row3column3 + "|"
 
-        matrix:SetToOrthographic2D(0, 0, 100, 100, 0, 1)
+        matrix:OrthographicProjection(0, 100, 0, 100, 0, 1, ndc:RIGHT_HANDED, ndc:DEPTH_NEGATIVE_ONE_TO_ONE)
 
         row0column0 = matrix:row0column0
         row0column1 = matrix:row0column1
@@ -54,7 +56,7 @@ class Matrix4SetToOrthographic
         output "|" + row2column0 + ", " + row2column1 + ", " + row2column2 + ", " + row2column3 + "|"
         output "|" + row3column0 + ", " + row3column1 + ", " + row3column2 + ", " + row3column3 + "|"
 
-        matrix:SetToOrthographic(0, 1, 0, 1, 0, 1)
+        matrix:OrthographicProjection(0, 1, 0, 1, 0, 1, ndc:RIGHT_HANDED, ndc:DEPTH_NEGATIVE_ONE_TO_ONE)
 
         row0column0 = matrix:row0column0
         row0column1 = matrix:row0column1
~~~~

## What to check by hand

These are the changes most likely to break something, ordered by risk. Each
one is easy to get wrong without an error message, so it needs to be looked
at on screen or checked with a test.

### 1. Leftover debugging changes from the work-in-progress commit `a9ff692`

None of these are part of the handedness fix. Decide on each before merging.

- **`DesktopOpenGL.java`: `glDeleteBuffer(bufferID)` is commented out.** OpenGL
  buffers are never freed, so a long-running game, or one that loads and
  unloads models, will leak GPU memory. Restore the call, or record why it was
  disabled.
- **`SPIRVShaderCompiler.java`: shader optimization is set to level 0.**
  Vulkan shaders are compiled without optimization. This helps debugging, but
  slows rendering. Probably revert.
- **Commented-out code.** `PerspectiveCamera` still has the old Vulkan-only
  look-at branch, `CameraMatrix4.SetToLookAt` keeps the old row-2 lines, and
  `VulkanPainter3D` has matrix-printing code and the old viewport lines. Clean
  up once the fix is confirmed.
- **The handedness setting is honored inconsistently.**
  `CameraMatrix4.PerspectiveProjection`'s left-handed and right-handed
  branches are identical, so the setting does nothing for perspective.
  `OrthographicProjection` does honor it. Either make perspective honor it, or
  remove the option.

### 2. The left-handed world, in both APIs

- **Item rotations.** `Item3D` no longer mirrors rotations between physics and
  drawing, and OpenGL no longer flips z (`InvertViewZ`, `InvertPositionZ` and
  the light z negations are gone).
  - Check AllTerrainVehicle in both APIs: steering left turns the chassis
    left, and the wheels steer and spin correctly.
  - The PhysicsTests test `DrawnRotationMatchesPhysicsTest` should pass.
- **OpenGL is no longer mirrored.** Check that a red, green and blue axis
  marker reads the same way in both APIs.
- **Lighting.** Directional and point lights should light the same sides in
  both APIs, and specular highlights should match.
- **Shadows in Vulkan.** These were not changed or tested in this work.
  - `EnvironmentVulkan`'s directional-light shadows build a left-handed view
    but use a right-handed orthographic projection
    (`ProjectionToVulkanOrthographic`), so objects may be clipped out of the
    shadow map.
  - The point-light cube-map faces use direction and up pairs chosen under
    the old look-at, so shadows may fall on the wrong side.

### 3. 2D

- **The 2D camera now looks along +z.** Check BoxDestroy and GroundFlightTactics
  in both APIs: text reads left to right, and labels are where they should
  be.
- **Mouse input.** Clicking 2D buttons should hit them. This checks the
  inverse matrix used to turn mouse positions into 2D coordinates.
- **Draw order.** Overlapping 2D items should stack in the order they were
  added.
- **Orthographic code moved out of `Matrix4`.** `SetToOrthographic` and
  `SetToOrthographic2D` were removed. Any code outside the standard library
  that calls them will no longer compile. Search the example games and IDE
  code.

### 4. Model geometry and texture coordinates

- **OpenGL shapes** (`MeshBuilder`): box, cylinder, sphere and plane textures
  were mirrored in u. Check text on every box face, around a cylinder and a
  sphere, and on cylinder caps.
- **Loaded models.**
  - OpenGL's `.obj` reader now flips z and reverses triangles.
  - Vulkan's Assimp loader now uses `aiProcess_MakeLeftHanded |
    aiProcess_FlipWindingOrder`. This needs the Java plugins rebuilt.
  - Check that Kenney models look the same in both APIs and aren't mirrored,
    and that Vulkan textures aren't upside down, which would mean v is
    flipped twice.
  - Check an animated model in Vulkan, since Assimp also mirrors skeletons
    and animations.
- **Other model formats.** `Graphics3DLoader` (`.g3dj`/`.g3db`) was not
  converted. Check any game that loads those formats.

### 5. Scenes

- **Old scene files are converted when loaded.** Files without a `Version`
  get their 3D rotations mirrored once, and their 2D camera moved to look
  along +z.
  - In GroundFlightTactics Levels 1-3, the walls should line up with their
    tiles.
  - Save a scene from the scene editor and reopen it. The file should
    contain `"Version": 2.0`, and nothing should rotate a second time. If
    the editor saves through a different path, the version is missing and
    rotations will flip on every load.
- **Item positions are not converted.** Levels look mirrored compared to how
  they were laid out before. That is expected, but confirm it doesn't break
  any game's grid or map data.

### 6. Physics and vehicles

- **`Vehicle.ToVisualRotation`** no longer mirrors wheel rotations. Wheels
  should steer and roll the right way in both APIs.
- **Culling is still off.** OpenGL's `if cullFace = 0 or true` and Vulkan's
  `CULL_MODE_NONE` are unchanged. `Bob.md` has the plan for turning culling
  on.
