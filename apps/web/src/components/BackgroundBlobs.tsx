export function BackgroundBlobs() {
  return (
    <div aria-hidden className="ambient-background pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="ambient-blob ambient-blob-blue" />
      <div className="ambient-blob ambient-blob-pink" />
      <div className="ambient-blob ambient-blob-violet" />
      <div className="ambient-blob ambient-blob-peach" />
      <div className="ambient-aurora" />
      <div className="ambient-vignette" />
      <div className="ambient-grain" />
    </div>
  );
}
