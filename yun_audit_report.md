# Independent Audit Report: EKF Dynamic Sampling under Transient Load Profiles

**Audit Target:** Seungjae Yun, Jeongju Jeon, Eunseong Lee, Taeyeon Jeong, Sunhee Kim. *FPGA Implementation of Battery State-of-Charge Estimation Using Extended Kalman Filter and Dynamic Sampling.* World Electric Vehicle Journal **2025**, 16(10), 587. DOI: [10.3390/wevj16100587](https://doi.org/10.3390/wevj16100587).

---

## 1. Scope and Boundary of the Audit

This audit evaluates the **algorithmic stability and validity** of the dynamic sampling scheme proposed in the target paper. Specifically, we audit the claim that a dynamic sampling rule—where the sample interval $\Delta t$ is adaptively scaled based on the estimated State of Charge (SOC)—can achieve a **~99.65% reduction in sampling frequency** while maintaining an SOC estimation error **RMSE < 0.75%**.

### 1.1 Out of Scope
All hardware-specific claims in the target paper are **explicitly out of scope**. This includes:
*   Logic-element (LE), flip-flop (FF), and DSP block utilization figures on the Terasic DE2-115 FPGA board.
*   System clock frequencies (e.g., 38 MHz) and dynamic power reduction calculations (e.g., 44.7% power savings).
*   Any claims regarding the hardware synthesis of the Verilog HDL modules.

We make no claims regarding the validity or efficiency of the FPGA implementation, as we have no access to the authors' HDL code, bitstream, or hardware setup. This audit focuses strictly on the mathematical and estimator behavior of the EKF under sub-sampling.

---

## 2. Key Clarification: The "RMSE < 0.75%" Metric

A critical reading of the target paper reveals that the reported **RMSE < 0.75%** (specifically $0.7465\%$ in Table 3 of the paper) is the tracking error of the **proposed sub-sampled EKF vs. the full-rate EKF** ($E_{\text{tracking}} = SOC_{\text{sub}} - SOC_{\text{full}}$), and **not the absolute error of the SOC estimator vs. the true battery SOC** ($E_{\text{absolute}} = SOC_{\text{sub}} - SOC_{\text{true}}$). 

We document this distinction plainly to avoid the common conflation of tracking error with absolute estimation accuracy. Our audit measures and reports both metrics, comparing all estimators to the independent tester-truth reference.

---

## 3. Method and Model Verification

To ensure a rigorous replication, we implemented a 1st-order Equivalent Circuit Model (ECM) and Extended Kalman Filter (EKF) matching the mathematical structure of Equations 1–13 in the target paper.

### 3.1 Model Re-fitting (Compliance with R3)
In accordance with Rule R3, we did not use the model parameters reported by the authors (which were fit to a different Samsung 50E cell). Instead, we re-fitted the ECM parameters ($R_i$, $R_d$, $C_d$, and the $OCV(SOC)$ polynomial curve) specifically to the LG Chem INR18650-HG2 cell at $25^\circ\text{C}$ using the Mendeley public dataset (Kollmeyer et al., 2020). 

The L-BFGS-B gradient optimization yielded the following parameters with a terminal voltage fit RMSE of **16.45 mV** over a 13-hour dynamic test:
*   **$R_i$ (Internal Resistance):** $0.021158\ \Omega$ (21.16 m$\Omega$)
*   **$R_d$ (Polarization Resistance):** $0.029942\ \Omega$ (29.94 m$\Omega$)
*   **$C_d$ (Polarization Capacitance):** $1619.13\text{ F}$ (yielding a time constant $\tau = R_d C_d = 48.48\text{ s}$)
*   **$OCV(SOC)$ 6th-degree Polynomial Coeffs (ascending):** `[2.2915, 10.6734, -36.7658, 64.3589, -52.5415, 15.8962, 0.2778]`

### 3.2 Baseline Verification (GATE 1 and R2 Compliance)
Before performing any sub-sampling tests, we verified the baseline full-rate (1 Hz) EKF against the dataset's **tester Coulomb-count reference** (our ground truth, representing practical truth). 

*   **Baseline EKF SOC RMSE:** **0.8248%**
*   **Baseline EKF Voltage RMSE:** **6.48 mV**

Because the baseline EKF tracks the true SOC with an error well below the 2% threshold, **GATE 1 is successfully passed**, confirming that our baseline code is correct and stable.

---

## 4. Quasi-Static Replication (GATE 2 Verification)

To test the authors' home-turf claim, we generated a synthetic quasi-static C/200 discharge profile ($I_{\text{load}} = -15.45\text{ mA}$) spanning $700,000$ seconds (~194 hours) and simulated the voltage response through our fitted ECM. We then applied their dynamic sampling rule:
*   $\text{If } SOC > 30\% \rightarrow \Delta t = 1000\text{ s}$
*   $\text{If } SOC \le 30\% \rightarrow \Delta t = 100\text{ s}$

### 4.1 Replication Results
*   **Total samples at full-rate:** $700,000$
*   **Total samples under dynamic sampling:** $2,456$
*   **Sample reduction:** **99.6491%** (matching the paper's reported ~99.65% exactly)
*   **Sub-sampled EKF SOC RMSE (vs. true):** **0.0000%** ($1.84 \times 10^{-13}\%$)
*   **Proposed vs. Full-rate EKF RMSE (tracking error):** **0.0001%** ($0.000139\%$)

Under a quasi-static DC load, the dynamic sampling rule holds the estimation error near zero, successfully reproducing the paper's results. **GATE 2 is passed**.

![Quasi-static tracking](/home/volmax-studio/.gemini/antigravity/brain/706c8f28-84ae-40ca-b2e7-a0e0ac75ce73/.tempmediaStorage/results_quasi_static.png)
*Figure 1: SOC tracking under a synthetic quasi-static C/200 discharge profile, showing perfect tracking for both full-rate and sub-sampled EKFs.*

---

## 5. Dynamic Load Evaluation (Stage 3 Divergence)

We evaluated the dynamic sampling scheme on the **LG HG2 Mixed Drive Cycle at 25°C** (consisting of sequential standard cycles: UDDS, HWFET, LA92, and US06, spanning 47,517 samples or 13.2 hours). To ensure a fair evaluation and eliminate any "strawman" implementations, both EKF setups were implemented with:
1.  **Time-scaled Process Noise ($Q_k = Q_c \cdot \Delta t$):** The process noise covariance is dynamically scaled with the time step $\Delta t$ to reflect increased state uncertainty over long intervals.
2.  **Physical State Clamping:** The SOC state is strictly clamped to its physical bounds $[0.0, 1.0]$ in both the estimator updates and the intermediate state reconstruction to prevent unhandled overflow.

We evaluated two distinct implementation cases:

### 5.1 Case 1: Pure Sub-sampling (The Audited Claim)
Both the State Prediction (Coulomb counting) and Measurement Update steps of the EKF are sub-sampled. The microcontroller sleeps between sampling instants and performs a single EKF step using the current and voltage measured at the sampling instant.
*   **SOC RMSE (vs. true):** **24.8408%** (Severe estimation divergence)
*   **Sample Reduction:** **99.7159%**

### 5.2 Case 2: Hybrid Sub-sampling
The State Prediction (Coulomb counting) runs continuously at 1 Hz in the background to capture high-frequency current transients, while only the EKF Measurement Update (Kalman correction) is sub-sampled.
*   **SOC RMSE (vs. true):** **0.9266%** (Stable tracking)
*   **Sample Reduction (Update step only):** **99.7159%**

### 5.3 Divergence Analysis
The dynamic sampling scheme's failure under transient loads is governed by a **temporal-discretization and model-mismatch mechanism**. 

Under a dynamic profile, the current fluctuates rapidly on a second-to-second basis. In Case 1 (Pure Sub-sampling), when $\Delta t = 1000\text{ s}$, the EKF assumes that the current measured at the sampling instant $I(t_{k+1})$ remains constant over the entire 1000-second interval. This crude discretization integrates a highly biased current value, causing the state prediction to deviate immediately. 

Furthermore, the polarization RC voltage $V_{rc}$ has a time constant of $\tau \approx 48\text{ s}$. Under transient load, $V_{rc}$ fluctuates rapidly, but a large $\Delta t = 1000\text{ s}$ violates the linearization of the non-linear measurement equation. Even though the process noise covariance $Q$ is properly scaled and the state is physically clamped, the Kalman corrections push the estimator into positive feedback and divergence, yielding an unacceptably high **24.84% RMSE**.

In Case 2 (Hybrid Sub-sampling), stability is restored because Coulomb counting runs at 1 Hz, maintaining an accurate state prediction. However, **this case loses the advertised 99.65% CPU power savings**, as the microcontroller must remain active to measure current and execute prediction equations at 1 Hz.

![Dynamic tracking divergence](/home/volmax-studio/.gemini/antigravity/brain/706c8f28-84ae-40ca-b2e7-a0e0ac75ce73/.tempmediaStorage/results_dynamic.png)
*Figure 2: SOC tracking under the LG HG2 Mixed Drive Cycle profile at 25°C. Pure sub-sampling (Case 1) diverges with 24.84% RMSE, while Hybrid sub-sampling (Case 2) remains stable but requires continuous 1 Hz current integration.*

---

## 6. The Safe-Δt Curve (Stage 4 Deliverable)

To identify the physical boundaries of EKF sub-sampling, we swept the constant sampling interval $\Delta t$ from $1\text{ s}$ to $1000\text{ s}$ under both the quasi-static and dynamic profiles (using Pure Sub-sampling).

| Sampling Interval $\Delta t$ (s) | Quasi-static SOC RMSE (%) | Dynamic SOC RMSE (%) |
|:---:|:---:|:---:|
| 1 | 0.0000 | 2.3599 |
| 2 | 0.0000 | 2.0761 |
| 5 | 0.0000 | 4.7662 |
| 10 | 0.0000 | 7.3381 |
| 20 | 0.0000 | 7.8584 |
| 50 | 0.0000 | 8.8865 |
| 100 | 0.0000 | 11.5583 |
| 200 | 0.0000 | 17.3735 |
| 500 | 0.0000 | 22.8058 |
| 1000 | 0.0000 | 25.7989 |

![Safe dt curve](/home/volmax-studio/.gemini/antigravity/brain/706c8f28-84ae-40ca-b2e7-a0e0ac75ce73/.tempmediaStorage/results_safe_dt.png)
*Figure 3: Safe-dt curve showing SOC RMSE vs. Sampling Interval. For dynamic load profiles, the sampling interval must remain below 2 to 5 seconds to prevent the error from exceeding a 3% safe boundary, whereas quasi-static profiles allow arbitrary sub-sampling.*

### 6.1 Structural Conclusion
The safe sampling interval $\Delta t$ is strictly governed by the **bandwidth and transient dynamics of the load current**, not by the SOC level. Keying the sampling rate to the SOC level (e.g., slowing to 1000 s when SOC > 30%) optimizes the wrong axis. A transient current pulse at 80% SOC causes the same integration error and linearization mismatch as a pulse at 20% SOC. Therefore, the dynamic sampling rule proposed in the target paper is an artifact of the quasi-static profile used for its evaluation and is fundamentally unsuitable for real-world electric vehicle battery management systems.

---

## 7. Audit Verdict

Based on our independent replication and physical-boundary analysis:
*   The claimed 99.65% reduction in sampling frequency is **Supported** strictly on the **quasi-static C/200 discharge regime**.
*   The generalized application of this dynamic sampling scheme to real-time EV BMS applications is an **Artifact of the evaluation profile**. Under transient load profiles, the pure sub-sampling scheme **diverges and yields a critical error (RMSE of 24.84%)**, failing the absolute accuracy threshold.
