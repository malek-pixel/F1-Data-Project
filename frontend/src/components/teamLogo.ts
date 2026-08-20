/**
 * Constructor logos.
 *
 * Keyed on the exact `constructors.name` values the dataset holds, because
 * that string is what every payload carries -- there is no logo column, and
 * adding one would mean a migration for what is purely a presentation asset.
 *
 * All 35 browsable constructors have artwork. The three kept out of the
 * listings by `HIDDEN_CONSTRUCTORS` do not, so a direct link to one still
 * resolves to null -- as does any constructor a later ETL run adds. Those
 * keep the "no logo" frame rather than falling back to a generic badge,
 * which would read as "this team looked like this" when it does not.
 *
 * These are third-party trademarks used to identify each team. Fine for an
 * internal analyst tool; a public deployment would need to check each team's
 * brand-usage terms.
 */
const LOGOS: Record<string, string> = {
  "Alfa Romeo": "alfa-romeo",
  AlphaTauri: "alphatauri",
  "Alpine F1 Team": "alpine",
  Arrows: "arrows",
  "Aston Martin": "aston-martin",
  "BMW Sauber": "bmw-sauber",
  Brawn: "brawn",
  Caterham: "caterham",
  Ferrari: "ferrari",
  "Force India": "force-india",
  HRT: "hrt",
  "Haas F1 Team": "haas",
  Honda: "honda",
  Jaguar: "jaguar",
  Jordan: "jordan",
  // Two separate teams, two separate marks. "Lotus" is Team Lotus of
  // 2010-2011, the green-and-gold roundel; "Lotus F1" is the black-and-gold
  // Lotus F1 Team of 2012-2015. The dataset holds them as distinct
  // constructors and so does this map.
  Lotus: "lotus",
  "Lotus F1": "lotus-f1",
  // MF1 became Spyker MF1 partway through 2006 and Spyker for 2007. Three
  // constructor rows, three marks the teams actually carried.
  MF1: "mf1",
  "Manor Marussia": "manor-marussia",
  Marussia: "marussia",
  McLaren: "mclaren",
  Mercedes: "mercedes",
  Minardi: "minardi",
  Prost: "prost",
  "Racing Point": "racing-point",
  "Red Bull": "red-bull",
  Renault: "renault",
  Sauber: "sauber",
  Spyker: "spyker",
  "Spyker MF1": "spyker-mf1",
  "Super Aguri": "super-aguri",
  "Toro Rosso": "toro-rosso",
  Toyota: "toyota",
  Virgin: "virgin",
  Williams: "williams",
};

/** Public path to a constructor's logo, or null when none ships for it. */
export function teamLogo(name: string): string | null {
  const slug = LOGOS[name];
  return slug ? `/teams/${slug}.webp` : null;
}
