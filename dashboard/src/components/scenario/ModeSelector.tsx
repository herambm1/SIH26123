// dashboard/src/components/scenario/ModeSelector.tsx
// Owner: Member 4

import type { SimulationMode } from '../../types/contracts';

const MODES: { value: SimulationMode; label: string }[] = [
  { value: 'STOP_AND_WAIT', label: 'STOP_AND_WAIT (baseline)' },
  { value: 'CENTRALIZED_RESERVATION', label: 'CENTRALIZED_RESERVATION (baseline)' },
  { value: 'DECENTRALIZED_PROPOSED', label: 'DECENTRALIZED_PROPOSED (proposed system)' },
];

export function ModeSelector({
  mode,
  onChange,
  disabled,
}: {
  mode: SimulationMode;
  onChange: (m: SimulationMode) => void;
  disabled: boolean;
}) {
  return (
    <div>
      <label htmlFor="mode-select">Mode</label>
      <br />
      <select
        id="mode-select"
        value={mode}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value as SimulationMode)}
        style={{ width: '100%', marginTop: 4 }}
      >
        {MODES.map((m) => (
          <option key={m.value} value={m.value}>
            {m.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export default ModeSelector;
