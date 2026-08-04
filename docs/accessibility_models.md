# Accessibility models -- to-do list

Roadmap for the accessibility models this tool should compute, once Layers
1-4 feed into a real function suite (see the "Suite of functions" item
below -- that's the prerequisite for everything else here). Each item notes
what it requires and how far a proven approach already got, before the old
one-off analysis scripts were archived (`archive/transportation-tool-
analysis-visualization-scripts/analysis/` next to this repo, kept for
reference while the new function suite gets designed).

## To-do, in priority order

- [ ] **Design the shared function suite** that brings Layers 1-4 together
      (one prep function per layer, a `Network` class, a routing/scoring
      split, and an `algorithm=` dispatcher). This replaces the archived
      one-off `analysis/` scripts with something reusable. Full design --
      including the schema decisions already made -- now lives in
      `docs/function_design.md`. Still design-only; no code written yet.
- [ ] **Cumulative Opportunity / Contour measure** -- count of opportunities
      reachable within a travel-time or distance threshold. Proven twice
      already in the archived scripts (straight-line and network-routed
      versions) -- porting it into the new function suite should be
      close to a direct copy once the suite exists.
- [ ] **Gravity-based accessibility** -- same idea, but closer opportunities
      count more (distance-decay weighting) instead of a hard threshold
      cutoff. Not built yet, but the lowest-effort real addition: it reuses
      the same origin-by-destination travel-time matrix the routing step
      already produces, just replacing "collapse to nearest/threshold" with
      "apply a decay function and sum." **Recommended as the first new model
      to build once the function suite exists.**
- [ ] **Two-Step Floating Catchment Area (2SFCA / E2SFCA / M2SFCA)** --
      balances destination capacity against competing population (a hospital
      surrounded by a huge population is a worse resource per person than
      the same hospital somewhere sparser, even at identical travel time).
      The real lift among these four: needs a new destination-side
      catchment-population computation, not just the origin-side
      computation the tool already does. Worth having as the answer to "why
      isn't this a standard academic accessibility measure" even before
      it's built.
- [ ] **Population-Weighted Distance (PWD)** -- one summary number per
      geography (e.g. "the average Massachusetts resident lives X minutes
      from the nearest hospital"), not a per-tract score. Effectively free
      once the function suite exists -- a population-weighted average over
      the same nearest-distance values the other models already use.

---

## Reference detail for each model

### 1. Cumulative Opportunity / Contour measure

**Formula:** `A_i = Σ o_j`, summed over every destination `j` reachable from
origin `i` within a travel-time or distance threshold `τ`.

**What it means:** a simple count -- "how many hospitals/schools/grocery
stores can this tract reach within 15 minutes (or 5 miles)."

**Citation:** Verma, R., Mittal, S., & Ukkusuri, S. V. (2025). "Spatial
Access of America: Multiple indicators of accessibility to opportunities."
*Scientific Data*, 12, 1223, Eq. 1. https://doi.org/10.1038/s41597-025-05440-8

### 2. Gravity-based accessibility

**Formula:** `A_i = Σ o_j · w_ij`, where `w_ij` is a distance-decay weight
(commonly `w_ij = exp(-β · t_ij)` or `1 / t_ij^n`) instead of a hard 0/1
threshold cutoff.

**What it means:** same idea as Cumulative Opportunity, but a hospital 2
minutes away contributes more to the score than one 14 minutes away (both
would count equally under a 15-minute threshold).

**Citation (synthesis + original formulation):** Luo, W., & Wang, F. (2003).
"Measures of spatial accessibility to health care in a GIS environment:
synthesis and a case study in the Chicago region." *Environment and Planning
B: Planning and Design*, 30(6), 865-884, Eq. (in "regional accessibility")
https://doi.org/10.1068/b29120
(Note: the file in `paper/Wang & Luo (2005).pdf` is mislabeled -- the paper
itself is Luo & Wang, 2003, not Wang & Luo, 2005.)
Also: Verma et al. (2025), Eq. 2 (same citation as above).

### 3. Two-Step Floating Catchment Area (2SFCA / E2SFCA / M2SFCA)

**Concept (two steps):**
1. For each *destination* (e.g. a hospital), compute a supply-to-demand
   ratio: `R_j = S_j / Σ(population within j's catchment)` -- how much
   capacity does this hospital have relative to everyone already competing
   for it.
2. For each *origin*, sum the `R_j` of every destination within *its own*
   catchment: `A_i = Σ R_j` for `j` reachable from `i`.

E2SFCA and M2SFCA are refinements that add distance-decay weighting inside
each step (the "enhanced"/"modified" versions) rather than a hard cutoff.

**Citation:** Luo, W., & Wang, F. (2003), as above (introduces the 2SFCA
distinction between "regional availability" and "regional accessibility").
Refinements (E2SFCA, M2SFCA) are discussed as one of several competition-based
methods in Verma et al. (2025).

### 4. Population-Weighted Distance (PWD)

**Formula:** for a geography (e.g. a whole state), `PWD = Σ(population_i ×
distance_i) / Σ(population_i)` -- the population-weighted average distance
to the nearest facility, across every origin in that geography.

**Citation:** Zhang, X., Lu, H., & Holt, J. B. (2011). "Modeling spatial
accessibility to parks: a national study." *International Journal of Health
Geographics*, 10, 31.

---

## Supporting / background citations

- Hansen, W. G. (1959). "How Accessibility Shapes Land Use." *Journal of the
  American Institute of Planners*, 25(2), 73-76. The foundational paper
  establishing accessibility as a place-based reachability measure. Not in
  `paper/`, useful for historical framing.
- Apparicio, P., Abdelmajid, M., Riva, M., & Shearmur, R. (2008). "Comparing
  alternative approaches to measuring the geographical accessibility of
  urban health services: Distance types and aggregation-error issues."
  *International Journal of Health Geographics*, 7, 7.
- Apparicio, P., Gelb, J., Dubé, A.-S., Kingham, S., Gauvin, L., & Robitaille,
  É. (2017). "The approaches to measuring the potential spatial access to
  urban health services revisited: distance types and aggregation-error
  issues." *International Journal of Health Geographics*, 16, 32.
