# Driver photos

All **129 drivers** in the dataset have a portrait, in
`frontend/public/drivers/`, named by the file names in the table below.

## Adding one

The file name is not what the UI reads — `PORTRAITS` in
`frontend/src/components/driverPhoto.ts` is, keyed on the driver's exact
`drivers.name`. So a new driver needs both:

1. The image in `frontend/public/drivers/`, named as in the table.
2. A row in `PORTRAITS` mapping their name to that file's slug.

A driver with no row keeps the `PORTRAIT — to be added` frame, which is
deliberate: the app does not ship a stock image in place of a person it has
no picture of. Adding the file without the row does nothing; adding the row
without the file gives a broken image.

**Format:** square-ish portrait, face visible at 190px wide (the card) and
84px (the detail masthead). `.png` or `.jpg`. Head-and-shoulders crops read
best at these sizes; full-car or podium shots do not. The frame crops to fill
from slightly above centre, so leave a little headroom.

## The set

Sorted by race entries, which is how often a driver actually surfaces in the
UI.

| # | Driver | File name | Entries | Wins | Podiums | Seasons |
|--:|---|---|--:|--:|--:|---|
| 1 | Fernando Alonso | `fernando-alonso.png` | 428 | 32 | 106 | 2001–2025 |
| 2 | Lewis Hamilton | `lewis-hamilton.png` | 380 | 105 | 202 | 2007–2025 |
| 3 | Kimi Räikkönen | `kimi-raikkonen.png` | 352 | 21 | 103 | 2001–2021 |
| 4 | Jenson Button | `jenson-button.png` | 309 | 15 | 50 | 2000–2017 |
| 5 | Sebastian Vettel | `sebastian-vettel.png` | 300 | 53 | 122 | 2007–2022 |
| 6 | Sergio Pérez | `sergio-perez.png` | 283 | 6 | 39 | 2011–2024 |
| 7 | Felipe Massa | `felipe-massa.png` | 271 | 11 | 41 | 2002–2017 |
| 8 | Daniel Ricciardo | `daniel-ricciardo.png` | 257 | 8 | 32 | 2011–2024 |
| 9 | Nico Hülkenberg | `nico-hulkenberg.png` | 254 | 0 | 1 | 2010–2025 |
| 10 | Valtteri Bottas | `valtteri-bottas.png` | 247 | 10 | 67 | 2013–2024 |
| 11 | Max Verstappen | `max-verstappen.png` | 233 | 71 | 127 | 2015–2025 |
| 12 | Carlos Sainz | `carlos-sainz.png` | 232 | 4 | 29 | 2015–2025 |
| 13 | Mark Webber | `mark-webber.png` | 217 | 9 | 42 | 2002–2013 |
| 14 | Rubens Barrichello | `rubens-barrichello.png` | 212 | 11 | 62 | 2000–2011 |
| 15 | Jarno Trulli | `jarno-trulli.png` | 210 | 1 | 10 | 2000–2011 |
| 16 | Nico Rosberg | `nico-rosberg.png` | 206 | 23 | 57 | 2006–2016 |
| 17 | Lance Stroll | `lance-stroll.png` | 191 | 0 | 3 | 2017–2025 |
| 18 | Kevin Magnussen | `kevin-magnussen.png` | 186 | 0 | 1 | 2014–2024 |
| 19 | Nick Heidfeld | `nick-heidfeld.png` | 184 | 0 | 13 | 2000–2011 |
| 20 | Romain Grosjean | `romain-grosjean.png` | 181 | 0 | 10 | 2009–2020 |
| 21 | Esteban Ocon | `esteban-ocon.png` | 180 | 1 | 4 | 2016–2025 |
| 22 | Michael Schumacher | `michael-schumacher.png` | 180 | 56 | 84 | 2000–2012 |
| 23 | Pierre Gasly | `pierre-gasly.png` | 178 | 1 | 5 | 2017–2025 |
| 24 | Giancarlo Fisichella | `giancarlo-fisichella.png` | 174 | 3 | 14 | 2000–2009 |
| 25 | Charles Leclerc | `charles-leclerc.png` | 173 | 8 | 50 | 2018–2025 |
| 26 | David Coulthard | `david-coulthard.png` | 157 | 7 | 32 | 2000–2008 |
| 27 | George Russell | `george-russell.png` | 152 | 5 | 24 | 2019–2025 |
| 28 | Lando Norris | `lando-norris.png` | 152 | 11 | 44 | 2019–2025 |
| 29 | Ralf Schumacher | `ralf-schumacher.png` | 131 | 6 | 21 | 2000–2007 |
| 30 | Alexander Albon | `alexander-albon.png` | 129 | 0 | 2 | 2019–2025 |
| 31 | Adrian Sutil | `adrian-sutil.png` | 128 | 0 | 0 | 2007–2014 |
| 32 | Yuki Tsunoda | `yuki-tsunoda.png` | 114 | 0 | 0 | 2021–2025 |
| 33 | Daniil Kvyat | `daniil-kvyat.png` | 112 | 0 | 3 | 2014–2020 |
| 34 | Heikki Kovalainen | `heikki-kovalainen.png` | 112 | 1 | 4 | 2007–2013 |
| 35 | Jacques Villeneuve | `jacques-villeneuve.png` | 100 | 0 | 2 | 2000–2006 |
| 36 | Robert Kubica | `robert-kubica.png` | 99 | 1 | 12 | 2006–2021 |
| 37 | Marcus Ericsson | `marcus-ericsson.png` | 97 | 0 | 0 | 2014–2018 |
| 38 | Pastor Maldonado | `pastor-maldonado.png` | 96 | 1 | 1 | 2011–2015 |
| 39 | Juan Pablo Montoya | `juan-pablo-montoya.png` | 95 | 7 | 30 | 2001–2006 |
| 40 | Timo Glock | `timo-glock.png` | 95 | 0 | 3 | 2004–2012 |
| 41 | Takuma Sato | `takuma-sato.png` | 91 | 0 | 1 | 2002–2008 |
| 42 | Pedro de la Rosa | `pedro-de-la-rosa.png` | 90 | 0 | 1 | 2000–2012 |
| 43 | Vitantonio Liuzzi | `vitantonio-liuzzi.png` | 80 | 0 | 0 | 2005–2011 |
| 44 | Kamui Kobayashi | `kamui-kobayashi.png` | 76 | 0 | 1 | 2009–2014 |
| 45 | Oscar Piastri | `oscar-piastri.png` | 70 | 9 | 26 | 2023–2025 |
| 46 | Guanyu Zhou | `guanyu-zhou.png` | 68 | 0 | 0 | 2022–2024 |
| 47 | Olivier Panis | `olivier-panis.png` | 67 | 0 | 0 | 2001–2004 |
| 48 | Antonio Giovinazzi | `antonio-giovinazzi.png` | 62 | 0 | 0 | 2017–2021 |
| 49 | Nicholas Latifi | `nicholas-latifi.png` | 61 | 0 | 0 | 2020–2022 |
| 50 | Heinz-Harald Frentzen | `heinz-harald-frentzen.png` | 60 | 0 | 3 | 2000–2003 |
| 51 | Esteban Gutiérrez | `esteban-gutierrez.png` | 59 | 0 | 0 | 2013–2016 |
| 52 | Paul di Resta | `paul-di-resta.png` | 59 | 0 | 0 | 2011–2017 |
| 53 | Jean-Éric Vergne | `jean-eric-vergne.png` | 58 | 0 | 0 | 2012–2014 |
| 54 | Vitaly Petrov | `vitaly-petrov.png` | 58 | 0 | 1 | 2010–2012 |
| 55 | Sébastien Buemi | `sebastien-buemi.png` | 55 | 0 | 0 | 2009–2011 |
| 56 | Christian Klien | `christian-klien.png` | 51 | 0 | 0 | 2004–2010 |
| 57 | Eddie Irvine | `eddie-irvine.png` | 50 | 0 | 2 | 2000–2002 |
| 58 | Jos Verstappen | `jos-verstappen.png` | 50 | 0 | 0 | 2000–2003 |
| 59 | Bruno Senna | `bruno-senna.png` | 46 | 0 | 0 | 2010–2012 |
| 60 | Christijan Albers | `christijan-albers.png` | 46 | 0 | 0 | 2005–2007 |
| 61 | Jaime Alguersuari | `jaime-alguersuari.png` | 46 | 0 | 0 | 2009–2011 |
| 62 | Narain Karthikeyan | `narain-karthikeyan.png` | 46 | 0 | 0 | 2005–2012 |
| 63 | Mick Schumacher | `mick-schumacher.png` | 44 | 0 | 0 | 2021–2022 |
| 64 | Stoffel Vandoorne | `stoffel-vandoorne.png` | 42 | 0 | 0 | 2016–2018 |
| 65 | Felipe Nasr | `felipe-nasr.png` | 40 | 0 | 0 | 2015–2016 |
| 66 | Charles Pic | `charles-pic.png` | 39 | 0 | 0 | 2012–2013 |
| 67 | Pascal Wehrlein | `pascal-wehrlein.png` | 39 | 0 | 0 | 2016–2017 |
| 68 | Jolyon Palmer | `jolyon-palmer.png` | 37 | 0 | 0 | 2016–2017 |
| 69 | Tiago Monteiro | `tiago-monteiro.png` | 37 | 0 | 1 | 2005–2006 |
| 70 | Kazuki Nakajima | `kazuki-nakajima.png` | 36 | 0 | 0 | 2007–2009 |
| 71 | Logan Sargeant | `logan-sargeant.png` | 36 | 0 | 0 | 2023–2024 |
| 72 | Liam Lawson | `liam-lawson.png` | 35 | 0 | 0 | 2023–2025 |
| 73 | Max Chilton | `max-chilton.png` | 35 | 0 | 0 | 2013–2014 |
| 74 | Alexander Wurz | `alexander-wurz.png` | 34 | 0 | 2 | 2000–2007 |
| 75 | Jean Alesi | `jean-alesi.png` | 34 | 0 | 0 | 2000–2001 |
| 76 | Jules Bianchi | `jules-bianchi.png` | 34 | 0 | 0 | 2013–2014 |
| 77 | Mika Häkkinen | `mika-hakkinen.png` | 34 | 6 | 14 | 2000–2001 |
| 78 | Mika Salo | `mika-salo.png` | 34 | 0 | 0 | 2000–2002 |
| 79 | Cristiano da Matta | `cristiano-da-matta.png` | 28 | 0 | 0 | 2003–2004 |
| 80 | Enrique Bernoldi | `enrique-bernoldi.png` | 28 | 0 | 0 | 2001–2002 |
| 81 | Nelson Piquet Jr. | `nelson-piquet-jr.png` | 28 | 0 | 1 | 2008–2009 |
| 82 | Scott Speed | `scott-speed.png` | 28 | 0 | 0 | 2006–2007 |
| 83 | Franco Colapinto | `franco-colapinto.png` | 27 | 0 | 0 | 2024–2025 |
| 84 | Oliver Bearman | `oliver-bearman.png` | 27 | 0 | 0 | 2024–2025 |
| 85 | Sébastien Bourdais | `sebastien-bourdais.png` | 27 | 0 | 0 | 2008–2009 |
| 86 | Brendon Hartley | `brendon-hartley.png` | 25 | 0 | 0 | 2017–2018 |
| 87 | Ricardo Zonta | `ricardo-zonta.png` | 25 | 0 | 0 | 2000–2005 |
| 88 | Andrea Kimi Antonelli | `andrea-kimi-antonelli.png` | 24 | 0 | 3 | 2025 |
| 89 | Anthony Davidson | `anthony-davidson.png` | 24 | 0 | 0 | 2002–2008 |
| 90 | Gabriel Bortoleto | `gabriel-bortoleto.png` | 24 | 0 | 0 | 2025 |
| 91 | Isack Hadjar | `isack-hadjar.png` | 24 | 0 | 1 | 2025 |
| 92 | Nikita Mazepin | `nikita-mazepin.png` | 22 | 0 | 0 | 2021 |
| 93 | Gastón Mazzacane | `gaston-mazzacane.png` | 21 | 0 | 0 | 2000–2001 |
| 94 | Sakon Yamamoto | `sakon-yamamoto.png` | 21 | 0 | 0 | 2006–2010 |
| 95 | Sergey Sirotkin | `sergey-sirotkin.png` | 21 | 0 | 0 | 2018 |
| 96 | Antônio Pizzonia | `antonio-pizzonia.png` | 20 | 0 | 0 | 2003–2005 |
| 97 | Jérôme d'Ambrosio | `jerome-d-ambrosio.png` | 20 | 0 | 0 | 2011–2012 |
| 98 | Marc Gené | `marc-gene.png` | 20 | 0 | 0 | 2000–2004 |
| 99 | Zsolt Baumgartner | `zsolt-baumgartner.png` | 20 | 0 | 0 | 2003–2004 |
| 100 | Giedo van der Garde | `giedo-van-der-garde.png` | 19 | 0 | 0 | 2013 |
| 101 | Lucas di Grassi | `lucas-di-grassi.png` | 19 | 0 | 0 | 2010 |
| 102 | Will Stevens | `will-stevens.png` | 19 | 0 | 0 | 2014–2015 |
| 103 | Gianmaria Bruni | `gianmaria-bruni.png` | 18 | 0 | 0 | 2004 |
| 104 | Allan McNish | `allan-mcnish.png` | 17 | 0 | 0 | 2002 |
| 105 | Johnny Herbert | `johnny-herbert.png` | 17 | 0 | 0 | 2000 |
| 106 | Pedro Diniz | `pedro-diniz.png` | 17 | 0 | 0 | 2000 |
| 107 | Justin Wilson | `justin-wilson.png` | 16 | 0 | 0 | 2003 |
| 108 | Alex Yoong | `alex-yoong.png` | 15 | 0 | 0 | 2001–2002 |
| 109 | Luciano Burti | `luciano-burti.png` | 15 | 0 | 0 | 2000–2001 |
| 110 | Giorgio Pantano | `giorgio-pantano.png` | 14 | 0 | 0 | 2004 |
| 111 | Ralph Firman | `ralph-firman.png` | 14 | 0 | 0 | 2003 |
| 112 | Roberto Merhi | `roberto-merhi.png` | 13 | 0 | 0 | 2015 |
| 113 | Tarso Marques | `tarso-marques.png` | 13 | 0 | 0 | 2001 |
| 114 | Rio Haryanto | `rio-haryanto.png` | 12 | 0 | 0 | 2016 |
| 115 | Karun Chandhok | `karun-chandhok.png` | 11 | 0 | 0 | 2010–2011 |
| 116 | Nyck de Vries | `nyck-de-vries.png` | 11 | 0 | 0 | 2022–2023 |
| 117 | Patrick Friesacher | `patrick-friesacher.png` | 11 | 0 | 0 | 2005 |
| 118 | Robert Doornbos | `robert-doornbos.png` | 11 | 0 | 0 | 2005–2006 |
| 119 | Franck Montagny | `franck-montagny.png` | 7 | 0 | 0 | 2006 |
| 120 | Jack Doohan | `jack-doohan.png` | 7 | 0 | 0 | 2024–2025 |
| 121 | Alexander Rossi | `alexander-rossi.png` | 5 | 0 | 0 | 2015 |
| 122 | Nicolas Kiesa | `nicolas-kiesa.png` | 5 | 0 | 0 | 2003 |
| 123 | Yuji Ide | `yuji-ide.png` | 4 | 0 | 0 | 2006 |
| 124 | Tomáš Enge | `tomas-enge.png` | 3 | 0 | 0 | 2001 |
| 125 | Luca Badoer | `luca-badoer.png` | 2 | 0 | 0 | 2009 |
| 126 | Pietro Fittipaldi | `pietro-fittipaldi.png` | 2 | 0 | 0 | 2020 |
| 127 | André Lotterer | `andre-lotterer.png` | 1 | 0 | 0 | 2014 |
| 128 | Jack Aitken | `jack-aitken.png` | 1 | 0 | 0 | 2020 |
| 129 | Markus Winkelhock | `markus-winkelhock.png` | 1 | 0 | 0 | 2007 |

---

Generated from `data/f1.db` — 129 drivers, 10,550 race entries, seasons 2000–2025.
