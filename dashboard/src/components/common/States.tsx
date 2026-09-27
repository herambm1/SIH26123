// dashboard/src/components/common/States.tsx
// Owner: Member 4
//
// Shared loading/empty/error state panels. Used wherever a data source is
// unavailable, not-yet-started, or pending backend support — never filled
// in with invented data. Full polish pass is Phase 7; these are the real,
// functional versions used from Phase 3 onward.

import type { ReactNode } from 'react';

function Frame({ children, tone }: { children: ReactNode; tone: 'neutral' | 'error' }) {
  return (
    <div
      style={{
        border: `1px dashed ${tone === 'error' ? 'var(--error)' : 'var(--border-1)'}`,
        borderRadius: 2,
        padding: '18px 16px',
        color: tone === 'error' ? 'var(--error)' : 'var(--text-1)',
        fontSize: 12,
        background: 'var(--surface-1)',
      }}
    >
      {children}
    </div>
  );
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <Frame tone="neutral">
      <div style={{ color: 'var(--text-0)', fontWeight: 600, marginBottom: detail ? 4 : 0 }}>{title}</div>
      {detail && <div>{detail}</div>}
    </Frame>
  );
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <Frame tone="neutral">
      <span className="mono">{label}</span>
    </Frame>
  );
}

export function ErrorState({ title, detail }: { title: string; detail?: string }) {
  return (
    <Frame tone="error">
      <div style={{ fontWeight: 600, marginBottom: detail ? 4 : 0 }}>{title}</div>
      {detail && <div className="mono" style={{ color: 'var(--text-1)' }}>{detail}</div>}
    </Frame>
  );
}

/** For any panel showing data that depends on an unimplemented/unapproved
 * backend capability — must never be silently replaced with fabricated data. */
export function PendingBackendSupport({ what }: { what: string }) {
  return (
    <Frame tone="neutral">
      <div style={{ color: 'var(--warn)', fontWeight: 600 }}>PENDING BACKEND SUPPORT</div>
      <div style={{ marginTop: 4 }}>{what}</div>
    </Frame>
  );
}
