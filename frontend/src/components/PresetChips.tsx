import { cn } from '../lib/utils'

interface Preset {
  id: string
  name: string
  schoolCount?: number
}

interface PresetChipsProps {
  presets: Preset[]
  selectedPreset: string
  onPresetChange: (presetId: string) => void
  className?: string
  // Quick presets to show at the top (ids)
  quickPresets?: string[]
}

// Default quick presets for hero section
const DEFAULT_QUICK_PRESETS = ['ivy', 'CA', 'NY', 'TX', 'FL', 'PA', 'OH', 'IL']

export default function PresetChips({
  presets,
  selectedPreset,
  onPresetChange,
  className,
  quickPresets = DEFAULT_QUICK_PRESETS,
}: PresetChipsProps) {
  // Filter to show only quick presets that exist in the presets list
  const availableQuickPresets = quickPresets
    .map(id => presets.find(p => p.id === id))
    .filter((p): p is Preset => p !== undefined)

  if (availableQuickPresets.length === 0) {
    return null
  }

  return (
    <div className={cn('flex flex-wrap gap-2 justify-center', className)}>
      {availableQuickPresets.map((preset, index) => (
        // Hide chips after first 3 on mobile (show all on sm+)
        <button
          key={preset.id}
          type="button"
          onClick={() => onPresetChange(preset.id)}
          className={cn(
            'px-3 py-1.5 rounded-full text-sm font-medium transition-all duration-200',
            'border-2',
            // Hide chips 6+ on mobile (show Ivy, CA, NY, TX, FL), show all on sm+
            index >= 5 && 'hidden sm:inline-flex',
            selectedPreset === preset.id
              ? [
                  'bg-primary-600 text-white border-primary-600',
                  'dark:bg-primary-500 dark:border-primary-500',
                  'shadow-md shadow-primary-500/20',
                ]
              : [
                  'bg-white text-gray-700 border-gray-200',
                  'hover:border-primary-300 hover:text-primary-700 hover:bg-primary-50',
                  'dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700',
                  'dark:hover:border-primary-600 dark:hover:text-primary-400 dark:hover:bg-primary-900/20',
                ]
          )}
        >
          {preset.name}
          {preset.schoolCount !== undefined && (
            <span className={cn(
              'ml-1.5 text-xs',
              selectedPreset === preset.id
                ? 'text-primary-200'
                : 'text-gray-400 dark:text-gray-500'
            )}>
              ({preset.schoolCount.toLocaleString()})
            </span>
          )}
        </button>
      ))}

      {/* "More" indicator if there are more presets - hidden on mobile */}
      {presets.length > availableQuickPresets.length && (
        <span className="hidden sm:inline px-3 py-2 text-sm text-gray-400 dark:text-gray-500">
          +{presets.length - availableQuickPresets.length} more in dropdown
        </span>
      )}
    </div>
  )
}
