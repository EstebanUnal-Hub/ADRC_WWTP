FUNCTION_BLOCK ADRC_ESO
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
    A         : ARRAY[1..2, 1..2] OF LREAL;
    B         : ARRAY[1..2] OF LREAL;
    C         : ARRAY[1..2] OF LREAL;
    L         : ARRAY[1..2] OF LREAL;
    K         : ARRAY[1..2] OF LREAL;
    X         : ARRAY[1..2] OF LREAL;   (* x_hat: estimated error and total disturbance *)
    X_old     : ARRAY[1..2] OF LREAL;
    Ey, Ey_old : LREAL;
    U0, U0_old : LREAL;
    Bo, Zc, Zo : LREAL;
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
    Zc := EXP(-WC * T_S);
    Zo := EXP(-WO * T_S);
    A[1,1] := 1.0;   A[1,2] := T_S;
    A[2,1] := 0.0;   A[2,2] := 1.0;
    B[1]   := T_S;    B[2]   := 0.0;
    C[1]   := 1.0;   C[2]   := 0.0;
    L[1]   := 2.0 * (1.0 - Zo);
    L[2]   := (1.0 - Zo) * (1.0 - Zo) / T_S;
    K[1]   := (1.0 - Zc) / T_S;
    K[2]   := 1.0;
    Bo     := B0;
    Ready  := TRUE;
END_IF

(* observer: x_hat[k] = (A - L C) x_hat[k-1] + B u0[k-1] + L ey[k-1] *)
X[1] := (A[1,1] - L[1]*C[1])*X_old[1] + (A[1,2] - L[1]*C[2])*X_old[2] + B[1]*U0_old + L[1]*Ey_old;
X[2] := (A[2,1] - L[2]*C[1])*X_old[1] + (A[2,2] - L[2]*C[2])*X_old[2] + B[2]*U0_old + L[2]*Ey_old;

CASE State OF
ST_RESET:
    (* output and observer to zero, as if it had just started *)
    U    := LIMIT(U_MIN, 0.0, U_MAX);
    X[1] := 0.0;
    X[2] := -Bo * U;
    Ey   := 0.0;

ST_AUTOMATIC:
    (* control law: u0 = -K x_hat[k],  u = u0/b0 *)
    Ey := ACTUAL - SET_POINT;
    U0 := -(K[1]*X[1] + K[2]*X[2]);
    U  := LIMIT(U_MIN, U0 / Bo, U_MAX);
END_CASE

(* the observer always receives the applied order *)
U0 := Bo * U;

X_old  := X;
U0_old := U0;
Ey_old := Ey;
END_FUNCTION_BLOCK
