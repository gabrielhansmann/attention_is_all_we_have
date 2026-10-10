import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

interface Props {
  id: string
  label: string
  value: string | undefined
  options: { value: string; label: string }[]
  onChange: (value: string | undefined) => void
  allLabel?: string
}

const ALL = '__all__'

// Label above the control, as the design guidelines require; "All" clears the filter.
export function FilterSelect({ id, label, value, options, onChange, allLabel = 'All' }: Props) {
  const items = [{ value: ALL, label: allLabel }, ...options]
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select items={items} value={value ?? ALL} onValueChange={(v) => onChange(!v || v === ALL ? undefined : v)}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {items.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
