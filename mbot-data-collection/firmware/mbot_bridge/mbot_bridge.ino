/*
 * mbot_bridge - a deterministic serial motor bridge for the Makeblock mBot v1.1
 * (mCore board: ATmega328P, Arduino Uno compatible).
 *
 * The board is deliberately dumb. It owns exactly two things the host cannot do
 * safely from the other side of a USB cable: it writes the motor pins, and it
 * stops the wheels when the host goes quiet. Every other decision - mixing,
 * ramping, polarity, speed limits - lives in Python where it can be changed
 * without a reflash.
 *
 * Pin assignment is taken from Makeblock's own library rather than from a
 * wiring diagram, so it stays true to what the stock firmware drives:
 *   MePort.h:  M1 = 0x09, M2 = 0x0a
 *   MeMCore.h: mePort[9]  = { 6, 7 }  -> M1 PWM D6, DIR D7
 *              mePort[10] = { 5, 4 }  -> M2 PWM D5, DIR D4
 * MeDCMotor::run() writes DIR HIGH for a positive speed, so we do too: a wheel
 * that spins backwards here would spin backwards under stock firmware as well,
 * and is a chassis wiring fact for the host to correct, not a bug to hide.
 *
 * Protocol: one ASCII command per line, one reply line per command.
 *
 *   M <left> <right>   set speeds, each -255..255      -> OK M <l> <r>
 *   S                  stop both motors                -> OK S
 *   P                  ping                            -> OK P
 *   V                  identify                        -> OK V <name> <ver> ...
 *   W <ms>             watchdog timeout, 0 disables    -> OK W <ms>
 *   T                  telemetry                       -> OK T <l> <r> <age> <up>
 *   Z <hz> <ms>        beep the buzzer                 -> OK Z
 *
 * Unsolicited lines are prefixed EV: "EV READY ..." once at boot, and
 * "EV WATCHDOG" when the failsafe fires.
 */

#define FW_NAME    "mbot_bridge"
#define FW_VERSION 1

static const uint8_t M1_PWM = 6, M1_DIR = 7;
static const uint8_t M2_PWM = 5, M2_DIR = 4;
static const uint8_t BUZZER = 8;

static const uint16_t DEFAULT_WATCHDOG_MS = 500;
static const uint8_t  BUF_LEN = 48;

static char     buf[BUF_LEN];
static uint8_t  buf_used = 0;
static int16_t  speed_m1 = 0, speed_m2 = 0;
static uint16_t watchdog_ms = DEFAULT_WATCHDOG_MS;
static uint32_t last_command_ms = 0;

/* Drive one motor the way MeDCMotor::run() does: direction pin, then duty. */
static void write_motor(uint8_t dir_pin, uint8_t pwm_pin, int16_t speed)
{
  if (speed > 255)  speed = 255;
  if (speed < -255) speed = -255;

  if (speed >= 0) {
    digitalWrite(dir_pin, HIGH);
    delayMicroseconds(5);
    analogWrite(pwm_pin, speed);
  } else {
    digitalWrite(dir_pin, LOW);
    delayMicroseconds(5);
    analogWrite(pwm_pin, -speed);
  }
}

static void apply(int16_t m1, int16_t m2)
{
  speed_m1 = m1 > 255 ? 255 : (m1 < -255 ? -255 : m1);
  speed_m2 = m2 > 255 ? 255 : (m2 < -255 ? -255 : m2);
  write_motor(M1_DIR, M1_PWM, speed_m1);
  write_motor(M2_DIR, M2_PWM, speed_m2);
}

/* Read the next whitespace-delimited integer; *ok stays true only if one was
 * actually there, so "M" and "M 40" are rejected rather than half-obeyed. */
static long next_int(char **cursor, bool *ok)
{
  char *p = *cursor;
  while (*p == ' ' || *p == '\t') p++;
  if (*p == '\0') { *ok = false; return 0; }

  char *end = p;
  long value = strtol(p, &end, 10);
  if (end == p) { *ok = false; return 0; }
  *cursor = end;
  return value;
}

static void handle(char *line)
{
  while (*line == ' ' || *line == '\t') line++;
  const char verb = *line;
  char *args = line + (verb ? 1 : 0);
  bool ok = true;

  switch (verb) {
    case 'M': {
      long left  = next_int(&args, &ok);
      long right = next_int(&args, &ok);
      if (!ok) { Serial.println(F("ERR M needs two integers")); return; }
      apply((int16_t)left, (int16_t)right);
      last_command_ms = millis();
      Serial.print(F("OK M ")); Serial.print(speed_m1);
      Serial.print(' ');        Serial.println(speed_m2);
      break;
    }
    case 'S':
      apply(0, 0);
      last_command_ms = millis();
      Serial.println(F("OK S"));
      break;

    case 'P':
      last_command_ms = millis();
      Serial.println(F("OK P"));
      break;

    case 'V':
      Serial.print(F("OK V " FW_NAME " "));
      Serial.print(FW_VERSION);
      Serial.println(F(" m1=pwm6/dir7 m2=pwm5/dir4"));
      break;

    case 'W': {
      long ms = next_int(&args, &ok);
      if (!ok || ms < 0 || ms > 60000) { Serial.println(F("ERR W needs 0..60000")); return; }
      watchdog_ms = (uint16_t)ms;
      last_command_ms = millis();
      Serial.print(F("OK W ")); Serial.println(watchdog_ms);
      break;
    }
    case 'T': {
      uint32_t now = millis();
      Serial.print(F("OK T "));
      Serial.print(speed_m1);            Serial.print(' ');
      Serial.print(speed_m2);            Serial.print(' ');
      Serial.print(now - last_command_ms); Serial.print(' ');
      Serial.println(now);
      break;
    }
    case 'Z': {
      long hz = next_int(&args, &ok);
      long ms = next_int(&args, &ok);
      if (!ok) { Serial.println(F("ERR Z needs hz and ms")); return; }
      if (hz > 0 && ms > 0 && ms <= 2000) { tone(BUZZER, hz, ms); }
      Serial.println(F("OK Z"));
      break;
    }
    case '\0':
      break;  /* a bare newline is a no-op, not an error */

    default:
      Serial.print(F("ERR unknown verb ")); Serial.println(verb);
      break;
  }
}

void setup()
{
  pinMode(M1_DIR, OUTPUT);
  pinMode(M1_PWM, OUTPUT);
  pinMode(M2_DIR, OUTPUT);
  pinMode(M2_PWM, OUTPUT);
  pinMode(BUZZER, OUTPUT);
  apply(0, 0);

  Serial.begin(115200);
  last_command_ms = millis();

  /* The host waits for this line, which is why it is printed last: seeing it
   * means the pins are already in a known, stopped state. */
  Serial.print(F("EV READY " FW_NAME " "));
  Serial.print(FW_VERSION);
  Serial.print(F(" watchdog="));
  Serial.println(watchdog_ms);
}

void loop()
{
  while (Serial.available() > 0) {
    const char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (buf_used > 0) {
        buf[buf_used] = '\0';
        handle(buf);
        buf_used = 0;
      }
    } else if (buf_used < BUF_LEN - 1) {
      buf[buf_used++] = c;
    } else {
      /* Overlong line: drop it whole rather than execute a truncated command. */
      buf_used = 0;
      Serial.println(F("ERR line too long"));
    }
  }

  if (watchdog_ms > 0 && (speed_m1 != 0 || speed_m2 != 0)) {
    if (millis() - last_command_ms > watchdog_ms) {
      apply(0, 0);
      Serial.println(F("EV WATCHDOG"));
    }
  }
}
