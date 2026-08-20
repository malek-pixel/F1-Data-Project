-- Defence in depth: RLS already returns zero rows for staging, but revoking
-- SELECT means the endpoint 401s instead of returning an empty array. The
-- table's existence is not a public fact.
REVOKE ALL ON staging_results FROM anon, authenticated;

-- ============================================================================
-- metric_definitions: the published methodology, seeded from the same
-- definitions backend/app/advanced.py serves. Stored so the frontend can
-- explain any number without the explanation drifting from the code.
-- ============================================================================
INSERT INTO metric_definitions
  (metric_key, display_name, definition, formula, source_fields, aggregation_level,
   edge_cases, limitations, sample_requirement)
VALUES
('entries','Entries (starts)',
 'One classified race entry. The denominator for every rate.',
 'COUNT(results rows)', ARRAY['position'], 'career / season / circuit',
 'No status column exists, so a lap-1 retirement counts as an entry.',
 'Not a count of finishes. Entries cannot be split into finishes and retirements.', NULL),

('avg_classified_position','Average classified position',
 'Mean final classification across all entries. Lower is better.',
 'mean(position)', ARRAY['position'], 'career / season / circuit',
 'Retirements are included at their classified position, inflating the mean.',
 'Not a measure of pace. Biased upward by unreliability and by field size. Not comparable across eras without noting both.', NULL),

('median_classified_position','Median classified position',
 'The middle classification. Robust to a handful of extreme results.',
 'median(position)', ARRAY['position'], 'career / season',
 'Even sample sizes use the mean of the two central values.',
 'Read alongside the mean. A mean far above the median indicates occasional very poor classifications, typically retirements.', NULL),

('position_stdev','Finishing spread (standard deviation)',
 'Dispersion of classified positions. Lower means more repeatable results.',
 'sample standard deviation of position', ARRAY['position'], 'career / season',
 'Not reported below 5 entries.',
 'Low spread is not inherently good: a driver consistently classified 15th has a low spread. Retirements inflate spread, so this partly measures car reliability.', 5),

('win_rate','Win rate','Share of entries resulting in a win.','wins / entries',
 ARRAY['position'], 'career / season / circuit',
 'NULL when entries = 0; 0.0 when entries exist but no wins.',
 'Dominated by car competitiveness. Not a driver-skill measure.', 10),

('top10_rate','Top-10 rate','Share of entries classified in the top ten.',
 'COUNT(position <= 10) / entries', ARRAY['position'], 'career / season / circuit',
 'Applied uniformly across all seasons.',
 'Field sizes vary 20-24 across the period, so a top-10 finish is not equally difficult every season. Purely positional -- the dataset has no points column.', 10),

('teammate_h2h','Teammate head-to-head',
 'Across races where both drivers started for the same constructor, the share in which this driver was classified ahead. The closest available control for car performance.',
 'races classified ahead of teammate / races both classified',
 ARRAY['position','constructor_id','race_id'], 'driver pair within a constructor',
 'Only races where both drivers appear for that constructor are counted, so unequal season lengths and mid-season replacements cannot distort the ratio. Ties are impossible -- classification order is unique within a race.',
 'No finishing status exists, so a mechanical retirement counts as a loss. This systematically penalises the driver who suffered more failures, independently of pace. A results comparison, not a pace comparison.', 5),

('teammate_position_delta','Teammate position delta',
 'Average positions gained on the teammate. Positive means finishing ahead.',
 'mean(teammate position - own position) over shared races',
 ARRAY['position','constructor_id','race_id'], 'driver pair within a constructor',
 'Computed only over races both drivers were classified in.',
 'Inherits the retirement problem above and is sensitive to a few large gaps. Read with the head-to-head count, which is not distance-weighted.', 5),

('circuit_specialism','Circuit performance delta',
 'How much better (positive) or worse a driver''s classification is at one circuit than across their career.',
 'career avg classified position - avg classified position at circuit',
 ARRAY['position','circuit_id'], 'driver x circuit',
 'Requires at least 5 appearances at the circuit.',
 'Confounded with career timing: a circuit visited mainly during a driver''s strongest seasons shows a positive delta regardless of track-specific ability.', 5),

('season_dominance','Season win share',
 'Proportion of a season''s races won by one driver or constructor.',
 'wins / races held that season', ARRAY['position','race_id'], 'season',
 'Denominator is races actually held, which varies from 16 to 24.',
 'Normalised for calendar length but not grid size or regulation era. Points dominance cannot be computed -- the dataset has no points column.', NULL),

('driver_contribution','Driver contribution',
 'A driver''s share of their constructor''s entries, wins or podiums.',
 'driver results / constructor results', ARRAY['position','constructor_id'], 'constructor x driver',
 'Shares sum to 1.0 across the team''s drivers.',
 'Share of POINTS is not offered -- the source has no points column.', NULL)
ON CONFLICT (metric_key, version) DO UPDATE
  SET definition = excluded.definition, formula = excluded.formula,
      limitations = excluded.limitations;
