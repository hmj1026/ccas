/**
 * SelectField -- 收斂專案內原生 <select> 的高階下拉元件。
 *
 * 包裝 @base-ui/react Select，提供與既有表單一致的外觀與無障礙行為：
 * - 有 `label` 時渲染 flex-col 標籤並以 htmlFor/id 與觸發器關聯；
 *   無 `label` 時改用 `aria-label`（兩者擇一，皆無則由呼叫端負責標示）。
 * - 以 `options` 描述選項；`items` 對應表讓觸發器顯示選中項的文字標籤。
 *
 * 不直接編輯 base-ui primitive；如需更細緻控制請改用 @base-ui/react/select。
 */
import { Select as SelectPrimitive } from '@base-ui/react/select'
import { Check, ChevronsUpDown } from 'lucide-react'
import { useId, useMemo } from 'react'
import { cn } from '@/lib/utils'

export interface SelectOption {
  readonly value: string
  readonly label: string
  readonly disabled?: boolean
}

interface SelectFieldProps {
  readonly value: string
  readonly onValueChange: (value: string) => void
  readonly options: readonly SelectOption[]
  /** 顯式關聯 id；省略時自動以 useId 產生。 */
  readonly id?: string
  /** 可見標籤文字；提供時渲染 <label htmlFor>。 */
  readonly label?: string
  /** 無可見標籤時的無障礙名稱。 */
  readonly 'aria-label'?: string
  /** 無選中值時的佔位文字（當選項含空值項時通常不需要）。 */
  readonly placeholder?: string
  readonly disabled?: boolean
  readonly required?: boolean
  readonly name?: string
  /** 套用於外層容器（僅 label 模式）。 */
  readonly className?: string
  /** 套用於觸發按鈕；用於調整高度／寬度等。 */
  readonly triggerClassName?: string
}

const TRIGGER_BASE =
  'flex h-9 items-center justify-between gap-2 rounded-lg border border-input bg-background px-3 text-sm ' +
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring ' +
  'disabled:cursor-not-allowed disabled:opacity-50'

export function SelectField({
  value,
  onValueChange,
  options,
  id,
  label,
  'aria-label': ariaLabel,
  placeholder,
  disabled,
  required,
  name,
  className,
  triggerClassName,
}: SelectFieldProps) {
  const generatedId = useId()
  const fieldId = id ?? generatedId
  // Maps value → label so SelectPrimitive.Value renders the selected label
  // text. Memoised so SelectRoot does not see a new items reference each render.
  const items = useMemo(
    () => Object.fromEntries(options.map((o) => [o.value, o.label])),
    [options],
  )

  const trigger = (
    <SelectPrimitive.Trigger
      id={fieldId}
      data-slot="select-trigger"
      disabled={disabled}
      aria-label={label ? undefined : ariaLabel}
      className={cn(TRIGGER_BASE, triggerClassName)}
    >
      <SelectPrimitive.Value placeholder={placeholder} />
      <SelectPrimitive.Icon className="text-muted-foreground">
        <ChevronsUpDown className="size-4" aria-hidden="true" />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  )

  return (
    <SelectPrimitive.Root
      items={items}
      value={value}
      onValueChange={(next) => onValueChange(next ?? '')}
      name={name}
      disabled={disabled}
      required={required}
    >
      {label ? (
        <div className={cn('flex flex-col gap-1 text-sm', className)}>
          {/* SelectPrimitive.Label registers its id into the select context so
              the trigger gets aria-labelledby automatically (robust accessible
              name, unlike a plain <label htmlFor> on a role=combobox button). */}
          <SelectPrimitive.Label className="text-muted-foreground">
            {label}
          </SelectPrimitive.Label>
          {trigger}
        </div>
      ) : (
        trigger
      )}
      <SelectPrimitive.Portal>
        <SelectPrimitive.Positioner sideOffset={4} className="z-50">
          <SelectPrimitive.Popup
            data-slot="select-popup"
            className="max-h-[min(var(--available-height),20rem)] min-w-[var(--anchor-width)] overflow-y-auto rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-md outline-none"
          >
            {options.map((opt) => (
              <SelectPrimitive.Item
                key={opt.value}
                value={opt.value}
                disabled={opt.disabled}
                className="flex cursor-default items-center justify-between gap-2 rounded px-2 py-1.5 text-sm outline-none select-none data-disabled:opacity-50 data-highlighted:bg-accent data-highlighted:text-accent-foreground"
              >
                <SelectPrimitive.ItemText>{opt.label}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator>
                  <Check className="size-4" aria-hidden="true" />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Popup>
        </SelectPrimitive.Positioner>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  )
}
