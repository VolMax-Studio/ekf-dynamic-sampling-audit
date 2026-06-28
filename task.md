# task.md — Independent Audit: Yun et al. 2025 (WEVJ 16, 587)

**Target:** Yun, S.; Jeon, J.; Lee, E.; Jeong, T.; Kim, S. *FPGA Implementation of
Battery State-of-Charge Estimation Using Extended Kalman Filter and Dynamic Sampling.*
World Electr. Veh. J. **2025**, 16, 587. https://doi.org/10.3390/wevj16100587 (CC-BY 4.0)

**Verdict target (P10):** one of {supported, artifact, unfalsifiable-as-stated} for the
claim *"dynamic sampling gives 99.65% sample reduction at RMSE < 0.75%."*

**The finding we are testing (fixed — do not drift):**
> Safe Δt is strictly profile-dependent and collapses with load dynamics. The paper's
> adaptation is bound to SOC-level, not to current-signal bandwidth — the wrong axis.
> The 99.65% reduction is an artifact of the quasi-static C/200 profile, not a property
> of the method.

We do **NOT** claim "their 1000 s / 99.65% number is wrong." We show the reduction is
profile-dependent and derive the safe-Δt-vs-dynamics curve.

---

## HARD RULES (apply to every stage — these are the product)

- **R1 — No "Nyquist."** The divergence mechanism is temporal-discretization /
  model-mismatch: when Δt exceeds the load time constant, the ECM linearization over the
  step is invalid, the Coulomb-count prediction integrates an averaged/wrong current, and
  the EKF update arrives too late to correct → covariance grows / estimate diverges.
  Name it this way. The word "Nyquist" does not appear in code comments or report.
- **R2 — Error is always vs. independent ground truth.** Every reported error is vs. the
  dataset's Coulomb-count true SOC, NEVER vs. our own full-rate EKF. (Measuring vs. our
  own full-rate run = the exact conflation we are auditing in them. Forbidden.)
- **R3 — ECM re-fit on the actual cell.** Ri, Rd, Cd, and the OCV-SOC curve are fit on
  the chosen dataset's cell. We do NOT carry Yun's parameters onto another cell. Label
  everywhere: "ECM re-fit on [cell] from [dataset]; Yun parameters not used."
- **R4 — NMC, not LFP.** Use an NMC drive-cycle cell (close to their 21700-50E chemistry).
  LFP's flat 40–80% OCV-SOC plateau weakens EKF observability and would cause divergence
  independent of sampling — that confounds the cause. If only LFP is available, STOP and
  flag; do not silently proceed.
- **R5 — Apples-to-apples on Δt.** Do NOT mechanically paste "1000 s" onto a 3000 s
  profile (trivial, dishonest — three samples total). Derive safe Δt as a function of
  load dynamics; show it lands ~1000 s on C/200 (reproducing them) and falls to ~seconds
  on dynamic profiles. The number is an output, not an input.
- **R6 — Every figure regenerates from one script into one results file.** No hand-typed
  metrics in the report. If it doesn't regenerate, it doesn't ship.
- **R7 — FPGA is out of scope, stated up front.** No claims about LE/FF/DSP, MHz, power,
  or the DE2-115 board. We audit the estimator + sampling claim only. Report leads with
  this boundary.

---

## Stage 0 — Provenance & data sanity
- [x] Fetch chosen NMC drive-cycle dataset (Kollmeyer LG or equivalent); record exact
      source URL, cell, capacity, license in `data/PROVENANCE.md`.
- [x] Confirm dataset provides: I(t), V(t), T, and a Coulomb-count reference SOC.
- [x] **GATE 0:** if no independent true-SOC reference exists → STOP. Without R2 ground
      truth there is no audit. Do not fabricate a reference from our own EKF.
- [x] **GATE 0b:** Calculate the SOC reference by dividing with the actual discharged capacity
      for that specific cycle and temperature, not the 3.0 Ah catalog nominal capacity. Record
      the actual capacity used in `data/PROVENANCE.md`.

## Stage 1 — ECM + EKF core (re-fit, verified)
- [x] Implement 1st-order ECM + EKF (their Eq. 1–13 structure; cite, paraphrase, don't copy).
- [x] Re-fit Ri/Rd/Cd/OCV-SOC on the dataset cell (R3). Log fitted params + fit residuals.
- [x] **GATE 1b:** Perform ECM re-fitting and evaluation at the SAME temperature. Primary analysis is at 25°C.
      Cross-temperature tests go only into a secondary robustness section.
- [x] Sanity: full-rate (1 s) EKF tracks true SOC within a sane band on a held-out segment.
- [x] **GATE 1:** full-rate EKF RMSE vs. true SOC must be reasonable (e.g. < ~2–3%) BEFORE
      any sub-sampling test. If the baseline itself is broken, every downstream number is
      noise. (Echo of the HALO base-R² discipline: prove the floor before the ceiling.)

## Stage 2 — Reproduce the quasi-static regime (their home turf)
- [ ] Construct/obtain a C/200-class slow discharge (≈their 700k s profile).
- [ ] Apply their rule (>30% → 1000 s; ≤30% → 100 s).
- [ ] **GATE 2:** sub-sampled EKF must ≈ match full-rate EKF here (reproduce their sub-1%).
      If we CANNOT reproduce their good result on quasi-static data, the bug is ours —
      fix before touching dynamic profiles. (We must reproduce them before we critique them.)

## Stage 3 — Dynamic-load evaluation (the real test)
- [ ] Run EKF + their sampling rule on DST / FUDS / US06 (NMC cell, re-fit ECM).
- [ ] Error vs. true SOC only (R2). Plot estimation error + EKF covariance trace over time.
- [ ] Show whether/where the estimate diverges or covariance explodes.
- [ ] Attribute divergence to the R1 mechanism explicitly (Δt vs. load time constant),
      with the actual numbers (step Δt, current slew within a step, resulting integral error).

## Stage 4 — The load-bearing deliverable: safe-Δt curve
- [ ] Sweep Δt; characterize **max safe Δt as a function of load bandwidth / SOC-rate**.
- [ ] Show: safe Δt ≈ 1000 s on C/200 (reproduces them) → ≈ seconds on dynamic load.
- [ ] State the structural point: their adaptation keys on SOC-level, but the variable
      that governs estimator stability is signal bandwidth — uncorrelated with SOC level.
      A transient at 80% SOC is as hard as one at 20%. **The adaptation optimizes the
      wrong axis.**

## Stage 5 — Report (`yun_audit_report.md`)
- [ ] Lead with scope boundary (R7) and the RMSE-conflation clarification (proposed-vs-full,
      not vs-true).
- [ ] State limitations of OUR reproduction first (re-fit cell ≠ their exact cell; our ECM;
      constructed quasi-static profile), then the finding.
- [ ] Verdict per claim: quasi-static reduction = **supported on that regime**; the
      generalized "for EV BMS" framing = **artifact of the quasi-static profile**.
- [ ] Generous citation of Yun et al. (DOI). Frame: independent replication with open
      questions, burden on our reproduction — not impugning their integrity.
- [ ] Every number traces to `results/yun_audit_metrics.json` (R6).

---

## Files
- `yun_audit_ekf.py` — ECM + EKF + dynamic-sampling engine
- `reproduce_yun_audit.py` — pulls public data, runs quasi-static + dynamic grid, writes JSON + plots
- `results/yun_audit_metrics.json` — single source of every reported number
- `data/PROVENANCE.md` — dataset source, cell, license
- `yun_audit_report.md` — final report

## Done = 
GATE 0–2 green, dynamic divergence shown vs. true SOC with the R1 mechanism named,
safe-Δt curve produced, report leads with limitations + scope, every figure regenerates.
