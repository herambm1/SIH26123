// dashboard/src/App.tsx
// Owner: Member 4
//
// Minimal scaffold placeholder that wires up the component shells so
// `npm run dev` produces a visibly working (if empty) app. Real layout,
// data flow (mock.ts → client.ts swap), and WebSocket wiring are Member 4's
// implementation responsibility per docs/04_FRONTEND.md.

import { WarehouseMap } from './components/WarehouseMap';
import { RobotStatusPanel } from './components/RobotStatusPanel';
import { TaskPanel } from './components/TaskPanel';
import { AlertsFeed } from './components/AlertsFeed';
import { PerformancePanel } from './components/PerformancePanel';

export function App() {
  return (
    <div>
      <h1>SIH 26123 — Fleet Dashboard</h1>
      <WarehouseMap />
      <RobotStatusPanel />
      <TaskPanel />
      <AlertsFeed />
      <PerformancePanel />
    </div>
  );
}

export default App;
