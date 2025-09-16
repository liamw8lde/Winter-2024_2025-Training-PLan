📋 SANITY CHECK – Winter Training 

You are my auditor. 

step 1: Audit the file and post results in chat.  
step 2: Repair all conflicts and output a CSV file in the same layout as the orginal file.

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
- Thommy/Thomas Grüneberg → start 18:00 or 19:00 70% of the time 30% wednesday 20:00.
- Jens Hafner → only Wednesday 19:00.

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
(keep your full holidays list here unchanged)
<<END MERGED HOLIDAYS LIST>>

WEEKDAY AVAILABILITY (JOTFORM) — USED WHEN NOT OVERRIDDEN ABOVE
- Apply the following **per-player day availability** (Mo/Di/Mi/Do/Fr/Sa/So).
- **Precedence:** Protected player rules and the explicit prompt availability (above) override whatever is written here. Only enforce these Jotform days when a player does not have an explicit prompt rule.
- If a player is missing from this list, do NOT enforce weekday availability for them.

<<START JOTFORM WEEKDAY AVAILABILITY LIST>>
(keep your full availability list here unchanged)
<<END JOTFORM WEEKDAY AVAILABILITY LIST>>

PLAYER RANKS (AUTHORITATIVE)
Use this list as the single source of truth for player strength (1 = strongest, 6 = weakest).  
If a player is not listed, treat their rank as unknown and skip rank checks while emitting a parsing warning.

- Andreas Dank: 5
- Anke Ihde: 6
- Arndt Stueber: 5
- Bernd Robioneck: 5
- Bernd Sotzek: 3
- Bjoern Junker: 1
- Carsten Gambal: 4
- Dirk Kistner: 5
- Frank Koller: 4
- Frank Petermann: 2
- Gunnar Brix: 6
- Heiko Thomsen: 4
- Jan Pappenheim: 5
- Jens Hafner: 6
- Jens Krause: 2
- Joerg Peters: 2
- Juergen Hansen: 3
- Kai Schroeder: 4
- Karsten Usinger: 3
- Kerstin Baarck: 6
- Lars Staubermann: 2
- Lena Meiss: 6
- Liam Wilde: 3
- Lorenz Kramp: 4
- Manfred Grell: 4
- Markus Muench: 5
- Martin Lange: 2
- Martina Schmidt: 6
- Matthias Duddek: 3
- Michael Bock: 6
- Michael Rabehl: 6
- Mohamad Albadry: 5
- Oliver Boess: 3
- Patrick Buehrsch: 1
- Peter Plaehn: 2
- Ralf Colditz: 4
- Sebastian Braune: 6
- Thomas Bretschneider: 3
- Thomas Grueneberg: 2
- Tobias Kahl: 5
- Torsten Bartel: 5
- Wolfgang Aleksik: 6

RANK-BASED MATCH RULES
- Singles Rank Window (HARD):  
  For a singles match with players A and B: abs(rank[A] − rank[B]) ≤ 2.  
  Else: violation `singles_rank_window`.

- Doubles Balance (SOFT / Advisory):  
  For a doubles match with players {p1, p2, p3, p4}, with ranks sorted r1 ≤ r2 ≤ r3 ≤ r4:  
  Mark an advisory `doubles_unbalanced_advisory` if neither holds:  
  1) Similar quartet: r4 − r1 ≤ 2, OR  
  2) Two-strong vs two-weak: (r2 − r1 ≤ 1) AND (r4 − r3 ≤ 1) AND (r3 − r2 ≥ 2).  

  This is a recommendation only; it doesn’t block the plan or count as a violation.

Interaction with other rules
- Rank checks run only after basic legality checks.  
- Rank rules do not override any other HARD rules.  
- Unknown rank = skip check + parsing warning.

OUTPUT
A) Sanity Summary (counts) — compact JSON with integers:
- headcount_errors; illegal_slot_codes; starts_after_20_00; wed_doubles_not_20_00;
- protected_time_violations; womens_singles; mixed_singles (optional);
- weekday_conflicts; holiday_conflicts;
- only_doubles_in_singles; only_singles_in_doubles;
- weekly_cap_violations; season_cap_violations;
- overlaps_same_day; dirk_rules_violations;
- mon_pla_mohamad; mon_pla_woman; mon_pla_core;
- missing_required_weekly_slots;
- kerstin_target {player, planned_total, target=6, shortfall};
- singles_rank_window;
- doubles_unbalanced_advisory.

B) Violations table (+ downloadable CSV):
- Columns: Datum | Tag | Slot | Typ | Spieler | Betroffene/r | Regel | Details
- One row per violation; “0 violations” if none.

C) Per-player weekly usage & caps (+ CSV):
- Spieler | Jahr | KW | Matches_in_KW | Cap | Over_Cap(Yes/No)
- If no cap: leave blank; Over_Cap = “No”.

D) Helpful tables (optional):
- Singles roster; Doubles roster; Players with >1 appearance on same date; Kerstin target check.
- Advisory list of `doubles_unbalanced_advisory` matches with player ranks.

PARSING WARNINGS
- Report unreadable slot codes, unknown names, inconsistent date formats, unknown ranks.

IMPORTANT
- Do NOT modify the uploaded file — check for conflicts then create new training plan in a CSV file in the same layout.
- Use ONLY this prompt + the uploaded plan.
- All date logic uses ISO weeks.
