# EKF Dynamic-Sampling Audit

**Independent reproduction and physical-boundary analysis of a published battery
SOC-estimation sampling scheme.**

> Audit target: Yun, S.; Jeon, J.; Lee, E.; Jeong, T.; Kim, S. *FPGA Implementation of
> Battery State-of-Charge Estimation Using Extended Kalman Filter and Dynamic Sampling.*
> World Electr. Veh. J. **2025**, 16, 587. https://doi.org/10.3390/wevj16100587 (CC-BY 4.0)
>
> This is an independent replication with open questions, not a refutation of the authors'
> integrity. The burden of proof is on **our** reproduction. The original work is cited
> generously throughout; its DOI stays with its authors. This audit carries its own DOI.

---

## Scope — read this first

**In scope (what this repo audits):** the *algorithmic* claim — that a dynamic sampling
rule (sample period keyed to SOC level) yields a ~99.65% reduction in samples while
holding SOC error low, on an EKF over a 1st-order ECM.

**Out of scope (explicitly not audited):** all FPGA / hardware claims — logic-element and
DSP utilization, clock frequency, the Terasic DE2-115 board, and any power-reduction
figure. We have no access to the authors' HDL, board, or bitstream, so we make **no claim**
about hardware results. Anyone citing this audit against the paper's hardware contribution
is misreading it.

---

## The finding (one sentence)

The reported sample reduction is a property of the **quasi-static C/200 discharge profile**
used to evaluate it, not of the method. Safe sampling interval Δt is governed by the
**bandwidth of the load current**, not by SOC level — so an adaptation keyed to SOC level
optimizes the wrong axis, and the scheme's stability does not transfer to dynamic EV loads.

*(Verdict per P10: quasi-static reduction — supported on that regime; the generalized
"for EV BMS real-time" framing — artifact of the evaluation profile.)*

---

## A clarification we document, not a gotcha

The abstract's "RMSE < 0.75" is the tracking error of the **proposed (sub-sampled) EKF vs.
the full-rate EKF** (the paper's Table 3: "EKF & Proposed EKF" = 0.7465), *not* the error
vs. true SOC. We verify and state this distinction plainly; it is easy to misread the
number as an absolute SOC accuracy, which it is not.

---

## Data & ground truth

**Dataset:** LG 18650HG2 Li-ion data, Kollmeyer et al., McMaster University (2020),
Mendeley Data, DOI 10.17632/cp3473x7xv.3. NMC chemistry (matches the target cell class;
avoids the flat-OCV observability confound that LFP would introduce).

**Ground truth = "practical truth."** The reference SOC is the dataset's tester
Coulomb-count integral (Digatron), normalized by the per-test discharged capacity
(**3.09 Ah at 25 °C**, see `data/PROVENANCE.md` for derivation and the SOC=0-at-end
consistency check). It is a high-precision tester reference, **not** an independent
capacity measurement — stated as such so no hidden conflation enters our own numbers.

**Two labels carried on every relevant figure:**
- `*Synthetic quasi-static discharge — modeled, not measured*` — the C/200 reproduction
  (GATE 2) is a constructed constant-low-current profile through our re-fit ECM, not a
  Kollmeyer measurement. Labeled everywhere it appears.
- `*Tester Coulomb-count reference (practical truth)*` — on every error plot.

---

## Method (what the scripts do)

1. **ECM + EKF**, 1st-order, re-fit on the LG HG2 cell at a fixed temperature
   (parameters Ri/Rd/Cd/OCV-SOC fit on this cell — the paper's parameters are **not**
   carried over). Primary analysis at **25 °C**; cold temperatures appear only in a
   separate robustness section to avoid temperature model-mismatch confounding the result.
2. **Dynamic sampling engine** implementing the paper's rule (>30% SOC → 1000 s;
   ≤30% → 100 s).
3. **Quasi-static reproduction (GATE 2):** synthetic C/200 → confirm sub-sampled EKF
   matches full-rate (reproduces the paper's good result *before* any critique).
4. **Dynamic evaluation:** EKF + sampling rule on real drive cycles; error vs. tester
   truth; covariance trace over time.
5. **Safe-Δt-facing deliverable:** max stable Δt as a function of load dynamics — the load-bearing
   deliverable.

**Divergence mechanism (named precisely — not "Nyquist"):** when Δt exceeds the load time
constant, the ECM linearization over the step is invalid and the Coulomb-count prediction
integrates an averaged/wrong current; the EKF update arrives too late to correct, so the
covariance grows and the estimate diverges. A temporal-discretization / model-mismatch
failure, not aliasing.

---

## Reproduce

```bash
python3 reproduce_yun_audit.py
```

Pulls the public dataset, runs the quasi-static and dynamic grid, and writes every reported
number to `results/yun_audit_metrics.json` plus the plots. No figure in this README or the
report is hand-typed; all regenerate from that script. If a number can't be regenerated, it
isn't claimed.

---

## Files

| File | Purpose |
|---|---|
| `yun_audit_ekf.py` | 1st-order ECM + EKF + dynamic-sampling engine |
| `reproduce_yun_audit.py` | data pull, quasi-static + dynamic runs, JSON + plots |
| `results/yun_audit_metrics.json` | single source of every reported number |
| `data/PROVENANCE.md` | dataset source, cell, license, capacity-denominator derivation |
| `yun_audit_report.md` | full audit report (leads with scope + limitations) |
| `task.md` | staged checklist with the P10 gates |

---

## Status

Pre-revenue independent audit. Method validated on public data by its author; not yet
independently reviewed. DOI minted only after the finding is final and the report leads
with its own limitations. Until then the git tag is the only marker — reversible by design.

## License

Code: see `LICENSE`. The audited paper is © its authors under CC-BY 4.0; cited, not
reproduced.
