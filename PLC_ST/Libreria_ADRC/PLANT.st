(*
Short description
"""""""""""""""""
**First-order test plant** K_DC/(TAU s + 1), discretized with Tustin, to test the controllers in
the PLC without connecting them to the process.

.. note::
  | TS must be equal to the period of the task that calls the block.
  | Call it after the controller in the same task: Y is the measurement of the next cycle.
  | The block has no RESET; it starts from Y = 0 and U = 0.

Connection
""""""""""
PLANT closes the loop in place of the process: its input is the order U of the controller and its
output Y goes back to ACTUAL:

.. image:: /../ADRC/_Images/CFC_BEZIER_REF_ADRC_ESO.png

Theory
""""""
.. image:: /../ADRC/_Images/EQ_PLANT.png

Example
"""""""
Design plant, K_DC = 0.05 mg/(L %) and TAU = 1200 s:

::

  fbAdrc(SET_POINT := lrSetPoint, ACTUAL := fbPlant.Y, WC := 0.00333, WO := 0.0167,
         B0 := 4.17E-5, TS := T#50MS, RESET := xReset);
  fbPlant(U := fbAdrc.U, K_DC := 0.05, TAU := 1200.0, TS := T#50MS);

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
FUNCTION_BLOCK PLANT
VAR_INPUT
    U        : LREAL;               (* plant input *)
    K_DC     : LREAL;               (* DC gain *)
    TAU      : LREAL;               (* time constant [s] *)
    TS       : TIME := T#50MS;      (* sampling time, equal to the task period *)
END_VAR
VAR_OUTPUT
    Y        : LREAL;               (* plant output *)
END_VAR
VAR
    T_S      : LREAL;               (* sampling time [s] *)
    Ag, Bg   : LREAL;
    U_1      : LREAL;               (* previous input *)
END_VAR

(* sampling time in seconds *)
T_S := TIME_TO_LREAL(TS) / 1000.0;

(* first-order plant K_DC/(TAU s + 1), discretized with Tustin *)
Ag := (T_S - 2.0 * TAU) / (T_S + 2.0 * TAU);
Bg := K_DC * T_S / (T_S + 2.0 * TAU);

(* call it after the controller: Y is the next measurement *)
Y   := -Ag * Y + Bg * (U + U_1);
U_1 := U;
END_FUNCTION_BLOCK
