# My Avatar Portfolio

A small interactive portfolio built with React, TypeScript, Vite, and Three.js. Move your mouse to meet the avatar: its head and eyes follow along, while water ripples and scattered sparkles trail your cursor.

[Try the live demo](https://my-avatar-portfolio-mvpv6c4zl-su-p-er-sg.vercel.app)

## What’s inside

- A rigged 3D avatar rendered with React Three Fiber and Drei, with spring-based head movement and subtle shader-based eye tracking.
- An Illinois Blue background with Illinois Orange, light-blue, and white accents.
- Overlapping ripples and occasional sparkles, with a clear area around the avatar’s face.
- Responsive framing, reduced-motion support, and neutral tracking on touch devices.

Head tracking rotates only the head bone; the neck and torso stay at rest. Leaving the page or switching windows returns the avatar to neutral, and eye tracking also settles after six seconds of inactivity.

## Run locally

Use Node.js 22.13 or later in the Node 22 series and npm.

```sh
npm ci
npm run dev
```

Open the URL Vite prints, usually http://localhost:5173/.

```sh
npm run build
npm run preview
npm run lint
```

The build checks TypeScript before creating the production files in `dist/`. Preview serves that build locally.

## Development controls

Press **Shift + D** during local development to open the visual tuning panel. Adjust the trail and eye response, freeze the head, or compare fixed gaze directions. The panel is hidden by default; its UI, styles, and shortcut are excluded from production builds.

## Implementation notes

The avatar loads `public/models/my-avatar-eye-prototype-neutral.glb` and eight eye projection PNGs from `public/models/avatar-eye-prototype/`. Eye movement uses a custom material shader rather than rotating eye geometry or playing a glTF animation. The previous refined GLB remains in the repository for rig validation.

The cursor effect uses a separate Canvas 2D layer with cached gradients and star geometry. Pools cap active stars at 160 and ripples at 32; DPR is capped at 1.5 and the backing store at four million pixels. Drawing pauses once the trail fades, and listeners and animation callbacks are cleaned up on unmount. Ripples normally last 0.6–0.8 seconds; fast movement can recycle older rings at the pool limit.

The model and JavaScript bundle are still relatively large, so initial loading and performance can vary by device.

## Tests

Run the motion test first because the rig test reads its generated report:

```sh
node --experimental-strip-types scripts/test-avatar-motion.mjs
node --experimental-strip-types scripts/test-refined-avatar-rig.mjs
```

These check 21 motion scenarios at 30, 60, and 144 Hz and 19 poses against the refined GLB. They cover head motion and skinning, rather than the eye shader or cursor visuals. Reports are generated locally and ignored by Git.

Blender scripts may require original assets and Blender’s Python environment. Backups, screenshots, Blender working files, caches, and build outputs stay local and are not included in a fresh clone.
