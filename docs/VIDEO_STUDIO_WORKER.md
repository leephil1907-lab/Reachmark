# Reachmark Studio — GPU worker contract

Reachmark's Flask app owns authenticated projects, briefs, job records, and the user-facing workspace. Diffusion inference and video rendering must run on a separate GPU-capable worker. The web service must never claim that a video rendered unless the worker returns a real output.

## Connect a worker

Set the server environment variable:

- `VIDEO_STUDIO_WORKER_URL=https://your-private-gpu-worker.example`

The worker must accept `POST /jobs` with JSON containing:

```json
{
  "id": "Reachmark job id",
  "project_id": "Reachmark project id",
  "provider": "ltx2",
  "prompt": "Creative brief",
  "aspect_ratio": "9:16",
  "style": "cinematic",
  "duration": 30,
  "callback_path": "/api/studio/jobs/<job-id>"
}
```

The initial response should be HTTP 202 and JSON such as `{"status":"queued","worker_job_id":"..."}`. If the job completed synchronously, the worker may return `{"status":"completed","output_url":"https://.../video.mp4"}`. Supported statuses are `queued`, `running`, `completed`, and `failed`.

## Adapter responsibilities

- Wan2GP: map provider id `wangp` to the installed Wan2GP API or headless job runner.
- LTX-2: map `ltx2` to a supported LTX-2 pipeline, including audio-video output where available.
- HunyuanVideo: map `hunyuan` to the installed model/runtime.
- Open-Sora: map `opensora` only when the selected Open-Sora implementation is installed and compatible.
- HyperFrames: use the rendering stage for HTML/CSS/JS scene composition, kinetic type, overlays, transitions, captions, and deterministic MP4 encoding.
- Remotion: optional renderer adapter for existing React-based compositions. It is not necessary to run both renderers for every project.

## Production requirements

1. Keep worker credentials and model download tokens in server-side secrets only.
2. Restrict worker ingress to the application and require authenticated requests.
3. Persist source assets and outputs in durable object storage; do not return temporary local paths.
4. Enforce per-user concurrency, timeouts, cancellation, quotas, and output-size limits.
5. Report progress and failures from real worker state. Never replace an error with a fabricated sample video.
6. Validate output URLs and MIME types before exposing them to clients.
7. Deploy the web workspace separately from GPU inference so a free/CPU web instance can still manage projects.

## Current scope

The web app exposes project CRUD, a provider capability endpoint, and a job submission adapter. A GPU worker is not bundled with the Flask web server. Without `VIDEO_STUDIO_WORKER_URL`, generation intentionally returns HTTP 503 and clearly explains that no render was created.
