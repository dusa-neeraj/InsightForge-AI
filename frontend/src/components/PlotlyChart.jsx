import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";

// Draws a Plotly figure ({ data, layout }) sent by the backend.
export default function PlotlyChart({ figure, label, height = 340 }) {
  const ref = useRef(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;

    const base = figure.layout || {};
    const layout = {
      ...base,
      title: undefined, // the card already shows the title
      autosize: true,
      height,
      margin: { ...base.margin, t: 16 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "system-ui, sans-serif", size: 12, color: "#334155" },
      ...(base.showlegend ? { legend: { orientation: "h", y: -0.25 } } : {}),
    };
    // Plotly changes the objects it receives, so give it copies
    Plotly.react(node, structuredClone(figure.data), layout, {
      responsive: true,
      displaylogo: false,
      modeBarButtonsToRemove: ["lasso2d", "select2d"],
    });
    return () => Plotly.purge(node);
  }, [figure, height]);

  return <div ref={ref} role="img" aria-label={label} className="w-full" />;
}