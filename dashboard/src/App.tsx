// dashboard/src/App.tsx
// Owner: Member 4
//
// App shell: scenario/mode/seed/speed selection wired to
// POST /api/simulation/control, the real Live Simulation view (warehouse
// canvas, robot inspector, communication/events panels, /ws/live buffering,
// tick playback), and the Benchmark & Proof view (Phase 6) — a static
// visualization of the already-audited offline benchmark result, never
// live/fetched/recomputed data. See components/benchmark/BenchmarkView.tsx.

import { useState } from 'react';
import './styles/theme.css';
import { useSimulationControl } from './hooks/useSimulationControl';
import { useLiveFeed } from './hooks/useLiveFeed';
import { Header } from './components/shell/Header';
import type { AppView } from './components/shell/ViewSwitcher';
import { ScenarioDrawer } from './components/scenario/ScenarioDrawer';
import { ModeSelector } from './components/scenario/ModeSelector';
import { SeedSpeedControls } from './components/scenario/SeedSpeedControls';
import { ErrorState } from './components/common/States';
import { LiveSimulationView } from './components/simulation/LiveSimulationView';
import { BenchmarkView } from './components/benchmark/BenchmarkView';
import { ProductView } from './components/product/ProductView';

export function App() {
  const control = useSimulationControl();
  const feed = useLiveFeed(control.runGeneration);
  const [view, setView] = useState<AppView>('live');
  const [presentationMode, setPresentationMode] = useState(false);

  const running = control.status?.running ?? false;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Header
        control={control}
        feed={feed}
        view={view}
        onViewChange={setView}
        presentationMode={presentationMode}
        onTogglePresentation={() => setPresentationMode((p) => !p)}
      />

      {control.actionError && (
        <div style={{ padding: '8px 16px' }}>
          <ErrorState title="Simulation control request failed" detail={control.actionError} />
        </div>
      )}

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {!presentationMode && view !== 'product' && (
          <aside
            style={{
              width: 340,
              flexShrink: 0,
              borderRight: '1px solid var(--border-0)',
              background: 'var(--surface-1)',
              padding: 14,
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: 14,
            }}
          >
            <ModeSelector mode={control.mode} onChange={control.setMode} disabled={running} />
            <SeedSpeedControls
              seed={control.seed}
              onSeedChange={control.setSeed}
              speed={control.speed}
              onSpeedChange={control.setSpeed}
              disabled={running}
            />
            <ScenarioDrawer scenarioId={control.scenarioId} onSelect={control.setScenarioId} disabled={running} />
          </aside>
        )}

        <main
          style={{
            flex: 1,
            minWidth: 0,
            minHeight: 0,
            padding: 16,
            overflow: view === 'live' || view === 'product' ? 'hidden' : 'auto',
            display: 'flex',
          }}
        >
          {view === 'live' ? (
            <div style={{ flex: 1, minWidth: 0, minHeight: 0 }}>
              <LiveSimulationView feed={feed} status={control.status} />
            </div>
          ) : view === 'product' ? (
            <div style={{ flex: 1, minWidth: 0, minHeight: 0 }}>
              <ProductView />
            </div>
          ) : (
            <div style={{ flex: 1, minWidth: 0 }}>
              <BenchmarkView />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
