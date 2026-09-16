import { Link } from 'react-router'
import { m } from 'motion/react'
import { ArrowRight, Sparkles, X } from 'lucide-react'

import { useOnboarding, useOnboardingPrompt } from '../../api/queries'
import { Button } from '../ui/Button'
import { rise, reducedVariants } from '../../lib/motion'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'

/**
 * The only thing that asks anyone to run the first-run flow.
 *
 * Onboarding is non-blocking, so this is the whole prompt - no redirect, no
 * modal, no interstitial. It shows only while the flow is neither finished nor
 * declined, and `should_prompt` is computed server-side so every client agrees
 * rather than each re-deriving the rule.
 *
 * Dismissing is permanent and says so. A prompt that reappears after being
 * declined is not a prompt, and the honest way to offer an escape hatch is to
 * leave the flow reachable from Profile, which is where someone who changes
 * their mind will actually go looking.
 */
export function SetupBanner() {
  const query = useOnboarding()
  const { dismiss } = useOnboardingPrompt()
  const reduced = usePrefersReducedMotion()

  if (!query.data?.should_prompt) return null

  const answered = query.data.step
  const total = query.data.steps.length
  const resuming = answered > 0

  return (
    <m.div
      variants={reduced ? reducedVariants : rise}
      initial="hidden"
      animate="visible"
      className="flex min-w-0 flex-wrap items-center gap-4 rounded-lg border border-brand/30 bg-brand/8 px-5 py-4"
    >
      <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-brand text-white">
        <Sparkles size={18} aria-hidden />
      </span>

      <div className="min-w-0 flex-1">
        <p className="text-label font-semibold text-ink">
          {resuming ? `Finish setting up — ${total - answered} steps left` : 'Finish setting up'}
        </p>
        <p className="text-meta text-ink-muted">
          Your height, weight and targets are what every score is measured against. Without
          them the app estimates, and says so.
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <Button
          variant="ghost"
          icon={X}
          loading={dismiss.isPending}
          onClick={() => dismiss.mutate()}
          title="You can still start it from Profile"
        >
          Not now
        </Button>
        <Link to="/welcome">
          <Button variant="primary" icon={ArrowRight} iconPosition="end">
            {resuming ? 'Resume' : 'Start'}
          </Button>
        </Link>
      </div>
    </m.div>
  )
}
