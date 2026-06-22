# ClawCodex Frontend

This React + TypeScript + Vite app is the local dashboard for the ClawCodex FastAPI control plane.

## Commands

```powershell
npm install
npm run dev
npm run lint
npm run build
```

`npm run dev` starts the Vite development server. `npm run build` writes production assets to `frontend/dist`, which `src/server/app.py` serves from `http://127.0.0.1:8000`.

## Dashboard Features

- Mission Control creates staged coding tasks for a repo path and prompt.
- Missions pause after `PLAN`; the approval banner shows the actual plan preview and waits for **Approve Plan and Code** before `CODE` runs.
- The Latest Plan card is populated from the latest `PLAN` stage output instead of static placeholder steps.
- Diff approvals remain separate from plan approval; generated changes wait for review before being written.
- The Missions page lists recent tasks with open, stop, and delete actions.
- The Repositories page lists recent repo paths from task history.
- The Templates page shows rule packs discovered under `clawcodex-packs/`.
- The Integrations page shows OpenRouter key status and links to model settings.
- The Rules panel shows active rule summaries and lets users choose rule packs for the next mission.
- Prompt preflight corrects high-confidence extension typos such as `xlxs` to `xlsx` and asks before applying uncertain corrections.

## API Expectations

The app talks to the local FastAPI server through `frontend/src/api/client.ts`. Core endpoints include:

- `GET /api/tasks`
- `POST /api/tasks`
- `POST /api/tasks/{task_id}/start`
- `POST /api/tasks/{task_id}/approve-plan`
- `DELETE /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/timeline`
- `GET /api/repos/recent`
- `GET /api/rules/packs`
- `POST /api/rules/active`

Run the backend from the repo root:

```powershell
$env:PYTHONPATH = "$PWD"
python -m uvicorn src.server.app:app --host 127.0.0.1 --port 8000
```

## Verification

Before merging frontend changes, run:

```powershell
npm run lint
npm run build
```
