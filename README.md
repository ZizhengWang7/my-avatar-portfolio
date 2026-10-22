# My Avatar Portfolio

React + Vite + TypeScript with an Illinois-inspired orange/navy gradient homepage and a refined rigged GLB avatar.

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

- `src/components/InteractiveAvatar.tsx`: Loads `/models/my-avatar-eye-prototype-neutral.glb` using Drei `useGLTF`, isolates its refined head skeleton with `SkeletonUtils.clone`, and retains existing responsive framing, studio lighting, error states and responsive layout.
- `src/components/avatarRig.ts`: Checks `AvatarHeadPrototype → torso → neck → head`. Preserves the nonidentity local head rest quaternion and converts model-world axes to the rest frame. Only head rotation is written.
- `src/components/avatarMotion.ts`: Configurable spring stiffness/damping and limits. Normal yaw target is ±30°. Safety ceilings are ±35° yaw, ±15° pitch and ±3° roll. Targets and transient overshoot are smoothly constrained inside `(yaw/35)^2 + (pitch/15)^2 + (roll/3)^2 <= 1`. The soft knee begins at normalized radius 0.9, with no abrupt pose/velocity clamping. Yaw above 30° is possible only with reduced pitch and roll. The ceilings are not simultaneous targets.

The 21 test scenarios at 30/60/144 Hz reached approximately 30.28° yaw, 14.67° pitch and 1.62° roll; these are measured test peaks, not guaranteed peaks for every pointer trajectory. Slow motion uses stronger damping; quick sweeps add subtle lean and overshoot. Head-only CPU skinning tests check the actual exported GLB, directions, neutral/rest preservation, normalized skin weights and fixed vertices for 19 poses.

Subtle eye tracking reuses the tested masked projection shader in `src/components/eyeShader.ts`, with configuration in `avatarEyeConfig.ts`. Both eyes have separate gaze uniforms that follow the pointer faster than the head (exponential response 24/s, with smooth pointer gain), without rotating eye geometry. The original tested displacement limits are ±0.003 horizontally and ±0.002 vertically in model units. Color, roughness and shading normals move together; bind-space projection and the head's current skin transform keep the effect attached during head turns. Each scene instance gets a cloned material; source textures and GLBs remain unchanged.

Gaze returns to the original material at neutral on pointer leave/blur, and after six seconds of pointer inactivity. Reduced motion and touch/coarse-pointer input stay neutral. No blinking, animation clips or drag controls are enabled. The orange, light-blue and white Canvas 2D cursor trail remains independent of the avatar.

The eye shader is application code, not a portable glTF animation. Production also requires the eight original PNG projection maps under `public/models/avatar-eye-prototype/`; Git now allows those existing assets and the neutral GLB. The neutral export retains the refined head rig and source appearance. The original refined GLB remains available and unchanged. See ignored `reports/eye-integration/` for Chromium pose screenshots and validation notes.

## Repository assets and local working files

The website loads `public/models/my-avatar-eye-prototype-neutral.glb`,
approximately 25 MiB with embedded original materials/textures, plus the small eye
projection PNGs. The previous refined GLB is retained. Website source,
configuration and development scripts are included.

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

## Development visual tuning

`npm run dev` keeps the temporary tuning panel hidden by default. Press **Shift + D** to show or hide it; the shortcut is not installed in production. The panel provides controls for star density/brightness/size/lifetime and safe eye strength/response. Freeze the head and select fixed gaze directions for comparison, or disable eyes independently. Defaults use Illinois Orange (#FF5F05), light blue (#91D6FF), and occasional white four-point stars lasting one second, with an initially opaque core and restrained halo. Eye gain reaches the original safe limits earlier in a pointer sweep; the maximum displacement is unchanged. The panel is excluded from production builds. Local screenshots and diagnosis are in ignored `reports/visual-visibility/`.

The water-led cursor effect uses irregular, overlapping ripples at randomized 12–18px path intervals, with varying radius, stroke, opacity and expansion speed. Small/medium rings and occasional larger waves expand over 0.6–0.8 seconds. Sparkles are probabilistic and scattered with approximately 35% orange, 40% light blue and 25% white; orange emission is about half the previous ribbon rate. Stars retain a one-second lifetime. Shift + D exposes Trail width and Ripple intensity (zero disables ripples). Pools cap stars at 160 and ripple objects at 32; feathered face protection applies to both.

The decorative canvas reuses cached gradients and star geometry, limits DPR to 1.5 and backing pixels to four million, and stops drawing when the trail has faded. The development tuning styles are loaded only with the development panel.
