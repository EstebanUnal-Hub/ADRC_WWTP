(*
Short description
"""""""""""""""""
**Setpoint prefilter** for |ADRC_ESO|: first-order filter F(s) = k0/(k1 s + k0) with static gain 1,
tuned with the same WC and WO of the controller.

.. note::
  | Use the same WC, WO and TS as in |ADRC_ESO|.
  | TS must be equal to the period of the task that calls the block.
  | The gains are only computed in RESET: a change of WC, WO or TS takes effect after the next RESET.

Connection
""""""""""
The output Y goes to the SET_POINT input of |ADRC_GPI| (or |ADRC_ESO|):

.. image:: /../ADRC/_Images/CFC_PREFILTER_ADRC_ADRC_GPI.png

Theory
""""""
| The reference-to-output transfer function of the error-based ADRC has a zero. The prefilter puts
  its pole on that zero and cancels it, so a setpoint step is followed without overshoot.
| The time constant is (WO + 2 WC)/(WC WO): 420 s with WC = 0.00333 and WO = 0.0167 rad/s.

.. image:: /../ADRC/_Images/EQ_PREFILTER_ADRC.png

The prefilter is outside the loop: the controller does not change and still receives only the error.

.. image:: /../ADRC/_Images/DIAG_PREFILTER.png

States
""""""
| **RESET** (RESET = TRUE, or no valid parameters yet): Y follows ACTUAL, so leaving RESET starts
  the filter from the measurement.
| **AUTOMATIC**: the filter is executed every cycle.
| Valid parameters: TS > 0, WC > 0 and WO > WC.

Example
"""""""
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
FUNCTION_BLOCK PREFILTER_ADRC
VAR_INPUT
    SET_POINT : LREAL;              (* setpoint r *)
    ACTUAL    : LREAL;              (* measurement y *)
    WC        : LREAL;              (* controller bandwidth [rad/s] *)
    WO        : LREAL;              (* observer bandwidth [rad/s] *)
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
    Af, Bf, Q : LREAL;
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
IF (State <> ST_AUTOMATIC) AND (T_S > 0.0) AND (WC > 0.0) AND (WO > WC) THEN
    (* Tustin of k0/(k1 s + k0), with k0/k1 = wc wo/(wo + 2 wc) *)
    Q  := 2.0 * (WO + 2.0 * WC);
    Af := (WC * WO * T_S - Q) / (WC * WO * T_S + Q);
    Bf := WC * WO * T_S / (WC * WO * T_S + Q);
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
