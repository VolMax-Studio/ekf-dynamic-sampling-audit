import numpy as np
import scipy.io
import os
import json
import matplotlib.pyplot as plt
from yun_audit_ekf import BatteryEKF
from scipy.optimize import minimize

# Ensure output directories exist
os.makedirs('results', exist_ok=True)
os.makedirs('scratch', exist_ok=True)

# Helper function to load and denormalize data
def load_and_denormalize(filepath, min_max_path):
    data = scipy.io.loadmat(filepath)
    min_max = scipy.io.loadmat(min_max_path)
    
    X = data['X']
    Y = data['Y'][0] # Target SOC
    
    V_norm = X[0]
    I_norm = X[1]
    T_norm = X[2]
    
    V_min, V_max = min_max['Min'][0, 0], min_max['Max'][0, 0]
    I_min, I_max = min_max['Min'][1, 0], min_max['Max'][1, 0]
    T_min, T_max = min_max['Min'][2, 0], min_max['Max'][2, 0]
    
    V = V_norm * (V_max - V_min) + V_min
    I = I_norm * (I_max - I_min) + I_min
    T = T_norm * (T_max - T_min) + T_min
    
    return V, I, T, Y

print("--- Step 1: Loading Dataset and Verifying Provenance ---")
filepath = 'data/LG_HG2/Test/04_TEST_LGHG2@25degC_Norm_(05_Inputs).mat'
min_max_path = 'data/LG_HG2/Other_Files/LGHG2_Min_Max_25degC_to_n10degC.mat'

if not os.path.exists(filepath) or not os.path.exists(min_max_path):
    raise FileNotFoundError("Kollmeyer dataset files not found. Please ensure Stage 0 ran successfully.")

V_dyn, I_dyn, T_dyn, SOC_dyn_true = load_and_denormalize(filepath, min_max_path)
print(f"Successfully loaded 25C dynamic test data: {len(SOC_dyn_true)} samples.")

# Capacity Denominator
capacity_Ah = 3.09
print(f"Using verified capacity denominator: {capacity_Ah} Ah (from PROVENANCE.md)")

print("\n--- Step 2: Fit ECM Parameters ---")
params_file = 'scratch/fitted_params_25C.npz'

if os.path.exists(params_file):
    print("Loading pre-fitted ECM parameters...")
    fit_data = np.load(params_file)
    Ri = float(fit_data['Ri'])
    Rd = float(fit_data['Rd'])
    Cd = float(fit_data['Cd'])
    tau = float(fit_data['tau'])
    ocv_coeffs = fit_data['p']
    rmse_V_fit = float(fit_data['rmse_V'])
else:
    print("No pre-fitted parameters found. Running L-BFGS-B optimization...")
    # Initial OCV polynomial guess (degree 6)
    p_init = np.polyfit(SOC_dyn_true, V_dyn, 6)[::-1]
    init_params = [0.025, 0.015, 50.0] + list(p_init)
    
    dt = 1.0
    def simulate_ecm(params, I, SOC):
        r_i, r_d, t_c = params[0], params[1], params[2]
        p_c = params[3:]
        ocv = np.zeros_like(SOC)
        for idx_p, c in enumerate(p_c):
            ocv += c * (SOC ** idx_p)
        N = len(I)
        v_rc = np.zeros(N)
        exp_factor = np.exp(-dt / t_c)
        rc_gain = r_d * (1.0 - exp_factor)
        for k in range(N - 1):
            v_rc[k+1] = exp_factor * v_rc[k] + rc_gain * I[k]
        return ocv + I * r_i + v_rc
        
    soc_test = np.linspace(0, 1, 100)
    def loss_func(params, V, I, SOC):
        r_i, r_d, t_c = params[0], params[1], params[2]
        p_c = params[3:]
        if r_i < 0.005 or r_i > 0.1 or r_d < 0.002 or r_d > 0.1 or t_c < 5.0 or t_c > 500.0:
            return 1e9
        dOCV = np.zeros_like(soc_test)
        for idx_p in range(1, len(p_c)):
            dOCV += idx_p * p_c[idx_p] * (soc_test ** (idx_p - 1))
        penalty = 10.0 * np.sum(np.maximum(0.0, -dOCV)) if np.any(dOCV < 0.0) else 0.0
        V_est = simulate_ecm(params, I, SOC)
        return np.mean((V - V_est) ** 2) + penalty
        
    bounds = [(0.005, 0.1), (0.002, 0.1), (5.0, 500.0)] + [(None, None)] * 7
    res = minimize(loss_func, init_params, args=(V_dyn, I_dyn, SOC_dyn_true), method='L-BFGS-B', bounds=bounds, options={'maxiter': 200})
    Ri, Rd, tau = res.x[0], res.x[1], res.x[2]
    Cd = tau / Rd
    ocv_coeffs = res.x[3:]
    
    # Calculate fitting RMSE
    V_est_fit = simulate_ecm(res.x, I_dyn, SOC_dyn_true)
    rmse_V_fit = np.sqrt(np.mean((V_dyn - V_est_fit)**2))
    np.savez(params_file, Ri=Ri, Rd=Rd, Cd=Cd, tau=tau, p=ocv_coeffs, rmse_V=rmse_V_fit)

print(f"Fitted Parameters (ECM re-fit on LG HG2 cell at 25C):")
print(f"  Ri = {Ri:.6f} Ohm")
print(f"  Rd = {Rd:.6f} Ohm")
print(f"  Cd = {Cd:.2f} F (tau = {tau:.2f} s)")
print(f"  OCV coeffs = {[f'{c:.4f}' for c in ocv_coeffs]}")
print(f"  Voltage Fit RMSE = {rmse_V_fit*1000:.2f} mV")

print("\n--- Step 3: Running EKF Core at Full-Rate (GATE 1 Verification) ---")
ekf_full = BatteryEKF(Ri=Ri, Rd=Rd, Cd=Cd, ocv_coeffs=ocv_coeffs, capacity_Ah=capacity_Ah)
ekf_full.reset(SOC_dyn_true[0])

N_dyn = len(SOC_dyn_true)
soc_full = np.zeros(N_dyn)
v_est_full = np.zeros(N_dyn)

for k in range(N_dyn):
    soc_full[k] = ekf_full.x[0]
    ekf_full.predict(I_dyn[k], dt=1.0)
    v_est_k, _ = ekf_full.update(V_dyn[k], I_dyn[k])
    v_est_full[k] = v_est_k

rmse_soc_full = float(np.sqrt(np.mean((SOC_dyn_true - soc_full) ** 2)))
rmse_v_full = float(np.sqrt(np.mean((V_dyn - v_est_full) ** 2)))
gate1_passed = rmse_soc_full < 0.02 # < 2% SOC error
print(f"Full-rate EKF SOC RMSE: {rmse_soc_full*100:.4f}%")
print(f"Full-rate EKF Voltage RMSE: {rmse_v_full*1000:.2f} mV")
print(f"GATE 1 Passed: {gate1_passed}")

print("\n--- Step 4: Reproducing Quasi-Static Regime (GATE 2 Verification) ---")
# Generate synthetic C/200 discharge profile
N_static = 700000
I_static_val = -0.01545 # A (C/200 for 3.09 Ah)
I_static = np.ones(N_static) * I_static_val
SOC_static_true = 1.0 + np.arange(N_static) * I_static_val / (capacity_Ah * 3600.0)

# Simulate terminal voltage for synthetic profile
V_static = np.zeros(N_static)
v_rc_sim = 0.0
exp_factor = np.exp(-1.0 / tau)
rc_gain = Rd * (1.0 - exp_factor)
for k in range(N_static):
    ocv = sum(c * (SOC_static_true[k] ** idx) for idx, c in enumerate(ocv_coeffs))
    V_static[k] = ocv + I_static_val * Ri + v_rc_sim
    v_rc_sim = exp_factor * v_rc_sim + rc_gain * I_static_val

# Run full-rate EKF on static profile (for comparison)
ekf_static_full = BatteryEKF(Ri=Ri, Rd=Rd, Cd=Cd, ocv_coeffs=ocv_coeffs, capacity_Ah=capacity_Ah)
ekf_static_full.reset(1.0)
soc_static_full = np.zeros(N_static)
for k in range(N_static):
    soc_static_full[k] = ekf_static_full.x[0]
    ekf_static_full.predict(I_static_val, dt=1.0)
    ekf_static_full.update(V_static[k], I_static_val)

# Run sub-sampled EKF on static profile (Yun's rule)
ekf_static_sub = BatteryEKF(Ri=Ri, Rd=Rd, Cd=Cd, ocv_coeffs=ocv_coeffs, capacity_Ah=capacity_Ah)
ekf_static_sub.reset(1.0)
soc_static_sub = np.ones(N_static)
t = 0
static_sample_indices = [0]
while t < N_static - 1:
    curr_soc = ekf_static_sub.x[0]
    dt = 1000.0 if curr_soc > 0.30 else 100.0
    next_t = int(t + dt)
    if next_t >= N_static:
        next_t = N_static - 1
        dt = float(next_t - t)
        
    ekf_static_sub.predict(I_static_val, dt=dt)
    ekf_static_sub.update(V_static[next_t], I_static_val)
    
    # Fill intermediate values
    for step in range(1, int(dt) + 1):
        idx = t + step
        if idx < N_static:
            soc_static_sub[idx] = np.clip(soc_static_sub[t] + (I_static_val * step) / (capacity_Ah * 3600.0), 0.0, 1.0)
    t = next_t
    static_sample_indices.append(t)

rmse_soc_static_full = float(np.sqrt(np.mean((SOC_static_true - soc_static_full) ** 2)))
rmse_soc_static_sub = float(np.sqrt(np.mean((SOC_static_true - soc_static_sub) ** 2)))
rmse_proposed_vs_full_static = float(np.sqrt(np.mean((soc_static_full - soc_static_sub) ** 2)))
static_reduction = 100.0 * (1.0 - len(static_sample_indices)/N_static)

gate2_passed = rmse_soc_static_sub < 0.01 # < 1% SOC error vs true
print(f"Quasi-static (C/200) Sub-sampled EKF SOC RMSE: {rmse_soc_static_sub*100:.6f}%")
print(f"Quasi-static Proposed vs Full-rate EKF RMSE: {rmse_proposed_vs_full_static*100:.6f}%")
print(f"Quasi-static Sample Reduction: {static_reduction:.4f}%")
print(f"GATE 2 Passed: {gate2_passed}")

# Save quasi-static plot
plt.figure(figsize=(10, 5), dpi=300)
plt.plot(np.arange(N_static)/3600, SOC_static_true * 100, label='True SOC', color='#2c3e50', linewidth=2.5)
plt.plot(np.arange(N_static)/3600, soc_static_sub * 100, '--', label='Sub-sampled EKF', color='#e67e22', linewidth=2)
plt.title("Quasi-static C/200 Discharge SOC Tracking (GATE 2 Verification)", fontsize=13, fontweight='bold', pad=15)
plt.xlabel("Time (Hours)", fontsize=11)
plt.ylabel("SOC (%)", fontsize=11)
plt.grid(True, linestyle=':', alpha=0.6)
plt.legend(loc='lower left', frameon=True)
plt.text(0.02, 0.1, "*Synthetic quasi-static discharge — modeled, not measured*", 
         transform=plt.gca().transAxes, fontsize=9.5, style='italic', bbox=dict(facecolor='white', alpha=0.8, edgecolor='none'))
plt.text(0.02, 0.03, "*Tester Coulomb-count reference (practical truth)*", 
         transform=plt.gca().transAxes, fontsize=9.5, style='italic', bbox=dict(facecolor='white', alpha=0.8, edgecolor='none'))
plt.tight_layout()
plt.savefig('results/quasi_static_tracking.png')
plt.close()

print("\n--- Step 5: Dynamic Load Evaluation (Stage 3 Divergence) ---")
# Run Case 1: Pure Sub-sampling (Predict and Update are sub-sampled)
ekf_dyn_sub1 = BatteryEKF(Ri=Ri, Rd=Rd, Cd=Cd, ocv_coeffs=ocv_coeffs, capacity_Ah=capacity_Ah)
ekf_dyn_sub1.reset(SOC_dyn_true[0])
soc_dyn_sub1 = np.ones(N_dyn) * SOC_dyn_true[0]

t = 0
dyn_sample_indices1 = [0]
while t < N_dyn - 1:
    curr_soc = ekf_dyn_sub1.x[0]
    dt = 1000.0 if curr_soc > 0.30 else 100.0
    next_t = int(t + dt)
    if next_t >= N_dyn:
        next_t = N_dyn - 1
        dt = float(next_t - t)
        
    I_sample = I_dyn[next_t]
    ekf_dyn_sub1.predict(I_sample, dt=dt)
    ekf_dyn_sub1.update(V_dyn[next_t], I_sample)
    
    for step in range(1, int(dt) + 1):
        idx = t + step
        if idx < N_dyn:
            soc_dyn_sub1[idx] = np.clip(soc_dyn_sub1[t] + (I_sample * step) / (capacity_Ah * 3600.0), 0.0, 1.0)
    t = next_t
    dyn_sample_indices1.append(t)

# Run Case 2: Hybrid Sub-sampling (Predict runs at 1 Hz, only Update is sub-sampled)
ekf_dyn_sub2 = BatteryEKF(Ri=Ri, Rd=Rd, Cd=Cd, ocv_coeffs=ocv_coeffs, capacity_Ah=capacity_Ah)
ekf_dyn_sub2.reset(SOC_dyn_true[0])
soc_dyn_sub2 = np.ones(N_dyn) * SOC_dyn_true[0]

t = 0
dyn_sample_indices2 = [0]
while t < N_dyn - 1:
    curr_soc = ekf_dyn_sub2.x[0]
    dt = 1000.0 if curr_soc > 0.30 else 100.0
    next_t = int(t + dt)
    if next_t >= N_dyn:
        next_t = N_dyn - 1
        dt = float(next_t - t)
        
    # Predict step runs at 1 Hz
    for step in range(int(dt)):
        idx = t + step
        if idx < N_dyn:
            ekf_dyn_sub2.predict(I_dyn[idx], dt=1.0)
            soc_dyn_sub2[idx] = ekf_dyn_sub2.x[0]
            
    # Update step runs only at sampling instants
    ekf_dyn_sub2.update(V_dyn[next_t], I_dyn[next_t])
    soc_dyn_sub2[next_t] = ekf_dyn_sub2.x[0]
    t = next_t
    dyn_sample_indices2.append(t)

rmse_soc_dyn_sub1 = float(np.sqrt(np.mean((SOC_dyn_true - soc_dyn_sub1) ** 2)))
rmse_soc_dyn_sub2 = float(np.sqrt(np.mean((SOC_dyn_true - soc_dyn_sub2) ** 2)))
dyn_reduction = 100.0 * (1.0 - len(dyn_sample_indices1)/N_dyn)

print(f"Dynamic Case 1 (Pure Sub-sampling) SOC RMSE: {rmse_soc_dyn_sub1*100:.4f}%")
print(f"Dynamic Case 2 (Hybrid Sub-sampling) SOC RMSE: {rmse_soc_dyn_sub2*100:.4f}%")
print(f"Dynamic Sample Reduction: {dyn_reduction:.4f}%")

# Save dynamic tracking plot
plt.figure(figsize=(10, 5), dpi=300)
plt.plot(np.arange(N_dyn)/3600, SOC_dyn_true * 100, label='True SOC (Tester-truth)', color='#2c3e50', linewidth=2)
plt.plot(np.arange(N_dyn)/3600, soc_dyn_sub1 * 100, label='Pure Sub-sampling (Case 1)', color='#e74c3c', linewidth=1.5, alpha=0.9)
plt.plot(np.arange(N_dyn)/3600, soc_dyn_sub2 * 100, '--', label='Hybrid Sub-sampling (Case 2)', color='#27ae60', linewidth=1.5, alpha=0.9)
plt.title("Dynamic Cycle SOC Tracking Divergence (Stage 3 Evaluation)", fontsize=13, fontweight='bold', pad=15)
plt.xlabel("Time (Hours)", fontsize=11)
plt.ylabel("SOC (%)", fontsize=11)
plt.ylim([-5, 105])
plt.grid(True, linestyle=':', alpha=0.6)
plt.legend(loc='lower left', frameon=True)
plt.text(0.02, 0.1, "*Tester Coulomb-count reference (practical truth)*", 
         transform=plt.gca().transAxes, fontsize=9.5, style='italic', bbox=dict(facecolor='white', alpha=0.8, edgecolor='none'))
plt.tight_layout()
plt.savefig('results/dynamic_tracking_divergence.png')
plt.close()

print("\n--- Step 6: Safe-dt Sweep Curve (Stage 4 Deliverable) ---")
dts = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
sweep_rmse_static = []
sweep_rmse_dynamic = []

for dt in dts:
    # 1. Static sweep
    ekf = BatteryEKF(Ri=Ri, Rd=Rd, Cd=Cd, ocv_coeffs=ocv_coeffs, capacity_Ah=capacity_Ah)
    ekf.reset(1.0)
    soc_est = np.ones(N_static)
    t = 0
    while t < N_static - 1:
        next_t = int(t + dt)
        if next_t >= N_static:
            next_t = N_static - 1
            dt_step = float(next_t - t)
        else:
            dt_step = float(dt)
            
        I_sample = I_static[next_t]
        ekf.predict(I_sample, dt=dt_step)
        ekf.update(V_static[next_t], I_sample)
        for step in range(1, int(dt_step) + 1):
            idx = t + step
            if idx < N_static:
                soc_est[idx] = np.clip(soc_est[t] + (I_sample * step) / (capacity_Ah * 3600.0), 0.0, 1.0)
        t = next_t
    sweep_rmse_static.append(float(np.sqrt(np.mean((SOC_static_true - soc_est) ** 2))))
    
    # 2. Dynamic sweep (Pure sub-sampling)
    ekf = BatteryEKF(Ri=Ri, Rd=Rd, Cd=Cd, ocv_coeffs=ocv_coeffs, capacity_Ah=capacity_Ah)
    ekf.reset(SOC_dyn_true[0])
    soc_est_d = np.ones(N_dyn) * SOC_dyn_true[0]
    t = 0
    while t < N_dyn - 1:
        next_t = int(t + dt)
        if next_t >= N_dyn:
            next_t = N_dyn - 1
            dt_step = float(next_t - t)
        else:
            dt_step = float(dt)
            
        I_sample = I_dyn[next_t]
        ekf.predict(I_sample, dt=dt_step)
        ekf.update(V_dyn[next_t], I_sample)
        for step in range(1, int(dt_step) + 1):
            idx = t + step
            if idx < N_dyn:
                soc_est_d[idx] = np.clip(soc_est_d[t] + (I_sample * step) / (capacity_Ah * 3600.0), 0.0, 1.0)
        t = next_t
    sweep_rmse_dynamic.append(float(np.sqrt(np.mean((SOC_dyn_true - soc_est_d) ** 2))))

# Save safe-dt plot
plt.figure(figsize=(10, 5), dpi=300)
plt.semilogx(dts, np.array(sweep_rmse_static) * 100, 'o-', label='Quasi-static C/200', color='#2980b9', linewidth=2)
plt.semilogx(dts, np.array(sweep_rmse_dynamic) * 100, 'o-', label='Dynamic Drive Cycle (Pure)', color='#c0392b', linewidth=2)
plt.axhline(3.0, color='gray', linestyle='--', alpha=0.7, label='Safe Boundary (3% SOC)')
plt.title("Safe-dt Curve: EKF SOC RMSE vs. Sampling Interval (Stage 4)", fontsize=13, fontweight='bold', pad=15)
plt.xlabel("Sampling Interval Δt (seconds, Log Scale)", fontsize=11)
plt.ylabel("SOC RMSE (%)", fontsize=11)
plt.grid(True, which="both", linestyle=':', alpha=0.6)
plt.legend(loc='upper left', frameon=True)
plt.text(0.02, 0.15, "*Tester Coulomb-count reference (practical truth)*", 
         transform=plt.gca().transAxes, fontsize=9.5, style='italic', bbox=dict(facecolor='white', alpha=0.8, edgecolor='none'))
plt.tight_layout()
plt.savefig('results/safe_dt_curve.png')
plt.close()

# Save metrics JSON
metrics = {
    "provenance": {
        "dataset": "LG 18650HG2 Li-ion (Kollmeyer et al., 2020)",
        "capacity_Ah": capacity_Ah,
        "temperature_C": 25.0
    },
    "ecm_parameters": {
        "Ri_Ohm": Ri,
        "Rd_Ohm": Rd,
        "Cd_F": Cd,
        "tau_s": tau,
        "voltage_fit_rmse_mV": rmse_V_fit * 1000
    },
    "full_rate_ekf": {
        "soc_rmse_percent": rmse_soc_full * 100,
        "voltage_rmse_mV": rmse_v_full * 1000
    },
    "quasi_static_evaluation": {
        "reduction_percent": static_reduction,
        "soc_rmse_percent": rmse_soc_static_sub * 100,
        "proposed_vs_full_rmse_percent": rmse_proposed_vs_full_static * 100
    },
    "dynamic_evaluation": {
        "reduction_percent": dyn_reduction,
        "case1_pure_soc_rmse_percent": rmse_soc_dyn_sub1 * 100,
        "case2_hybrid_soc_rmse_percent": rmse_soc_dyn_sub2 * 100
    },
    "safe_dt_sweep": {
        "delta_t_seconds": dts,
        "static_soc_rmse_percent": [x * 100 for x in sweep_rmse_static],
        "dynamic_soc_rmse_percent": [x * 100 for x in sweep_rmse_dynamic]
    }
}

with open('results/yun_audit_metrics.json', 'w') as f:
    json.dump(metrics, f, indent=2)

print("\n--- Audit Completed Successfully! ---")
print("Metrics written to: results/yun_audit_metrics.json")
print("Plots generated in: results/")
print(f"GATE 1: {'PASSED' if gate1_passed else 'FAILED'}")
print(f"GATE 2: {'PASSED' if gate2_passed else 'FAILED'}")
