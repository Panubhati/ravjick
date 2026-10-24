// Small shared building blocks: cards, KPI tiles and loading/error/empty states.
import { useEffect, useState, type ReactNode } from "react";
import type { ApiState } from "../lib/useApi";

export function Card(props: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      <h2>{props.title}</h2>
      {props.subtitle && <p className="subtitle">{props.subtitle}</p>}
      {props.children}
    </section>
  );
}

export function Kpi(props: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="kpi">
      <div className="label">{props.label}</div>
      <div className="value">{props.value}</div>
      {props.hint && <div className="hint">{props.hint}</div>}
    </div>
  );
}

export function Skeleton({ height = 120 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} aria-hidden="true" />;
}

/**
 * Free hosting puts the server to sleep when idle, so the first visit can take
 * up to ~30 s. After a few seconds of waiting, say so instead of showing an
 * endless skeleton.
 */
function SlowNotice({ afterMs = 4000 }: { afterMs?: number }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setShow(true), afterMs);
    return () => clearTimeout(timer);
  }, [afterMs]);
  if (!show) return null;
  return (
    <p className="slow-notice" role="status">
      Still loading… The server may be waking up. This can take up to 30 seconds.
    </p>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="error-state" role="alert">
      <strong>Something went wrong.</strong> {message}
      <button className="secondary" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty-state">{children}</div>;
}

/**
 * Show a skeleton while loading, an error with a retry button on failure,
 * and otherwise render the data. Keeps showing old data while reloading.
 */
export function Async<T>(props: {
  state: ApiState<T>;
  skeletonHeight?: number;
  children: (data: T) => ReactNode;
}) {
  const { state } = props;
  if (state.error) return <ErrorState message={state.error} onRetry={state.retry} />;
  if (state.data === undefined) {
    return (
      <>
        <SlowNotice />
        <Skeleton height={props.skeletonHeight} />
      </>
    );
  }
  return (
    <div aria-busy={state.loading} style={{ opacity: state.loading ? 0.6 : 1 }}>
      {props.children(state.data)}
    </div>
  );
}
