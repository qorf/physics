# Item 37: the point light fix, and spotlights under Vulkan (no shadows)

**Status (2026-10-19): committed** as `0b5de0b62` on `quorum-language` branch
`MakeAWish`. Not yet reported on screen. DriveOpen also has headlights to
see it: N for night, H for the headlights. Vulkan only: see "As applied" below. This was
phases 1 and 2 of `SpotlightPlan.md`, with its recommended answers:

| Decision | Answer |
|---|---|
| 1. OpenGL | Support later (phase 4). Here OpenGL only stores spotlights, so adding one doesn't fail. |
| 2. Direction | Turns with the light's item, and its parents (a headlight follows the car) |
| 3. Shadows | One layer, no cascades (phase 3; none in this Item) |
| 4. Shadow map size | Later |
| 5. Range falloff | Yes, for point lights too |
| 6. Scenes and editor | Later |

**Branch:** `MakeAWish`, from `8a656d7c3`.

**OpenGL behaviour:** unchanged, apart from `EnvironmentOpenGL` accepting and
storing spotlights.

Paths: **G/** = `Quorum/Library/Standard/Libraries/Game/Graphics/`,
**I/** = `Quorum/Library/Standard/Libraries/Interface/`.

## What it changes

1. **Point lights are lit from the right direction.**
   - `calculatePointLight` used `normalize(tmpSub - worldPos)`, where
     `tmpSub` is already `lightPos - worldPos`.
   - Away from the world's origin, point lights shaded as if they came from
     somewhere else. DriveOpen's lamp is hundreds of units out.
2. **Point lights fade smoothly to nothing at their range,** with the usual
   window `(1 - (d/range)^4)^2`. Their range is the one `PointLight:GetRange`
   already works out.
3. **Point lights added as children of another item** are placed at their
   world position. The light record used `GetX/Y/Z`, which are relative to
   the parent.
4. **New class `SpotLight`:** a cone of light. It is placed and moved like a
   `PointLight`, and can be a child of a model. Its cone turns with the
   model.
5. **The light record grows from 8 words to 16.** It gains:
   - a light type (point 0, directional 1, spot 2; the same values as
     today's `isDirectional`);
   - the spot direction;
   - the range;
   - the cone's cosines.
6. **Lights are re-packed every frame** while the scene has any point light
   or spotlight. A light that is a child of a moving model (a lamp on a
   car) then follows it, though nothing calls `LightChanged`.
   - At most 16 records of 16 numbers.
   - Their shadow projections are not recomputed each frame (unchanged).

**No shadows from spotlights here** (phase 3).
- Shadow maps, the shadow pass and caster culling still count only
  directional and point lights.
- Spotlights come after them in the light list, so every existing index is
  unchanged.
- The shader never samples a shadow for a spotlight.

## The code

### New file `G/SpotLight.quorum`

```
package Libraries.Game.Graphics

use Libraries.Compute.Vector3
use Libraries.Game.Graphics.Light
use Libraries.Interface.Item3D

/*
A SpotLight lights a 3D scene from one point, in a cone, the way a torch, a
car's headlight or a stage light does. Inside its inner angle the light is
at full strength; between the inner and outer angles it fades; outside the
outer angle it gives no light. Like a point light, it gets dimmer the
farther it travels, and it gives no light past its range.

A spotlight is an Item3D, so it can be placed with SetPosition, and added
to another item, such as a car, so that it moves and turns with it. Its
direction is given in its own space: when the item it belongs to turns,
the cone turns with it.

Under Vulkan, spotlights don't cast shadows yet. Under OpenGL they are not
drawn yet.

Attribute: Example

use Libraries.Game.Game
use Libraries.Game.Graphics.SpotLight
use Libraries.Game.Graphics.Model
use Libraries.Game.Graphics.Color

class Main is Game
    action Main
        StartGame()
    end

    action CreateGame
        Color color

        Model floor
        floor:LoadBox(20, 0.2, 20, color:White())
        Add(floor)

        // A lamp above the floor, shining straight down.
        SpotLight lamp
        lamp:SetPosition(0, 6, 0)
        lamp:SetDirection(0, -1, 0)
        lamp:SetConeAngles(20, 30)
        lamp:SetIntensity(40)
        lamp:SetRange(15)
        Add(lamp)
    end
end
*/
class SpotLight is Light, Item3D

    /*
    How bright the light is.
    */
    number intensity = 0

    /*
    How far the light reaches, as set with SetRange, or 0 to work it out
    from the intensity and color, as a PointLight does. See GetRange.
    */
    number range = 0

    /*
    The cone's half-angles, in degrees: full strength inside the inner
    angle, fading to nothing at the outer one.
    */
    number innerAngle = 20
    number outerAngle = 30

    /*
    The direction the cone points, in the light's own space, of length 1.
    */
    Vector3 direction

    /*
    The light level below which the light is treated as having no effect,
    as for a PointLight. It decides GetRange when no range is set.
    */
    constant number MINIMUM_ILLUMINATION_THRESHOLD = 0.0003

    on create
        direction:Set(0, -1, 0)
    end

    /*
    This action sets how bright the light is.

    Attribute: Parameter newIntensity The light's intensity.
    */
    action SetIntensity(number newIntensity)
        intensity = newIntensity
        NotifyChanged()
    end

    /*
    This action returns how bright the light is.

    Attribute: Returns The light's intensity.
    */
    action GetIntensity returns number
        return intensity
    end

    /*
    This action sets how far the light reaches. It fades smoothly to nothing
    at this distance. A range of 0 works the range out from the intensity
    and color instead (see GetRange).

    Attribute: Parameter newRange How far the light reaches, in world units, or 0.
    */
    action SetRange(number newRange)
        if newRange < 0
            range = 0
        else
            range = newRange
        end
        NotifyChanged()
    end

    /*
    This action returns how far the light reaches: the range set with
    SetRange, or, if none was set, the distance at which its brightest
    color, at its intensity, falls below MINIMUM_ILLUMINATION_THRESHOLD.

    Attribute: Returns How far the light reaches, in world units.
    */
    action GetRange returns number
        if range > 0
            return range
        end
        Color lightColor = GetColor()
        number brightest = lightColor:GetRed()
        if lightColor:GetGreen() > brightest
            brightest = lightColor:GetGreen()
        end
        if lightColor:GetBlue() > brightest
            brightest = lightColor:GetBlue()
        end
        return parent:Item3D:math:SquareRoot(brightest * intensity / MINIMUM_ILLUMINATION_THRESHOLD)
    end

    /*
    This action sets the cone's half-angles, in degrees, measured from the
    direction the light points. Inside the inner angle the light is at full
    strength; it fades between the two, and gives no light past the outer
    angle. The outer angle is kept between 1 and 89 degrees, and the inner
    angle between 0 and the outer angle.

    Attribute: Parameter inner The angle of full strength, in degrees.
    Attribute: Parameter outer The angle where the light ends, in degrees.
    */
    action SetConeAngles(number inner, number outer)
        outerAngle = outer
        if outerAngle < 1
            outerAngle = 1
        elseif outerAngle > 89
            outerAngle = 89
        end
        innerAngle = inner
        if innerAngle < 0
            innerAngle = 0
        elseif innerAngle > outerAngle
            innerAngle = outerAngle
        end
        NotifyChanged()
    end

    /*
    This action returns the angle of full strength, in degrees.

    Attribute: Returns The inner half-angle.
    */
    action GetInnerAngle returns number
        return innerAngle
    end

    /*
    This action returns the angle where the light ends, in degrees.

    Attribute: Returns The outer half-angle.
    */
    action GetOuterAngle returns number
        return outerAngle
    end

    /*
    This action sets the direction the cone points, in the light's own
    space. It is made length 1. A direction of zero length is ignored.

    Attribute: Parameter x The direction along x.
    Attribute: Parameter y The direction along y.
    Attribute: Parameter z The direction along z.
    */
    action SetDirection(number x, number y, number z)
        number length = parent:Item3D:math:SquareRoot(x * x + y * y + z * z)
        if length < 0.000001
            return now
        end
        direction:Set(x / length, y / length, z / length)
        NotifyChanged()
    end

    /*
    This action sets the direction the cone points, in the light's own
    space. It is made length 1.

    Attribute: Parameter newDirection The direction.
    */
    action SetDirection(Vector3 newDirection)
        SetDirection(newDirection:GetX(), newDirection:GetY(), newDirection:GetZ())
    end

    /*
    This action returns the direction the cone points, in the light's own
    space. Change it with SetDirection, not by changing the vector.

    Attribute: Returns The direction, of length 1.
    */
    action GetDirection returns Vector3
        return direction
    end

    /*
    This action sets the color, position, direction, intensity and outer
    angle of the light at once. The inner angle becomes two thirds of the
    outer one.

    Attribute: Parameter newColor The color, or undefined to keep it.
    Attribute: Parameter newPosition The position.
    Attribute: Parameter newDirection The direction, in the light's own space.
    Attribute: Parameter newIntensity The intensity.
    Attribute: Parameter newOuterAngle The angle where the light ends, in degrees.
    */
    action SetLight(Color newColor, Vector3 newPosition, Vector3 newDirection, number newIntensity, number newOuterAngle)
        if newColor not= undefined
            SetColor(newColor)
        end
        SetPosition(newPosition)
        SetDirection(newDirection)
        SetConeAngles(newOuterAngle * 2 / 3, newOuterAngle)
        SetIntensity(newIntensity)
    end

    /*
    This action makes a copy of this light: color, position, offsets,
    direction, cone angles, intensity and range.

    Attribute: Returns The copy.
    */
    action Copy returns SpotLight
        SpotLight copy
        copy:SetColor(GetColor())
        copy:SetPosition(GetPosition())
        copy:SetOffset(GetOffsetX(), GetOffsetY(), GetOffsetZ())
        copy:SetDirection(direction)
        copy:SetConeAngles(innerAngle, outerAngle)
        copy:SetIntensity(intensity)
        copy:SetRange(range)
        return copy
    end

    /*
    This action tells the light's environment that the light has changed.
    */
    private action NotifyChanged
        if GetEnvironment() not= undefined
            GetEnvironment():LightChanged(me)
        end
    end
end
```

**Moving it** needs no overrides, unlike `PointLight`'s `MoveX` and the
rest. While any spotlight is in the scene, the environment re-packs the
lights every frame (below). So moving or turning the light, or its parent,
is picked up anyway.

**Item3D's `math` field.** `PointLight` already uses
`parent:Item3D:math:SquareRoot`, so `SpotLight` does the same.

### `G/Environment.quorum`

**Uses.** Add `use Libraries.Game.Graphics.SpotLight` (it is in the same
package, so this is only for clarity; leave it out if the compiler objects).

**New blueprints,** after `blueprint action Remove(PointLight light)`:

```
    /*
    Adds a SpotLight to this environment.
    */
    blueprint action Add(SpotLight light)

    /*
    This action will remove the given SpotLight from the Environment. If the
    light was not present in the Environment, it will have no effect.
    */
    blueprint action Remove(SpotLight light)
```

**And,** after `blueprint action GetPointLight(integer index) returns PointLight`:

```
    /*
    This action returns an iterator over the SpotLights in the environment.
    */
    blueprint action GetSpotLightIterator returns Iterator<SpotLight>

    /*
    This action returns how many SpotLights the environment has.
    */
    blueprint action GetSpotLightCount returns integer

    /*
    This action returns one of the environment's SpotLights.
    */
    blueprint action GetSpotLight(integer index) returns SpotLight
```

### `I/Item3D.quorum`

**Uses.** Add `use Libraries.Game.Graphics.SpotLight` after the `PointLight`
use.

**`GetLights`.** After the `if me is PointLight ... end` block, add:

```
        if me is SpotLight
            SpotLight spot = cast(SpotLight, me)
            array:Add(spot)
        end
```

### `G/Models/OpenGL/Attributes/EnvironmentOpenGL.quorum`

Spotlights are stored, so adding one to a layer works under OpenGL. They
aren't drawn until phase 4.

**Uses.** Add `use Libraries.Game.Graphics.SpotLight`.

**New field,** after `boolean containsLighting = false`:

```
    // Spotlights, kept but not drawn under OpenGL yet (Item 37).
    Array<SpotLight> spotLights
```

**`Add(Light)` and `Remove(Light)`.** Each gains a branch before the `else`:

```
        elseif light is SpotLight
            Add(cast(SpotLight, light))
```

and, in `Remove(Light)`:

```
        elseif light is SpotLight
            Remove(cast(SpotLight, light))
```

The two alert texts become "I can use DirectionalLight, PointLight or
SpotLight."

**New actions,** before `LightChanged`:

```
    /*
    Adds a SpotLight to this environment. OpenGL doesn't draw spotlights
    yet; they are kept so the light can be removed again.
    */
    action Add(SpotLight light)
        spotLights:Add(light)
        light:SetEnvironment(me)
    end

    /*
    This action will remove the given SpotLight from the Environment.
    */
    action Remove(SpotLight light)
        spotLights:Remove(light)
        light:SetEnvironment(undefined)
    end

    action GetSpotLightIterator returns Iterator<SpotLight>
        return spotLights:GetIterator()
    end

    action GetSpotLightCount returns integer
        return spotLights:GetSize()
    end

    action GetSpotLight(integer index) returns SpotLight
        return spotLights:Get(index)
    end
```

### `G/Models/Vulkan/EnvironmentVulkan.quorum`

**Uses.** Add `use Libraries.Game.Graphics.SpotLight`.

**Fields.** After `Array<DirectionalLight> directionalLights`:

```
    Array<SpotLight> spotLights

    // For working out a spotlight's cone (Item 37).
    Math lightMath
```

**The light record constants** (the comment and the six constants from
`LIGHTS_WORD_SIZE` to `COLOR_INDEX`) become:

```
    /*Lights store these components in the buffer, 16 words each (Item 37):
* Position (a point or spotlight) or direction (a directional light) (Vec3)
* Type (uint): 0 point, 1 directional, 2 spot
* Intensity (float)
* RGB Color (Vec3)
* Spot direction, in world space (Vec3)
* Range (float): where the light fades to nothing; 0 for directional
* Cosine of the inner and outer cone angles (2 floats)
* Two spare words*/
    constant integer LIGHTS_WORD_SIZE = 16
    constant integer LIGHTS_BYTE_SIZE = LIGHTS_WORD_SIZE * 4

    constant integer POSITION_DIRECTION_INDEX = 0
    constant integer TYPE_INDEX = 3
    constant integer INTENSITY_INDEX = 4
    constant integer COLOR_INDEX = 5
    constant integer SPOT_DIRECTION_INDEX = 8
    constant integer RANGE_INDEX = 11
    constant integer COS_INNER_INDEX = 12
    constant integer COS_OUTER_INDEX = 13

    constant integer POINT_LIGHT_TYPE = 0
    constant integer DIRECTIONAL_LIGHT_TYPE = 1
    constant integer SPOT_LIGHT_TYPE = 2
```

`lightMappingArray:SetSize(maxLights * LIGHTS_WORD_SIZE)` and the light
buffer size already use these constants, so they grow with them.

**`Update`.** At its end, after the camera check, add:

```
        // A point light or spotlight may belong to a model that moves or
        // turns without telling the environment, such as a headlight on a
        // car. Re-pack the lights every frame while there are any; their
        // shadow projections are left as they are (Item 37).
        if not pointLights:IsEmpty() or not spotLights:IsEmpty()
            integer slot = 0
            repeat while slot < lightsDirty:GetSize()
                lightsDirty:Set(slot, true)
                slot = slot + 1
            end
        end
```

**`Add(Light)` and `Remove(Light)`.** Each gains a branch:

```
        elseif light is SpotLight
            Add(cast(SpotLight, light))
```

(in `Remove`, `Remove(cast(SpotLight, light))`). The alert becomes "I can only
add PointLights, DirectionalLights or SpotLights."

**New actions,** after `Remove(PointLight light)`:

```
    /*
    Adds a SpotLight to this environment.
    */
    action Add(SpotLight light)
        spotLights:Add(light)
        light:SetEnvironment(me)
        SetDirty()
    end

    /*
    This action will remove the given SpotLight from the Environment. If
    the light was not present in the Environment before using this action,
    it will have no effect.
    */
    action Remove(SpotLight light)
        spotLights:Remove(light)
        light:SetEnvironment(undefined)
        SetDirty()
    end
```

**And,** after `GetPointLight(integer index)`:

```
    action GetSpotLightIterator returns Iterator<SpotLight>
        return spotLights:GetIterator()
    end

    action GetSpotLightCount returns integer
        return spotLights:GetSize()
    end

    action GetSpotLight(integer index) returns SpotLight
        return spotLights:Get(index)
    end
```

**`ContainsLighting`** becomes:

```
        return (not pointLights:IsEmpty()) or (not directionalLights:IsEmpty()) or (not spotLights:IsEmpty()) or ambientLight not= undefined
```

**`LightChanged`.** Its first test becomes:

```
        if light is PointLight or light is DirectionalLight or light is SpotLight
```

**`UpdateBuffers`, the `if lightsDirty:Get(resourceIndex)` block.** From
`integer index = 0` through `lightsDirty:Set(resourceIndex, false)` it
becomes:

```
            // Directional lights first, then point lights, then
            // spotlights. Shadows count lights in the same order, so
            // directional and point lights keep their places (Item 37).
            integer written = 0
            integer i = 0
            repeat while i < directionalLights:GetSize() and written < maxLights
                DirectionalLight light = directionalLights:Get(i)
                Vector3 direction = light:GetDirection()
                integer index = written * LIGHTS_WORD_SIZE
                ClearLightRecord(index)
                lightMappingArray:Set(index + POSITION_DIRECTION_INDEX, direction:GetX())
                lightMappingArray:Set(index + POSITION_DIRECTION_INDEX + 1, direction:GetY())
                lightMappingArray:Set(index + POSITION_DIRECTION_INDEX + 2, direction:GetZ())
                lightMappingArray:Set(index + TYPE_INDEX, utility:EncodeIntegerAsNumber(DIRECTIONAL_LIGHT_TYPE))
                WriteIntensityAndColor(index, light:GetIntensity(), light:GetColor())
                written = written + 1
                i = i + 1
            end

            i = 0
            repeat while i < pointLights:GetSize() and written < maxLights
                PointLight light = pointLights:Get(i)
                integer index = written * LIGHTS_WORD_SIZE
                ClearLightRecord(index)
                // The world position, so a light that belongs to another
                // item is placed correctly (Item 37).
                Matrix4 transform = light:GetTransform()
                lightMappingArray:Set(index + POSITION_DIRECTION_INDEX, transform:row0column3)
                lightMappingArray:Set(index + POSITION_DIRECTION_INDEX + 1, transform:row1column3)
                lightMappingArray:Set(index + POSITION_DIRECTION_INDEX + 2, transform:row2column3)
                lightMappingArray:Set(index + TYPE_INDEX, utility:EncodeIntegerAsNumber(POINT_LIGHT_TYPE))
                WriteIntensityAndColor(index, light:GetIntensity(), light:GetColor())
                lightMappingArray:Set(index + RANGE_INDEX, light:GetRange())
                written = written + 1
                i = i + 1
            end

            i = 0
            repeat while i < spotLights:GetSize() and written < maxLights
                SpotLight light = spotLights:Get(i)
                integer index = written * LIGHTS_WORD_SIZE
                ClearLightRecord(index)
                Matrix4 transform = light:GetTransform()
                lightMappingArray:Set(index + POSITION_DIRECTION_INDEX, transform:row0column3)
                lightMappingArray:Set(index + POSITION_DIRECTION_INDEX + 1, transform:row1column3)
                lightMappingArray:Set(index + POSITION_DIRECTION_INDEX + 2, transform:row2column3)
                lightMappingArray:Set(index + TYPE_INDEX, utility:EncodeIntegerAsNumber(SPOT_LIGHT_TYPE))
                WriteIntensityAndColor(index, light:GetIntensity(), light:GetColor())

                // The cone's direction turned by the light's world rotation,
                // then made length 1 again (the transform may be scaled).
                Vector3 localDirection = light:GetDirection()
                number x = transform:row0column0 * localDirection:GetX() + transform:row0column1 * localDirection:GetY() + transform:row0column2 * localDirection:GetZ()
                number y = transform:row1column0 * localDirection:GetX() + transform:row1column1 * localDirection:GetY() + transform:row1column2 * localDirection:GetZ()
                number z = transform:row2column0 * localDirection:GetX() + transform:row2column1 * localDirection:GetY() + transform:row2column2 * localDirection:GetZ()
                number length = lightMath:SquareRoot(x * x + y * y + z * z)
                if length > 0.000001
                    x = x / length
                    y = y / length
                    z = z / length
                end
                lightMappingArray:Set(index + SPOT_DIRECTION_INDEX, x)
                lightMappingArray:Set(index + SPOT_DIRECTION_INDEX + 1, y)
                lightMappingArray:Set(index + SPOT_DIRECTION_INDEX + 2, z)
                lightMappingArray:Set(index + RANGE_INDEX, light:GetRange())
                lightMappingArray:Set(index + COS_INNER_INDEX, lightMath:Cosine(lightMath:DegreesToRadians(light:GetInnerAngle())))
                lightMappingArray:Set(index + COS_OUTER_INDEX, lightMath:Cosine(lightMath:DegreesToRadians(light:GetOuterAngle())))
                written = written + 1
                i = i + 1
            end

            lightsMemory:Set(lightMappingArray)
            lightsDirty:Set(resourceIndex, false)
```

The variable names `light`, `index` and `transform` are declared in each
loop's own block. If the compiler objects to the same name in sibling
blocks, they become `directional`, `point` and `spot`, with
`directionalIndex` and so on.

**The light count.** In the scene data block, the line setting
`LIGHT_COUNT_INDEX` becomes:

```
            integer shaderLightCount = pointLights:GetSize() + directionalLights:GetSize() + spotLights:GetSize()
            if shaderLightCount > maxLights
                shaderLightCount = maxLights
            end
            sceneDataMappingArray:Set(LIGHT_COUNT_INDEX, utility:EncodeIntegerAsNumber(shaderLightCount))
```

**A spotlight is added later.** Adding one calls `SetDirty`, which marks the
scene data dirty, so the count is written again.

**The "no lights at all" ambient check** (white ambient when there is no
lighting) gains spotlights: `pointLights:IsEmpty() and directionalLights:IsEmpty() and spotLights:IsEmpty()`.

**New private actions,** before `UpdateBuffers`:

```
    /*
    This action sets one light record in the transfer array to zeros, so no
    value from a light that was there before is left behind.

    Attribute: Parameter index Where the record starts.
    */
    private action ClearLightRecord(integer index)
        integer word = 0
        repeat while word < LIGHTS_WORD_SIZE
            lightMappingArray:Set(index + word, 0)
            word = word + 1
        end
    end

    /*
    This action writes a light's intensity and color into its record.

    Attribute: Parameter index Where the record starts.
    Attribute: Parameter intensity The light's intensity.
    Attribute: Parameter color The light's color.
    */
    private action WriteIntensityAndColor(integer index, number intensity, Color color)
        lightMappingArray:Set(index + INTENSITY_INDEX, intensity)
        lightMappingArray:Set(index + COLOR_INDEX, color:GetRed())
        lightMappingArray:Set(index + COLOR_INDEX + 1, color:GetGreen())
        lightMappingArray:Set(index + COLOR_INDEX + 2, color:GetBlue())
    end
```

**Shadows:** unchanged. `CalculateShadowProjections` and the shadow upload
still loop over directional, then point, lights. Spotlights come after them
and get no shadow data.

### `G/Shaders/Vulkan/Fragment/DefaultLightingFragmentShaderVulkan.quorum`

**The `Light` struct** becomes:

```glsl
struct Light
{
	// A point light's or spotlight's position, or a directional light's direction
	vec3 positionDirection;
	// 0 point, 1 directional, 2 spot (Item 37)
	uint lightType;
	float intensity;
	vec3 color;
	// A spotlight's direction, in world space
	vec3 spotDirection;
	// Where a point light or spotlight fades to nothing
	float range;
	float cosInner;
	float cosOuter;
	vec2 spare;
};
```

Under `scalar` layout this is 16 words with no padding, matching the
record.

**The point and directional functions.** Everything from
`vec3 calculatePointLight(` through the end of `calculateDirectionalLight`
becomes four functions:

```glsl
// The light a surface reflects toward the eye from one light, given the
// direction to the light and the light's strength there (Cook-Torrance).
vec3 lightContribution(vec3 L, vec3 radiance, vec3 V, vec3 N, vec3 F0, vec3 albedo, float metallic, float roughness) {
    vec3 H = normalize(V + L);

    float NDF = distributionGGX(N, H, roughness);
    float G = geometrySmith(N, V, L, roughness);
    vec3 F = fresnelSchlick(max(dot(H, V), 0.0), F0);

    vec3 numerator = NDF * G * F;
    float denominator = 4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0) + 0.0001;
    vec3 specular = numerator / denominator;

    vec3 kS = F;
    vec3 kD = vec3(1.0) - kS;
    kD *= 1.0 - metallic;

    float NdotL = max(dot(N, L), 0.0);
    return (kD * albedo / PI + specular) * radiance * NdotL;
}

// How much of a light's strength reaches a distance: the inverse square,
// faded smoothly to nothing at the light's range (Item 37).
float rangeAttenuation(float distance, float range) {
    float inverseSquare = 1.0 / max(distance * distance, 0.0001);
    if (range <= 0.0) {
        return inverseSquare;
    }
    float ratio = distance / range;
    float window = clamp(1.0 - ratio * ratio * ratio * ratio, 0.0, 1.0);
    return inverseSquare * window * window;
}

vec3 calculatePointLight(Light light, vec3 worldPos, vec3 V, vec3 N, vec3 F0, vec3 albedo, float metallic, float roughness) {
    vec3 toLight = light.positionDirection - worldPos;
    float distance = length(toLight);
    // The direction to the light (Item 37: this subtracted worldPos twice).
    vec3 L = toLight / max(distance, 0.0001);
    vec3 radiance = light.color * light.intensity * rangeAttenuation(distance, light.range);
    return lightContribution(L, radiance, V, N, F0, albedo, metallic, roughness);
}

vec3 calculateSpotLight(Light light, vec3 worldPos, vec3 V, vec3 N, vec3 F0, vec3 albedo, float metallic, float roughness) {
    vec3 toLight = light.positionDirection - worldPos;
    float distance = length(toLight);
    vec3 L = toLight / max(distance, 0.0001);

    // Full strength inside the inner angle, fading to nothing at the outer.
    float cosAngle = dot(-L, light.spotDirection);
    float cone = clamp((cosAngle - light.cosOuter) / max(light.cosInner - light.cosOuter, 0.0001), 0.0, 1.0);
    if (cone <= 0.0) {
        return vec3(0.0);
    }
    cone = cone * cone;

    vec3 radiance = light.color * light.intensity * rangeAttenuation(distance, light.range) * cone;
    return lightContribution(L, radiance, V, N, F0, albedo, metallic, roughness);
}

vec3 calculateDirectionalLight(Light light, vec3 V, vec3 N, vec3 F0, vec3 albedo, float metallic, float roughness) {
    vec3 L = normalize(-light.positionDirection);
    vec3 radiance = light.color * light.intensity;
    return lightContribution(L, radiance, V, N, F0, albedo, metallic, roughness);
}
```

The point light's unused `float intensity = 10.0f` goes. The directional
light's result is unchanged: the same Cook-Torrance terms, now in
`lightContribution`.

**The light loop in `main`.** The test `if (light.isDirectional == 1)`
becomes `if (light.lightType == 1u)`, and before the existing `else`
(the point light branch) a spotlight branch is added:

```glsl
        else if (light.lightType == 2u)
		{
			// Spotlights cast no shadows yet (Item 37).
            Lo += calculateSpotLight(light, worldPosition, V, N, F0, albedo, metallic, roughness);
		}
		else
		{
			... the existing point light branch, unchanged ...
		}
```

The point branch's shadow lookup still indexes the shadow data by `i`. Point
lights keep their indices, since spotlights come after them.

## As applied (2026-10-19)

The user asked for the Vulkan side only, with no OpenGL change unless it is
absolutely necessary. So:

- **`Environment.quorum` is unchanged:** no SpotLight blueprints.
  `EnvironmentVulkan` has `Add`, `Remove`, `GetSpotLightIterator`,
  `GetSpotLightCount` and `GetSpotLight` as its own actions.
- **`EnvironmentOpenGL.quorum` is unchanged.** Under OpenGL, a `SpotLight`
  added to a layer reaches its `Add(Light)`, which alerts "I couldn't
  identify the type of this light!". Spotlights are Vulkan-only until
  phase 4.
- **What is applied:**
  - **`SpotLight.quorum`:** new, as written.
  - **`Item3D:GetLights`:** collects spotlights. Shared code, but it only
    matters when a spotlight exists.
  - **`EnvironmentVulkan`:** as written.
  - **The lighting shader:** as written.
- **Project:**
  - `SourceCode/SpotlightCheck.quorum` is written.
  - **DriveOpen has headlights:** two `SpotLight`s placed from the car's
    physics transform every frame. H switches them and N switches night. Run it under
  Vulkan only. The OpenGL step in the test plan is dropped.

## What changes on screen

- **Point lights away from the origin** light surfaces facing them, and the
  light falls off around the lamp, not from a wrong direction. DriveOpen's
  lamp looks different, and right.
- **Point lights' outer edge fades to zero** at `GetRange`, where they were
  already very dim, so in practice almost nothing changes.
- **Directional lights and the sun** are unchanged.
- **Spotlights** draw a cone of light with a soft edge, and no shadow.
- **OpenGL:** unchanged. Spotlights are accepted but not drawn.

## Project: `AllTerrainVehicle/SourceCode/SpotlightCheck.quorum`

```
use Libraries.Game.Game
use Libraries.Game.InputMonitor
use Libraries.Game.Graphics.Color
use Libraries.Game.Graphics.Model
use Libraries.Game.Graphics.Label
use Libraries.Game.Graphics.AmbientLight
use Libraries.Game.Graphics.PointLight
use Libraries.Game.Graphics.SpotLight
use Libraries.Interface.Events.KeyboardEvent
use Libraries.Compute.Math

/*
SpotlightCheck tests spotlights and the point light fix under Vulkan (library
Item 37, Item37.md). The scene is placed far from the world's origin, at x
and z of 300, where the old point light bug was obvious.

- A white spotlight on a post sweeps slowly over a floor with boxes and
  pillars.
- A red spotlight hangs over one box, pointing straight down.
- A turning platform carries a green spotlight as its child, pointing
  forward and down, so its cone turns with the platform.

Keys:
- A and Z widen and narrow the white light's cone.
- R and F lengthen and shorten its range.
- S stops or starts the sweep.
- P adds or removes a point light over the middle (the fixed point light).

What to see:
1. Round or oval pools of light with a soft edge; nothing lit behind a
   light or outside its cone.
2. The green cone turns with the platform.
3. The point light lights the faces of the boxes that face it, wherever it
   is, with its brightness falling off around it.
4. No shadows from the spotlights yet (Item 37 has none).

Attribute: Example
// SpotlightCheck is a main program: set it as the project's main file and
// run it.
*/
class SpotlightCheck is Game
    constant number CENTER = 300

    Label label
    InputMonitor monitor
    KeyboardEvent keys
    Math math
    AmbientLight ambient
    Model floor
    Model platform
    SpotLight sweeper
    SpotLight redLight
    SpotLight carried
    PointLight bulb

    boolean sweeping = true
    boolean bulbShown = false
    number sweepTime = 0
    number outer = 25
    number range = 30

    boolean aWasDown = false
    boolean zWasDown = false
    boolean rWasDown = false
    boolean fWasDown = false
    boolean sWasDown = false
    boolean pWasDown = false

    action Main
        SetScreenSize(1000, 600)
        UseVulkan(true)
        StartGame()
    end

    action CreateGame
        Color colors
        ambient:SetColor(0.06, 0.06, 0.08, 1)
        SetAmbientLight(ambient)

        floor:LoadBox(40, 0.2, 40, colors:CustomColor(0.7, 0.7, 0.7, 1))
        floor:SetPosition(CENTER, -0.1, CENTER)
        Add(floor)

        integer i = 0
        repeat while i < 6
            Model box
            box:LoadBox(1.5, 1.5, 1.5, colors:CustomColor(0.8, 0.8, 0.9, 1))
            box:SetPosition(CENTER - 7 + i * 2.8, 0.75, CENTER + 4)
            Add(box)
            Model pillar
            pillar:LoadBox(0.5, 4, 0.5, colors:CustomColor(0.6, 0.5, 0.4, 1))
            pillar:SetPosition(CENTER - 7 + i * 2.8, 2, CENTER - 4)
            Add(pillar)
            i = i + 1
        end

        Model post
        post:LoadBox(0.3, 8, 0.3, colors:Gray())
        post:SetPosition(CENTER, 4, CENTER - 10)
        Add(post)

        sweeper:SetColor(colors:White())
        sweeper:SetPosition(CENTER, 8, CENTER - 10)
        sweeper:SetConeAngles(outer * 2 / 3, outer)
        sweeper:SetIntensity(120)
        sweeper:SetRange(range)
        Add(sweeper)

        redLight:SetColor(colors:Red())
        redLight:SetPosition(CENTER - 7, 6, CENTER + 4)
        redLight:SetDirection(0, -1, 0)
        redLight:SetConeAngles(12, 20)
        redLight:SetIntensity(60)
        redLight:SetRange(10)
        Add(redLight)

        // The green light is a child of a turning platform.
        platform:LoadBox(2, 0.4, 2, colors:CustomColor(0.3, 0.3, 0.3, 1))
        platform:SetPosition(CENTER + 8, 3, CENTER)
        carried:SetColor(colors:Green())
        carried:SetPosition(0, 0, 0)
        carried:SetDirection(0, -0.6, 1)
        carried:SetConeAngles(15, 25)
        carried:SetIntensity(80)
        carried:SetRange(20)
        platform:Add(carried)
        Add(platform)

        bulb:SetColor(colors:CustomColor(1, 0.9, 0.7, 1))
        bulb:SetPosition(CENTER, 3, CENTER)
        bulb:SetIntensity(20)

        GetCamera3D():SetPosition(CENTER, 14, CENTER - 24)
        GetCamera3D():LookAt(CENTER, 0, CENTER)
        GetCamera3D():SetFar(200)

        label:SetPosition(10, 10)
        label:SetText("A/Z cone, R/F range, S sweep, P point light")
        Add(label)
        UpdateSweep(0)
    end

    action Update(number seconds)
        if Pressed(keys:A, aWasDown)
            outer = math:MinimumOf(outer + 5, 85)
            sweeper:SetConeAngles(outer * 2 / 3, outer)
            output "Cone: " + outer + " degrees"
        end
        aWasDown = monitor:IsKeyPressed(keys:A)
        if Pressed(keys:Z, zWasDown)
            outer = math:MaximumOf(outer - 5, 5)
            sweeper:SetConeAngles(outer * 2 / 3, outer)
            output "Cone: " + outer + " degrees"
        end
        zWasDown = monitor:IsKeyPressed(keys:Z)
        if Pressed(keys:R, rWasDown)
            range = range + 5
            sweeper:SetRange(range)
            output "Range: " + range
        end
        rWasDown = monitor:IsKeyPressed(keys:R)
        if Pressed(keys:F, fWasDown)
            range = math:MaximumOf(range - 5, 5)
            sweeper:SetRange(range)
            output "Range: " + range
        end
        fWasDown = monitor:IsKeyPressed(keys:F)
        if Pressed(keys:S, sWasDown)
            sweeping = not sweeping
        end
        sWasDown = monitor:IsKeyPressed(keys:S)
        if Pressed(keys:P, pWasDown)
            if bulbShown
                Remove(bulb)
            else
                Add(bulb)
            end
            bulbShown = not bulbShown
            output "Point light: " + bulbShown
        end
        pWasDown = monitor:IsKeyPressed(keys:P)

        if sweeping
            UpdateSweep(seconds)
        end
        platform:Rotate(0, 1, 0, 25 * seconds)
    end

    private action Pressed(integer key, boolean wasDown) returns boolean
        return monitor:IsKeyPressed(key) and not wasDown
    end

    // The white light swings from side to side, pointing down and forward.
    private action UpdateSweep(number seconds)
        sweepTime = sweepTime + seconds
        number swing = math:Sine(sweepTime * 0.5) * 0.8
        sweeper:SetDirection(swing, -0.7, 1)
    end
end
```

(`Math:MinimumOf`, `MaximumOf` and `Sine`, and `Game:Add` and `Remove` for
`PointLight`, exist; checked.)

## Test plan

1. **SpotlightCheck:** the "what to see" list in its comment, including A,
   Z, R, F, S and P, and the green cone turning with the platform.
2. **DriveOpen:** the lamp lights the ground around it correctly, not from
   one side. Everything else looks as before.
3. **MSAACheck, TerrainWalk:** sun lighting and shadows unchanged.
4. **MemoryCheck:** unchanged numbers. The light buffer grows from 512 to
   1,024 bytes per frame slot.

## Rollback

Delete `SpotLight.quorum` and revert the Item 37 changes in the six library
files and the shader.
