import { Progress as ProgressPrimitive } from '@base-ui/react/progress'

import { cn } from '@/lib/utils'

function Progress({
  className,
  value = 0,
  ...props
}: ProgressPrimitive.Root.Props) {
  const normalized =
    value === null ? null : Math.max(0, Math.min(100, Number(value)))

  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      value={normalized}
      className={cn(
        'relative h-2 w-full overflow-hidden rounded-full bg-muted',
        className,
      )}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        className="h-full w-full flex-1 bg-primary transition-transform"
        style={{
          transform:
            normalized === null
              ? 'translateX(-35%)'
              : `translateX(-${100 - normalized}%)`,
        }}
      />
    </ProgressPrimitive.Root>
  )
}

export { Progress }
