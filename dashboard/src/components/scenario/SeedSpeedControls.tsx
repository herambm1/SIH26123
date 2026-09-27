// dashboard/src/components/scenario/SeedSpeedControls.tsx
// Owner: Member 4
//
// Speed note (verified against simulation/runner.py): LIVE paces at
// time.sleep(0.5) per tick (~2 ticks/sec, real-time-visible telemetry
// pushes) — the mode this UI defaults to for a live demo. BATCH runs with
// no artificial delay and is what the finalized benchmark used.

import type { SimulationSpeed } from '../../types/contracts';

export function SeedSpeedControls({
  seed,
  onSeedChange,
  speed,
  onSpeedChange,
  disabled,
}: {
  seed: number;
  onSeedChange: (s: number) => void;
  speed: SimulationSpeed;
  onSpeedChange: (s: SimulationSpeed) => void;
  disabled: boolean;
}) {
  return (
    <div style={{ display: 'flex', gap: 10 }}>
      <div style={{ flex: 1 }}>
        <label htmlFor="seed-input">Seed</label>
        <br />
        <input
          id="seed-input"
          type="number"
          value={seed}
          disabled={disabled}
          onChange={(e) => onSeedChange(Number(e.target.value))}
          style={{ width: '100%', marginTop: 4 }}
        />
      </div>
      <div style={{ flex: 1 }}>
        <label htmlFor="speed-select">Speed</label>
        <br />
        <select
          id="speed-select"
          value={speed}
          disabled={disabled}
          onChange={(e) => onSpeedChange(e.target.value as SimulationSpeed)}
          style={{ width: '100%', marginTop: 4 }}
        >
          <option value="LIVE">LIVE (~2 ticks/sec, for demo)</option>
          <option value="BATCH">BATCH (no delay)</option>
        </select>
      </div>
    </div>
  );
}

export default SeedSpeedControls;
