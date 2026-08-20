import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DataTable } from "../components/DataTable";
import { Dock } from "../components/Dock";
import { DynamicIsland } from "../components/DynamicIsland";
import { SearchField } from "../components/SearchField";

/**
 * The animated components, tested for the things animation can quietly break:
 * the control still works, the label still reaches assistive tech, and the
 * layout maths that the effects sit on top of still holds.
 */

const railItems = [
  { to: "/", label: "Overview", icon: "overview" as const, end: true },
  { to: "/drivers", label: "Drivers", icon: "drivers" as const },
  { to: "/cars", label: "Cars", icon: "cars" as const, badge: "NEW" },
];

function withRouter(ui: React.ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("Dock", () => {
  it("keeps every destination reachable and labelled", () => {
    withRouter(<Dock items={railItems} />);
    for (const item of railItems) {
      expect(screen.getByRole("link", { name: item.label })).toHaveAttribute("href", item.to);
    }
  });

  it("reveals the hidden label of an icon-only rail on hover", () => {
    withRouter(<Dock items={railItems} />);
    expect(screen.queryByText("Drivers")).not.toBeInTheDocument();
    fireEvent.mouseEnter(screen.getByRole("link", { name: "Drivers" }));
    expect(screen.getByText("Drivers")).toBeInTheDocument();
  });

  it("reveals the same label on keyboard focus, not just pointer hover", () => {
    withRouter(<Dock items={railItems} />);
    fireEvent.focus(screen.getByRole("link", { name: "Cars" }));
    expect(screen.getByText("Cars")).toBeInTheDocument();
  });
});

describe("SearchField", () => {
  it("associates its label with the input", () => {
    render(<SearchField id="q" label="SEARCH" value="" onChange={vi.fn()} />);
    expect(screen.getByLabelText("SEARCH")).toBeInTheDocument();
  });

  it("reports every keystroke to the caller", () => {
    const onChange = vi.fn();
    render(<SearchField id="q" label="SEARCH" value="" onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("SEARCH"), { target: { value: "alonso" } });
    expect(onChange).toHaveBeenCalledWith("alonso");
  });

  it("offers a clear control only when there is something to clear", () => {
    const onChange = vi.fn();
    const { rerender } = render(<SearchField id="q" label="SEARCH" value="" onChange={onChange} />);
    expect(screen.queryByRole("button", { name: "Clear search" })).not.toBeInTheDocument();

    rerender(<SearchField id="q" label="SEARCH" value="spa" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(onChange).toHaveBeenCalledWith("");
  });
});

describe("DynamicIsland", () => {
  it("announces state politely rather than silently animating", () => {
    withRouter(<DynamicIsland state={{ kind: "ok", label: "healthy" }} />);
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("healthy");
  });

  it("shows the failure state when the API is unreachable", () => {
    withRouter(<DynamicIsland state={{ kind: "error", label: "api unreachable" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("api unreachable");
  });
});

describe("DataTable column sizing", () => {
  const rows = [{ id: 1, name: "2004 Italian Grand Prix", date: "12 Sep" }];

  /**
   * Regression: every text column defaulted to `1fr`, so a nine-column
   * listing measured 2716px inside a 1143px pane. Only the first text column
   * may flex; the rest size to content with a readable floor.
   */
  it("flexes one column and sizes the rest to content", () => {
    const { container } = render(
      <DataTable
        caption="Races"
        rows={rows}
        rowKey={(r) => r.id}
        columns={[
          { key: "rd", header: "Rd", numeric: true, render: () => "01" },
          { key: "name", header: "Race", render: (r) => r.name },
          { key: "date", header: "Date", render: (r) => r.date },
          { key: "pole", header: "Pole", render: () => "—" },
        ]}
      />,
    );
    const grid = container.querySelector("[role=table]") as HTMLElement;
    const template = grid.style.getPropertyValue("--cols");
    expect(template).toBe("minmax(56px, max-content) minmax(140px, 1fr) minmax(72px, max-content) minmax(72px, max-content)");
    expect(template.match(/1fr/g)).toHaveLength(1);
  });

  it("honours an explicit width over the default track", () => {
    const { container } = render(
      <DataTable
        caption="Races"
        rows={rows}
        rowKey={(r) => r.id}
        columns={[{ key: "name", header: "Race", width: "200px", render: (r) => r.name }]}
      />,
    );
    const grid = container.querySelector("[role=table]") as HTMLElement;
    expect(grid.style.getPropertyValue("--cols")).toBe("200px");
  });
});

describe("reduced motion", () => {
  beforeEach(() => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("prefers-reduced-motion"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  it("leaves the rail fully usable when the user asks for less motion", () => {
    withRouter(<Dock items={railItems} />);
    expect(screen.getAllByRole("link")).toHaveLength(railItems.length);
    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("href", "/");
  });
});
