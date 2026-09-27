// dashboard/src/components/shell/PresentationModeToggle.tsx
// Owner: Member 4
//
// Functional now: flips a boolean owned by App.tsx. What Presentation Mode
// actually hides/enlarges is a Phase 7 concern (layout/emphasis only, same
// data) — this component just owns the on/off control.

export function PresentationModeToggle({
  active,
  onToggle,
}: {
  active: boolean;
  onToggle: () => void;
}) {
  return (
    <button onClick={onToggle} className={active ? 'primary' : undefined} title="Presentation Mode">
      {active ? '◼ EXIT PRESENTATION' : '▭ PRESENTATION MODE'}
    </button>
  );
}

export default PresentationModeToggle;
