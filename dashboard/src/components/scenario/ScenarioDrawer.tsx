// dashboard/src/components/scenario/ScenarioDrawer.tsx
// Owner: Member 4

import { SCENARIO_CATALOG } from '../../data/scenarioCatalog';
import { ScenarioCard } from './ScenarioCard';

export function ScenarioDrawer({
  scenarioId,
  onSelect,
  disabled,
}: {
  scenarioId: string;
  onSelect: (id: string) => void;
  disabled: boolean;
}) {
  return (
    <div>
      <label>Scenario (9)</label>
      <div style={{ marginTop: 6, opacity: disabled ? 0.5 : 1, pointerEvents: disabled ? 'none' : 'auto' }}>
        {SCENARIO_CATALOG.map((entry) => (
          <ScenarioCard
            key={entry.scenarioId}
            entry={entry}
            selected={entry.scenarioId === scenarioId}
            onSelect={() => onSelect(entry.scenarioId)}
          />
        ))}
      </div>
    </div>
  );
}

export default ScenarioDrawer;
