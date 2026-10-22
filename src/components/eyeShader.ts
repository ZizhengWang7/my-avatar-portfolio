// Reused from the validated isolated eye prototype.
import { Matrix3, NoColorSpace, SRGBColorSpace, Vector2, Vector4 } from 'three'
import type { MeshStandardMaterial, Texture } from 'three'
import { visualDiagnostics } from './visualTuning'

export interface EyeConfig {
  label: string
  domain: [number, number, number, number]
  base: string
  mr: string
  mask: string
  normal: string
}
export interface PrototypeConfig { range_x: number; range_y: number; eyes: EyeConfig[] }

export function patchEyeMaterial(material: MeshStandardMaterial, config: PrototypeConfig, textures: Texture[]) {
  const uniforms = {
    eyeRange: { value: new Vector2(config.range_x, config.range_y) },
    eyeNormalToView: { value: new Matrix3() },
    eyeGaze0: { value: new Vector2() }, eyeGaze1: { value: new Vector2() },
  }
  const maps: Record<string, { value: Texture | Vector4 }> = {}
  config.eyes.forEach((eye, index) => {
    maps[`eyeDomain${index}`] = { value: new Vector4(...eye.domain) }
    ;['base', 'mr', 'mask', 'normal'].forEach((role, channel) => {
      const texture = textures[index * 4 + channel]
      texture.colorSpace = role === 'base' ? SRGBColorSpace : NoColorSpace
      texture.needsUpdate = true
      maps[`eye${role}${index}`] = { value: texture }
    })
  })
  material.onBeforeCompile = shader => {
    if (import.meta.env.DEV) visualDiagnostics.shaderCompiled = true
    Object.assign(shader.uniforms, uniforms, maps)
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 eyeBindPosition;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\neyeBindPosition = position;')
    shader.fragmentShader = shader.fragmentShader.replace('#include <common>', `#include <common>
      varying vec3 eyeBindPosition;
      uniform vec2 eyeRange, eyeGaze0, eyeGaze1;
      uniform vec4 eyeDomain0, eyeDomain1;
      uniform mat3 eyeNormalToView;
      uniform sampler2D eyebase0, eyemr0, eyemask0, eyenormal0;
      uniform sampler2D eyebase1, eyemr1, eyemask1, eyenormal1;
      void eyeCoordinates(vec4 domain, sampler2D maskMap, vec2 gaze, out vec2 shifted, out float weight) {
        vec2 uv = (eyeBindPosition.xy - domain.xy) / domain.zw;
        float inside = step(0.0, uv.x) * step(uv.x, 1.0) * step(0.0, uv.y) * step(uv.y, 1.0);
        float front = smoothstep(0.24, 0.29, eyeBindPosition.z) * (1.0 - smoothstep(0.40, 0.45, eyeBindPosition.z));
        float mask = texture2D(maskMap, uv).r * front * inside;
        shifted = uv - gaze * eyeRange / domain.zw * mask;
        float activation = smoothstep(0.0, 0.125, max(abs(gaze.x), abs(gaze.y)));
        weight = smoothstep(0.0, 0.1, mask) * activation;
      }
      vec3 eyeViewNormal(sampler2D normalMap, vec2 uv) {
        vec3 blenderNormal = texture2D(normalMap, uv).xyz * 2.0 - 1.0;
        return normalize(eyeNormalToView * vec3(blenderNormal.x, blenderNormal.z, -blenderNormal.y));
      }
    `)
    shader.fragmentShader = shader.fragmentShader.replace('#include <map_fragment>', `#include <map_fragment>
      vec2 eyeUV0, eyeUV1;
      float eyeWeight0, eyeWeight1;
      eyeCoordinates(eyeDomain0, eyemask0, eyeGaze0, eyeUV0, eyeWeight0);
      eyeCoordinates(eyeDomain1, eyemask1, eyeGaze1, eyeUV1, eyeWeight1);
      diffuseColor.rgb = mix(diffuseColor.rgb, texture2D(eyebase0, eyeUV0).rgb * diffuse, eyeWeight0);
      diffuseColor.rgb = mix(diffuseColor.rgb, texture2D(eyebase1, eyeUV1).rgb * diffuse, eyeWeight1);
    `)
    shader.fragmentShader = shader.fragmentShader.replace('#include <roughnessmap_fragment>', `#include <roughnessmap_fragment>
      roughnessFactor = mix(roughnessFactor, texture2D(eyemr0, eyeUV0).g * roughness, eyeWeight0);
      roughnessFactor = mix(roughnessFactor, texture2D(eyemr1, eyeUV1).g * roughness, eyeWeight1);
    `)
    shader.fragmentShader = shader.fragmentShader.replace('#include <metalnessmap_fragment>', `#include <metalnessmap_fragment>
      metalnessFactor = mix(metalnessFactor, texture2D(eyemr0, eyeUV0).b * metalness, eyeWeight0);
      metalnessFactor = mix(metalnessFactor, texture2D(eyemr1, eyeUV1).b * metalness, eyeWeight1);
    `)
    shader.fragmentShader = shader.fragmentShader.replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
      normal = normalize(mix(normal, eyeViewNormal(eyenormal0, eyeUV0), eyeWeight0));
      normal = normalize(mix(normal, eyeViewNormal(eyenormal1, eyeUV1), eyeWeight1));
    `)
  }
  material.customProgramCacheKey = () => 'isolated-eye-projection-v3'
  material.needsUpdate = true
  return uniforms
}
