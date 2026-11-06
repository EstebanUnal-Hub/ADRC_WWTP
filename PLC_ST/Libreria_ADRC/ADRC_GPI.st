(*
Short description
"""""""""""""""""
**GPI controller tuned with bandwidths**, for a first-order plant (n = 1) with a constant
disturbance model (m = 1): the same structure as |GPI|, but with E1(s) = (s + WO)^2 and the gains
computed from WC and WO, as in |ADRC_ESO|.

.. note::
  | The block works with -e_y = SET_POINT - ACTUAL.
  | TS must be equal to the period of the task that calls the block.
  | The gains are only computed in RESET: a change of WC, WO, B0 or TS takes effect after the next RESET.

Connection
""""""""""
The reference comes from |PREFILTER_ADRC| or |BEZIER_REF|; |PLANT| can replace the process for tests:

.. image:: /../ADRC/_Images/CFC_PREFILTER_ADRC_ADRC_GPI.png

Theory
""""""
| The closed loop has the poles of |ADRC_ESO|, (s + WC)(s + WO)^2, but the controller is a transfer
  function instead of an observer.
| To avoid windup the controller is split in two filters: H2 receives the applied order u_sat, so
  when the actuator saturates the controller stops integrating.

.. image:: /../ADRC/_Images/EQ_ADRC_GPI.png

.. image:: /../ADRC/_Images/DIAG_GPI_DISCRETE.png

States
""""""
| **RESET** (RESET = TRUE, or no valid parameters yet): U = LIMIT(U_MIN, 0, U_MAX); the delays start from U.
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

Call with the setpoint prefilter:

::

  fbPrefilter(SET_POINT := lrSetPoint, ACTUAL := lrDO, WC := 0.00333, WO := 0.0167,
              TS := T#50MS, RESET := xReset);
  fbAdrcGpi(SET_POINT := fbPrefilter.Y, ACTUAL := lrDO, WC := 0.00333, WO := 0.0167,
            B0 := 4.17E-5, TS := T#50MS, RESET := xReset);
  lrU := fbAdrcGpi.U;

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
FUNCTION_BLOCK ADRC_GPI
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

(* gains are only updated outside AUTOMATIC *)
IF (State <> ST_AUTOMATIC) AND (T_S > 0.0) AND (WC > 0.0) AND (WO > WC) AND (B0 > 0.0) THEN
    (* Tustin with E1(s) = (s + wo)^2 *)
    Q   := 2.0 + WO * T_S;
    D0  := Q * Q;
    A1  := -2.0 * (4.0 - WO * WO * T_S * T_S) / D0;
    A2  := (2.0 - WO * T_S) * (2.0 - WO * T_S) / D0;
    B0z := WO * T_S * (WC * WO * T_S + 2.0 * (WO + 2.0 * WC)) / D0;
    B1z := 2.0 * WC * WO * WO * T_S * T_S / D0;
    B2z := WO * T_S * (WC * WO * T_S - 2.0 * (WO + 2.0 * WC)) / D0;
    G0  := T_S * (2.0 * WC - WO * WO * T_S) / D0;
    G1  := -2.0 * WO * WO * T_S * T_S / D0;
    G2  := -T_S * (2.0 * WC + WO * WO * T_S) / D0;
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
