import { Lock, ShieldCheck, Sparkles } from 'lucide-react'

import type { Badge } from '../../api/types'
import { TiltSurface } from '../ui/TiltSurface'
import { AchievementEmblem } from './AchievementEmblem'

export function AchievementCard({ achievement }: { achievement: Badge }) {
  const progress = Math.max(0, Math.min(100, Math.round(achievement.progress * 100)))

  return <TiltSurface className={`achievement-card tier-${achievement.tier}${achievement.earned ? ' achievement-earned' : ' achievement-locked'}`}>
    <article aria-label={achievement.name}>
      <div className="achievement-topline"><span>{achievement.tier} edition</span><span><Sparkles size={12} aria-hidden="true" /> {achievement.xp_reward} XP</span></div>
      <div className="achievement-art">
        <span className="achievement-orbit" aria-hidden="true" />
        <AchievementEmblem achievement={achievement} />
        {!achievement.earned && <span className="achievement-lock"><Lock size={12} aria-hidden="true" /> Locked</span>}
      </div>
      <div className="achievement-copy"><h3>{achievement.name}</h3><p>{achievement.description}</p></div>
      <footer className="achievement-footer">
        {achievement.earned ? <span className="achievement-unlocked"><ShieldCheck size={15} aria-hidden="true" /> In your collection</span> : <>
          <div className="achievement-progress-label"><span>{achievement.current.toLocaleString()} / {achievement.threshold.toLocaleString()}</span><span>{progress}%</span></div>
          <div className="achievement-progress" role="progressbar" aria-label={`${achievement.name} progress`} aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
            <span style={{ width: `${progress}%` }} />
          </div>
        </>}
      </footer>
    </article>
  </TiltSurface>
}
