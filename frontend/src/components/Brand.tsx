type BrandProps = {
  compact?: boolean;
};

export default function Brand({ compact = false }: BrandProps) {
  return (
    <div className={`wordmark${compact ? " compact" : ""}`}>
      <span className="wordmark-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none">
          <path d="M7 5.5h7.2a4.3 4.3 0 0 1 0 8.6H11" />
          <path d="m8 10-4 4 4 4" />
          <path d="M4 14h9" />
        </svg>
      </span>
      <span className="wordmark-text">QuickDrop</span>
    </div>
  );
}
