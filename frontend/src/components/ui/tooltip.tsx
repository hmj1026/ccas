import { cn } from '@/lib/utils'

function Tooltip({
  className,
  ...props
}: React.ComponentProps<'span'>) {
  return (
    <span
      data-slot="tooltip"
      className={cn('group/tooltip relative inline-flex', className)}
      {...props}
    />
  )
}

function TooltipTrigger({
  className,
  type = 'button',
  ...props
}: React.ComponentProps<'button'>) {
  return (
    <button
      data-slot="tooltip-trigger"
      type={type}
      className={className}
      {...props}
    />
  )
}

function TooltipContent({
  className,
  ...props
}: React.ComponentProps<'span'>) {
  return (
    <span
      data-slot="tooltip-content"
      className={cn(
        'pointer-events-none absolute right-0 top-full z-50 mt-1 hidden w-max max-w-xs rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md group-focus-within/tooltip:block group-hover/tooltip:block',
        className,
      )}
      {...props}
    />
  )
}

export { Tooltip, TooltipContent, TooltipTrigger }
