// dashboard/src/components/shell/ViewSwitcher.tsx
// Owner: Member 4

export type AppView = 'live' | 'product' | 'benchmark';

export function ViewSwitcher({ view, onChange }: { view: AppView; onChange: (v: AppView) => void }) {
  const tab = (v: AppView, label: string) => (
    <button
      onClick={() => onChange(v)}
      style={{
        background: view === v ? 'var(--surface-3)' : 'var(--surface-1)',
        borderColor: view === v ? 'var(--accent)' : 'var(--border-1)',
        color: view === v ? 'var(--text-0)' : 'var(--text-1)',
        fontWeight: view === v ? 700 : 400,
      }}
    >
      {label}
    </button>
  );

  return (
    <div style={{ display: 'flex', gap: 4 }}>
      {tab('live', 'LIVE SIMULATION')}
      {tab('product', 'PRODUCT')}
      {tab('benchmark', 'BENCHMARK & PROOF')}
    </div>
  );
}

export default ViewSwitcher;
