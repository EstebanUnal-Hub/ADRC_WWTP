(*
Short description
"""""""""""""""""
Error-based **active disturbance rejection controller (ADRC)** for a first-order plant (n = 1) with a
constant disturbance model (m = 1). A discrete extended state observer (ESO) estimates the tracking
error and the total disturbance; the control law cancels the disturbance and imposes a first-order
error dynamics with bandwidth WC.

.. note::
  | The error is defined as e_y = ACTUAL - SET_POINT.
  | TS must be equal to the period of the task that calls the block.
  | The gains are only computed in RESET: a change of WC, WO, B0 or TS takes effect after the next RESET.

Connection
""""""""""
The reference comes from |BEZIER_REF| or |PREFILTER_ADRC|; |PLANT| can replace the process for tests:

.. image:: /../ADRC/_Images/CFC_BEZIER_REF_ADRC_ESO.png

Theory
""""""
| The plant is written as an integrator chain on the error. Everything that is not b0 u (the plant
  dynamics, the load and the setpoint) goes into the total disturbance xi, which the ESO estimates and
  the control law cancels.
| The discrete version keeps the same dynamics: z_c and z_o are the images of the poles -WC and -WO.
| The observer always receives the applied order, so the block does not wind up at U_MIN or U_MAX.

.. image:: /../ADRC/_Images/EQ_ADRC_ESO.png

Structure of the error-based ADRC: the observer receives e_y and u0, and b0 only converts u0 into
the physical order u.

.. image:: /../ADRC/_Images/DIAG_ADRC_ESO.png

States
""""""
| **RESET** (RESET = TRUE, or no valid parameters yet): U = LIMIT(U_MIN, 0, U_MAX); the observer starts from x_hat = [0, -B0 U] and the gains are recomputed.
| **AUTOMATIC**: the control law is executed every cycle.
| Valid parameters: TS > 0, WC > 0, WO > WC and B0 > 0.

Example
"""""""
Tuning example (design plant G(s) = kdc/(tau s + 1), tau = 1200 s, kdc = 0.05 mg/(L %);
WC and WO in rad/s, B0 in mg/(L s %)):

::

  WC = 4/tau   = 0.00333
  WO = 5 WC    = 0.0167
  B0 = kdc/tau = 4.17E-5

Call with the setpoint prefilter (|BEZIER_REF| is used the same way):

::

  fbPrefilter(SET_POINT := lrSetPoint, ACTUAL := lrDO, WC := 0.00333, WO := 0.0167,
              TS := T#50MS, RESET := xReset);
  fbAdrc(SET_POINT := fbPrefilter.Y, ACTUAL := lrDO, WC := 0.00333, WO := 0.0167,
         B0 := 4.17E-5, TS := T#50MS, RESET := xReset);
  lrU := fbAdrc.U;

Modification - History
""""""""""""""""""""""
========   ========================================================================
Version:   1.1.0.0
Name   :   Manuel Esteban Peña Choachi
Date   :   2026-Nov-05
Comment:   - documentation with equations, block diagram and CFC connection

Version:   1.0.0.0
Name   :   Manuel Esteban Peña Choachi
Date   :   2026-Nov-05
Comment:   - 1st version
========   ========================================================================
*)
{attribute 'conditionalshow_all_locals'}
FUNCTION_BLOCK ADRC_ESO
VAR_INPUT
    SET_POINT : LREAL;              (* setpoint r *)
    ACTUAL    : LREAL;              (* measurement y *)
    WC        : LREAL;              (* controller bandwidth [rad/s] *)
    WO        : LREAL;              (* observer bandwidth [rad/s] *)
    B0        : LREAL;              (* plant input gain *)
    TS        : TIME := T#50MS;     (* sampling time, equal to the task period *)
    U_MIN     : LREAL := 0.0;
    U_MAX     : LREAL := 100.0;
    RESET     : BOOL := FALSE;
END_VAR
VAR_OUTPUT
    U         : LREAL;              (* control signal to the actuator *)
END_VAR
VAR CONSTANT
    ST_RESET     : INT := 0;
    ST_AUTOMATIC : INT := 1;
END_VAR
VAR
    T_S       : LREAL;              (* sampling time [s] *)
    State     : INT;
    Ready     : BOOL := FALSE;      (* valid gains available *)
    A         : ARRAY[1..2, 1..2] OF LREAL;
    B         : ARRAY[1..2] OF LREAL;
    C         : ARRAY[1..2] OF LREAL;
    L         : ARRAY[1..2] OF LREAL;
    K         : ARRAY[1..2] OF LREAL;
    X         : ARRAY[1..2] OF LREAL;   (* x_hat: estimated error and total disturbance *)
    X_old     : ARRAY[1..2] OF LREAL;
    Ey, Ey_old : LREAL;
    U0, U0_old : LREAL;
    Bo, Zc, Zo : LREAL;
END_VAR

(* state selection *)
IF RESET OR NOT Ready THEN
    State := ST_RESET;
ELSE
    State := ST_AUTOMATIC;
END_IF

(* sampling time in seconds *)
T_S := TIME_TO_LREAL(TS) / 1000.0;

(* gains are only updated outside AUTOMATIC *)
IF (State <> ST_AUTOMATIC) AND (T_S > 0.0) AND (WC > 0.0) AND (WO > WC) AND (B0 > 0.0) THEN
    Zc := EXP(-WC * T_S);
    Zo := EXP(-WO * T_S);
    A[1,1] := 1.0;   A[1,2] := T_S;
    A[2,1] := 0.0;   A[2,2] := 1.0;
    B[1]   := T_S;    B[2]   := 0.0;
    C[1]   := 1.0;   C[2]   := 0.0;
    L[1]   := 2.0 * (1.0 - Zo);
    L[2]   := (1.0 - Zo) * (1.0 - Zo) / T_S;
    K[1]   := (1.0 - Zc) / T_S;
    K[2]   := 1.0;
    Bo     := B0;
    Ready  := TRUE;
END_IF

(* observer: x_hat[k] = (A - L C) x_hat[k-1] + B u0[k-1] + L ey[k-1] *)
X[1] := (A[1,1] - L[1]*C[1])*X_old[1] + (A[1,2] - L[1]*C[2])*X_old[2] + B[1]*U0_old + L[1]*Ey_old;
X[2] := (A[2,1] - L[2]*C[1])*X_old[1] + (A[2,2] - L[2]*C[2])*X_old[2] + B[2]*U0_old + L[2]*Ey_old;

CASE State OF
ST_RESET:
    (* output and observer to zero, as if it had just started *)
    U    := LIMIT(U_MIN, 0.0, U_MAX);
    X[1] := 0.0;
    X[2] := -Bo * U;
    Ey   := 0.0;

ST_AUTOMATIC:
    (* control law: u0 = -K x_hat[k],  u = u0/b0 *)
    Ey := ACTUAL - SET_POINT;
    U0 := -(K[1]*X[1] + K[2]*X[2]);
    U  := LIMIT(U_MIN, U0 / Bo, U_MAX);
END_CASE

(* the observer always receives the applied order *)
U0 := Bo * U;

X_old  := X;
U0_old := U0;
Ey_old := Ey;
END_FUNCTION_BLOCK
