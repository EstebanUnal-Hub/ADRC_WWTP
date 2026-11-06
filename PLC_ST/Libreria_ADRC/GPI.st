(*
Short description
"""""""""""""""""
**Generalized proportional integral (GPI) controller** for a first-order plant (n = 1) with a
constant disturbance model (m = 1), tuned directly with its gains K0, K1 and K2. It is the same
controller as |ADRC_ESO|, written as a transfer function and with anti-windup.

.. note::
  | The block works with -e_y = SET_POINT - ACTUAL.
  | TS must be equal to the period of the task that calls the block.
  | The gains are only computed in RESET: a change of K0, K1, K2, B0 or TS takes effect after the next RESET.

Connection
""""""""""
The reference comes from |PREFILTER_GPI|; |PLANT| can replace the process for tests:

.. image:: /../ADRC/_Images/CFC_PREFILTER_GPI_GPI.png

Theory
""""""
| The GPI uses only the error, the order and their integrals, without an observer; with the gains of
  the example it has the same closed loop as |ADRC_ESO|.
| To avoid windup the controller is split in two filters: H2 receives the applied order u_sat, so
  when the actuator saturates the controller stops integrating. Without saturation, u_sat = v and the
  loop has the designed dynamics.

.. image:: /../ADRC/_Images/EQ_GPI.png

.. image:: /../ADRC/_Images/DIAG_GPI_DISCRETE.png

States
""""""
| **RESET** (RESET = TRUE, or no valid parameters yet): U = LIMIT(U_MIN, 0, U_MAX); the delays start from U.
| **AUTOMATIC**: the control law is executed every cycle.
| Valid parameters: TS > 0, B0 > 0, K0 > 0, K1 > 0, K2 > 0 and K2 K1 > K0.

Example
"""""""
Tuning example, equivalent to |ADRC_ESO| with WC = 0.00333 and WO = 0.0167 rad/s,
(s + WC)(s + WO)^2 = s^3 + K2 s^2 + K1 s + K0:

::

  K2 = WC + 2 WO      = 0.0367
  K1 = 2 WC WO + WO^2 = 3.89E-4
  K0 = WC WO^2        = 9.26E-7

Call with the setpoint prefilter:

::

  fbPrefilter(SET_POINT := lrSetPoint, ACTUAL := lrDO, K0 := 9.26E-7, K1 := 3.89E-4,
              TS := T#50MS, RESET := xReset);
  fbGpi(SET_POINT := fbPrefilter.Y, ACTUAL := lrDO, K0 := 9.26E-7, K1 := 3.89E-4, K2 := 0.0367,
        B0 := 4.17E-5, TS := T#50MS, RESET := xReset);
  lrU := fbGpi.U;

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
FUNCTION_BLOCK GPI
VAR_INPUT
    SET_POINT : LREAL;              (* setpoint r *)
    ACTUAL    : LREAL;              (* measurement y *)
    K0        : LREAL;              (* GPI gains: (k1 s + k0)/(s (s + k2)) *)
    K1        : LREAL;
    K2        : LREAL;
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
    Bo, D0, Q : LREAL;
    A1, A2    : LREAL;              (* common denominator of H1 and H2 *)
    B0z, B1z, B2z : LREAL;          (* numerator of H1 *)
    G0, G1, G2    : LREAL;          (* numerator of H2 *)
    E, E_1, E_2   : LREAL;          (* r - y and its delays *)
    V, V_1, V_2   : LREAL;
    U_1, U_2, W   : LREAL;
END_VAR

(* state selection *)
IF RESET OR NOT Ready THEN
    State := ST_RESET;
ELSE
    State := ST_AUTOMATIC;
END_IF

(* sampling time in seconds *)
T_S := TIME_TO_LREAL(TS) / 1000.0;

(* gains are only updated outside AUTOMATIC, and only if they are stable *)
IF (State <> ST_AUTOMATIC) AND (T_S > 0.0) AND (B0 > 0.0) AND (K0 > 0.0) AND (K1 > 0.0)
        AND (K2 > 0.0) AND (K2 * K1 > K0) THEN
    (* Tustin with E1(s) = s^2 + k2 s + k1 *)
    Q   := K1 * T_S * T_S;
    D0  := 4.0 + 2.0 * K2 * T_S + Q;
    A1  := (2.0 * Q - 8.0) / D0;
    A2  := (4.0 - 2.0 * K2 * T_S + Q) / D0;
    B0z := (K0 * T_S * T_S + 2.0 * K1 * T_S) / D0;
    B1z := 2.0 * K0 * T_S * T_S / D0;
    B2z := (K0 * T_S * T_S - 2.0 * K1 * T_S) / D0;
    G0  := -Q / D0;
    G1  := -2.0 * Q / D0;
    G2  := -Q / D0;
    Bo  := B0;
    Ready := TRUE;
END_IF

CASE State OF
ST_RESET:
    (* output and delays to zero, as if it had just started *)
    U := LIMIT(U_MIN, 0.0, U_MAX);
    E := 0.0;   E_1 := 0.0;   E_2 := 0.0;
    V := U;     V_1 := U;     V_2 := U;
    U_1 := U;   U_2 := U;

ST_AUTOMATIC:
    (* direct form I; 1 + G0 solves the loop through the direct term of H2 *)
    E := SET_POINT - ACTUAL;
    W := (B0z*E + B1z*E_1 + B2z*E_2) / Bo - (G1*U_1 + G2*U_2) - A1*V_1 - A2*V_2;
    U := LIMIT(U_MIN, W / (1.0 + G0), U_MAX);
    V := W - G0 * U;
END_CASE

(* shift: oldest first *)
E_2 := E_1;   E_1 := E;
V_2 := V_1;   V_1 := V;
U_2 := U_1;   U_1 := U;
END_FUNCTION_BLOCK
