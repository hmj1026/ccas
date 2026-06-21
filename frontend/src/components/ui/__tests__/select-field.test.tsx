/**
 * SelectField 測試 -- 驗證 label 關聯、開啟選單、選擇回呼與 aria-label 模式。
 */
import { useState } from 'react'
import { screen, render, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { SelectField, type SelectOption } from '../select-field'

const OPTIONS: readonly SelectOption[] = [
  { value: '', label: '全部' },
  { value: 'ctbc', label: '中國信託' },
  { value: 'fubon', label: '富邦' },
]

function Harness({
  onValueChange,
  initial = '',
  ...rest
}: {
  onValueChange?: (v: string) => void
  initial?: string
} & Partial<Parameters<typeof SelectField>[0]>) {
  const [value, setValue] = useState(initial)
  return (
    <SelectField
      label="銀行"
      options={OPTIONS}
      value={value}
      onValueChange={(v) => {
        setValue(v)
        onValueChange?.(v)
      }}
      {...rest}
    />
  )
}

describe('SelectField', () => {
  it('associates a visible label with the trigger via htmlFor/id', () => {
    render(<Harness id="bank-select" />)
    const trigger = screen.getByLabelText('銀行')
    expect(trigger).toHaveAttribute('id', 'bank-select')
    // Selected option label shows in the trigger.
    expect(trigger).toHaveTextContent('全部')
  })

  it('opens the listbox and reports the chosen value', async () => {
    const user = userEvent.setup()
    const onValueChange = vi.fn()
    render(<Harness onValueChange={onValueChange} />)

    await user.click(screen.getByLabelText('銀行'))
    const listbox = await screen.findByRole('listbox')
    await user.click(within(listbox).getByRole('option', { name: '富邦' }))

    expect(onValueChange).toHaveBeenCalledWith('fubon')
    expect(screen.getByLabelText('銀行')).toHaveTextContent('富邦')
  })

  it('uses aria-label when no visible label is given', () => {
    render(
      <Harness label={undefined} aria-label="銀行篩選" initial="ctbc" />,
    )
    const trigger = screen.getByLabelText('銀行篩選')
    expect(trigger).toHaveTextContent('中國信託')
  })
})
