import { ArrowRight, ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router'

import type { HomeSummary } from '../../api/types'
import { LifeIllustration } from './LifeIllustration'

export function JourneyHero({ today, daysLogged }: { today: HomeSummary['today']; daysLogged: number }) {
  return <section className="journey-hero">
    <div className="journey-copy"><p className="story-eyebrow">Your everyday, a little more intentional</p>
      <h2>{daysLogged > 0 ? 'Small steps. A story worth building.' : 'Every good story starts somewhere.'}</h2>
      <p>{today.logged ? 'You made space for yourself today. Keep the momentum, or take a moment to look back.' : 'Make a little room for movement, a meal you love, or a quiet moment. Start with what feels right today.'}</p>
      <div className="journey-actions"><Link to="/today" className="story-action">{today.logged ? 'Continue your day' : 'Start your day'} <ArrowRight size={16} aria-hidden="true" /></Link><Link to="/feed" className="story-link">Your weekly story <ArrowUpRight size={16} aria-hidden="true" /></Link></div>
    </div>
    <div className="journey-art"><LifeIllustration kind="journey" /><span>One day at a time.</span></div>
  </section>
}
