import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  addProjectMemory,
  approveAllDiffs,
  approveDiff,
  approveHunk,
  approvePlan,
  cancelTask,
  deleteTask,
  listPacks,
  clearModelKey,
  createTask,
  getModelKeyStatus,
  getOpenRouterModels,
  getModelRoles,
  getProjectMemory,
  getTimeline,
  health,
  linkAttachment,
  listRecentRepos,
  listTasks,
  rejectAllDiffs,
  rejectDiff,
  rejectHunk,
  rollback,
  runTests,
  saveModelKey,
  scanProject,
  selfCheck,
  startTask,
  retryCode,
  updateDiffContent,
  updateModelRoles,
} from './api/client'
import type {
  Attachment,
  ModelKeyStatus,
  ModelOption,
  ModelRoles,
  PackInfo,
  ProjectProfile,
  RecentRepoRow,
  Task,
  TaskTimeline,
} from './api/types'
import { AdvancedDrawer } from './components/AdvancedDrawer'
import { ApiKeySetupModal } from './components/ApiKeySetupModal'
import { ApprovalBanner } from './components/ApprovalBanner'
import { MissionProgress } from './components/MissionProgress'
import {
  IntegrationsPage,
  MissionsPage,
  RepositoriesPage,
  TemplatesPage,
} from './components/NavPages'
import { MissionShell, type ShellNavId } from './components/MissionShell'
import { RulesMissionPanel } from './components/RulesMissionPanel'
import { MissionSummaryCards } from './components/MissionSummaryCards'
import { ModelCostPanel } from './components/ModelCostPanel'
import { ProjectMemoryPanel } from './components/ProjectMemoryPanel'
import { ReviewChangesCard } from './components/ReviewChangesCard'
import { RollbackPanel } from './components/RollbackPanel'
import { SimpleTaskComposer } from './components/SimpleTaskComposer'
import { StageTimeline } from './components/StageTimeline'
import { TaskDetailsPanel } from './components/TaskDetailsPanel'
import { TestDebugPanel } from './components/TestDebugPanel'
import { VerificationCard } from './components/VerificationCard'
import { buildMissionView } from './lib/missionView'

const defaultRepo = 'd:\\clawcodex'

function App() {
  const [repoPath, setRepoPath] = useState(defaultRepo)
  const [prompt, setPrompt] = useState('')
  const [intent, setIntent] = useState('')
  const [deniedPaths, setDeniedPaths] = useState('.env, .env.local, secrets.json')
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [task, setTask] = useState<Task | null>(null)
  const [timeline, setTimeline] = useState<TaskTimeline | null>(null)
  const [profile, setProfile] = useState<ProjectProfile | null>(null)
  const [memory, setMemory] = useState<Array<Record<string, unknown>>>([])
  const [roles, setRoles] = useState<ModelRoles | null>(null)
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([])
  const [modelSource, setModelSource] = useState('')
  const [enabledPhases, setEnabledPhases] = useState(['PLAN', 'CODE', 'TEST', 'DEBUG', 'REVIEW'])
  const [keyStatus, setKeyStatus] = useState<ModelKeyStatus | null>(null)
  const [backendOnline, setBackendOnline] = useState(false)
  const [running, setRunning] = useState(false)
  const [savingKey, setSavingKey] = useState(false)
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [keyMessage, setKeyMessage] = useState('')
  const [showComposer, setShowComposer] = useState(true)
  const [showDiffs, setShowDiffs] = useState(false)
  const [pendingRetryTaskId, setPendingRetryTaskId] = useState<string | null>(null)
  const [promptCorrectionNote, setPromptCorrectionNote] = useState('')
  const [packs, setPacks] = useState<PackInfo[]>([])
  const [currentPage, setCurrentPage] = useState<ShellNavId>('mission')
  const [missionsRows, setMissionsRows] = useState<Task[]>([])
  const [missionsLoading, setMissionsLoading] = useState(false)
  const [missionsError, setMissionsError] = useState<string | null>(null)
  const [reposRows, setReposRows] = useState<RecentRepoRow[]>([])
  const [reposLoading, setReposLoading] = useState(false)
  const [reposError, setReposError] = useState<string | null>(null)
  const [packsLoadError, setPacksLoadError] = useState<string | null>(null)
  const [enabledPackIds, setEnabledPackIds] = useState<string[]>([])

  const view = useMemo(() => buildMissionView(timeline), [timeline])
  const planApprovalNeeded = Boolean(task?.stage === 'PLAN' && latestPlanPassed(timeline))

  const refreshTimeline = useCallback(async (taskId = task?.id) => {
    if (!taskId) return
    const next = await getTimeline(taskId)
    setTimeline(next)
    setTask(next.task)
  }, [task?.id])

  const checkHealth = useCallback(async () => {
    try {
      await health()
      setBackendOnline(true)
    } catch {
      setBackendOnline(false)
    }
  }, [])

  const refreshKeyStatus = useCallback(async () => {
    const status = await getModelKeyStatus()
    setKeyStatus(status)
    if (!status.configured) setShowKeyModal(true)
    return status
  }, [])

  useEffect(() => {
    const id = window.setTimeout(() => {
      void checkHealth()
      void refreshKeyStatus().catch(() => undefined)
      getModelRoles().then(setRoles).catch(() => undefined)
      getOpenRouterModels().then((result) => {
        setModelOptions(result.models)
        setModelSource(result.source)
      }).catch(() => undefined)
      listPacks(repoPath)
        .then((rows) => {
          setPacks(rows)
          setPacksLoadError(null)
        })
        .catch((err: Error) => setPacksLoadError(err.message || 'Failed to load packs'))
    }, 0)
    return () => window.clearTimeout(id)
  }, [checkHealth, refreshKeyStatus, repoPath])

  const loadMissionsList = useCallback(async () => {
    setMissionsLoading(true)
    setMissionsError(null)
    try {
      const rows = await listTasks(200)
      setMissionsRows(rows)
    } catch (err: unknown) {
      setMissionsError(err instanceof Error ? err.message : 'Failed to load missions')
    } finally {
      setMissionsLoading(false)
    }
  }, [])

  const loadReposList = useCallback(async () => {
    setReposLoading(true)
    setReposError(null)
    try {
      const rows = await listRecentRepos(100)
      setReposRows(rows)
    } catch (err: unknown) {
      setReposError(err instanceof Error ? err.message : 'Failed to load repositories')
    } finally {
      setReposLoading(false)
    }
  }, [])

  const handleNavigate = useCallback(
    (id: ShellNavId) => {
      setCurrentPage(id)
      if (id === 'missions') void loadMissionsList()
      if (id === 'repos') void loadReposList()
    },
    [loadMissionsList, loadReposList],
  )

  useEffect(() => {
    if (!task || task.stage === 'COMPLETE' || task.stage === 'FAILED') return
    const id = window.setInterval(() => void refreshTimeline(task.id), 2000)
    return () => window.clearInterval(id)
  }, [refreshTimeline, task])

  async function handleScan() {
    const scanned = await scanProject(repoPath)
    setProfile(scanned)
    setMemory(await getProjectMemory(repoPath))
  }

  async function handleRunTask() {
    setRunning(true)
    try {
      const correction = normalizePromptExtensions(prompt)
      let correctedPrompt = correction.prompt
      const notes = [...correction.notes]
      for (const suggestion of correction.suggestions) {
        const accepted = window.confirm(`Use ${suggestion.corrected} instead of ${suggestion.original}?`)
        if (accepted) {
          correctedPrompt = correctedPrompt.split(suggestion.original).join(suggestion.corrected)
          notes.push(`Corrected ${suggestion.original} to ${suggestion.corrected}.`)
        }
      }
      setPrompt(correctedPrompt)
      setPromptCorrectionNote(notes.join(' '))
      const fullPrompt = [
        correctedPrompt,
        intent ? `Intent lock: ${intent}` : '',
        notes.length ? `Prompt corrections: ${notes.join(' ')}` : '',
        deniedPaths ? `Never touch these files: ${deniedPaths}` : '',
      ].filter(Boolean).join('\n\n')
      const created = await createTask({
        repo_path: repoPath,
        prompt: fullPrompt,
        attachment_ids: attachments.map((item) => item.id),
        model_config: { enabled_phases: enabledPhases, enabled_packs: [...enabledPackIds], prompt_corrections: notes },
      })
      setTask(created)
      for (const attachment of attachments) await linkAttachment(created.id, attachment.id)
      await startTask(created.id)
      const next = await getTimeline(created.id)
      setTimeline(next)
      setTask(next.task)
      setShowComposer(false)
      setShowDiffs(next.diff_previews.some((diff) => diff.status === 'pending'))
      const blockedReason = latestCodeBlockedReason(next)
      if (blockedReason && isAuthBlocker(blockedReason)) {
        setPendingRetryTaskId(created.id)
        setKeyMessage(blockedReason)
        setShowKeyModal(true)
      }
    } finally {
      setRunning(false)
    }
  }

  async function handleApprovePlan() {
    if (!task) return
    setRunning(true)
    try {
      await approvePlan(task.id)
      const next = await getTimeline(task.id)
      setTimeline(next)
      setTask(next.task)
      setShowDiffs(next.diff_previews.some((diff) => diff.status === 'pending'))
    } finally {
      setRunning(false)
    }
  }

  async function handleOpenMission(taskId: string) {
    const next = await getTimeline(taskId)
    setTimeline(next)
    setTask(next.task)
    setRepoPath(next.task.repo_path)
    setShowComposer(false)
    setShowDiffs(next.diff_previews.some((diff) => diff.status === 'pending'))
    handleNavigate('mission')
  }

  async function handleCancelMission(taskId: string) {
    const stopped = await cancelTask(taskId)
    if (task?.id === taskId) {
      const next = await getTimeline(taskId)
      setTimeline(next)
      setTask(next.task)
    }
    await loadMissionsList()
    if (task?.id !== taskId) {
      setMissionsRows((rows) => rows.map((row) => (row.id === taskId ? stopped : row)))
    }
  }

  async function handleDeleteMission(taskId: string) {
    if (!window.confirm('Delete this mission and its timeline? This cannot be undone.')) return
    await deleteTask(taskId)
    if (task?.id === taskId) {
      setTask(null)
      setTimeline(null)
      setShowDiffs(false)
      setShowComposer(true)
    }
    await loadMissionsList()
  }

  async function handleApproveAll() {
    if (!task) return
    setRunning(true)
    try {
      await approveAllDiffs(task.id)
      await refreshTimeline(task.id)
      setShowDiffs(false)
    } finally {
      setRunning(false)
    }
  }

  async function handleRejectAll() {
    if (!task) return
    await rejectAllDiffs(task.id)
    await refreshTimeline(task.id)
  }

  async function handleApprove(previewId: string) {
    await approveDiff(previewId)
    await refreshTimeline()
  }

  async function handleReject(previewId: string) {
    await rejectDiff(previewId)
    await refreshTimeline()
  }

  async function handleApproveHunk(previewId: string, hunkId: string) {
    await approveHunk(previewId, hunkId)
    await refreshTimeline()
  }

  async function handleRejectHunk(previewId: string, hunkId: string) {
    await rejectHunk(previewId, hunkId)
    await refreshTimeline()
  }

  async function handleUpdateDiffContent(previewId: string, content: string) {
    await updateDiffContent(previewId, content)
    await refreshTimeline()
  }

  async function handleSelfCheck() {
    if (!task) return
    await selfCheck(task.id)
    await refreshTimeline(task.id)
  }

  async function handleRollback(checkpointId: string, mode: 'clean' | 'restore_dirty') {
    if (!task) return
    await rollback(task.id, checkpointId, mode)
    await refreshTimeline()
  }

  async function handleRunTests() {
    if (!task) return
    await runTests(repoPath, task.id)
    await refreshTimeline()
  }

  async function handleRemember(content: string) {
    await addProjectMemory({ repo_path: repoPath, kind: 'note', content, evidence: ['ui'] })
    setMemory(await getProjectMemory(repoPath))
  }

  async function handleSaveKey(apiKey: string) {
    setSavingKey(true)
    try {
      const status = await saveModelKey(apiKey)
      setKeyStatus(status)
      const models = await getOpenRouterModels()
      setModelOptions(models.models)
      setModelSource(models.source)
      if (pendingRetryTaskId) {
        await retryCode(pendingRetryTaskId)
        const next = await getTimeline(pendingRetryTaskId)
        setTimeline(next)
        setTask(next.task)
        const blockedReason = latestCodeBlockedReason(next)
        if (blockedReason && isAuthBlocker(blockedReason)) {
          setKeyMessage(blockedReason)
          setShowKeyModal(true)
          throw new Error(blockedReason)
        }
        setShowDiffs(next.diff_previews.some((diff) => diff.status === 'pending'))
        setPendingRetryTaskId(null)
      }
      setShowKeyModal(false)
      setKeyMessage('')
    } finally {
      setSavingKey(false)
    }
  }

  async function handleClearKey() {
    const status = await clearModelKey()
    setKeyStatus(status)
    setShowKeyModal(!status.configured)
  }

  function togglePack(packId: string, enabled: boolean) {
    setEnabledPackIds((prev) => {
      const next = new Set(prev)
      if (enabled) next.add(packId)
      else next.delete(packId)
      return [...next]
    })
  }

  return (
    <MissionShell
      backendOnline={backendOnline}
      keyConfigured={Boolean(keyStatus?.configured)}
      activeNav={currentPage}
      onNavigate={handleNavigate}
      onNewMission={() => {
        handleNavigate('mission')
        setShowComposer(true)
      }}
      onOpenSettings={() => {
        setKeyMessage('')
        setPendingRetryTaskId(null)
        void refreshKeyStatus().finally(() => setShowKeyModal(true))
      }}
    >
      <ApiKeySetupModal
        key={`${showKeyModal}-${keyStatus?.configured}-${keyStatus?.source}-${keyMessage}`}
        open={showKeyModal}
        status={keyStatus}
        message={keyMessage}
        saving={savingKey}
        onSave={handleSaveKey}
        onSkip={() => setShowKeyModal(false)}
      />

      {currentPage !== 'mission' ? (
        <section className="nav-page">
          <header className="nav-page-header">
            <div>
              <h2 className="nav-page-title">
                {currentPage === 'missions' && 'Missions'}
                {currentPage === 'repos' && 'Repositories'}
                {currentPage === 'templates' && 'Templates'}
                {currentPage === 'integrations' && 'Integrations'}
              </h2>
              <p className="nav-page-sub">Browse and configure the workspace. Mission execution stays on Mission Control.</p>
            </div>
            <button type="button" className="ghost-button" onClick={() => handleNavigate('mission')}>
              Mission Control
            </button>
          </header>
          {currentPage === 'missions' && (
            <MissionsPage
              tasks={missionsRows}
              loading={missionsLoading}
              error={missionsError}
              onOpenMission={handleOpenMission}
              onCancelMission={handleCancelMission}
              onDeleteMission={handleDeleteMission}
            />
          )}
          {currentPage === 'repos' && (
            <RepositoriesPage
              repos={reposRows}
              loading={reposLoading}
              error={reposError}
              onUseRepo={(path) => {
                setRepoPath(path)
                handleNavigate('mission')
              }}
            />
          )}
          {currentPage === 'templates' && (
            <TemplatesPage packs={packs} repoPath={repoPath} loading={false} error={packsLoadError} />
          )}
          {currentPage === 'integrations' && (
            <IntegrationsPage keyStatus={keyStatus} onOpenSettings={() => setShowKeyModal(true)} />
          )}
        </section>
      ) : (
        <>
      <section className="mission-grid">
        <div className="mission-left">
          <ApprovalBanner
            pendingDiffs={view.pendingDiffs}
            blockedReason={view.latestBlockedReason}
            planApprovalNeeded={planApprovalNeeded}
            planSummary={view.latestPlanSummary}
            planItems={view.latestPlanItems}
            promptCorrectionNote={promptCorrectionNote}
            running={running}
            onApprove={handleApproveAll}
            onReject={handleRejectAll}
            onApprovePlan={handleApprovePlan}
            onCancelMission={task ? () => void handleCancelMission(task.id) : undefined}
            onViewDiff={() => setShowDiffs((value) => !value)}
            onOpenSettings={() => {
              setKeyMessage(view.latestBlockedReason || '')
              if (task && view.latestBlockedReason && isAuthBlocker(view.latestBlockedReason)) {
                setPendingRetryTaskId(task.id)
              }
              setShowKeyModal(true)
            }}
          />

          {showComposer && (
            <>
              <ModelCostPanel
                roles={roles}
                stageRuns={timeline?.stage_runs || []}
                modelOptions={modelOptions}
                modelSource={modelSource}
                compact
                onRolesChange={async (nextRoles) => {
                  const saved = await updateModelRoles(nextRoles)
                  setRoles(saved)
                }}
              />
              <SimpleTaskComposer
                repoPath={repoPath}
                prompt={prompt}
                intent={intent}
                deniedPaths={deniedPaths}
                attachments={attachments}
                enabledPhases={enabledPhases}
                running={running}
                onRepoPathChange={setRepoPath}
                onPromptChange={setPrompt}
                onIntentChange={setIntent}
                onDeniedPathsChange={setDeniedPaths}
                onAttachmentsChange={setAttachments}
                onEnabledPhasesChange={setEnabledPhases}
                onRun={handleRunTask}
                onScan={handleScan}
              />
            </>
          )}

          <MissionProgress view={view} />
          <RulesMissionPanel
            activeRules={view.activeRules}
            packs={packs}
            enabledPackIds={enabledPackIds}
            onTogglePack={togglePack}
            onSelfCheck={task ? handleSelfCheck : undefined}
            selfCheckDisabled={!task}
          />
        </div>

        <TaskDetailsPanel view={view} repoPath={repoPath} />
      </section>

      <MissionSummaryCards view={view} onViewPlan={() => setShowComposer(true)} onViewDiff={() => setShowDiffs((value) => !value)} />

      {showDiffs && (
        <ReviewChangesCard
          diffs={timeline?.diff_previews || []}
            hunks={timeline?.diff_hunks || []}
          running={running}
          onApproveAll={handleApproveAll}
          onRejectAll={handleRejectAll}
          onApprove={handleApprove}
          onReject={handleReject}
            onApproveHunk={handleApproveHunk}
            onRejectHunk={handleRejectHunk}
            onUpdateContent={handleUpdateDiffContent}
        />
      )}

      <VerificationCard
        tests={timeline?.test_runs || []}
        attempts={task?.debug_attempts || 0}
        maxAttempts={task?.max_debug_attempts || 3}
        onRunTests={handleRunTests}
      />

      <section className="advanced-stack mission-advanced">
        <AdvancedDrawer title="Rollback details">
          <RollbackPanel checkpoints={timeline?.git_checkpoints || []} onRollback={handleRollback} />
        </AdvancedDrawer>
        <AdvancedDrawer title="Model routing">
          <div className="key-status-row">
            <span>OpenRouter key: {keyStatus?.configured ? `configured from ${keyStatus.source}` : 'not configured'}</span>
            <button type="button" className="ghost-button" onClick={handleClearKey}>Clear saved key</button>
          </div>
          <p>Model routing is available in the mission setup panel before each run.</p>
        </AdvancedDrawer>
        <AdvancedDrawer title="Mission evidence">
          <div className="detail-section">
            <strong>Evidence</strong>
            <small>{timeline?.search_evidence?.length || 0} searches recorded</small>
            <small>{timeline?.diagnostics?.length || 0} diagnostics recorded</small>
          </div>
          <p className="nav-page-hint">Rule sources and pack toggles live in the Rules panel above. Run self-check from that panel when a mission is active.</p>
        </AdvancedDrawer>
        <AdvancedDrawer title="Project memory">
          <ProjectMemoryPanel profile={profile} memory={memory} onRemember={handleRemember} />
        </AdvancedDrawer>
        <AdvancedDrawer title="Raw stage logs">
          <StageTimeline task={task} stageRuns={timeline?.stage_runs || []} />
          <TestDebugPanel
            tests={timeline?.test_runs || []}
            debugAttempts={task?.debug_attempts || 0}
            maxDebugAttempts={task?.max_debug_attempts || 3}
            onRunTests={handleRunTests}
            onStop={async () => {
              if (!task) return
              const stopped = await cancelTask(task.id)
              setTask(stopped)
              await refreshTimeline(stopped.id)
            }}
          />
        </AdvancedDrawer>
      </section>
        </>
      )}
    </MissionShell>
  )
}

function latestCodeBlockedReason(timeline: TaskTimeline): string | null {
  const latestCode = [...timeline.stage_runs].reverse().find((run) => run.stage === 'CODE' && run.status === 'blocked')
  return typeof latestCode?.output?.blocked_reason === 'string' ? latestCode.output.blocked_reason : null
}

function latestPlanPassed(timeline: TaskTimeline | null): boolean {
  const latestPlan = [...(timeline?.stage_runs || [])].reverse().find((run) => run.stage === 'PLAN')
  return latestPlan?.status === 'passed'
}

function isAuthBlocker(message: string): boolean {
  return /key|auth|401|403|openrouter/i.test(message)
}

type ExtensionSuggestion = {
  original: string
  corrected: string
}

type PromptCorrectionResult = {
  prompt: string
  notes: string[]
  suggestions: ExtensionSuggestion[]
}

const HIGH_CONFIDENCE_EXTENSION_FIXES: Record<string, string> = {
  hmtl: 'html',
  htlm: 'html',
  jsson: 'json',
  xlxs: 'xlsx',
  xslx: 'xlsx',
}

const KNOWN_EXTENSIONS = ['css', 'csv', 'docx', 'html', 'js', 'json', 'jsx', 'md', 'pptx', 'py', 'ts', 'tsx', 'txt', 'xlsx']

function normalizePromptExtensions(input: string): PromptCorrectionResult {
  const notes: string[] = []
  const suggestions: ExtensionSuggestion[] = []
  let prompt = input
  const seen = new Set<string>()
  for (const match of input.matchAll(/\b[A-Za-z0-9_-]+\.([A-Za-z0-9]{2,8})\b/g)) {
    const token = match[0]
    const ext = match[1].toLowerCase()
    const highConfidence = HIGH_CONFIDENCE_EXTENSION_FIXES[ext]
    if (highConfidence) {
      const corrected = token.replace(new RegExp(`${ext}$`, 'i'), highConfidence)
      prompt = prompt.split(token).join(corrected)
      notes.push(`Corrected ${token} to ${corrected}.`)
      continue
    }
    if (KNOWN_EXTENSIONS.includes(ext)) continue
    const close = KNOWN_EXTENSIONS.find((known) => editDistanceAtMostOne(ext, known))
    if (close && !seen.has(token)) {
      seen.add(token)
      suggestions.push({ original: token, corrected: token.replace(new RegExp(`${ext}$`, 'i'), close) })
    }
  }
  return { prompt, notes, suggestions }
}

function editDistanceAtMostOne(a: string, b: string): boolean {
  if (a === b) return true
  if (Math.abs(a.length - b.length) > 1) return false
  let i = 0
  let j = 0
  let edits = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      i += 1
      j += 1
      continue
    }
    edits += 1
    if (edits > 1) return false
    if (a.length > b.length) i += 1
    else if (b.length > a.length) j += 1
    else {
      i += 1
      j += 1
    }
  }
  return edits + (a.length - i) + (b.length - j) <= 1
}

export default App
