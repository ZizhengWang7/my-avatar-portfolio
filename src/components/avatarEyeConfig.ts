import type { PrototypeConfig } from './eyeShader'

// Original tested ranges and projection maps; do not expand without visual review.
export const AVATAR_EYES: PrototypeConfig = {
  "range_x": 0.003,
  "range_y": 0.002,
  "eyes": [
    {
      "label": "viewer-left",
      "domain": [
        -0.245,
        0.065,
        0.2,
        0.17
      ],
      "base": "/models/avatar-eye-prototype/viewer-left-base.png",
      "mr": "/models/avatar-eye-prototype/viewer-left-mr.png",
      "mask": "/models/avatar-eye-prototype/viewer-left-mask.png",
      "normal": "/models/avatar-eye-prototype/viewer-left-normal.png"
    },
    {
      "label": "viewer-right",
      "domain": [
        0.044999999999999984,
        0.065,
        0.2,
        0.17
      ],
      "base": "/models/avatar-eye-prototype/viewer-right-base.png",
      "mr": "/models/avatar-eye-prototype/viewer-right-mr.png",
      "mask": "/models/avatar-eye-prototype/viewer-right-mask.png",
      "normal": "/models/avatar-eye-prototype/viewer-right-normal.png"
    }
  ]
}
