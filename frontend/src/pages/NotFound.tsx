import { useNavigate } from 'react-router'
import { Compass } from 'lucide-react'

import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'

export function NotFound() {
  const navigate = useNavigate()

  return (
    <Card>
      <EmptyState
        icon={Compass}
        title="Page not found"
        description="That route doesn't exist in Neural Log."
        action={
          <Button variant="primary" onClick={() => void navigate('/')}>
            Back to Home
          </Button>
        }
      />
    </Card>
  )
}
