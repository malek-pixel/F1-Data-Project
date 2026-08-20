-- ============================================================================
-- One identity for an entity, shared with the SQLite build.
--
-- THE PROBLEM
-- -----------
-- Both stores already had a natural key, and they were different keys.
-- Postgres derived `driver_key` by slugifying the display name
-- ('adrian-sutil'); the SQLite build now uses the upstream source's own id
-- ('sutil'). Circuits happened to agree because both take the project's
-- curated circuit slug. Drivers and constructors did not.
--
-- Integer ids never matched either -- serial here, sorted-name enumeration
-- there -- so before this migration there was NO identifier that addressed
-- the same driver in both stores. Any cross-store check had to join on the
-- display name, which is the one field a rename breaks.
--
-- THE FIX
-- -------
-- Add `slug`, holding the source's own id, in both stores under the same
-- name. `driver_key` and `constructor_key` are left exactly as they are:
-- existing views, the ingestion's ON CONFLICT targets and any saved link
-- keep working. This adds an identity, it does not repoint one.
--
-- The values below are generated from the committed dimension CSVs
-- (data/jolpica_drivers.csv, data/jolpica_constructors.csv) and are written
-- out in full rather than derived at runtime, so the mapping is reviewable in
-- the diff and cannot change under a later code edit.
-- ============================================================================

alter table drivers      add column slug text;
alter table constructors add column slug text;

update drivers d set slug = m.slug
  from (values
        ('Jack Aitken', 'aitken'),
        ('Christijan Albers', 'albers'),
        ('Alexander Albon', 'albon'),
        ('Jean Alesi', 'alesi'),
        ('Jaime Alguersuari', 'alguersuari'),
        ('Fernando Alonso', 'alonso'),
        ('Jérôme d''Ambrosio', 'ambrosio'),
        ('Andrea Kimi Antonelli', 'antonelli'),
        ('Luca Badoer', 'badoer'),
        ('Rubens Barrichello', 'barrichello'),
        ('Zsolt Baumgartner', 'baumgartner'),
        ('Oliver Bearman', 'bearman'),
        ('Enrique Bernoldi', 'bernoldi'),
        ('Gabriel Bortoleto', 'bortoleto'),
        ('Valtteri Bottas', 'bottas'),
        ('Sébastien Bourdais', 'bourdais'),
        ('Brendon Hartley', 'brendon_hartley'),
        ('Gianmaria Bruni', 'bruni'),
        ('Bruno Senna', 'bruno_senna'),
        ('Sébastien Buemi', 'buemi'),
        ('Luciano Burti', 'burti'),
        ('Jenson Button', 'button'),
        ('Karun Chandhok', 'chandhok'),
        ('Max Chilton', 'chilton'),
        ('Franco Colapinto', 'colapinto'),
        ('David Coulthard', 'coulthard'),
        ('Anthony Davidson', 'davidson'),
        ('Nyck de Vries', 'de_vries'),
        ('Pedro Diniz', 'diniz'),
        ('Jack Doohan', 'doohan'),
        ('Robert Doornbos', 'doornbos'),
        ('Tomáš Enge', 'enge'),
        ('Marcus Ericsson', 'ericsson'),
        ('Ralph Firman', 'firman'),
        ('Giancarlo Fisichella', 'fisichella'),
        ('Heinz-Harald Frentzen', 'frentzen'),
        ('Patrick Friesacher', 'friesacher'),
        ('Giedo van der Garde', 'garde'),
        ('Pierre Gasly', 'gasly'),
        ('Marc Gené', 'gene'),
        ('Antonio Giovinazzi', 'giovinazzi'),
        ('Timo Glock', 'glock'),
        ('Lucas di Grassi', 'grassi'),
        ('Romain Grosjean', 'grosjean'),
        ('Esteban Gutiérrez', 'gutierrez'),
        ('Isack Hadjar', 'hadjar'),
        ('Mika Häkkinen', 'hakkinen'),
        ('Lewis Hamilton', 'hamilton'),
        ('Rio Haryanto', 'haryanto'),
        ('Nick Heidfeld', 'heidfeld'),
        ('Johnny Herbert', 'herbert'),
        ('Nico Hülkenberg', 'hulkenberg'),
        ('Yuji Ide', 'ide'),
        ('Eddie Irvine', 'irvine'),
        ('Jolyon Palmer', 'jolyon_palmer'),
        ('Jules Bianchi', 'jules_bianchi'),
        ('Narain Karthikeyan', 'karthikeyan'),
        ('Kevin Magnussen', 'kevin_magnussen'),
        ('Nicolas Kiesa', 'kiesa'),
        ('Christian Klien', 'klien'),
        ('Kamui Kobayashi', 'kobayashi'),
        ('Heikki Kovalainen', 'kovalainen'),
        ('Robert Kubica', 'kubica'),
        ('Daniil Kvyat', 'kvyat'),
        ('Nicholas Latifi', 'latifi'),
        ('Liam Lawson', 'lawson'),
        ('Charles Leclerc', 'leclerc'),
        ('Vitantonio Liuzzi', 'liuzzi'),
        ('André Lotterer', 'lotterer'),
        ('Pastor Maldonado', 'maldonado'),
        ('Markus Winkelhock', 'markus_winkelhock'),
        ('Tarso Marques', 'marques'),
        ('Felipe Massa', 'massa'),
        ('Cristiano da Matta', 'matta'),
        ('Max Verstappen', 'max_verstappen'),
        ('Nikita Mazepin', 'mazepin'),
        ('Gastón Mazzacane', 'mazzacane'),
        ('Allan McNish', 'mcnish'),
        ('Roberto Merhi', 'merhi'),
        ('Michael Schumacher', 'michael_schumacher'),
        ('Mick Schumacher', 'mick_schumacher'),
        ('Franck Montagny', 'montagny'),
        ('Tiago Monteiro', 'monteiro'),
        ('Juan Pablo Montoya', 'montoya'),
        ('Kazuki Nakajima', 'nakajima'),
        ('Felipe Nasr', 'nasr'),
        ('Lando Norris', 'norris'),
        ('Esteban Ocon', 'ocon'),
        ('Olivier Panis', 'panis'),
        ('Giorgio Pantano', 'pantano'),
        ('Sergio Pérez', 'perez'),
        ('Vitaly Petrov', 'petrov'),
        ('Oscar Piastri', 'piastri'),
        ('Charles Pic', 'pic'),
        ('Pietro Fittipaldi', 'pietro_fittipaldi'),
        ('Nelson Piquet Jr.', 'piquet_jr'),
        ('Antônio Pizzonia', 'pizzonia'),
        ('Kimi Räikkönen', 'raikkonen'),
        ('Ralf Schumacher', 'ralf_schumacher'),
        ('Paul di Resta', 'resta'),
        ('Daniel Ricciardo', 'ricciardo'),
        ('Pedro de la Rosa', 'rosa'),
        ('Nico Rosberg', 'rosberg'),
        ('Alexander Rossi', 'rossi'),
        ('George Russell', 'russell'),
        ('Carlos Sainz', 'sainz'),
        ('Mika Salo', 'salo'),
        ('Logan Sargeant', 'sargeant'),
        ('Takuma Sato', 'sato'),
        ('Sergey Sirotkin', 'sirotkin'),
        ('Scott Speed', 'speed'),
        ('Will Stevens', 'stevens'),
        ('Lance Stroll', 'stroll'),
        ('Adrian Sutil', 'sutil'),
        ('Jarno Trulli', 'trulli'),
        ('Yuki Tsunoda', 'tsunoda'),
        ('Stoffel Vandoorne', 'vandoorne'),
        ('Jean-Éric Vergne', 'vergne'),
        ('Jos Verstappen', 'verstappen'),
        ('Sebastian Vettel', 'vettel'),
        ('Jacques Villeneuve', 'villeneuve'),
        ('Mark Webber', 'webber'),
        ('Pascal Wehrlein', 'wehrlein'),
        ('Justin Wilson', 'wilson'),
        ('Alexander Wurz', 'wurz'),
        ('Sakon Yamamoto', 'yamamoto'),
        ('Alex Yoong', 'yoong'),
        ('Guanyu Zhou', 'zhou'),
        ('Ricardo Zonta', 'zonta')
  ) as m(display_name, slug)
 where d.display_name = m.display_name;

update constructors c set slug = m.slug
  from (values
        ('Alfa Romeo', 'alfa'),
        ('AlphaTauri', 'alphatauri'),
        ('Alpine F1 Team', 'alpine'),
        ('Arrows', 'arrows'),
        ('Aston Martin', 'aston_martin'),
        ('BAR', 'bar'),
        ('Benetton', 'benetton'),
        ('BMW Sauber', 'bmw_sauber'),
        ('Brawn', 'brawn'),
        ('Caterham', 'caterham'),
        ('Ferrari', 'ferrari'),
        ('Force India', 'force_india'),
        ('Haas F1 Team', 'haas'),
        ('Honda', 'honda'),
        ('HRT', 'hrt'),
        ('Jaguar', 'jaguar'),
        ('Jordan', 'jordan'),
        ('Lotus F1', 'lotus_f1'),
        ('Lotus', 'lotus_racing'),
        ('Manor Marussia', 'manor'),
        ('Marussia', 'marussia'),
        ('McLaren', 'mclaren'),
        ('Mercedes', 'mercedes'),
        ('MF1', 'mf1'),
        ('Minardi', 'minardi'),
        ('Prost', 'prost'),
        ('Racing Point', 'racing_point'),
        ('RB F1 Team', 'rb'),
        ('Red Bull', 'red_bull'),
        ('Renault', 'renault'),
        ('Sauber', 'sauber'),
        ('Spyker', 'spyker'),
        ('Spyker MF1', 'spyker_mf1'),
        ('Super Aguri', 'super_aguri'),
        ('Toro Rosso', 'toro_rosso'),
        ('Toyota', 'toyota'),
        ('Virgin', 'virgin'),
        ('Williams', 'williams')
  ) as m(constructor_name, slug)
 where c.constructor_name = m.constructor_name;

-- Fail loudly rather than leaving a half-populated identity column. A NULL
-- slug would silently exclude that entity from every cross-store comparison,
-- which is precisely the blindness this column exists to remove.
do $$
declare missing int;
begin
    select count(*) into missing from drivers where slug is null;
    if missing > 0 then
        raise exception 'slug backfill missed % drivers', missing;
    end if;
    select count(*) into missing from constructors where slug is null;
    if missing > 0 then
        raise exception 'slug backfill missed % constructors', missing;
    end if;
end $$;

alter table drivers      alter column slug set not null;
alter table constructors alter column slug set not null;

create unique index drivers_slug_key      on drivers (slug);
create unique index constructors_slug_key on constructors (slug);

comment on column drivers.slug is
    'Upstream source driver id (''hamilton''). The portable identity: the same '
    'value addresses the same driver in the SQLite build. Integer ids and '
    'driver_key are store-local and are not comparable across backends.';
comment on column constructors.slug is
    'Upstream source constructor id (''ferrari''). Portable identity; see '
    'drivers.slug.';
