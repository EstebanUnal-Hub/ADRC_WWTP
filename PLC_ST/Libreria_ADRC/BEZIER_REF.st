(*
Short description
"""""""""""""""""
**Bezier reference trajectory** for |ADRC_ESO|: at each setpoint change it generates a smooth cubic
segment from the current reference to the new setpoint, with zero slope at the end, in a time TF.

.. note::
  | TS must be equal to the period of the task that calls the block.
  | TF is taken at each setpoint change; TS is only taken in RESET.

Connection
""""""""""
The output Y goes to the SET_POINT input of |ADRC_ESO| (or |ADRC_GPI|):

.. image:: /../ADRC/_Images/CFC_BEZIER_REF_ADRC_ESO.png

Theory
""""""
| The controller follows a smooth reference instead of a step, so the order does not jump and, with
  a long enough TF, the actuator is not saturated.
| When SET_POINT changes, the segment is replanned from the current value and slope of the
  reference, so consecutive changes stay smooth.

.. image:: /../ADRC/_Images/BEZIER_SEGMENT.png

TF is the duration of the segment: the reference leaves y_c at t0, when SET_POINT changes, and reaches
the setpoint r at tf = t0 + TF. The control points are P0 = y_c, P1 = y_c + dy_c TF/3 and P2 = P3 = r,
so the slope at the end is zero.

.. image:: /../ADRC/_Images/EQ_BEZIER_REF.png

States
""""""
| **RESET** (RESET = TRUE, or no valid parameters yet): Y follows ACTUAL, so leaving RESET starts
  the reference from the measurement.
| **AUTOMATIC**: the segment is evaluated every cycle and replanned at each setpoint change.
| Valid parameters: TS > 0 and TF > 0.

Example
"""""""
::

  fbBezier(SET_POINT := lrSetPoint, ACTUAL := lrDO, TF := T#40M, TS := T#50MS, RESET := xReset);
  fbAdrc(SET_POINT := fbBezier.Y, ACTUAL := lrDO, WC := 0.00333, WO := 0.0167,
         B0 := 4.17E-5, TS := T#50MS, RESET := xReset);

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
FUNCTION_BLOCK BEZIER_REF
VAR_INPUT
    SET_POINT : LREAL;              (* setpoint r *)
    ACTUAL    : LREAL;              (* measurement y *)
    TF        : TIME := T#20M;      (* segment duration, taken at each setpoint change *)
    TS        : TIME := T#50MS;     (* sampling time, equal to the task period *)
    RESET     : BOOL := FALSE;
END_VAR
VAR_OUTPUT
    Y         : LREAL;              (* reference y*, goes to the controller *)
END_VAR
VAR CONSTANT
    ST_RESET     : INT := 0;
    ST_AUTOMATIC : INT := 1;
END_VAR
VAR
    T_S       : LREAL;              (* sampling time [s] *)
    T_F       : LREAL;              (* segment duration [s] *)
    State     : INT;
    Ready     : BOOL := FALSE;      (* valid parameters available *)
    Ts_set         : LREAL;
    Tf_set         : LREAL;         (* duration of the current segment *)
    Yc, Dyc, Yf    : LREAL;         (* segment start state and target *)
    Delta, C1, C2, C3 : LREAL;      (* polynomial coefficients in tau *)
    Dy, Tn, Cnt, SP_old : LREAL;
END_VAR

(* state selection *)
IF RESET OR NOT Ready THEN
    State := ST_RESET;
ELSE
    State := ST_AUTOMATIC;
END_IF

(* times in seconds *)
T_S := TIME_TO_LREAL(TS) / 1000.0;
T_F := TIME_TO_LREAL(TF) / 1000.0;

(* parameters are only updated outside AUTOMATIC *)
IF (State <> ST_AUTOMATIC) AND (T_S > 0.0) AND (T_F > 0.0) THEN
    Ts_set := T_S;
    Tf_set := T_F;
    Ready  := TRUE;
END_IF

CASE State OF
ST_RESET:
    (* at rest on the measurement; leaving RESET starts the manoeuvre again *)
    Y  := ACTUAL;   Dy := 0.0;
    Yc := ACTUAL;   Dyc := 0.0;   Yf := ACTUAL;
    C1 := 0.0;      C2 := 0.0;    C3 := 0.0;
    Cnt := 0.0;     SP_old := ACTUAL;

ST_AUTOMATIC:
    (* evaluate the current segment, tau = n Ts/Tf *)
    Tn := Cnt * Ts_set / Tf_set;
    IF Tn < 1.0 THEN
        Y  := Yc + Tn * (C1 + Tn * (C2 + Tn * C3));
        Dy := (C1 + Tn * (2.0 * C2 + 3.0 * Tn * C3)) / Tf_set;
    ELSE
        Y  := Yf;
        Dy := 0.0;
    END_IF

    (* new setpoint: replan from the state of the reference *)
    IF SET_POINT <> SP_old THEN
        Yc := Y;
        Dyc := Dy;
        Yf := SET_POINT;
        Delta := Yf - Yc;
        IF T_F > 0.0 THEN
            Tf_set := T_F;
        END_IF
        C1 := Dyc * Tf_set;
        C2 := 3.0 * Delta - 2.0 * Dyc * Tf_set;
        C3 := -2.0 * Delta + Dyc * Tf_set;
        Cnt := 0.0;
        SP_old := SET_POINT;
    END_IF

    IF Cnt * Ts_set < Tf_set THEN
        Cnt := Cnt + 1.0;
    END_IF
END_CASE

END_FUNCTION_BLOCK
