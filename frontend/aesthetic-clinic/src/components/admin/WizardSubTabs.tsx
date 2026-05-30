import type { ReactNode } from 'react'

export type SubTab = {
  id: string
  label: string
  icon?: ReactNode
}

interface WizardSubTabsProps {
  tabs: SubTab[]
  activeTab: string
  onTabChange: (tabId: string) => void
}

export function WizardSubTabs({ tabs, activeTab, onTabChange }: WizardSubTabsProps) {
  return (
    <nav className="wizard-sub-tabs" aria-label="Subsecciones del paso">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onTabChange(tab.id)}
          className={`wizard-sub-tabs__link ${activeTab === tab.id ? 'is-active' : ''}`}
        >
          {tab.icon && <span className="wizard-sub-tabs__icon">{tab.icon}</span>}
          {tab.label}
        </button>
      ))}
    </nav>
  )
}