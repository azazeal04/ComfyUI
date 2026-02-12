# NOVA v2: Low‑VRAM First Node Runtime + Frontend System

> Target: a **new backend + frontend node platform** optimized for Nvidia GTX 10xx (Pascal, 2–8GB VRAM), while preserving compatibility with all other GPUs.

---

## 0) Review Scope and Constraints

## Repositories reviewed
- Backend/main repo: `/workspace/ComfyUI` (direct code inspection performed).
- Frontend repo requested by user: `https://github.com/azazeal04/ComfyUI_frontend` (attempted clone in this environment).

## Constraint encountered
- Outbound GitHub clone failed in this environment (`403 CONNECT tunnel failed`) for both frontend URLs (`Comfy-Org/ComfyUI_frontend` and `azazeal04/ComfyUI_frontend`), so frontend source-level validation could not be completed here.

---

## 1) Current-System Findings (Ground Truth from this backend)

1. Execution is queue-driven from `main.py::prompt_worker`, which feeds `execution.PromptExecutor` in a single worker thread.
2. `execution.py` already contains partial-dag re-execution and cache primitives (`CLASSIC`, `LRU`, `RAM_PRESSURE`, `NONE`), but cache policy is global, not hardware/profile aware.
3. `comfy/model_management.py` has broad device support (CUDA/XPU/NPU/MLU/MPS/CPU), VRAM states, and offload logic.
4. Frontend is package/version managed (`app/frontend_management.py`, `requirements.txt`) and connected via websocket with feature flags (`comfy_api/feature_flags.py`).
5. Startup in `main.py` includes full custom-node prestartup scanning and initialization paths that can dominate time-to-first-interaction on heavily customized installs.

Implication: the architecture is already portable and extensible, but low-VRAM performance on Pascal can be significantly improved with **scheduler + residency + loader redesign**.

---

## 2) NOVA Runtime (New Backend)

## 2.1 Design principles
- **VRAM as a first-class resource** in planning and scheduling.
- **Streaming-first execution** for large image/video/audio tasks.
- **Fast cold start + fast warm repeat** through staged loading and persistent indexes.
- **Back-compat first** via adapter shims for existing nodes.

## 2.2 Hardware Profiles

At startup, runtime selects profile from detected device, overrideable per workflow:

- `PASCAL_2G` (GTX 1050 class)
- `PASCAL_4G` (1050 Ti / constrained 1060)
- `PASCAL_6G_8G` (1060/1070/1080)
- `RTX_MODERN`
- `AMD_ROCM`
- `INTEL_XPU`
- `CPU_SAFE`

Each profile sets:
- default precision policy,
- quantization allowances,
- tile/chunk defaults,
- prefetch depth,
- target memory headroom,
- kernel preference family.

### Pascal defaults
- Prefer fp16 activations, but allow weight-only int8/int4 where quality-validated.
- Enforce latent-tiled inference for oversized resolutions.
- Keep strict workspace bounds to avoid fragmentation/OOM.
- Prefer deterministic low-overhead kernels over tensor-core-only paths.

---

## 2.3 Two-Plane Scheduler

### Control Plane responsibilities
- Build execution plan from DAG.
- Estimate memory/time per node by profile.
- Choose execution mode: full, tiled, micro-batched, streamed.
- Decide prefetch/offload order.

### Compute Plane responsibilities
- Submit kernels/ops to device queues.
- Overlap H2D/D2H transfer with compute.
- Emit telemetry events continuously.

### Key scheduling primitive
Every node executes as one of:
- `atomic` (small, single-pass)
- `tiled` (spatial chunks)
- `streamed` (time/frequency/frame chunks)
- `microbatch` (batch split)

---

## 2.4 Residency Graph (Model/Artifact lifecycle)

Create a centralized residency registry:

```text
AssetState = UNLOADED | CPU_MMAP | CPU_HOT | GPU_FULL | GPU_PARTIAL
```

Tracked metadata per asset:
- bytes_total
- bytes_gpu_resident
- load_ms_estimate
- transfer_ms_estimate
- last_used_ts
- pin_priority
- quality_critical (bool)

Policies:
- Memory-map safetensors by default.
- Lazy hydrate tensors by key-range.
- Support partial GPU residency for large blocks.
- Add LRU + “pin set” for active pipeline components.

---

## 2.5 Node ABI v2

Introduce ABI v2 without breaking v1.

### New node metadata (declarative)
- `estimate_vram(profile, input_shape)`
- `execution_modes_supported = {atomic|tiled|streamed|microbatch}`
- `quantization_support = {none|int8|int4}`
- `checkpointable_state`
- `warmup_signature`

### Compatibility
- Legacy nodes are wrapped with a `NodeV1Adapter` that supplies conservative defaults.
- New scheduler can still plan around unknown nodes using safe upper bounds.

---

## 2.6 Media engines (shared runtime contract)

1. `ImageEngine`
   - latent-tile planner
   - seam-aware overlap blend
   - progressive preview stream

2. `VideoEngine`
   - frame-window chunking
   - temporal cache reuse
   - partial sequence output while remaining windows run

3. `AudioEngine`
   - spectrogram/time-chunk planner
   - overlap-add synthesis
   - low-latency chunk playback previews

All engines use identical telemetry schema and scheduling hooks.

---

## 3) NOVA Studio (New Frontend System)

## 3.1 UX pillars for low-VRAM users
- **VRAM budget rail** on graph + selected subgraph.
- **Auto-Optimize** action generating profile-specific execution overrides.
- **Bottleneck inspector** splitting latency into:
  - startup/import,
  - model load,
  - transfer,
  - compute,
  - cache replay.

## 3.2 Execution lifecycle states shown in UI
- `planning`
- `indexing`
- `prefetching`
- `warming`
- `running`
- `streaming_partial`
- `finalizing`
- `cached_replay`

## 3.3 Frontend protocol additions (WS)

New events (feature-flagged):
- `telemetry.node_start`
- `telemetry.node_end`
- `telemetry.memory_forecast`
- `telemetry.residency_delta`
- `output.partial.image`
- `output.partial.video`
- `output.partial.audio`

These are additive; old clients remain functional.

## 3.4 Hardware templates
Ship workflow presets for:
- GTX 1050/2–4GB
- GTX 1060/6GB
- GTX 1070/1080/8GB
- RTX modern

Each template includes defaults for dimensions, batch/chunk sizes, and quality mode.

---

## 4) Fast Startup + Fast Model Loading

## 4.1 Startup pipeline redesign

Current pain point: heavy initialization before first usable UI.

Proposed staged startup:
1. `Stage A` (fast): API + minimal UI shell online.
2. `Stage B`: node registry warmup async.
3. `Stage C`: model index + residency planner warmup async.

## 4.2 Persistent model index

Create on-disk index database with:
- model path
- size/hash/mtime
- tensor map metadata
- compatibility tags (image/video/audio)

Incremental refresh only for changed files.

## 4.3 Deferred custom-node import

- Keep compatibility but load custom-node modules lazily unless explicitly marked eager.
- Cache import success/failure signatures to skip repeated slow probes.

## 4.4 Model warm pool

Based on recent workflow history:
- preload top-N likely model assets into `CPU_MMAP` / `CPU_HOT`.
- avoid repeated cold loads across runs.

---

## 5) Concrete Integration Plan for this Backend

## 5.1 New modules to add
- `comfy_execution/nova_scheduler.py`
- `comfy_execution/residency_graph.py`
- `comfy_execution/profile_policy.py`
- `comfy_execution/telemetry.py`
- `comfy_execution/node_abi_v2.py`

## 5.2 Existing modules to adapt
- `main.py`
  - add scheduler selection flag (`--executor legacy|nova`).
  - staged startup orchestration.
- `execution.py`
  - expose node planning metadata and adapter hooks.
- `comfy/model_management.py`
  - integrate residency states and profile memory headroom constraints.
- `server.py`
  - emit new telemetry and partial-output websocket events.
- `comfy_api/feature_flags.py`
  - advertise NOVA protocol capabilities.

## 5.3 Migration strategy
- Release 1: NOVA behind feature flag, legacy default.
- Release 2: NOVA default for Pascal profiles, legacy fallback toggle.
- Release 3: broad default, legacy frozen for compatibility.

---

## 6) Benchmark & Validation Plan

## 6.1 Test hardware matrix
- GTX 1050 Ti 4GB
- GTX 1060 6GB
- GTX 1080 8GB
- RTX 3060/4060 baseline
- AMD and Intel sanity nodes

## 6.2 Workload suites
- Image: SD1.5, SDXL, upscale pipeline
- Video: short diffusion video generation + interpolation
- Audio: music generation chunk pipeline

## 6.3 Required KPIs
- time-to-UI-ready
- time-to-first-output
- steady-state it/s or sec/frame
- model-switch latency
- OOM incidence rate
- quality delta (LPIPS/CLIPScore/audio MOS proxy)

Target outcomes for Pascal:
- 30%+ faster time-to-first-output on common workflows
- 40%+ lower OOM rate on 2–4GB cards
- 20%+ faster model switch on warm runs

---

## 7) Risk Register

- **Custom-node compatibility risk**
  - Mitigation: adapter, telemetry warnings, long deprecation window.

- **Quality drop from quantization/tiling**
  - Mitigation: quality modes + per-node quantization opt-out + golden-set validation.

- **Complex scheduler regressions**
  - Mitigation: legacy executor fallback and A/B benchmarking gate in CI.

- **Frontend/backend protocol drift**
  - Mitigation: strict feature-flag negotiation and versioned event contracts.

---

## 8) Immediate Next Steps (Implementation Order)

1. Implement telemetry first (no behavior change).
2. Add profile policy and residency graph read-only mode.
3. Integrate NOVA scheduler for one image path behind flag.
4. Add partial output streaming for image tiles.
5. Extend to video/audio stream engines.
6. Enable auto-optimize frontend panel after telemetry is stable.

This order minimizes regression risk while delivering measurable gains early for GTX 10xx users.
