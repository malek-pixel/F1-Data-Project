/**
 * Car photos, one per constructor-season.
 *
 * Keyed on the exact `constructors.name` values the dataset holds, like
 * `teamLogo` and `driverPhoto`: that string is what every payload carries.
 * Seasons are listed rather than expressed as a range because a team's entry
 * has to say which years it actually raced -- Sauber's run is split either
 * side of its BMW Sauber and Alfa Romeo spells, which are separate
 * constructors in the dataset and carry their own photos.
 *
 * All 266 constructor-seasons have one, so the lookup never misses today. It
 * still returns null for an unknown team or year rather than guessing a path:
 * a season added by a later ETL run should get the "to be added" frame, not a
 * broken image.
 *
 * These are third-party images of third-party liveries. Fine for an internal
 * analyst tool; a public deployment would need a licensed source.
 */
const CARS: Record<string, { slug: string; seasons: number[] }> = {
  "Alfa Romeo": { slug: "alfa-romeo", seasons: [2019, 2020, 2021, 2022, 2023] },
  AlphaTauri: { slug: "alphatauri", seasons: [2020, 2021, 2022, 2023] },
  "Alpine F1 Team": { slug: "alpine-f1-team", seasons: [2021, 2022, 2023, 2024, 2025] },
  Arrows: { slug: "arrows", seasons: [2000, 2001, 2002] },
  "Aston Martin": { slug: "aston-martin", seasons: [2021, 2022, 2023, 2024, 2025] },
  "BMW Sauber": { slug: "bmw-sauber", seasons: [2006, 2007, 2008, 2009] },
  Brawn: { slug: "brawn", seasons: [2009] },
  Caterham: { slug: "caterham", seasons: [2012, 2013, 2014] },
  Ferrari: { slug: "ferrari", seasons: [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] },
  "Force India": { slug: "force-india", seasons: [2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018] },
  HRT: { slug: "hrt", seasons: [2010, 2011, 2012] },
  "Haas F1 Team": { slug: "haas-f1-team", seasons: [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] },
  Honda: { slug: "honda", seasons: [2006, 2007, 2008] },
  Jaguar: { slug: "jaguar", seasons: [2000, 2001, 2002, 2003, 2004] },
  Jordan: { slug: "jordan", seasons: [2000, 2001, 2002, 2003, 2004, 2005] },
  Lotus: { slug: "lotus", seasons: [2010, 2011] },
  "Lotus F1": { slug: "lotus-f1", seasons: [2012, 2013, 2014, 2015] },
  MF1: { slug: "mf1", seasons: [2006] },
  "Manor Marussia": { slug: "manor-marussia", seasons: [2015, 2016] },
  Marussia: { slug: "marussia", seasons: [2012, 2013, 2014] },
  McLaren: { slug: "mclaren", seasons: [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] },
  Mercedes: { slug: "mercedes", seasons: [2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] },
  Minardi: { slug: "minardi", seasons: [2000, 2001, 2002, 2003, 2004, 2005] },
  Prost: { slug: "prost", seasons: [2000, 2001] },
  "Racing Point": { slug: "racing-point", seasons: [2019, 2020] },
  "Red Bull": { slug: "red-bull", seasons: [2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] },
  Renault: { slug: "renault", seasons: [2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2016, 2017, 2018, 2019, 2020] },
  Sauber: { slug: "sauber", seasons: [2000, 2001, 2002, 2003, 2004, 2005, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2024, 2025] },
  Spyker: { slug: "spyker", seasons: [2007] },
  "Spyker MF1": { slug: "spyker-mf1", seasons: [2006] },
  "Super Aguri": { slug: "super-aguri", seasons: [2006, 2007, 2008] },
  "Toro Rosso": { slug: "toro-rosso", seasons: [2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019] },
  Toyota: { slug: "toyota", seasons: [2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009] },
  Virgin: { slug: "virgin", seasons: [2010, 2011] },
  Williams: { slug: "williams", seasons: [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] },
};

/** Public path to a car's photo, or null when none ships for that season. */
export function carPhoto(team: string, season: number): string | null {
  const entry = CARS[team];
  if (!entry || !entry.seasons.includes(season)) return null;
  return `/cars/${entry.slug}-${season}.webp`;
}
