import { useMemo, useState } from 'react'
import { Link, Navigate } from 'react-router'
import {
  Activity,
  ArrowLeft,
  Ban,
  Bot,
  Check,
  Copy,
  Database,
  HardDriveDownload,
  KeyRound,
  Plus,
  RefreshCw,
  ShieldCheck,
  ShieldOff,
  Ticket,
  Trash2,
  UserCheck,
  Users,
  X,
} from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from '../api/client'
import {
  queryKeys,
  useAdminAiUsage,
  useAdminInviteCodes,
  useAdminOverview,
  useAdminUsers,
  useCurrentUser,
} from '../api/queries'
import type { AdminUser, BackupStatus, InviteCode } from '../api/types'
import { PageHeader } from '../components/layout/PageHeader'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ConfirmationDialog } from '../components/ui/ConfirmationDialog'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Field, TextInput } from '../components/ui/Field'
import { Modal } from '../components/ui/Modal'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { StatCard } from '../components/ui/StatCard'

type AdminAction = 'role' | 'status' | 'delete'

interface PendingAction {
  type: AdminAction
  user: AdminUser
}

function dateLabel(value: string | null): string {
  if (!value) return 'Not yet'
  const [year, month, day] = value.slice(0, 10).split('-').map(Number)
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
    .format(new Date(year, month - 1, day))
}

function actionCopy(action: PendingAction): { title: string; description: string; confirmLabel: string; destructive: boolean } {
  if (action.type === 'delete') {
    return {
      title: `Delete ${action.user.username}?`,
      description: 'This permanently removes the account and every log, goal, habit, workout, meal, and learning record it owns.',
      confirmLabel: 'Delete account',
      destructive: true,
    }
  }

  if (action.type === 'status') {
    return action.user.is_active
      ? {
          title: `Suspend ${action.user.username}?`,
          description: 'Their existing sessions will stop working. Their history stays intact and you can resume the account later.',
          confirmLabel: 'Suspend account',
          destructive: true,
        }
      : {
          title: `Resume ${action.user.username}?`,
          description: 'They can sign in and resume using the app immediately.',
          confirmLabel: 'Resume account',
          destructive: false,
        }
  }

  return action.user.is_admin
    ? {
        title: `Remove admin access from ${action.user.username}?`,
        description: 'They will keep their account and history, but lose access to this control room.',
        confirmLabel: 'Remove admin',
        destructive: true,
      }
    : {
        title: `Make ${action.user.username} an admin?`,
        description: 'They will be able to manage accounts, reset passwords, suspend access, and remove user data.',
        confirmLabel: 'Make admin',
        destructive: false,
      }
}

function UserManagement() {
  const users = useAdminUsers()
  const queryClient = useQueryClient()
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null)
  const [passwordUser, setPasswordUser] = useState<AdminUser | null>(null)
  const [newPassword, setNewPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers })
    void queryClient.invalidateQueries({ queryKey: queryKeys.adminOverview })
  }

  const executeAction = async () => {
    if (!pendingAction) return
    setBusy(true)
    setNotice(null)

    const { type, user } = pendingAction
    const path = type === 'role'
      ? `/api/admin/users/${user.id}/toggle-admin`
      : type === 'status'
        ? `/api/admin/users/${user.id}/toggle-active`
        : `/api/admin/users/${user.id}`

    try {
      if (type === 'delete') {
        await api.delete(path)
      } else {
        await api.post(path)
      }
      setNotice({
        tone: 'success',
        text: type === 'delete'
          ? `${user.username}'s account was deleted.`
          : type === 'status'
            ? `${user.username}'s account was ${user.is_active ? 'suspended' : 'resumed'}.`
            : `${user.username}'s admin access was ${user.is_admin ? 'removed' : 'granted'}.`,
      })
      setPendingAction(null)
      refresh()
    } catch (error) {
      setNotice({
        tone: 'error',
        text: error instanceof ApiError ? error.message : 'That account change could not be completed.',
      })
    } finally {
      setBusy(false)
    }
  }

  const resetPassword = async () => {
    if (!passwordUser) return
    setBusy(true)
    setNotice(null)
    try {
      await api.post(`/api/admin/users/${passwordUser.id}/reset-password`, { new_password: newPassword })
      setNotice({ tone: 'success', text: `Password reset for ${passwordUser.username}.` })
      setPasswordUser(null)
      setNewPassword('')
    } catch (error) {
      setNotice({
        tone: 'error',
        text: error instanceof ApiError ? error.message : 'The password could not be reset.',
      })
    } finally {
      setBusy(false)
    }
  }

  const columns = useMemo<Column<AdminUser>[]>(() => [
    {
      key: 'account',
      header: 'Account',
      render: (user) => (
        <div className="min-w-[10rem]">
          <p className="font-medium text-ink">{user.username}</p>
          <p className="mt-0.5 truncate text-meta text-ink-subtle">{user.email || 'No email provided'}</p>
        </div>
      ),
    },
    {
      key: 'access',
      header: 'Access',
      hideBelow: 'sm',
      render: (user) => (
        <div className="flex flex-wrap gap-1.5">
          <Badge tone={user.is_admin ? 'brand' : 'neutral'}>{user.is_admin ? 'Admin' : 'Member'}</Badge>
          <Badge tone={user.is_active ? 'success' : 'danger'}>{user.is_active ? 'Active' : 'Suspended'}</Badge>
        </div>
      ),
    },
    {
      key: 'activity',
      header: 'Activity',
      hideBelow: 'md',
      render: (user) => (
        <div className="min-w-[8rem] text-meta text-ink-muted">
          <p className="tabular text-label text-ink">{user.logged_days} logged days</p>
          <p className="mt-0.5">Last: {dateLabel(user.last_logged_on)}</p>
        </div>
      ),
    },
    {
      key: 'progress',
      header: 'Progress',
      align: 'right',
      hideBelow: 'md',
      render: (user) => (
        <div className="min-w-[5rem]">
          <p className="tabular text-label text-ink">{user.total_xp.toLocaleString()} XP</p>
          <p className="mt-0.5 text-meta text-ink-subtle">{user.activity_count} entries</p>
        </div>
      ),
    },
    {
      key: 'actions',
      header: <span className="sr-only">Actions</span>,
      align: 'right',
      render: (user) => (
        <div className="flex min-w-[15rem] justify-end gap-1.5">
          <Button size="sm" variant="ghost" icon={KeyRound} onClick={() => setPasswordUser(user)}>
            Password
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={user.is_admin ? ShieldOff : ShieldCheck}
            onClick={() => setPendingAction({ type: 'role', user })}
          >
            {user.is_admin ? 'Demote' : 'Promote'}
          </Button>
          <Button
            size="sm"
            variant={user.is_active ? 'ghost' : 'secondary'}
            icon={user.is_active ? Ban : UserCheck}
            onClick={() => setPendingAction({ type: 'status', user })}
          >
            {user.is_active ? 'Suspend' : 'Resume'}
          </Button>
          <Button
            size="sm"
            variant="danger"
            icon={Trash2}
            onClick={() => setPendingAction({ type: 'delete', user })}
          >
            Delete
          </Button>
        </div>
      ),
    },
  ], [])

  return (
    <>
      <Card
        title="People"
        subtitle="Roles, access, recovery, and permanent deletion. Account changes apply immediately."
        icon={Users}
        accent="brand"
        action={
          <Button size="sm" variant="secondary" icon={RefreshCw} loading={users.isFetching} onClick={refresh}>
            Refresh
          </Button>
        }
        bodyClassName="px-3 py-2 sm:px-4"
      >
        {notice && (
          <p className={notice.tone === 'success' ? 'mb-2 px-2 text-label text-success' : 'mb-2 px-2 text-label text-danger'}>
            {notice.text}
          </p>
        )}
        <QueryBoundary query={users} loading={<SkeletonGrid />}>
          {(data) => <DataTable columns={columns} rows={data} rowKey={(user) => user.id} caption="User accounts" />}
        </QueryBoundary>
      </Card>

      <ConfirmationDialog
        open={pendingAction !== null}
        onCancel={() => !busy && setPendingAction(null)}
        onConfirm={() => void executeAction()}
        busy={busy}
        {...(pendingAction ? actionCopy(pendingAction) : {
          title: '', description: '', confirmLabel: '', destructive: false,
        })}
      />

      <Modal
        open={passwordUser !== null}
        onClose={() => !busy && setPasswordUser(null)}
        title={passwordUser ? `Reset ${passwordUser.username}'s password` : 'Reset password'}
        description="Set a temporary password, then send it through a private channel."
        size="sm"
        footer={
          <>
            <Button variant="ghost" disabled={busy} onClick={() => setPasswordUser(null)}>Cancel</Button>
            <Button variant="primary" loading={busy} disabled={newPassword.length < 6} onClick={() => void resetPassword()}>
              Reset password
            </Button>
          </>
        }
      >
        <Field label="New temporary password" hint="At least six characters">
          {(id) => (
            <TextInput
              id={id}
              type="password"
              autoComplete="new-password"
              minLength={6}
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
          )}
        </Field>
      </Modal>
    </>
  )
}

/**
 * Whether the backups are actually happening.
 *
 * This is here rather than in a log because of how backups fail: silently. The
 * timer stops firing, credentials expire, a bucket policy changes - and nothing
 * anywhere says so until the day somebody needs a restore. Putting the age on
 * the page an administrator already opens turns a silent failure into a visible
 * one, which is the whole of the fix.
 *
 * Three states, deliberately distinguished:
 *
 * - **unknown** - no status file. A fresh instance, not a fault. Saying "FAILED"
 *   at somebody on their first afternoon teaches them to ignore the indicator.
 * - **on the instance only** - backups run and succeed, on the same disk as the
 *   database. Real protection against deleting the wrong thing; none at all
 *   against losing the instance. A warning, not a pass.
 * - **off-instance** - the only one that is actually a backup.
 */
function BackupHealth({ backup }: { backup: BackupStatus }) {
  if (!backup.known) {
    return (
      <Badge tone="neutral">
        Backups: {backup.reason ?? 'unknown'}
      </Badge>
    )
  }

  const age =
    backup.age_hours === null || backup.age_hours === undefined
      ? 'unknown age'
      : backup.age_hours < 1
        ? 'just now'
        : backup.age_hours < 48
          ? `${Math.round(backup.age_hours)}h ago`
          : `${Math.round(backup.age_hours / 24)}d ago`

  if (!backup.ok) {
    return <Badge tone="danger">Last backup FAILED — {age}</Badge>
  }

  if (backup.stale) {
    return <Badge tone="danger">Backup overdue — last succeeded {age}</Badge>
  }

  return (
    <>
      <Badge tone={backup.offsite ? 'success' : 'warning'}>
        Backup: {age}
        {backup.offsite ? '' : ', on this instance only'}
      </Badge>
      {backup.local_copies ? (
        <Badge tone="neutral">{backup.local_copies} local snapshots</Badge>
      ) : null}
    </>
  )
}

/**
 * What the assistant costs.
 *
 * Its own card rather than a line on the system status, because this is the
 * first thing in the app that spends money per use and it is the number that
 * decides whether the feature stays.
 *
 * Every figure says "estimated" and means it. The dollars are computed locally
 * from configurable rates so a spend cap can be enforced *before* a request -
 * which the provider's billing, lagging and organisation-wide, cannot do. When
 * the two disagree, the invoice is right and the rates want correcting.
 */
function AssistantSpend() {
  const query = useAdminAiUsage(30)
  const data = query.data

  if (!data || (!data.configured && data.totals.calls === 0)) return null

  const money = (value: number) =>
    value < 0.01 && value > 0 ? '<$0.01' : `$${value.toFixed(2)}`

  return (
    <Card
      title="Assistant spend"
      subtitle="Last 30 days, estimated from configured rates"
      icon={Bot}
      accent="brand"
    >
      <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
        {[
          ['Estimated cost', money(data.totals.estimated_cost_usd)],
          ['Requests', data.totals.calls.toLocaleString()],
          ['Input tokens', data.totals.input_tokens.toLocaleString()],
          ['Output tokens', data.totals.output_tokens.toLocaleString()],
        ].map(([label, value]) => (
          <div key={label}>
            <dt className="text-meta text-ink-subtle">{label}</dt>
            <dd className="mt-1 tabular text-section text-ink">{value}</dd>
          </div>
        ))}
      </div>

      {data.by_feature.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {data.by_feature.map((row) => (
            <Badge key={row.feature} tone="neutral">
              {row.feature}: {money(row.estimated_cost_usd)} over {row.calls}
            </Badge>
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Badge tone="info">{data.chat_model}</Badge>
        <Badge tone="neutral">
          ${data.monthly_budget_usd.toFixed(2)}/month cap per account
        </Badge>
        {data.totals.failures > 0 && (
          <Badge tone="danger">{data.totals.failures} failed</Badge>
        )}
        {!data.configured && <Badge tone="warning">No API key set</Badge>}
      </div>

      <p className="mt-3 text-meta text-ink-subtle">
        Estimated, not billed. These figures exist so a request can be refused before
        it is made; your provider invoice is the authority on what was charged.
      </p>
    </Card>
  )
}

function InviteCodeManagement() {
  const codes = useAdminInviteCodes()
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState<number | null>(null)
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)

  const refresh = () => void queryClient.invalidateQueries({ queryKey: queryKeys.adminInviteCodes })

  const create = async () => {
    setBusy(true)
    setNotice(null)
    try {
      const result = await api.post<{ code: string }>('/api/admin/invite-codes', { label: label || undefined })
      setNotice({ tone: 'success', text: `Code created: ${result.code}` })
      setCreating(false)
      setLabel('')
      refresh()
    } catch (error) {
      setNotice({ tone: 'error', text: error instanceof ApiError ? error.message : 'Could not create code.' })
    } finally {
      setBusy(false)
    }
  }

  const revoke = async (id: number) => {
    setNotice(null)
    try {
      await api.post(`/api/admin/invite-codes/${id}/revoke`)
      setNotice({ tone: 'success', text: 'Code revoked.' })
      refresh()
    } catch (error) {
      setNotice({ tone: 'error', text: error instanceof ApiError ? error.message : 'Could not revoke code.' })
    }
  }

  const copyCode = (code: InviteCode) => {
    void navigator.clipboard.writeText(code.code)
    setCopied(code.id)
    setTimeout(() => setCopied(null), 2000)
  }

  const columns = useMemo<Column<InviteCode>[]>(() => [
    {
      key: 'code',
      header: 'Code',
      render: (row) => (
        <div className="flex items-center gap-2">
          <code className="text-label text-ink">{row.code}</code>
          <button
            type="button" className="text-ink-subtle hover:text-ink"
            onClick={() => copyCode(row)} aria-label="Copy code"
          >
            {copied === row.id ? <Check size={14} /> : <Copy size={14} />}
          </button>
        </div>
      ),
    },
    {
      key: 'label',
      header: 'Label',
      hideBelow: 'sm',
      render: (row) => <span className="text-ink-muted">{row.label || '—'}</span>,
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => row.used_by
        ? <Badge tone="success">Used by {row.used_by}</Badge>
        : row.revoked
          ? <Badge tone="danger">Revoked</Badge>
          : <Badge tone="info">Available</Badge>,
    },
    {
      key: 'created',
      header: 'Created',
      hideBelow: 'md',
      render: (row) => (
        <span className="text-meta text-ink-muted">
          {dateLabel(row.created_at)} by {row.created_by}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (row) => !row.used_by && !row.revoked ? (
        <Button size="sm" variant="danger" icon={X} onClick={() => void revoke(row.id)}>
          Revoke
        </Button>
      ) : null,
    },
  ], [copied])

  return (
    <Card
      title="Invite codes"
      subtitle="Generate single-use codes to share with new users"
      icon={Ticket}
      accent="brand"
      action={
        <Button size="sm" variant="primary" icon={Plus} onClick={() => setCreating(true)}>
          New code
        </Button>
      }
      bodyClassName="px-3 py-2 sm:px-4"
    >
      {notice && (
        <p className={notice.tone === 'success' ? 'mb-2 px-2 text-label text-success' : 'mb-2 px-2 text-label text-danger'}>
          {notice.text}
        </p>
      )}
      <QueryBoundary query={codes} loading={<SkeletonGrid />}>
        {(data) => data.length === 0
          ? <p className="px-2 py-4 text-label text-ink-subtle">No invite codes yet. Create one to invite a new user.</p>
          : <DataTable columns={columns} rows={data} rowKey={(row) => row.id} caption="Invite codes" />
        }
      </QueryBoundary>

      <Modal
        open={creating}
        onClose={() => !busy && setCreating(false)}
        title="Create invite code"
        description="The code will be generated automatically. Add an optional label to remember who it's for."
        size="sm"
        footer={
          <>
            <Button variant="ghost" disabled={busy} onClick={() => setCreating(false)}>Cancel</Button>
            <Button variant="primary" loading={busy} onClick={() => void create()}>Create code</Button>
          </>
        }
      >
        <Field label="Label (optional)" hint="e.g. 'For Alice'">
          {(id) => (
            <TextInput
              id={id} value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder="Who is this code for?"
            />
          )}
        </Field>
      </Modal>
    </Card>
  )
}

export function Admin() {
  const currentUser = useCurrentUser()
  const overview = useAdminOverview()

  if (currentUser.data && !currentUser.data.is_admin) return <Navigate to="/" replace />

  return (
    <div className="admin-shell">
      <header className="admin-topbar">
        <Link to="/" className="admin-back">
          <ArrowLeft size={16} aria-hidden /> Back to app
        </Link>
        <span className="admin-title">
          <ShieldCheck size={18} aria-hidden /> Admin
        </span>
        {currentUser.data && (
          <span className="text-meta text-ink-subtle">{currentUser.data.username}</span>
        )}
      </header>

      <main id="main" className="admin-content" data-page-theme="admin">
        <PageHeader
          title="Admin"
          description="The operational view of Neural Log: people, usage, and the safeguards around both."
          icon={ShieldCheck}
          accent="brand"
        />

        <QueryBoundary query={overview} loading={<SkeletonGrid />}>
          {(data) => (
            <RevealGroup className="flex flex-col gap-4" step={0.05}>
              <Reveal>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <StatCard label="Accounts" value={data.accounts.total} icon={Users} accent="brand" hint={`${data.accounts.active} active`} />
                  <StatCard label="Active this week" value={data.accounts.active_this_week} icon={UserCheck} accent="lifestyle" hint="Logged a daily check-in" />
                  <StatCard label="Logged days" value={data.logging.days.toLocaleString()} icon={Activity} accent="discipline" hint={`${data.logging.activities.toLocaleString()} classic entries`} />
                  <StatCard label="Active admins" value={data.accounts.admins} icon={ShieldCheck} accent="brand" hint="At least one is always protected" />
                </div>
              </Reveal>

              <Reveal>
                <div className="grid gap-4 xl:grid-cols-[1.35fr_0.65fr]">
                  <Card title="Workspace pulse" subtitle="Records currently stored across the app" icon={Activity} accent="learning">
                    <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-5">
                      {[
                        ['Workouts', data.features.workouts],
                        ['Meals', data.features.meals],
                        ['Study sessions', data.features.learning_sessions],
                        ['Goals', data.features.goals],
                        ['Personal habits', data.features.habits],
                      ].map(([label, value]) => (
                        <div key={label as string}>
                          <dt className="text-meta text-ink-subtle">{label}</dt>
                          <dd className="mt-1 tabular text-section text-ink">{Number(value).toLocaleString()}</dd>
                        </div>
                      ))}
                    </dl>
                  </Card>

                  <Card title="System status" subtitle="Read-only production checks" icon={Database} accent="recovery">
                    <div className="flex flex-wrap gap-2">
                      <Badge tone={data.database_integrity === 'ok' ? 'success' : 'danger'}>
                        Database: {data.database_integrity === 'ok' ? 'Healthy' : data.database_integrity}
                      </Badge>
                      <Badge tone="info">Registration: {data.registration_mode}</Badge>
                      <Badge tone="neutral">
                        v{data.version}
                        {data.commit && data.commit !== 'unknown' && (
                          <span className="tabular ml-1 text-ink-subtle">
                            {data.commit.slice(0, 7)}
                          </span>
                        )}
                      </Badge>
                      <Badge tone="neutral">{data.accounts.active} accounts enabled</Badge>
                      <BackupHealth backup={data.backup} />
                    </div>

                    {data.backup.known && !data.backup.offsite && (
                      <p className="mt-3 flex items-start gap-2 text-meta text-ink-subtle">
                        <HardDriveDownload size={14} className="mt-0.5 shrink-0" aria-hidden />
                        <span>
                          Snapshots are being written next to the database, so losing the instance
                          loses both. See <code>docs/BACKUPS.md</code> to send them to S3.
                        </span>
                      </p>
                    )}
                  </Card>
                </div>
              </Reveal>

              <Reveal><InviteCodeManagement /></Reveal>

              <Reveal><AssistantSpend /></Reveal>

              <Reveal><UserManagement /></Reveal>
            </RevealGroup>
          )}
        </QueryBoundary>
      </main>
    </div>
  )
}
