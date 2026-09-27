// dashboard/src/components/shell/Header.tsx
// Owner: Member 4
//
// Persistent app header: system status, current run identity, playback
// controls, view switcher, presentation mode toggle. Always visible
// (Presentation Mode compresses it in Phase 7, never removes it entirely).

import type { SimulationControl } from '../../hooks/useSimulationControl';
import type { LiveFeed } from '../../hooks/useLiveFeed';
import type { AppView } from './ViewSwitcher';
import { SystemStatusBadge } from './SystemStatusBadge';
import { RunInfoStrip } from './RunInfoStrip';
import { PlaybackControls } from './PlaybackControls';
import { ViewSwitcher } from './ViewSwitcher';
import { PresentationModeToggle } from './PresentationModeToggle';

interface HeaderProps {
  control: SimulationControl;
  feed: LiveFeed;
  view: AppView;
  onViewChange: (v: AppView) => void;
  presentationMode: boolean;
  onTogglePresentation: () => void;
}

export function Header({ control, feed, view, onViewChange, presentationMode, onTogglePresentation }: HeaderProps) {
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 20,
        padding: '10px 16px',
        borderBottom: '1px solid var(--border-0)',
        background: 'var(--surface-1)',
        flexWrap: 'wrap',
      }}
    >
      <div style={{ fontWeight: 700, fontSize: 13, letterSpacing: '0.02em', whiteSpace: 'nowrap' }}>
        SIH 26123 <span style={{ color: 'var(--text-1)', fontWeight: 400 }}>— Fleet Console</span>
      </div>

      <SystemStatusBadge reachability={control.reachability} engineReachability={control.engineReachability} />

      {/* The Product tab runs its own session controls; the scenario run info / START-STOP / playback below belong to the Live view. */}
      {view !== 'product' && <RunInfoStrip status={control.status} />}

      <div style={{ flex: 1 }} />

      {view !== 'product' && <PlaybackControls control={control} feed={feed} />}

      <ViewSwitcher view={view} onChange={onViewChange} />

      <PresentationModeToggle active={presentationMode} onToggle={onTogglePresentation} />
    </header>
  );
}

export default Header;
