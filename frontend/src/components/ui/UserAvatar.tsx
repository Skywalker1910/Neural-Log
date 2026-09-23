import { cn } from '../../lib/cn'

export function UserAvatar({ username, className }: { username?: string; className?: string }) {
  const words = username?.trim().split(/\s+/).filter(Boolean) ?? []
  const initials = (words.length > 1
    ? `${Array.from(words[0])[0]}${Array.from(words[words.length - 1])[0]}`
    : Array.from(words[0] ?? '').slice(0, 2).join('')).toLocaleUpperCase() || 'NL'
  return <span className={cn('user-avatar', className)} aria-hidden="true">{initials}</span>
}
