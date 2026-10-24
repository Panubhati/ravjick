import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { Meta } from "./api/types";
import { Methodology } from "./components/Methodology";
import { Async } from "./components/ui";
import { useApi } from "./lib/useApi";
import { parseState, TABS, toSearch, type ViewState } from "./lib/urlState";
import { DecisionPlanner } from "./pages/DecisionPlanner";
import { Insights } from "./pages/Insights";
import { Performance } from "./pages/Performance";

export function App() {
  const meta = useApi(() => api.meta(), []);
  return (
    <div className="app">
      <header>
        <h1>Wind Forecast Portal</h1>
        <p>
          Planning tomorrow's electricity purchase? See the wind forecast you had when you had to decide,
          and how far you could trust it. Times are UK time; power is in megawatts (MW).
        </p>
      </header>
      <Async state={meta} skeletonHeight={400}>
        {(m) => <Portal meta={m} />}
      </Async>
      <footer>
        Source: Elexon, which publishes Great Britain's electricity market data. Actual wind power and wind
        forecasts for January 2026. Historical data, not updated live.
      </footer>
    </div>
  );
}

function Portal({ meta }: { meta: Meta }) {
  // Selections are shared across views and mirrored in the URL, so a link
  // reopens exactly the same view.
  const [view, setView] = useState<ViewState>(() => parseState(window.location.search, meta));
  const update = (patch: Partial<ViewState>) => setView((v) => ({ ...v, ...patch }));

  useEffect(() => {
    window.history.replaceState(null, "", toSearch(view));
  }, [view]);

  const range = { from: view.from, to: view.to };
  const setRange = (r: { from: string; to: string }) => update(r);
  const setCutoff = (cutoff: string) => update({ cutoff });

  return (
    <>
      <nav className="tabs" role="tablist" aria-label="Views">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={view.tab === t.id}
            aria-controls="panel"
            onClick={() => update({ tab: t.id })}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <Methodology />
      <main id="panel" role="tabpanel" aria-labelledby={`tab-${view.tab}`}>
        {view.tab === "planner" && (
          <DecisionPlanner
            meta={meta}
            date={view.date}
            cutoff={view.cutoff}
            onDateChange={(date) => update({ date })}
            onCutoffChange={setCutoff}
          />
        )}
        {view.tab === "performance" && (
          <Performance
            meta={meta}
            range={range}
            cutoff={view.cutoff}
            onRangeChange={setRange}
            onCutoffChange={setCutoff}
          />
        )}
        {view.tab === "insights" && (
          <Insights meta={meta} range={range} cutoff={view.cutoff} onRangeChange={setRange} onCutoffChange={setCutoff} />
        )}
      </main>
    </>
  );
}
