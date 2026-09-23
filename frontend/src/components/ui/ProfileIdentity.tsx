import { ArrowUpRight, Flame, ShieldCheck, Sparkles, Trophy } from 'lucide-react'
import { Link } from 'react-router'

import { useCurrentUser, useGamificationSummary } from '../../api/queries'
import { AchievementEmblem } from '../gamification/AchievementEmblem'
import { Skeleton } from './Skeleton'
import { TiltSurface } from './TiltSurface'
import { UserAvatar } from './UserAvatar'

export function ProfileIdentity() {
  const user = useCurrentUser()
  const summary = useGamificationSummary()
  const earned = (summary.data?.badges ?? []).filter(badge => badge.earned)
  const progress = summary.data && summary.data.xp_for_next_level > 0
    ? Math.max(0, Math.min(100, summary.data.xp_into_level / summary.data.xp_for_next_level * 100)) : 0

  return <div className="profile-showcase">
    <TiltSurface className="profile-identity">
      <section aria-label="Your profile card">
        <div className="profile-card-top"><span>NEURAL LOG / YOUR STORY</span>{user.data?.is_admin && <span><ShieldCheck size={13} aria-hidden="true" /> Admin</span>}</div>
        <div className="profile-avatar-stage"><span className="profile-orbit" aria-hidden="true" /><span className="profile-orbit profile-orbit-offset" aria-hidden="true" /><UserAvatar username={user.data?.username} className="profile-avatar" /><Sparkles className="profile-spark" size={24} aria-hidden="true" /></div>
        {user.isPending ? <Skeleton className="mx-auto h-9 w-40" /> : <h2>{user.data?.username ?? 'Your profile'}</h2>}
        <p className="profile-path">{user.data?.selected_path || 'A little progress, every day.'}</p>
        {summary.isPending ? <Skeleton className="mt-6 h-16 w-full" /> : summary.data ? <>
          <div className="profile-level"><span><Sparkles size={14} aria-hidden="true" /> Level {summary.data.level}</span><span>{summary.data.xp_into_level} / {summary.data.xp_for_next_level} XP</span></div>
          <div className="profile-progress" role="progressbar" aria-label="Profile level progress" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${progress}%` }} /></div>
          <div className="profile-card-footer"><span><Flame size={15} aria-hidden="true" /> {summary.data.current_streak} day streak</span><span><Trophy size={15} aria-hidden="true" /> {earned.length} collected</span></div>
        </> : <p className="mt-6 text-meta text-ink-muted">Your progress is unavailable right now.</p>}
      </section>
    </TiltSurface>
    <section className="profile-collection" aria-label="Achievement highlights">
      <p className="story-eyebrow">Collected along the way</p>
      <h2>More than a set of numbers.</h2>
      <p>Your meals, movement, and moments of rest build a story that is yours. These are a few of its milestones.</p>
      {summary.isPending ? <Skeleton className="h-32 w-full" /> : summary.isError ? <p>Your collection is unavailable right now. Open achievements to try again.</p> : earned.length ? <div className="profile-medals">
        {earned.slice(-3).map(badge => <Link key={badge.code} to="/achievements" className="profile-medal" aria-label={`View ${badge.name} in achievements`}><AchievementEmblem achievement={badge} compact /><span>{badge.name}</span></Link>)}
      </div> : <div className="profile-first-badge"><Trophy size={28} aria-hidden="true" /><p>Your collection starts with a first step.<br />Log a day, a meal, or a workout to begin.</p></div>}
      <Link to="/achievements" className="story-link">Explore your achievements <ArrowUpRight size={16} aria-hidden="true" /></Link>
    </section>
  </div>
}
