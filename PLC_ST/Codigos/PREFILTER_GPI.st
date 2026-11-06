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
