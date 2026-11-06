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
