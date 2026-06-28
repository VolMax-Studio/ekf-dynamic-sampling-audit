import numpy as np

class BatteryEKF:
    def __init__(self, Ri, Rd, Cd, ocv_coeffs, capacity_Ah, Q_soc=1e-8, Q_vrc=1e-6, R_v=1e-4):
        """
        1st-order Equivalent Circuit Model (ECM) + Extended Kalman Filter (EKF).
        All parameters are fit on the specific cell dataset.
        
        Parameters:
        - Ri: Internal resistance (Ohm)
        - Rd: Charge transfer resistance (Ohm)
        - Cd: Double layer capacitance (F)
        - ocv_coeffs: Coefficients of OCV polynomial from p0 to p6 (ascending power)
        - capacity_Ah: Actual cell capacity at test temperature (Ah)
        - Q_soc: Process noise covariance for SOC
        - Q_vrc: Process noise covariance for Vrc
        - R_v: Measurement noise covariance for terminal voltage
        """
        self.Ri = Ri
        self.Rd = Rd
        self.Cd = Cd
        self.tau = Rd * Cd
        self.ocv_coeffs = ocv_coeffs
        self.Cn = capacity_Ah * 3600.0 # Capacity in Ampere-seconds (Coulombs)
        
        # Noise covariance matrices
        self.Q = np.array([
            [Q_soc, 0.0],
            [0.0, Q_vrc]
        ])
        self.R = R_v
        
        # State vector: [SOC, Vrc]^T
        # Initalize at None; will be set on first step or reset
        self.x = np.array([1.0, 0.0]) # Default start at SOC=100%, Vrc=0
        
        # State covariance matrix P
        self.P = np.array([
            [1e-4, 0.0],
            [0.0, 1e-4]
        ])
        
    def ocv_val(self, soc):
        """Compute OCV from SOC using the polynomial coefficients."""
        val = 0.0
        for i, coeff in enumerate(self.ocv_coeffs):
            val += coeff * (soc ** i)
        return val
        
    def ocv_deriv(self, soc):
        """Compute dOCV/dSOC (derivative of OCV with respect to SOC)."""
        deriv = 0.0
        for i, coeff in enumerate(self.ocv_coeffs):
            if i > 0:
                deriv += i * coeff * (soc ** (i - 1))
        return deriv
        
    def reset(self, initial_soc, initial_vrc=0.0):
        """Reset the EKF state and covariance."""
        self.x = np.array([initial_soc, initial_vrc])
        self.P = np.array([
            [1e-4, 0.0],
            [0.0, 1e-4]
        ])
        
    def predict(self, I, dt):
        """
        EKF State Prediction step.
        Parameters:
        - I: Current (A). Negative for discharge, positive for charge.
        - dt: Time step (s). Can be dynamic.
        """
        # State transition matrix A
        # Since SOC_k+1 = SOC_k + I_k * dt / Cn
        # Vrc_k+1 = exp(-dt/tau) * Vrc_k + Rd * (1 - exp(-dt/tau)) * I_k
        exp_factor = np.exp(-dt / self.tau)
        
        # Update states
        soc_pred = self.x[0] + (I * dt) / self.Cn
        # Clip SOC to physical bounds [0, 1]
        soc_pred = np.clip(soc_pred, 0.0, 1.0)
        
        vrc_pred = exp_factor * self.x[1] + self.Rd * (1.0 - exp_factor) * I
        
        self.x = np.array([soc_pred, vrc_pred])
        
        # Update covariance P_pred = A * P * A^T + Q
        # Jacobian A is [[1, 0], [0, exp_factor]]
        A = np.array([
            [1.0, 0.0],
            [0.0, exp_factor]
        ])
        
        self.P = A @ self.P @ A.T + self.Q * dt
        
    def update(self, V, I):
        """
        EKF State Measurement Update step.
        Parameters:
        - V: Measured terminal voltage (V)
        - I: Measured current (A)
        """
        # Measurement Jacobian H = [dOCV/dSOC, 1]
        dh_dsoc = self.ocv_deriv(self.x[0])
        H = np.array([[dh_dsoc, 1.0]])
        
        # Estimated voltage V_est = OCV(SOC) + I * Ri + Vrc
        V_est = self.ocv_val(self.x[0]) + I * self.Ri + self.x[1]
        
        # Innovation (error)
        y_tilde = V - V_est
        
        # Innovation covariance S = H * P * H^T + R
        S = H @ self.P @ H.T + self.R
        
        # Kalman Gain K = P * H^T * S^-1
        K = self.P @ H.T / S[0, 0]
        
        # Update state x = x + K * y_tilde
        self.x = self.x + K.flatten() * y_tilde
        self.x[0] = np.clip(self.x[0], 0.0, 1.0) # Clip SOC to [0, 1]
        
        # Update covariance P = (I - K * H) * P
        I_mat = np.eye(2)
        self.P = (I_mat - K @ H) @ self.P
        
        return V_est, float(y_tilde)
