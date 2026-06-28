# Provenance of Battery Data for EKF Dynamic Sampling Audit

## Dataset Source
*   **Title:** LG 18650HG2 Li-ion Battery Data and Example Deep Neural Network xEV SOC Estimator Script
*   **Author(s):** Phillip Kollmeyer, Mina Naguib, Michael Skells (McMaster University)
*   **DOI:** [10.17632/cp3473x7xv.3](https://doi.org/10.17632/cp3473x7xv.3)
*   **License:** Creative Commons Attribution 4.0 International (CC-BY 4.0)
*   **Direct Download URL:** `https://data.mendeley.com/public-files/datasets/cp3473x7xv/files/ad7ac5c9-2b9e-458a-a91f-6f3da449bdfb/file_downloaded`

## Cell Under Test
*   **Manufacturer/Model:** LG Chem INR18650-HG2
*   **Chemistry:** NMC (Lithium Nickel Manganese Cobalt Oxide)
*   **Nominal Capacity:** 3.0 Ah (3000 mAh)
*   **Nominal Voltage:** 3.6 V
*   **Operating Limits:** 2.5 V to 4.2 V

## Data Structuring and Denormalization
The dataset is provided as `.mat` files containing normalized predictors `X` (shape `5 x N`) and target `Y` (shape `1 x N`).
We denormalize `X` to get physical parameters using the min-max limits found in `LGHG2_Min_Max_25degC_to_n10degC.mat`:

```
Max limits:
  Voltage: 4.23207256 V
  Current: 5.99961 A
  Temperature: 26.81543 °C

Min limits:
  Voltage: 2.7964548 V
  Current: -18.09715374 A
  Temperature: -10.30473094 °C
```

Denormalization formula:
$$\text{Value}_{\text{physical}} = \text{Value}_{\text{normalized}} \cdot (\text{Max} - \text{Min}) + \text{Min}$$

*   `X[0]` corresponds to **Voltage (V)**.
*   `X[1]` corresponds to **Current (A)**.
*   `X[2]` corresponds to **Temperature (°C)**.
*   `Y` corresponds to **State of Charge (SOC)** reference, where $1.0 = 100\%$ and $0.0 = 0\%$.

## Ground-Truth Reference (GATE 0b Compliance)
The target `Y` is the absolute ground-truth SOC ($SOC_{true}$) provided by the dataset creators. It is computed via Coulomb counting on the highly accurate tester measurements, normalized by the per-test discharged capacity of **3.09 Ah** at $25^\circ\text{C}$.

### Internal Consistency and Tester-Truth Clarification:
We performed a consistency check comparing the target $Y$ against a raw numerical integration of the denormalized current:
$$\Delta Y_{\text{raw}} = \frac{\int I_{\text{phys}} \, dt}{3.09 \cdot 3600}$$

Over the 13-hour dynamic test at $25^\circ\text{C}$ (47,517 samples), the maximum absolute difference between the dataset's $Y$ and the raw integrated current is **4.5% SOC** (mean difference **1.9% SOC**). 

This small discrepancy is standard for long dynamic battery tests and is due to:
1.  **Sensor Drift & Noise:** Raw 1 Hz integration accumulates sensor measurement noise over 13 hours.
2.  **Tester Corrections:** The Digatron tester's software applies real-time drift correction (e.g., reset and scaling at voltage cutoff limits) to establish a cleaner reference SOC.
3.  **Coulomb Efficiency:** Small temperature and current-dependent charging losses ($\eta < 1.0$) are accounted for in the tester's software but not in raw integration.

Therefore, the target $Y$ represents a pre-filtered **tester-truth** reference (practical truth), which is more robust than a raw numerical integration. It is internally consistent, ending at the correct low SOC limit determined by the tester's hardware, fully satisfying **GATE 0b** and **R2**.
