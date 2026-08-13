# Car photos

All **266 constructor-seasons** have an image, in `frontend/public/cars/`,
named by the file names in the tables below.

The unit is the **constructor-season**, not the chassis, because the dataset has
no chassis column. So the picture for `mclaren-2025.png` is "the McLaren
that raced in 2025" — you and I both know that is the MCL39, but the app will
not print that name until a chassis table backs it.

## Adding one

The file name is not what the UI reads — `CARS` in
`frontend/src/components/carPhoto.ts` is, keyed on the constructor's exact
`constructors.name` with an explicit list of the seasons that have artwork.
So a new car needs both:

1. The image in `frontend/public/cars/`, named as in the tables below.
2. Its season added to that team's `seasons` array (and a new entry, with the
   team's slug, if the team is not there yet).

A season with no entry renders a `CAR IMAGE — to be added` frame, which is
deliberate: the app does not put a stock photo behind a page that claims every
figure on it is measured, and it does not fall back to an adjacent year, which
would show a livery that season never raced.

## What the picture should look like

**Shape:** landscape **4:3**, because that is the aspect ratio the card frame
already reserves (`.gallery__media`). Anything else gets letterboxed or cropped.

**Size:** **800 × 600 px**. Cards render at roughly 220 × 165, so 800 wide is
comfortably retina-sharp with room for the layout to grow. Bigger is wasted
weight; smaller goes soft on a high-DPI screen.

**Format:** `.png`, or `.jpg` if the source is a photo and file size matters.
Keep each file under ~200 KB — 266 of them load across a scrolling gallery.

**Framing:** the **whole car, side-on or three-quarter front, filling most of
the frame**. The car should be identifiable at 220 px wide, which is small: a
distant trackside shot, a start-line pack, or a cockpit close-up all turn to
mush at that size. Livery and shape are what the reader is scanning for.

**Background:** plain or quiet. A studio/launch shot on white or a clean garage
background reads best; a busy grandstand competes with the numbers under it.
Consistent treatment across cars matters more than any single image being
dramatic — this is a gallery, and one heavily-stylised shot next to twenty flat
ones looks broken.

**Not wanted:** podium shots, driver portraits (those belong in
`docs/DRIVER_PHOTOS.md`), crashes, wet-race spray, heavy motion blur, or
anything with a watermark or burned-in caption.

**Rights:** these are third-party images of third-party liveries. Fine for an
internal analyst tool; a public deployment needs a licensed source or team
press-kit permission. Team launch/press photos are the usual answer.

## Priority

The library defaults to showing current and recent cars; retired ones sit behind
a **Show N retired** button. So the first 48 files below cover everything a
reader sees without clicking.

| Tier | What | Count |
|---|---|--:|
| 1 | **Current** — raced in 2025, on screen by default | 9 |
| 2 | **Recent** — 2021–2024, on screen by default | 39 |
| 3 | **Retired** — 2000–2020, behind the archive button | 218 |
| | **Total** | **266** |

### Tier 1 — current cars (9)

| Team | File name | Races | Wins | Podiums |
|---|---|--:|--:|--:|
| Red Bull | `red-bull-2025.png` | 24 | 8 | 15 |
| Ferrari | `ferrari-2025.png` | 24 | 0 | 7 |
| Mercedes | `mercedes-2025.png` | 24 | 2 | 12 |
| McLaren | `mclaren-2025.png` | 24 | 14 | 34 |
| Williams | `williams-2025.png` | 24 | 0 | 2 |
| Alpine F1 Team | `alpine-f1-team-2025.png` | 24 | 0 | 0 |
| Aston Martin | `aston-martin-2025.png` | 24 | 0 | 0 |
| Haas F1 Team | `haas-f1-team-2025.png` | 24 | 0 | 0 |
| Sauber | `sauber-2025.png` | 24 | 0 | 1 |

### Tier 2 — recent cars, 2021–2024 (39)

| Team | File name | Races | Wins | Podiums |
|---|---|--:|--:|--:|
| Red Bull | `red-bull-2024.png` | 24 | 9 | 18 |
| Red Bull | `red-bull-2023.png` | 22 | 21 | 30 |
| Red Bull | `red-bull-2022.png` | 22 | 17 | 28 |
| Red Bull | `red-bull-2021.png` | 22 | 11 | 23 |
| Ferrari | `ferrari-2024.png` | 24 | 5 | 22 |
| Ferrari | `ferrari-2023.png` | 22 | 1 | 9 |
| Ferrari | `ferrari-2022.png` | 22 | 4 | 20 |
| Ferrari | `ferrari-2021.png` | 22 | 0 | 5 |
| Mercedes | `mercedes-2024.png` | 24 | 4 | 9 |
| Mercedes | `mercedes-2023.png` | 22 | 0 | 8 |
| Mercedes | `mercedes-2022.png` | 22 | 1 | 17 |
| Mercedes | `mercedes-2021.png` | 22 | 9 | 28 |
| McLaren | `mclaren-2024.png` | 24 | 6 | 21 |
| McLaren | `mclaren-2023.png` | 22 | 0 | 9 |
| McLaren | `mclaren-2022.png` | 22 | 0 | 1 |
| McLaren | `mclaren-2021.png` | 22 | 1 | 5 |
| Williams | `williams-2024.png` | 24 | 0 | 0 |
| Williams | `williams-2023.png` | 22 | 0 | 0 |
| Williams | `williams-2022.png` | 22 | 0 | 0 |
| Williams | `williams-2021.png` | 22 | 0 | 1 |
| AlphaTauri | `alphatauri-2023.png` | 22 | 0 | 0 |
| AlphaTauri | `alphatauri-2022.png` | 22 | 0 | 0 |
| AlphaTauri | `alphatauri-2021.png` | 22 | 0 | 1 |
| Alpine F1 Team | `alpine-f1-team-2024.png` | 24 | 0 | 2 |
| Alpine F1 Team | `alpine-f1-team-2023.png` | 22 | 0 | 2 |
| Alpine F1 Team | `alpine-f1-team-2022.png` | 22 | 0 | 0 |
| Alpine F1 Team | `alpine-f1-team-2021.png` | 22 | 1 | 2 |
| Alfa Romeo | `alfa-romeo-2023.png` | 22 | 0 | 0 |
| Alfa Romeo | `alfa-romeo-2022.png` | 22 | 0 | 0 |
| Alfa Romeo | `alfa-romeo-2021.png` | 22 | 0 | 0 |
| Aston Martin | `aston-martin-2024.png` | 24 | 0 | 0 |
| Aston Martin | `aston-martin-2023.png` | 22 | 0 | 8 |
| Aston Martin | `aston-martin-2022.png` | 22 | 0 | 0 |
| Aston Martin | `aston-martin-2021.png` | 22 | 0 | 1 |
| Haas F1 Team | `haas-f1-team-2024.png` | 24 | 0 | 0 |
| Haas F1 Team | `haas-f1-team-2023.png` | 22 | 0 | 0 |
| Haas F1 Team | `haas-f1-team-2022.png` | 22 | 0 | 0 |
| Haas F1 Team | `haas-f1-team-2021.png` | 22 | 0 | 0 |
| Sauber | `sauber-2024.png` | 24 | 0 | 0 |

### Tier 3 — retired cars, 2000–2020 (218)

Grouped by team, teams ordered by career wins. These only appear once a reader
opens a team's archive, so they are the long tail — fill them in per team rather
than per season, so an opened archive is either whole or clearly empty.

**Red Bull** — 16 cars, 2005–2020

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `red-bull-2020.png` | 2020 | 17 | 2 | 13 |
| `red-bull-2019.png` | 2019 | 21 | 3 | 9 |
| `red-bull-2018.png` | 2018 | 21 | 4 | 13 |
| `red-bull-2017.png` | 2017 | 20 | 3 | 13 |
| `red-bull-2016.png` | 2016 | 21 | 2 | 16 |
| `red-bull-2015.png` | 2015 | 19 | 0 | 3 |
| `red-bull-2014.png` | 2014 | 19 | 3 | 12 |
| `red-bull-2013.png` | 2013 | 19 | 13 | 24 |
| `red-bull-2012.png` | 2012 | 20 | 7 | 14 |
| `red-bull-2011.png` | 2011 | 19 | 12 | 27 |
| `red-bull-2010.png` | 2010 | 19 | 9 | 20 |
| `red-bull-2009.png` | 2009 | 17 | 6 | 16 |
| `red-bull-2008.png` | 2008 | 18 | 0 | 1 |
| `red-bull-2007.png` | 2007 | 17 | 0 | 1 |
| `red-bull-2006.png` | 2006 | 18 | 0 | 1 |
| `red-bull-2005.png` | 2005 | 19 | 0 | 0 |

**Ferrari** — 21 cars, 2000–2020

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `ferrari-2020.png` | 2020 | 17 | 0 | 3 |
| `ferrari-2019.png` | 2019 | 21 | 3 | 19 |
| `ferrari-2018.png` | 2018 | 21 | 6 | 24 |
| `ferrari-2017.png` | 2017 | 20 | 5 | 20 |
| `ferrari-2016.png` | 2016 | 21 | 0 | 11 |
| `ferrari-2015.png` | 2015 | 19 | 3 | 16 |
| `ferrari-2014.png` | 2014 | 19 | 0 | 2 |
| `ferrari-2013.png` | 2013 | 19 | 2 | 10 |
| `ferrari-2012.png` | 2012 | 20 | 3 | 15 |
| `ferrari-2011.png` | 2011 | 19 | 1 | 10 |
| `ferrari-2010.png` | 2010 | 19 | 5 | 15 |
| `ferrari-2009.png` | 2009 | 17 | 1 | 6 |
| `ferrari-2008.png` | 2008 | 18 | 8 | 19 |
| `ferrari-2007.png` | 2007 | 17 | 9 | 22 |
| `ferrari-2006.png` | 2006 | 18 | 9 | 19 |
| `ferrari-2005.png` | 2005 | 19 | 1 | 9 |
| `ferrari-2004.png` | 2004 | 18 | 15 | 29 |
| `ferrari-2003.png` | 2003 | 16 | 8 | 16 |
| `ferrari-2002.png` | 2002 | 17 | 15 | 27 |
| `ferrari-2001.png` | 2001 | 17 | 9 | 24 |
| `ferrari-2000.png` | 2000 | 17 | 10 | 21 |

**Mercedes** — 11 cars, 2010–2020

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `mercedes-2020.png` | 2020 | 17 | 13 | 25 |
| `mercedes-2019.png` | 2019 | 21 | 15 | 32 |
| `mercedes-2018.png` | 2018 | 21 | 11 | 25 |
| `mercedes-2017.png` | 2017 | 20 | 12 | 26 |
| `mercedes-2016.png` | 2016 | 21 | 19 | 33 |
| `mercedes-2015.png` | 2015 | 19 | 16 | 32 |
| `mercedes-2014.png` | 2014 | 19 | 16 | 31 |
| `mercedes-2013.png` | 2013 | 19 | 3 | 9 |
| `mercedes-2012.png` | 2012 | 20 | 1 | 3 |
| `mercedes-2011.png` | 2011 | 19 | 0 | 0 |
| `mercedes-2010.png` | 2010 | 19 | 0 | 3 |

**McLaren** — 21 cars, 2000–2020

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `mclaren-2020.png` | 2020 | 17 | 0 | 2 |
| `mclaren-2019.png` | 2019 | 21 | 0 | 1 |
| `mclaren-2018.png` | 2018 | 21 | 0 | 0 |
| `mclaren-2017.png` | 2017 | 20 | 0 | 0 |
| `mclaren-2016.png` | 2016 | 21 | 0 | 0 |
| `mclaren-2015.png` | 2015 | 19 | 0 | 0 |
| `mclaren-2014.png` | 2014 | 19 | 0 | 2 |
| `mclaren-2013.png` | 2013 | 19 | 0 | 0 |
| `mclaren-2012.png` | 2012 | 20 | 7 | 13 |
| `mclaren-2011.png` | 2011 | 19 | 6 | 18 |
| `mclaren-2010.png` | 2010 | 19 | 5 | 16 |
| `mclaren-2009.png` | 2009 | 17 | 2 | 5 |
| `mclaren-2008.png` | 2008 | 18 | 6 | 13 |
| `mclaren-2007.png` | 2007 | 17 | 8 | 24 |
| `mclaren-2006.png` | 2006 | 18 | 0 | 9 |
| `mclaren-2005.png` | 2005 | 19 | 10 | 18 |
| `mclaren-2004.png` | 2004 | 18 | 1 | 4 |
| `mclaren-2003.png` | 2003 | 16 | 2 | 13 |
| `mclaren-2002.png` | 2002 | 17 | 1 | 10 |
| `mclaren-2001.png` | 2001 | 17 | 4 | 13 |
| `mclaren-2000.png` | 2000 | 17 | 7 | 22 |

**Renault** — 15 cars, 2002–2020

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `renault-2020.png` | 2020 | 17 | 0 | 3 |
| `renault-2019.png` | 2019 | 21 | 0 | 0 |
| `renault-2018.png` | 2018 | 21 | 0 | 0 |
| `renault-2017.png` | 2017 | 20 | 0 | 0 |
| `renault-2016.png` | 2016 | 21 | 0 | 0 |
| `renault-2011.png` | 2011 | 19 | 0 | 2 |
| `renault-2010.png` | 2010 | 19 | 0 | 3 |
| `renault-2009.png` | 2009 | 17 | 0 | 1 |
| `renault-2008.png` | 2008 | 18 | 2 | 4 |
| `renault-2007.png` | 2007 | 17 | 0 | 1 |
| `renault-2006.png` | 2006 | 18 | 8 | 19 |
| `renault-2005.png` | 2005 | 19 | 8 | 18 |
| `renault-2004.png` | 2004 | 18 | 1 | 6 |
| `renault-2003.png` | 2003 | 16 | 1 | 5 |
| `renault-2002.png` | 2002 | 17 | 0 | 0 |

**Williams** — 21 cars, 2000–2020

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `williams-2020.png` | 2020 | 17 | 0 | 0 |
| `williams-2019.png` | 2019 | 21 | 0 | 0 |
| `williams-2018.png` | 2018 | 21 | 0 | 0 |
| `williams-2017.png` | 2017 | 20 | 0 | 1 |
| `williams-2016.png` | 2016 | 21 | 0 | 1 |
| `williams-2015.png` | 2015 | 19 | 0 | 4 |
| `williams-2014.png` | 2014 | 19 | 0 | 9 |
| `williams-2013.png` | 2013 | 19 | 0 | 0 |
| `williams-2012.png` | 2012 | 20 | 1 | 1 |
| `williams-2011.png` | 2011 | 19 | 0 | 0 |
| `williams-2010.png` | 2010 | 19 | 0 | 0 |
| `williams-2009.png` | 2009 | 17 | 0 | 0 |
| `williams-2008.png` | 2008 | 18 | 0 | 2 |
| `williams-2007.png` | 2007 | 17 | 0 | 1 |
| `williams-2006.png` | 2006 | 18 | 0 | 0 |
| `williams-2005.png` | 2005 | 19 | 0 | 4 |
| `williams-2004.png` | 2004 | 18 | 1 | 4 |
| `williams-2003.png` | 2003 | 16 | 4 | 12 |
| `williams-2002.png` | 2002 | 17 | 1 | 13 |
| `williams-2001.png` | 2001 | 17 | 4 | 9 |
| `williams-2000.png` | 2000 | 17 | 0 | 3 |

**Brawn** — 1 cars, 2009–2009

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `brawn-2009.png` | 2009 | 17 | 8 | 15 |

**Lotus F1** — 4 cars, 2012–2015

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `lotus-f1-2015.png` | 2015 | 19 | 0 | 1 |
| `lotus-f1-2014.png` | 2014 | 19 | 0 | 0 |
| `lotus-f1-2013.png` | 2013 | 19 | 1 | 14 |
| `lotus-f1-2012.png` | 2012 | 20 | 1 | 10 |

**AlphaTauri** — 1 cars, 2020–2020

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `alphatauri-2020.png` | 2020 | 17 | 1 | 1 |

**BMW Sauber** — 4 cars, 2006–2009

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `bmw-sauber-2009.png` | 2009 | 17 | 0 | 2 |
| `bmw-sauber-2008.png` | 2008 | 18 | 1 | 11 |
| `bmw-sauber-2007.png` | 2007 | 17 | 0 | 2 |
| `bmw-sauber-2006.png` | 2006 | 18 | 0 | 2 |

**Honda** — 3 cars, 2006–2008

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `honda-2008.png` | 2008 | 18 | 0 | 1 |
| `honda-2007.png` | 2007 | 17 | 0 | 0 |
| `honda-2006.png` | 2006 | 18 | 1 | 3 |

**Jordan** — 6 cars, 2000–2005

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `jordan-2005.png` | 2005 | 19 | 0 | 1 |
| `jordan-2004.png` | 2004 | 18 | 0 | 0 |
| `jordan-2003.png` | 2003 | 16 | 1 | 1 |
| `jordan-2002.png` | 2002 | 17 | 0 | 0 |
| `jordan-2001.png` | 2001 | 17 | 0 | 0 |
| `jordan-2000.png` | 2000 | 17 | 0 | 2 |

**Racing Point** — 2 cars, 2019–2020

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `racing-point-2020.png` | 2020 | 17 | 1 | 4 |
| `racing-point-2019.png` | 2019 | 21 | 0 | 0 |

**Toro Rosso** — 14 cars, 2006–2019

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `toro-rosso-2019.png` | 2019 | 21 | 0 | 2 |
| `toro-rosso-2018.png` | 2018 | 21 | 0 | 0 |
| `toro-rosso-2017.png` | 2017 | 20 | 0 | 0 |
| `toro-rosso-2016.png` | 2016 | 21 | 0 | 0 |
| `toro-rosso-2015.png` | 2015 | 19 | 0 | 0 |
| `toro-rosso-2014.png` | 2014 | 19 | 0 | 0 |
| `toro-rosso-2013.png` | 2013 | 19 | 0 | 0 |
| `toro-rosso-2012.png` | 2012 | 20 | 0 | 0 |
| `toro-rosso-2011.png` | 2011 | 19 | 0 | 0 |
| `toro-rosso-2010.png` | 2010 | 19 | 0 | 0 |
| `toro-rosso-2009.png` | 2009 | 17 | 0 | 0 |
| `toro-rosso-2008.png` | 2008 | 18 | 1 | 1 |
| `toro-rosso-2007.png` | 2007 | 17 | 0 | 0 |
| `toro-rosso-2006.png` | 2006 | 18 | 0 | 0 |

**Alfa Romeo** — 2 cars, 2019–2020

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `alfa-romeo-2020.png` | 2020 | 17 | 0 | 0 |
| `alfa-romeo-2019.png` | 2019 | 21 | 0 | 0 |

**Arrows** — 3 cars, 2000–2002

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `arrows-2002.png` | 2002 | 11 | 0 | 0 |
| `arrows-2001.png` | 2001 | 17 | 0 | 0 |
| `arrows-2000.png` | 2000 | 17 | 0 | 0 |

**Caterham** — 3 cars, 2012–2014

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `caterham-2014.png` | 2014 | 17 | 0 | 0 |
| `caterham-2013.png` | 2013 | 19 | 0 | 0 |
| `caterham-2012.png` | 2012 | 20 | 0 | 0 |

**Force India** — 11 cars, 2008–2018

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `force-india-2018.png` | 2018 | 21 | 0 | 1 |
| `force-india-2017.png` | 2017 | 20 | 0 | 0 |
| `force-india-2016.png` | 2016 | 21 | 0 | 2 |
| `force-india-2015.png` | 2015 | 19 | 0 | 1 |
| `force-india-2014.png` | 2014 | 19 | 0 | 1 |
| `force-india-2013.png` | 2013 | 19 | 0 | 0 |
| `force-india-2012.png` | 2012 | 20 | 0 | 0 |
| `force-india-2011.png` | 2011 | 19 | 0 | 0 |
| `force-india-2010.png` | 2010 | 19 | 0 | 0 |
| `force-india-2009.png` | 2009 | 17 | 0 | 1 |
| `force-india-2008.png` | 2008 | 18 | 0 | 0 |

**HRT** — 3 cars, 2010–2012

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `hrt-2012.png` | 2012 | 19 | 0 | 0 |
| `hrt-2011.png` | 2011 | 18 | 0 | 0 |
| `hrt-2010.png` | 2010 | 19 | 0 | 0 |

**Haas F1 Team** — 5 cars, 2016–2020

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `haas-f1-team-2020.png` | 2020 | 17 | 0 | 0 |
| `haas-f1-team-2019.png` | 2019 | 21 | 0 | 0 |
| `haas-f1-team-2018.png` | 2018 | 21 | 0 | 0 |
| `haas-f1-team-2017.png` | 2017 | 20 | 0 | 0 |
| `haas-f1-team-2016.png` | 2016 | 21 | 0 | 0 |

**Jaguar** — 5 cars, 2000–2004

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `jaguar-2004.png` | 2004 | 18 | 0 | 0 |
| `jaguar-2003.png` | 2003 | 16 | 0 | 0 |
| `jaguar-2002.png` | 2002 | 17 | 0 | 1 |
| `jaguar-2001.png` | 2001 | 17 | 0 | 1 |
| `jaguar-2000.png` | 2000 | 17 | 0 | 0 |

**Lotus** — 2 cars, 2010–2011

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `lotus-2011.png` | 2011 | 19 | 0 | 0 |
| `lotus-2010.png` | 2010 | 19 | 0 | 0 |

**MF1** — 1 cars, 2006–2006

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `mf1-2006.png` | 2006 | 14 | 0 | 0 |

**Manor Marussia** — 2 cars, 2015–2016

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `manor-marussia-2016.png` | 2016 | 21 | 0 | 0 |
| `manor-marussia-2015.png` | 2015 | 18 | 0 | 0 |

**Marussia** — 3 cars, 2012–2014

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `marussia-2014.png` | 2014 | 16 | 0 | 0 |
| `marussia-2013.png` | 2013 | 19 | 0 | 0 |
| `marussia-2012.png` | 2012 | 20 | 0 | 0 |

**Minardi** — 6 cars, 2000–2005

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `minardi-2005.png` | 2005 | 19 | 0 | 0 |
| `minardi-2004.png` | 2004 | 18 | 0 | 0 |
| `minardi-2003.png` | 2003 | 16 | 0 | 0 |
| `minardi-2002.png` | 2002 | 17 | 0 | 0 |
| `minardi-2001.png` | 2001 | 17 | 0 | 0 |
| `minardi-2000.png` | 2000 | 17 | 0 | 0 |

**Prost** — 2 cars, 2000–2001

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `prost-2001.png` | 2001 | 17 | 0 | 0 |
| `prost-2000.png` | 2000 | 17 | 0 | 0 |

**Sauber** — 15 cars, 2000–2018

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `sauber-2018.png` | 2018 | 21 | 0 | 0 |
| `sauber-2017.png` | 2017 | 20 | 0 | 0 |
| `sauber-2016.png` | 2016 | 21 | 0 | 0 |
| `sauber-2015.png` | 2015 | 19 | 0 | 0 |
| `sauber-2014.png` | 2014 | 19 | 0 | 0 |
| `sauber-2013.png` | 2013 | 19 | 0 | 0 |
| `sauber-2012.png` | 2012 | 20 | 0 | 4 |
| `sauber-2011.png` | 2011 | 19 | 0 | 0 |
| `sauber-2010.png` | 2010 | 19 | 0 | 0 |
| `sauber-2005.png` | 2005 | 19 | 0 | 0 |
| `sauber-2004.png` | 2004 | 18 | 0 | 0 |
| `sauber-2003.png` | 2003 | 16 | 0 | 1 |
| `sauber-2002.png` | 2002 | 17 | 0 | 0 |
| `sauber-2001.png` | 2001 | 17 | 0 | 1 |
| `sauber-2000.png` | 2000 | 17 | 0 | 0 |

**Spyker** — 1 cars, 2007–2007

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `spyker-2007.png` | 2007 | 17 | 0 | 0 |

**Spyker MF1** — 1 cars, 2006–2006

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `spyker-mf1-2006.png` | 2006 | 4 | 0 | 0 |

**Super Aguri** — 3 cars, 2006–2008

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `super-aguri-2008.png` | 2008 | 4 | 0 | 0 |
| `super-aguri-2007.png` | 2007 | 17 | 0 | 0 |
| `super-aguri-2006.png` | 2006 | 18 | 0 | 0 |

**Toyota** — 8 cars, 2002–2009

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `toyota-2009.png` | 2009 | 17 | 0 | 5 |
| `toyota-2008.png` | 2008 | 18 | 0 | 2 |
| `toyota-2007.png` | 2007 | 17 | 0 | 0 |
| `toyota-2006.png` | 2006 | 18 | 0 | 1 |
| `toyota-2005.png` | 2005 | 19 | 0 | 5 |
| `toyota-2004.png` | 2004 | 18 | 0 | 0 |
| `toyota-2003.png` | 2003 | 16 | 0 | 0 |
| `toyota-2002.png` | 2002 | 17 | 0 | 0 |

**Virgin** — 2 cars, 2010–2011

| File name | Season | Races | Wins | Podiums |
|---|--:|--:|--:|--:|
| `virgin-2011.png` | 2011 | 19 | 0 | 0 |
| `virgin-2010.png` | 2010 | 19 | 0 | 0 |

## Naming rules

`{team-slug}-{season}.png`, all lowercase. The slug is the constructor name
lowercased with non-alphanumerics collapsed to hyphens — the same convention
`frontend/public/teams/` already uses for logos. Every slug you need is spelled
out in the tables above; copy it rather than deriving it, since a few teams
(`alphatauri`, `haas-f1-team`, `alpine-f1-team`) do not slug the way you would
guess.

If a team's slug and a logo file share a name, that is expected — they live in
different directories (`/teams/` vs `/cars/`) and do not collide.
