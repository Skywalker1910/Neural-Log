import { ArrowRight, ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router'

import type { HomeSummary } from '../../api/types'
import { PageHeader } from '../layout/PageHeader'

export function JourneyHero({ today, daysLogged }: { today?: HomeSummary['today']; daysLogged?: number }) {
  return <PageHeader
    storyKind="journey"
    title={daysLogged === undefined ? 'Your everyday, a little more intentional' : daysLogged > 0 ? 'Small steps. A story worth building.' : 'Every good story starts somewhere.'}
    description={today?.logged ? 'You made space for yourself today. Keep the momentum, or take a moment to look back.' : 'Make a little room for movement, a meal you love, or a quiet moment. Start with what feels right today.'}
    actions={<>
      <Link to="/today" className="app-button button-primary inline-flex items-center gap-2 rounded-md border px-4 text-meta font-medium">{today?.logged ? 'Continue your day' : 'Start your day'} <ArrowRight size={16} aria-hidden="true" /></Link>
      <Link to="/feed" className="app-button button-secondary inline-flex items-center gap-2 rounded-md border px-4 text-meta font-medium">Your weekly story <ArrowUpRight size={16} aria-hidden="true" /></Link>
    </>}
  />
}
