(*
Short description
"""""""""""""""""
**Setpoint prefilter** for |GPI|: first-order filter F(s) = K0/(K1 s + K0) with static gain 1,
tuned with the same K0 and K1 of the controller.

.. note::
  | Use the same K0, K1 and TS as in |GPI|.
  | TS must be equal to the period of the task that calls the block.
  | The gains are only computed in RESET: a change of K0, K1 or TS takes effect after the next RESET.

Connection
""""""""""
The output Y goes to the SET_POINT input of |GPI|:

.. image:: /../ADRC/_Images/CFC_PREFILTER_GPI_GPI.png

Theory
""""""
| The numerator K1 s + K0 of the GPI puts a zero in the reference-to-output transfer function. The
  prefilter puts its pole on that zero and cancels it, so a setpoint step is followed without overshoot.
| The time constant is K1/K0: 420 s with K0 = 9.26E-7 and K1 = 3.89E-4.

.. image:: /../ADRC/_Images/EQ_PREFILTER_GPI.png

The prefilter is outside the loop: the controller does not change and still receives only the error.

.. image:: /../ADRC/_Images/DIAG_PREFILTER.png

States
""""""
| **RESET** (RESET = TRUE, or no valid parameters yet): Y follows ACTUAL, so leaving RESET starts
  the filter from the measurement.
| **AUTOMATIC**: the filter is executed every cycle.
| Valid parameters: TS > 0, K0 > 0 and K1 > 0.

Example
"""""""
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
FUNCTION_BLOCK PREFILTER_GPI
VAR_INPUT
    SET_POINT : LREAL;              (* setpoint r *)
    ACTUAL    : LREAL;              (* measurement y *)
    K0        : LREAL;              (* prefilter: k0/(k1 s + k0) *)
    K1        : LREAL;
    TS        : TIME := T#50MS;     (* sampling time, equal to the task period *)
    RESET     : BOOL := FALSE;
END_VAR
VAR_OUTPUT
    Y         : LREAL;              (* filtered setpoint, goes to the controller *)
END_VAR
VAR CONSTANT
    ST_RESET     : INT := 0;
    ST_AUTOMATIC : INT := 1;
END_VAR
VAR
    T_S       : LREAL;              (* sampling time [s] *)
    State     : INT;
    Ready     : BOOL := FALSE;      (* valid gains available *)
    Af, Bf    : LREAL;
    Y_1, R_1  : LREAL;              (* delays of the output and the setpoint *)
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
IF (State <> ST_AUTOMATIC) AND (T_S > 0.0) AND (K0 > 0.0) AND (K1 > 0.0) THEN
    (* Tustin *)
    Af := (K0 * T_S - 2.0 * K1) / (K0 * T_S + 2.0 * K1);
    Bf := K0 * T_S / (K0 * T_S + 2.0 * K1);
    Ready := TRUE;
END_IF

CASE State OF
ST_RESET:
    (* follow the measurement; leaving RESET starts from it *)
    Y   := ACTUAL;
    Y_1 := ACTUAL;
    R_1 := ACTUAL;

ST_AUTOMATIC:
    (* r_f[k] = -af r_f[k-1] + bf (r[k] + r[k-1]) *)
    Y   := -Af * Y_1 + Bf * (SET_POINT + R_1);
    Y_1 := Y;
    R_1 := SET_POINT;
END_CASE

END_FUNCTION_BLOCK
