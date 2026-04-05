/**
 * Analytics 頁面測試 -- 載入與空狀態。
 */
import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import AnalyticsPage from '../analytics'
import { renderWithProviders } from '@/test-utils'

// Mock recharts to avoid canvas issues in jsdom
vi.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => <div data-testid="line-chart">{children}</div>,
  Line: () => null,
  PieChart: ({ children }: { children: React.ReactNode }) => <div data-testid="pie-chart">{children}</div>,
  Pie: () => null,
  BarChart: ({ children }: { children: React.ReactNode }) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Cell: () => null,
  Legend: () => null,
}))

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
}))

import { apiGet } from '@/lib/api-client'
const mockApiGet = vi.mocked(apiGet)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AnalyticsPage', () => {
  it('shows loading state initially', () => {
    mockApiGet.mockReturnValue(new Promise(() => {}))
    renderWithProviders(<AnalyticsPage />)
    expect(screen.getByText('載入中...')).toBeInTheDocument()
  })

  it('renders charts when data is available', async () => {
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/analytics/years')
        return Promise.resolve({ success: true, data: [2026], message: '' })
      if (path === '/api/settings/banks')
        return Promise.resolve({ success: true, data: [], message: '' })
      if (path.includes('trend'))
        return Promise.resolve({ success: true, data: [{ month: '2026-01', total: 10000 }], message: '' })
      if (path.includes('categories'))
        return Promise.resolve({ success: true, data: [{ category: '餐飲', total: 5000 }], message: '' })
      return Promise.resolve({ success: true, data: [{ bank_code: 'CTBC', bank_name: '中國信託', total: 8000 }], message: '' })
    })

    renderWithProviders(<AnalyticsPage />)

    await waitFor(() => {
      expect(screen.getByText('消費分析')).toBeInTheDocument()
    })
    expect(screen.getByText('月消費趨勢')).toBeInTheDocument()
    expect(screen.getByText('類別分布')).toBeInTheDocument()
    expect(screen.getByText('銀行比較')).toBeInTheDocument()
  })

  it('shows empty states when no data', async () => {
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/analytics/years' || path === '/api/settings/banks')
        return Promise.resolve({ success: true, data: [], message: '' })
      return Promise.resolve({ success: true, data: [], message: '' })
    })

    renderWithProviders(<AnalyticsPage />)

    await waitFor(() => {
      expect(screen.getByText('尚無趨勢資料')).toBeInTheDocument()
    })
    expect(screen.getByText('尚無類別資料')).toBeInTheDocument()
    expect(screen.getByText('尚無銀行資料')).toBeInTheDocument()
  })

  it('shows error state on failure', async () => {
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/analytics/years' || path === '/api/settings/banks')
        return Promise.resolve({ success: true, data: [], message: '' })
      return Promise.reject(new Error('Server error'))
    })

    renderWithProviders(<AnalyticsPage />)

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })
  })
})
