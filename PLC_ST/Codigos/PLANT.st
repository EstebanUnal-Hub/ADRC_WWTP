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
