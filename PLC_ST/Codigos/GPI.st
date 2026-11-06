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
