# My Avatar Portfolio

React + Vite + TypeScript with a lavender homepage and a refined rigged GLB avatar.

## Preview and checks

```sh
npm install
npm run dev
npm run build
node --experimental-strip-types scripts/test-avatar-motion.mjs
node --experimental-strip-types scripts/test-refined-avatar-rig.mjs
```

Open the local URL Vite prints (normally http://localhost:5173/).
`build` checks TypeScript before producing the production build. Motion tests use Node 22's experimental type stripping.

Move the pointer slowly across the entire browser window, then try fast left/right flicks, diagonals and corner holds. The head follows; the torso and neck bones remain at rest. Leaving the page or switching windows returns to neutral. Enable Reduce Motion in the OS or browser developer tools to disable all tracking and spring velocity. Touch input stays neutral for scrolling.

## Refined avatar implementation

- `src/components/InteractiveAvatar.tsx`: Loads `/models/my-avatar-head-refined.glb` using Drei `useGLTF`, isolates its skeleton with `SkeletonUtils.clone`, and retains existing responsive framing, studio lighting, materials, loading/error states and lavender layout.
- `src/components/avatarRig.ts`: Checks `AvatarHeadPrototype → torso → neck → head`. Preserves the nonidentity local head rest quaternion and converts model-world axes to the rest frame. Only head rotation is written.
- `src/components/avatarMotion.ts`: Configurable spring stiffness/damping and limits. Normal yaw target is ±30°. Safety ceilings are ±35° yaw, ±15° pitch and ±3° roll. Targets and transient overshoot are smoothly constrained inside `(yaw/35)^2 + (pitch/15)^2 + (roll/3)^2 <= 1`. The soft knee begins at normalized radius 0.9, with no abrupt pose/velocity clamping. Yaw above 30° is possible only with reduced pitch and roll. The ceilings are not simultaneous targets.

The 21 test scenarios at 30/60/144 Hz reached approximately 30.28° yaw, 14.67° pitch and 1.62° roll; these are measured test peaks, not guaranteed peaks for every pointer trajectory. Slow motion uses stronger damping; quick sweeps add subtle lean and overshoot. Head-only CPU skinning tests check the actual exported GLB, directions, neutral/rest preservation, normalized skin weights and fixed vertices for 19 poses.

No eye tracking, blinking, animation clips or drag controls are enabled. Materials, textures, geometry, UVs and the original/test/refined GLB files are not edited by this integration.

## Repository assets and local working files

The published website includes only `public/models/my-avatar-head-refined.glb`,
approximately 22 MiB with embedded materials and textures. No external texture
files are required. Website source, configuration and development scripts are included.

Backups, reports, Blender working files, unused reference images, original/test
models and experimental eye assets are intentionally ignored by Git. They remain
on the original development machine; the paths below describe local artifacts,
not files supplied by a fresh clone. Blender inspection/prototype scripts require
those local inputs and Blender's Python environment. The two Node motion/rig tests
above work with the published refined GLB and generate their own ignored reports.

- `backups/pre-refined-integration/`: Full prior website source/configuration, prior motion tests and checksum manifest, created before this integration. The manifest also records all three GLB hashes.
- `backups/pre-expressive/`: Earlier working website backup.
- `src/components/ProceduralAvatarBackup.tsx`: Original procedural avatar backup.
- `public/assets/人物3d建模.glb`: Original static model.
- `public/models/my-avatar-head-test.glb`: Previous rig.
- `public/models/my-avatar-head-refined.glb`: Current refined rig, approximately 22 MiB and 436k triangles.

For a tracking-only rollback, restore `InteractiveAvatar.tsx` and `avatarMotion.ts` from `backups/pre-refined-integration/src/components/`. The added rig helper then becomes unused. Do not overwrite any GLB to revert the website.

## Validation artifacts and limits

- `reports/refined-avatar-integration.json`: Integration summary and measured maxima.
- `reports/refined-avatar-motion-tests.json`: Flicks, repeated sweeps, combined corner holds, jitter, envelope continuity and neutral return.
- `reports/refined-avatar-rig-tests.json`: Actual GLB hierarchy/rest-transform and skinning checks.
- `reports/refined-avatar-integration-previews/`: Textured Blender previews of sampled runtime spring peaks and a constrained corner pose.
- `scripts/preview_refined_tracking.py`: Reproduces these previews read-only using the motion test report.
- `reports/avatar-head-refinement/`: Previous rig refinement diagnosis and full angle-sweep comparisons.

Sampled runtime poses showed no obvious previous jaw stretching, hair collapse or collar flap in the reviewed Blender views. Existing coarse neck facets and baked shading remain. Live browser PBR appearance/continuous motion and mobile performance still need user visual review; the bundle-size warning and large model are unchanged constraints. Combining all full axis maxima is deliberately prevented.
