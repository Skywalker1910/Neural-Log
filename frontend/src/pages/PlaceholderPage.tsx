import { Hammer } from 'lucide-react'

import { PageHeader } from '../components/layout/PageHeader'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import type { NavSection } from '../navigation'

/**
 * Honest placeholder for a section whose phase hasn't landed yet. Phase 1 ships
 * the shell; each later phase replaces one of these with the real workspace.
 */
export function PlaceholderPage({ section }: { section: NavSection }) {
  return (
    <>
      <PageHeader
        title={section.label}
        description={section.blurb}
        icon={section.icon}
        accent={section.accent}
        actions={<Badge tone="neutral">Phase {section.phase}</Badge>}
      />

      <Card>
        <EmptyState
          icon={Hammer}
          title="Not built yet"
          description={
            <>
              This workspace arrives in phase {section.phase} of the redesign. The daily
              checklist you use today is still running at{' '}
              <a href="/" className="text-brand underline underline-offset-2">
                the classic dashboard
              </a>
              .
            </>
          }
        />
      </Card>
    </>
  )
}
