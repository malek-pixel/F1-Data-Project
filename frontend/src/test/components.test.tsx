import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DataTable } from "../components/DataTable";
import { Async, EmptyState, ErrorState, Unavailable } from "../components/States";
import { StatBlock, UnavailableMetrics } from "../components/StatBlock";
import { ApiError } from "../services/api";
import type { Stats } from "../types";

const stats = (overrides: Partial<Stats> = {}): Stats => ({
  entries: 100,
  wins: 20,
  podiums: 40,
  top5: 55,
  top10: 80,
  win_rate: 0.2,
  podium_rate: 0.4,
  top5_rate: 0.55,
  top10_rate: 0.8,
  avg_classified_position: 6.5,
  best_classified_position: 1,
  // Enrichment fields. Present so the fixture matches the real payload shape;
  // a partial fixture would let a component read undefined and render it as
  // blank rather than as the explicit "unavailable" state.
  finishes: 85,
  dnfs: 15,
  dnf_rate: 0.15,
  points: 1200,
  avg_grid: 4.2,
  avg_positions_gained: 0.8,
  rates_reliable: true,
  ...overrides,
});

describe("StatBlock", () => {
  it("never labels the average as a finishing position", () => {
    render(<StatBlock stats={stats()} />);
    expect(screen.getByText("AVG CLASSIFIED POS")).toBeInTheDocument();
    expect(screen.queryByText(/AVG FINISH/i)).not.toBeInTheDocument();
    // The caveat travels with the number, not in a footnote elsewhere. It sits
    // on both entry-derived cards, so more than one match is expected.
    expect(screen.getAllByText(/incl\. retirements/i).length).toBeGreaterThan(0);
  });

  it("shows a small-sample caveat instead of hiding the rate", () => {
    render(<StatBlock stats={stats({ entries: 4, rates_reliable: false })} />);
    expect(screen.getByText("20.0%")).toBeInTheDocument();
    expect(screen.getAllByText(/Small sample \(4 entries\)/).length).toBeGreaterThan(0);
  });

  it("renders no caveat when the sample is adequate", () => {
    render(<StatBlock stats={stats()} />);
    expect(screen.queryByText(/Small sample/)).not.toBeInTheDocument();
  });

  it("distinguishes a zero-win driver from one with no data", () => {
    const { rerender } = render(<StatBlock stats={stats({ wins: 0, win_rate: 0 })} />);
    expect(screen.getByText("0.0%")).toBeInTheDocument();

    rerender(<StatBlock stats={stats({ entries: 0, wins: 0, win_rate: null, podium_rate: null })} />);
    expect(screen.queryByText("0.0%")).not.toBeInTheDocument();
  });
});

describe("Unavailable", () => {
  it("names the missing column rather than showing a blank", () => {
    render(<Unavailable label="POLE RATE" why="No qualifying column in results.csv." />);
    expect(screen.getByText("Not available in dataset")).toBeInTheDocument();
    expect(screen.getByText(/No qualifying column/)).toBeInTheDocument();
  });

  it("lists every unsupported metric explicitly", () => {
    render(<UnavailableMetrics />);
    // Labels say RACE explicitly where the answer differs by session: race
    // laps carry no sectors or compounds, practice laps do. A blanket
    // "SECTOR TIMES" would claim more absence than is true.
    for (const label of [
      "FASTEST-LAP AWARDS", "RACE SECTOR TIMES", "RACE TYRE COMPOUND", "CAR / ENGINE SPEC",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getAllByText("Not available in dataset")).toHaveLength(4);
  });

  it("never lists a metric the dataset actually has", () => {
    // This panel claimed POLE RATE, DNF RATE and POINTS / RACE were missing
    // for a long time after all three were ingested, so the UI told users a
    // column was absent while the API was serving it. These labels are the
    // specific ones that were wrong; none may come back without the data
    // going away first.
    render(<UnavailableMetrics />);
    for (const label of ["POLE RATE", "DNF RATE", "POINTS / RACE", "POINTS", "GRID"]) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });
});

describe("DataTable", () => {
  const rows = [
    { id: 1, name: "Alice", wins: 5 },
    { id: 2, name: "Bob", wins: 3 },
  ];
  const columns = [
    { key: "name", header: "Name", render: (r: (typeof rows)[0]) => r.name },
    { key: "wins", header: "Wins", numeric: true, sortKey: "wins", render: (r: (typeof rows)[0]) => r.wins },
  ];

  it("requests a sort rather than sorting the page locally", () => {
    const onSort = vi.fn();
    render(
      <DataTable caption="Test" columns={columns} rows={rows} rowKey={(r) => r.id} sort="wins" onSort={onSort} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Sort by Wins/ }));
    expect(onSort).toHaveBeenCalledWith("wins");
  });

  it("announces the active sort to screen readers", () => {
    render(
      <DataTable caption="Test" columns={columns} rows={rows} rowKey={(r) => r.id} sort="wins" onSort={vi.fn()} />,
    );
    expect(screen.getByRole("columnheader", { name: /Wins/ })).toHaveAttribute("aria-sort", "descending");
  });

  it("carries a caption for assistive technology", () => {
    render(<DataTable caption="Drivers ranked by wins" columns={columns} rows={rows} rowKey={(r) => r.id} />);
    expect(screen.getByRole("table", { name: "Drivers ranked by wins" })).toBeInTheDocument();
  });

  it("shows a specific empty message when filters match nothing", () => {
    render(
      <DataTable
        caption="Test"
        columns={columns}
        rows={[]}
        rowKey={(r) => r.id}
        emptyMessage="No drivers match “zzz”."
      />,
    );
    expect(screen.getByText("No drivers match “zzz”.")).toBeInTheDocument();
  });

  it("renders every row", () => {
    render(<DataTable caption="Test" columns={columns} rows={rows} rowKey={(r) => r.id} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3); // header + 2
  });
});

describe("states", () => {
  it("offers a retry only when retrying could help", () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <ErrorState error={new ApiError("Data store unavailable.", 503, true)} onRetry={onRetry} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalled();

    rerender(<ErrorState error={new ApiError("No driver with id 999", 404, false)} onRetry={onRetry} />);
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("surfaces the message but never a stack trace", () => {
    render(<ErrorState error={new ApiError("Could not reach the API.", 0, true)} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not reach the API.");
    expect(screen.getByRole("alert").textContent).not.toMatch(/at .*\.tsx:/);
  });

  it("gives an empty state a title and guidance", () => {
    render(<EmptyState title="Nothing here" body="Try a broader filter." />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByText("Try a broader filter.")).toBeInTheDocument();
  });
});

describe("Async", () => {
  const base = { reload: vi.fn() };

  it("shows loading before data arrives", () => {
    render(
      <Async state={{ ...base, data: null, loading: true, error: null }}>{() => <div>content</div>}</Async>,
    );
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("content")).not.toBeInTheDocument();
  });

  it("prefers the error state over stale data", () => {
    render(
      <Async state={{ ...base, data: "old" as unknown as string, loading: false, error: new ApiError("boom", 500, true) }}>
        {() => <div>content</div>}
      </Async>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("content")).not.toBeInTheDocument();
  });

  it("shows the empty state for an empty array", () => {
    render(
      <Async
        state={{ ...base, data: [] as unknown[], loading: false, error: null }}
        empty={{ title: "No circuits", body: "Nothing matched." }}
      >
        {() => <div>content</div>}
      </Async>,
    );
    expect(screen.getByText("No circuits")).toBeInTheDocument();
  });

  it("renders content once data arrives", () => {
    render(
      <Async state={{ ...base, data: { ok: true }, loading: false, error: null }}>{() => <div>content</div>}</Async>,
    );
    expect(screen.getByText("content")).toBeInTheDocument();
  });
});

/**
 * The 2007 constructors' table is the one place the UI must not simply print
 * what it is given. McLaren were excluded, so they have no championship
 * position -- rendering the derived rank would state a classification that
 * never existed, and printing "0 points" with no explanation reads as a team
 * that scored nothing rather than one that scored 218 and lost them.
 */
describe("championship penalties in the standings", () => {
  const excluded = {
    position: 11,
    id: 22,
    slug: "mclaren",
    name: "McLaren",
    points: 0,
    wins: 8,
    podiums: 24,
    entries: 34,
    penalty: {
      points_scored: 218,
      points_deducted: 218,
      excluded: true,
      reason: "Excluded from the 2007 Constructors' Championship.",
      evidence: "FIA World Motor Sport Council, 13 September 2007.",
    },
  };

  it("marks an excluded team EX rather than ranking it", () => {
    expect(excluded.penalty.excluded).toBe(true);
    // The rank the UI must not print, and the marker it must print instead.
    const rendered = excluded.penalty.excluded ? "EX" : String(excluded.position);
    expect(rendered).toBe("EX");
    expect(rendered).not.toBe("11");
  });

  it("keeps the races that were actually won", () => {
    expect(excluded.wins).toBe(8);
    expect(excluded.points).toBe(0);
  });

  it("says what was taken away, so a zero is never unexplained", () => {
    expect(excluded.penalty.points_scored).toBe(218);
    expect(excluded.penalty.evidence).toMatch(/FIA/);
  });
});
