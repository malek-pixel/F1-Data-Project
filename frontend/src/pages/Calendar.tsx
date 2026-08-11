import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DataTable } from "../components/DataTable";
import { Async } from "../components/States";
import { dec, formatDate, num } from "../components/format";
import { Badge, PageHeader, SectionTitle, Tabs } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { count, useDataset } from "../hooks/useDataset";
import { qs } from "../services/api";
import type { Race, RaceDetail as RaceDetailType, SeasonIndexRow, SeasonSummary } from "../types";
import { StatCard } from "../components/ui";

interface Dominance {
  races: number;
  distinct_driver_winners: number;
  distinct_constructor_winners: number;
  top_driver_win_share: number | null;
  top_constructor_win_share: number | null;
  drivers: { name: string }[];
  basis: string;
}

/** Repeated wherever a wins-based table appears. These are not standings. */
function RankingBasisNote() {
  return (
    <p style={{ fontSize: 13, color: "var(--text-dim)", marginTop: 0 }}>
      <Badge tone="warning">Not championship standings</Badge> Ranked by wins, then podiums, then average
      classified position. The dataset has no points column, so official championship order cannot be reproduced.
    </p>
  );
}

export function SeasonIndex() {
  const state = useApi<SeasonIndexRow[]>("/seasons");
  const info = useDataset();
  return (
    <>
      <PageHeader
        eyebrow="SEASON EXPLORER"
        title="Seasons"
        sub={`${count(info?.seasons, "seasons")}, ${count(info?.races, "races")}, ${info ? `${info.season_from}–${info.season_to}` : "—"}.`}
      />
      <Async state={state} loadingRows={8}>
        {(seasons) => (
          <DataTable
            caption="Seasons in the dataset"
            rows={seasons}
            rowKey={(row) => row.season}
            columns={[
              {
                key: "season",
                header: "Season",
                render: (r) => (
                  <Link to={`/seasons/${r.season}`} className="mono" style={{ fontWeight: 600 }}>
                    {r.season}
                  </Link>
                ),
              },
              { key: "races", header: "Races", numeric: true, render: (r) => num(r.races) },
              { key: "drivers", header: "Drivers", numeric: true, render: (r) => num(r.drivers) },
              { key: "constructors", header: "Constructors", numeric: true, render: (r) => num(r.constructors) },
              { key: "entries", header: "Classifications", numeric: true, render: (r) => num(r.entries) },
            ]}
          />
        )}
      </Async>
    </>
  );
}

export function SeasonDetail() {
  const { season } = useParams();
  const [tab, setTab] = useState<"drivers" | "constructors">("drivers");
  const state = useApi<SeasonSummary>(`/seasons/${season}`);
  const dominance = useApi<Dominance>(`/seasons/${season}/dominance`);

  return (
    <Async state={state} loadingRows={6}>
      {(summary) => (
        <>
          <PageHeader
            eyebrow="SEASON"
            title={String(summary.season)}
            sub={`${summary.races} races · ${summary.entries.toLocaleString()} classifications`}
          />

          <SectionTitle aside="NORMALISED BY RACES HELD">Season concentration</SectionTitle>
          <Async state={dominance} loadingRows={2}>
            {(dom) => (
              <>
                <div className="grid grid--kpi">
                  <StatCard
                    label="LEADER WIN SHARE"
                    value={dom.top_driver_win_share === null ? "—" : `${(dom.top_driver_win_share * 100).toFixed(0)}%`}
                    note={dom.drivers[0] ? `${dom.drivers[0].name} — of ${dom.races} races` : undefined}
                  />
                  <StatCard
                    label="DIFFERENT RACE WINNERS"
                    value={String(dom.distinct_driver_winners)}
                    note="Drivers who won at least one race"
                  />
                  <StatCard
                    label="WINNING CONSTRUCTORS"
                    value={String(dom.distinct_constructor_winners)}
                    note="Teams who won at least one race"
                  />
                  <StatCard
                    label="TOP TEAM WIN SHARE"
                    value={dom.top_constructor_win_share === null ? "—" : `${(dom.top_constructor_win_share * 100).toFixed(0)}%`}
                  />
                </div>
                <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{dom.basis}</p>
              </>
            )}
          </Async>

          <SectionTitle>Wins-based ranking</SectionTitle>
          <RankingBasisNote />
          <Tabs
            label="Ranking type"
            active={tab}
            onChange={setTab}
            tabs={[
              { id: "drivers", label: "Drivers" },
              { id: "constructors", label: "Constructors" },
            ]}
          />
          <DataTable
            caption={`${summary.season} ${tab} ranked by wins`}
            rows={tab === "drivers" ? summary.drivers : summary.constructors}
            rowKey={(row) => row.id}
            columns={[
              {
                key: "name",
                header: tab === "drivers" ? "Driver" : "Constructor",
                render: (r) => <Link to={`/${tab}/${r.id}`}>{r.name}</Link>,
              },
              { key: "entries", header: "Entries", numeric: true, render: (r) => num(r.entries) },
              { key: "wins", header: "Wins", numeric: true, render: (r) => num(r.wins) },
              { key: "podiums", header: "Podiums", numeric: true, render: (r) => num(r.podiums) },
              { key: "avg", header: "Avg class. pos", numeric: true, render: (r) => dec(r.avg_classified_position) },
            ]}
          />

          <SectionTitle>Calendar</SectionTitle>
          <DataTable
            caption={`${summary.season} race calendar`}
            rows={summary.races_list}
            rowKey={(row) => row.id}
            columns={[
              { key: "round", header: "Rd", numeric: true, render: (r) => <span className="mono">{r.round}</span> },
              { key: "name", header: "Race", render: (r) => <Link to={`/races/${r.id}`}>{r.name}</Link> },
              {
                key: "circuit",
                header: "Circuit",
                render: (r) => <Link to={`/circuits/${r.circuit_id}`}>{r.circuit_name}</Link>,
              },
              { key: "date", header: "Date", render: (r) => <span className="mono">{formatDate(r.date)}</span> },
            ]}
          />
        </>
      )}
    </Async>
  );
}

export function RaceIndex() {
  // Defaults to the latest season present in the data. A hardcoded year
  // silently points at a season that may not exist after a data refresh.
  const info = useDataset();
  const [season, setSeason] = useState<number | "" | null>(null);
  const seasons = useApi<SeasonIndexRow[]>("/seasons");
  const active = season === null ? (info?.season_to ?? "") : season;
  const races = useApi<Race[]>(`/races${qs({ season: active || undefined, limit: 500 })}`);

  return (
    <>
      <PageHeader
        eyebrow="RACE EXPLORER"
        title="Races"
        sub="Browse a season's races and open the full classification for any of them."
      />
      <div className="controls">
        <div className="field">
          <label htmlFor="race-season">SEASON</label>
          <select
            id="race-season"
            className="select"
            value={active}
            onChange={(event) => setSeason(event.target.value ? Number(event.target.value) : "")}
          >
            <option value="">All seasons</option>
            {(seasons.data ?? []).map((row) => (
              <option key={row.season} value={row.season}>
                {row.season}
              </option>
            ))}
          </select>
        </div>
      </div>

      <Async
        state={races}
        loadingRows={8}
        empty={{ title: "No races", body: "No races recorded for this selection." }}
      >
        {(rows) => (
          <DataTable
            caption="Races"
            rows={rows}
            rowKey={(row) => row.id}
            columns={[
              { key: "season", header: "Season", render: (r) => <span className="mono">{r.season}</span> },
              { key: "round", header: "Rd", numeric: true, render: (r) => <span className="mono">{r.round}</span> },
              { key: "name", header: "Race", render: (r) => <Link to={`/races/${r.id}`}>{r.name}</Link> },
              {
                key: "circuit",
                header: "Circuit",
                render: (r) => <Link to={`/circuits/${r.circuit_id}`}>{r.circuit_name}</Link>,
              },
              { key: "date", header: "Date", render: (r) => <span className="mono">{formatDate(r.date)}</span> },
            ]}
          />
        )}
      </Async>
    </>
  );
}

export function RaceDetail() {
  const { id } = useParams();
  const state = useApi<RaceDetailType>(`/races/${id}`);

  return (
    <Async state={state} loadingRows={6}>
      {(race) => (
        <>
          <PageHeader
            eyebrow={`ROUND ${race.round} · ${race.season}`}
            title={race.name}
            sub={
              <>
                <Link to={`/circuits/${race.circuit_id}`}>{race.circuit_name}</Link> · {formatDate(race.date)}
              </>
            }
          />

          <p style={{ fontSize: 13, color: "var(--text-dim)" }}>
            <Badge tone="warning">Classification order</Badge> Positions are the final classification, which
            includes retirements. The source has no status column, so a retirement cannot be distinguished from a
            finish.
          </p>

          <DataTable
            caption={`${race.season} ${race.name} classification`}
            rows={race.results}
            rowKey={(row) => row.driver_id}
            columns={[
              {
                key: "pos",
                header: "Pos",
                numeric: true,
                render: (r) => (
                  <span className="mono" style={r.position <= 3 ? { color: "var(--accent-text)", fontWeight: 600 } : undefined}>
                    {r.position}
                  </span>
                ),
              },
              {
                key: "driver",
                header: "Driver",
                render: (r) => <Link to={`/drivers/${r.driver_id}`}>{r.driver_name}</Link>,
              },
              {
                key: "team",
                header: "Constructor",
                render: (r) => <Link to={`/constructors/${r.constructor_id}`}>{r.constructor_name}</Link>,
              },
            ]}
          />

          <p style={{ fontSize: 12, color: "var(--text-faint)", marginTop: 24 }}>
            Grid positions, points scored, fastest lap, pit stops and lap times are not present in the dataset.
          </p>
        </>
      )}
    </Async>
  );
}
