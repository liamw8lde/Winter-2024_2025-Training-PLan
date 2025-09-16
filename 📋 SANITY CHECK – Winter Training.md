📋 SANITY CHECK – Winter Training 

You are my auditor. 
step 1:audit the file and post results in chat.
step 2: repair all conflicts and output a CSV file in the same layout as the orginal file.

INPUT
- I will upload ONE Excel file (the plan) or CSV file , typically named trainplan_FIXED.xlsx.
- Use ONLY the plan + the rules below. Do NOT fetch anything else. No assumptions.

HOW TO PARSE THE PLAN
1) Prefer the sheet named “Spielplan”.
2) If missing, reconstruct from the “Herren 40–50–60” grid:
   - For each row (date), group players by identical slot code; emit one row per group.
   - Typ = Einzel if headcount = 2, otherwise Doppel if headcount = 4.
3) Slot code must match (else illegal):
   ^([DE])(\d{2}):(\d{2})-([0-9]+)\s+PL([AB])$
4) Headcount expectations: Einzel = 2, Doppel = 4.
5) Compute ISO week (Year + Week) for weekly rules and coverage.

ALLOWED SLOTS (STRICT)
- Montag
  - D20:00-120 PLA — Doppel
  - D20:00-120 PLB — Doppel
- Mittwoch
  - E18:00-60 PLA — Einzel (note: PLB at 18:00 is illegal)
  - E19:00-60 PLA — Einzel
  - E19:00-60 PLB — Einzel
  - D20:00-90 PLA — Doppel
  - D20:00-90 PLB — Doppel
- Donnerstag
  - E20:00-90 PLA — Einzel
  - E20:00-90 PLB — Einzel

WEEKLY COVERAGE (STRICT)
- For EACH ISO week, every allowed weekday/slot combination must appear EXACTLY ONCE.
- Missing or duplicate required slots = violation.

GLOBAL TIME RULES
- No starts after 20:00 (e.g., 20:30 is illegal).
- Wednesday doubles must be exactly 20:00 for 90 min.
- Duration/court must match the slot code.

PROTECTED PLAYERS (HARD)
- Patrick Buehrsch → 18:00 only.
- Frank Petermann → 19:00 or 20:00 only (never 18:00).
- Matthias Duddek → 18:00 or 19:00 only (never ≥20:00).
- Dirk Kistner → Mo/Mi/Do only; on Wednesday only 19:00 (never 18:00 or 20:00); max 2/week.
- Arndt Stüber → only Wednesday 19:00.
- Thommy/Thomas Grüneberg → start 18:00 or 19:00 70% of the time 30% wednesday 20:00 .
- Jens Hafner →  only Wednesday 19:00.

WOMEN & SINGLES (HARD)
- Women (Anke Ihde, Lena Meiß/Meiss, Martina Schmidt, Kerstin Baarck) must NOT play singles.
- Any female in singles = violation (mixed singles included).

MONDAY CORE SLOT (HARD): Montag D20:00–120 PLA
- No women at all (exception: Lena Meiß/Meiss allowed ONLY if Liam Wilde is also in the four).
- Mohamad Albadry is NEVER allowed.
- Core players be present: Martin Lange, Björn (Bjoern) Junker, (Frank Petermann, Lars Staubermann, Peter Plähn can be rotate evenly through).
  - If >1 core missing, or missing core not on holiday → violation.


ONE-PER-DAY (HARD)
- A player may not appear more than once per calendar date.

WEEKLY CAPS / SEASON CAPS / PREFERENCES
- Weekly caps:
  - Tobias Kahl: max 1/week
  - Dirk Kistner: max 2/week
  - Torsten Bartel: max 1/week
- Season caps:
  - Torsten Bartel: max 5/season
  - Frank Petermann: max 12/season (Monday PLA still counts toward this cap)
- Additional explicit weekday availability (PROMPT rules; these OVERRIDE Jotform):
  - Torsten Bartel: Mo/Mi/Do only; blocked dates below; 1/week; max 5/season.
  - Dirk Kistner: Mo/Mi/Do only (reinforced in Protected).
  - Arndt Stüber: only Wednesday (reinforced in Protected).
- If weekday availability isn’t defined here for a player, use the **Jotform availability** below.
- If a player is missing from both, do NOT enforce weekday availability for them (still enforce all other hard rules).

HOLIDAYS / BLACKOUTS (AUTHORITATIVE)
- Use ONLY the list below for holiday checks (merged prompt + Jotform; prompt wins on overlap).
- Monday PLA core exemption: in that slot ONLY, the core four are exempt from holiday checks (caps still apply).

<<START MERGED HOLIDAYS LIST>>
- Kerstin Baarck: 2025-09-01 → 2025-09-30.
- Lena Meiß/Meiss: (blocked up to and including 2025-09-20).
- Oliver Böss: 2025-09-01 → 2025-09-30; 2025-12-01; 2025-12-07; 2025-12-24 → 2025-12-25.
- Karsten/Carsten Gambal: 2025-11-12; 2025-11-13; 2025-12-24; 2025-12-29.
- Karsten Usinger: 2025-09-01 → 2025-09-30; 2025-12-31.
- Wolfgang Aleksik: 2025-09-16; 2025-09-18; 2025-10-14; 2025-11-25; 2025-11-27; 2025-12-09; 2025-12-11; 2025-12-23 → 2025-12-31.
- Jens Krause: 2025-09-24; 2025-09-26.
- Michael Rabehl: 2025-10-09 → 2025-10-12.
- Jens Hafner: 2025-10-23; 2025-10-30; 2025-12-24 → 2025-12-26.
- Bernd Sotzek: No holidays.
- Heiko Thomsen: 2025-09-15; 2025-10-10; 2025-11-12; 2025-12-03; 2025-12-17; 2025-12-22; 2025-12-24; 2025-12-26; 2025-12-31.
- Frank Petermann: 2025-09-08; 2025-09-14; 2025-10-13; 2025-10-25; 2025-12-01; 2025-12-07; 2025-12-24; 2025-12-31.
- Liam Wilde: 2025-12-24.
- Matthias Duddek: 2025-11-04 → 2025-11-10; 2025-12-24 → 2025-12-31.
- Anke Ihde: 2025-09-25.
- Arndt Stüber: 2025-10-16; 2025-10-31; 2025-11-17; 2025-11-23; 2025-12-15; 2025-12-31.
- Bernd Robioneck: 2025-12-01; 2025-12-08; 2025-12-22; 2026-01-04.
- Björn Junker: 2025-10-25; 2025-10-31; 2025-12-20; 2025-12-31.
- Frank Koller: 2025-10-10; 2025-10-31; 2025-12-18; 2026-01-05.
- Gunnar Brix: 2025-09-26; 2025-10-06; 2025-10-11; 2025-10-20; 2025-10-25; 2025-11-17; 2025-11-22; 2025-12-22; 2025-12-31.
- Jörg Peters: 2025-12-22; 2026-01-02.
- Jürgen Hansen: 2025-12-22; 2026-01-04.
- Kai Schröder: 2025-10-06; 2025-10-12; 2025-12-01; 2025-12-06; 2025-12-22; 2025-12-27.
- Markus Münch: 2025-10-13; 2025-10-19; 2025-12-22; 2026-01-04.
- Martin Lange: 2025-12-22; 2026-01-04.
- Martina Schmidt: 2025-11-08; 2025-11-22; 2026-01-01.
- Michael Bock: 2025-12-20; 2026-01-04.
- Patrick Buehrsch: 2025-11-01; 2025-11-30.
- Ralf Colditz: 2025-09-08; 2025-09-30; 2025-12-22; 2026-01-03.
- Sebastian Braune: 2025-10-20; 2025-10-30; 2025-12-28; 2026-01-06.
- Tobias Kahl: 2025-09-14; 2025-09-23; 2025-10-09; 2025-10-20; 2025-10-31; 2025-12-22; 2025-12-31.
- Torsten Bartel: 2025-09-15; 2025-09-24; 2025-09-29; 2025-11-19; 2025-11-24; 2025-12-17; 2025-12-22; 2025-12-25.
<<END MERGED HOLIDAYS LIST>>

WEEKDAY AVAILABILITY (JOTFORM) — USED WHEN NOT OVERRIDDEN ABOVE
- Apply the following **per-player day availability** (Mo/Di/Mi/Do/Fr/Sa/So).
- **Precedence:** Protected player rules and the explicit prompt availability (above) override whatever is written here. Only enforce these Jotform days when a player does not have an explicit prompt rule.
- If a player is missing from this list, do NOT enforce weekday availability for them.

<<START JOTFORM WEEKDAY AVAILABILITY LIST>>
- Andreas Dank: Montag, Mittwoch
- Anke Ihde: Montag, Mittwoch, Donnerstag
- Arndt Stüber: Mittwoch
- Bernd Robioneck: Mittwoch, Donnerstag
- Bernd Sotzek: Montag, Mittwoch
- Björn Junker: Montag
- Carsten Gambal: Montag, Mittwoch, Donnerstag
- Dirk Kistner: Montag, Mittwoch, Donnerstag
- Frank Koller: Mittwoch, Donnerstag
- Frank Petermann: Montag, Mittwoch, Donnerstag
- Gunnar Brix: Montag, Mittwoch, Donnerstag
- Heiko Thomsen: Mittwoch
- Jan Pappenheim: Montag, Mittwoch, Donnerstag
- Jens Hafner: Montag, Mittwoch
- Jens Krause: Mittwoch
- Jörg Peters: Mittwoch
- Jürgen Hansen: Mittwoch
- Kai Schröder: Mittwoch
- Karsten Usinger: Mittwoch, Donnerstag
- Kerstin Baarck: Montag, Donnerstag
- Lars Staubermann: Montag, Donnerstag
- Lena Meiß: Montag, Donnerstag
- Liam Wilde: Montag, Donnerstag
- Lorenz Kramp: Montag, Mittwoch
- Manfred Grell: Mittwoch, Donnerstag
- Markus Muench: Mittwoch, Sonntag
- MARTIN LANGE: Montag
- Martina Schmidt: Montag, Mittwoch, Donnerstag
- Matthias Duddek: Montag, Mittwoch, Donnerstag
- Michael Bock: Montag, Mittwoch
- Michael Rabehl: Montag, Donnerstag
- Mohamad Albadry: Montag
- Oliver Böss: Mittwoch, Donnerstag
- Patrick Buehrsch: Mittwoch, Donnerstag
- Peter Plähn: Montag
- Ralf Colditz: Mittwoch
- Sebastian Braune: Montag, Donnerstag
- Thomas Bretschneider: Donnerstag
- Thomas Grüneberg: Mittwoch, Donnerstag
- Tobias Kahl: Montag, Mittwoch
- Torsten Bartel: Montag, Mittwoch, Donnerstag
- Wolfgang Aleksik: Mittwoch
<<END JOTFORM WEEKDAY AVAILABILITY LIST>>

NAME NORMALIZATION (for matching)
- Lowercase; trim; collapse internal whitespace; remove zero-width/NBSP.
- Map diacritics: ä→ae, ö→oe, ü→ue, ß→ss (treat “oe/ae/ue” as equivalent to “ö/ä/ü”).
- Treat “Junker, Björn/Bjoern” as the same person.
- Use the normalized key for joins, rollups, and filtering.

OUTPUT
A) Sanity Summary (counts) — compact JSON with integers:
- headcount_errors; illegal_slot_codes; starts_after_20_00; wed_doubles_not_20_00;
- protected_time_violations; womens_singles; mixed_singles (optional);
- weekday_conflicts (only if availability defined); holiday_conflicts;
- only_doubles_in_singles; only_singles_in_doubles;
- weekly_cap_violations; season_cap_violations;
- overlaps_same_day; dirk_rules_violations;
- mon_pla_mohamad; mon_pla_woman; mon_pla_core;
- missing_required_weekly_slots;
- kerstin_target {player, planned_total, target=6, shortfall}.

B) Violations table (+ downloadable CSV):
- Columns: Datum | Tag | Slot | Typ | Spieler | Betroffene/r | Regel | Details
- One row per violation; “0 violations” if none.

C) Per-player weekly usage & caps (+ CSV):
- Spieler | Jahr | KW | Matches_in_KW | Cap | Over_Cap(Yes/No)
- If no cap: leave blank; Over_Cap = “No”.
- Season caps are reported in A.

D) Helpful tables (optional):
- Singles roster; Doubles roster; Players with >1 appearance on same date; Kerstin target check.

PARSING WARNINGS
- Report unreadable slot codes, unknown names, inconsistent date formats.

IMPORTANT
- Do NOT modify the uploaded file — check for conflicts then create new CSV file in the same format.
- Use ONLY this prompt + the uploaded plan.
- If weekday availability isn’t specified for a player in the prompt, enforce the Jotform days; otherwise, prompt rules win.
- All date logic uses ISO weeks.
