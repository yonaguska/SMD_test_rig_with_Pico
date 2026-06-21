'''
   The simplest test of WDT, just reset it and pulse the trigger.

   It runs an a special test rig PCB I designed which uses a
   Raspberry Pi Pico to manage testing. There are two tests; insure
   the timeout is at least what we deem usable, and then make sure
   the unit can be successfully retriggered.

   The first test resets the 7555, waits and then triggers the one-shot.
   It then monitors how long it takes to time out, it will trigger it
   one or more times and collect the minimum and maximum timeout periods.
   The minimum time is used to control the behavior of the second test,
   to optimize the amount of time the test takes.

   The second test sets the trigger interval at 60% of the unit's minimum
   timeout before retriggering it; looking for unexpected timeouts which
   cause a test failure. We want to insure retriggering extends the WDT
   timeout indefinitely. It runs with the same trigger interval several times,
   because we have seen it extend, only to timeout before the second trigger.
   We consider this a failure.

   The second test then increments the trigger interval by a certain amount
   and tries this all again. We keep bumping up the trigger interval until
   we have successfully reached our desired minimum of 300 seconds.

   Note that we have designed it to run tests on units with shorter timeouts,
   this being done to expedite the development of the test. Seriously, the
   normal test cycle takes about two and a half hours. The short version takes
   about a tenth of that.

   Pinout of the WDT:

      Pin 1 GND
      Pin 2 Reset        -_-----------------------------------------------
      Pin 3 Trigger      ----_---------_---------_---------_---------_----
      Pin 4 Control Voltage pin of 7555
      Pin 5 Reset pulse  -----------_---------_---------_---------_-------
      Pin 6 7555 output  X___-------___-------___-------___-------___-----
      Pin 7 Capacitor+ of RC network (only load with high-impedance probe)
      Pin 8 VCC

   >>> import board (Raspberry Pi Pico)
   >>> dir(board)
   ['__class__', 'A0', 'A1', 'A2', 'A3', 'GP0', 'GP1', 'GP10', 'GP11',
   'GP12', 'GP13', 'GP14', 'GP15', 'GP16', 'GP17', 'GP18', 'GP19',
   'GP2', 'GP20', 'GP21', 'GP22', 'GP23', 'GP24', 'GP25', 'GP26',
   'GP26_A0', 'GP27', 'GP27_A1', 'GP28', 'GP28_A2', 'GP3', 'GP4', 'GP5',
   'GP6', 'GP7', 'GP8', 'GP9', 'LED', 'SMPS_MODE', 'VBUS_SENSE',
   'VOLTAGE_MONITOR']
   >>>

   Modified to tests several units concurrently, because the test
   runs for a long time and we have a lot to test.
'''
version = '1.0'
print("\n########################################\nWATCHDOG TEST SYSTEM version {}\n########################################".format(version))

import board
import time
from digitalio import DigitalInOut, Pull, Direction
import neopixel

'''##### DEFINITIONS ##########################################################'''
test_type  = 'normal'  # normal/short/chip'
run_test1  = True
run_test2  = True

reset_duration    = 0.1
trigger_duration  = 0.2
delay_before_test = 10
test1_status = 'FAIL                 '
test2_status = 'PASS                 '

if test_type == 'short':
    # CAP VALUE 10 uF
    cap = 0.000010          # farads 10 uF = 0.00001 F
    resistor = 3300000   # ohms
    print_sample = 10
    trigger_delay = 30  # 20uF/3.3M= 1000u/100k=113s  100u/1m=115.5s  100u/3.3m=435s
    passing_interval = 30
    interval_increment = 10
    progress_increment = 5
    count_maximum = 50
    wdt_minimum = count_maximum
    wdt_maximum = 0
elif test_type == 'chip':
    # CAP VALUE 5.7 uF
    cap = 0.0000057          # farads 5.7 uF = 0.0000057 F
    resistor = 3300000   # ohms
    print_sample = 10
    trigger_delay = 30  # 20uF/3.3M= 1000u/100k=113s  100u/1m=115.5s  100u/3.3m=435s
    passing_interval = 15
    interval_increment = 2
    progress_increment = 1
    count_maximum = 30
    retrigger_start = 0.7
    wdt_minimum = count_maximum
    wdt_maximum = 0
elif test_type == 'normal':
    # CAP VALUE 100 uF
    cap = 0.0001          # farads 100 uF = 0.0001 F
    resistor = 3300000   # ohms
    print_sample = 60
    trigger_delay = 300  # 20uF/3.3M= 1000u/100k=113s  100u/1m=115.5s  100u/3.3m=435s
    passing_interval = 300
    interval_increment = 20
    progress_increment = 10
    count_maximum = 800   # 1200 is the upper limit/800 normal test
    retrigger_start = 0.9
    wdt_minimum = count_maximum
    wdt_maximum = 0
else:
    print("UNKNOWN test_type {}".format(test_type))

RC = 1.1 * resistor * cap
do_reset = True

# pixel colors
barely_red = (2, 0, 0)
barely_green = (0, 2, 0)
barely_blue = (0, 0, 2)
barely_yellow = (2, 1, 0)
dim_red = (5, 0, 0)
dim_green = (0, 5, 0)
dim_blue = (0, 0, 5)
dim_yellow = (5, 3, 0)
medium_red = (10, 0, 0)
medium_green = (0, 10, 0)
medium_blue = (0, 0, 10)
medium_yellow = (10, 7, 0)
bright_red = (100, 0, 0)
bright_green = (0, 100, 0)
bright_blue = (0, 0, 100)
bright_yellow = (100, 70, 0)
yellow = (255, 150, 0)
pixel_off = (0, 0, 0)

num_pixels = 10
boards     = 10

'''##### PIN SETUPS ###############################################'''
# define reset pin
reset = DigitalInOut(board.GP0)
reset.direction = Direction.OUTPUT
reset.value = False
time.sleep(0.1)
reset.value = True

# define trigger pin
trigger = DigitalInOut(board.GP1)
trigger.direction = Direction.OUTPUT
trigger.value = False
time.sleep(0.1)
trigger.value = True


# define LED pin
Onboard_LED = DigitalInOut(board.LED)
Onboard_LED.direction = Direction.OUTPUT
Onboard_LED.value = False


# # define input pins to read pulse outputs
# pulse_output1 = DigitalInOut(board.GP20)
# pulse_output1.direction = Direction.INPUT
#
# define pulse_output pins on the Pi Pico
WDT = {
    1:  {'input_pin': DigitalInOut(board.GP2),  'last_state': True, 'this_state': True, 'wdt_minimum': count_maximum, 'wdt_maximum': wdt_maximum, 'test1_timed_out': False, 'test1_status': test1_status, 'test1_pixel': pixel_off, 'test2_timed_out': False, 'test2_status': test2_status, 'test2_pixel': pixel_off, 'composite_pixel': pixel_off},
    2:  {'input_pin': DigitalInOut(board.GP3),  'last_state': True, 'this_state': True, 'wdt_minimum': count_maximum, 'wdt_maximum': wdt_maximum, 'test1_timed_out': False, 'test1_status': test1_status, 'test1_pixel': pixel_off, 'test2_timed_out': False, 'test2_status': test2_status, 'test2_pixel': pixel_off, 'composite_pixel': pixel_off},
    3:  {'input_pin': DigitalInOut(board.GP4),  'last_state': True, 'this_state': True, 'wdt_minimum': count_maximum, 'wdt_maximum': wdt_maximum, 'test1_timed_out': False, 'test1_status': test1_status, 'test1_pixel': pixel_off, 'test2_timed_out': False, 'test2_status': test2_status, 'test2_pixel': pixel_off, 'composite_pixel': pixel_off},
    4:  {'input_pin': DigitalInOut(board.GP5),  'last_state': True, 'this_state': True, 'wdt_minimum': count_maximum, 'wdt_maximum': wdt_maximum, 'test1_timed_out': False, 'test1_status': test1_status, 'test1_pixel': pixel_off, 'test2_timed_out': False, 'test2_status': test2_status, 'test2_pixel': pixel_off, 'composite_pixel': pixel_off},
    5:  {'input_pin': DigitalInOut(board.GP6),  'last_state': True, 'this_state': True, 'wdt_minimum': count_maximum, 'wdt_maximum': wdt_maximum, 'test1_timed_out': False, 'test1_status': test1_status, 'test1_pixel': pixel_off, 'test2_timed_out': False, 'test2_status': test2_status, 'test2_pixel': pixel_off, 'composite_pixel': pixel_off},
    6:  {'input_pin': DigitalInOut(board.GP7),  'last_state': True, 'this_state': True, 'wdt_minimum': count_maximum, 'wdt_maximum': wdt_maximum, 'test1_timed_out': False, 'test1_status': test1_status, 'test1_pixel': pixel_off, 'test2_timed_out': False, 'test2_status': test2_status, 'test2_pixel': pixel_off, 'composite_pixel': pixel_off},
    7:  {'input_pin': DigitalInOut(board.GP8),  'last_state': True, 'this_state': True, 'wdt_minimum': count_maximum, 'wdt_maximum': wdt_maximum, 'test1_timed_out': False, 'test1_status': test1_status, 'test1_pixel': pixel_off, 'test2_timed_out': False, 'test2_status': test2_status, 'test2_pixel': pixel_off, 'composite_pixel': pixel_off},
    8:  {'input_pin': DigitalInOut(board.GP9),  'last_state': True, 'this_state': True, 'wdt_minimum': count_maximum, 'wdt_maximum': wdt_maximum, 'test1_timed_out': False, 'test1_status': test1_status, 'test1_pixel': pixel_off, 'test2_timed_out': False, 'test2_status': test2_status, 'test2_pixel': pixel_off, 'composite_pixel': pixel_off},
    9:  {'input_pin': DigitalInOut(board.GP10), 'last_state': True, 'this_state': True, 'wdt_minimum': count_maximum, 'wdt_maximum': wdt_maximum, 'test1_timed_out': False, 'test1_status': test1_status, 'test1_pixel': pixel_off, 'test2_timed_out': False, 'test2_status': test2_status, 'test2_pixel': pixel_off, 'composite_pixel': pixel_off},
    10: {'input_pin': DigitalInOut(board.GP11), 'last_state': True, 'this_state': True, 'wdt_minimum': count_maximum, 'wdt_maximum': wdt_maximum, 'test1_timed_out': False, 'test1_status': test1_status, 'test1_pixel': pixel_off, 'test2_timed_out': False, 'test2_status': test2_status, 'test2_pixel': pixel_off, 'composite_pixel': pixel_off},
}
# define the output_pins as INPUTS
for n in range(1, boards+1, 1):
    WDT[n]['input_pin'].direction = Direction.INPUT
    WDT[n]['input_pin'].pull = Pull.DOWN   # pullup/pulldown ~50-80k

# count the number of boards by checking the level of the input pins
unit = []
board_count = 0
for n in range(1, boards+1, 1):
    pin_value = WDT[n]['input_pin'].value
    if pin_value:
        unit.append(True)
        board_count += 1
    else:
        unit.append(False)
for n in range(0, boards):
    print("unit {:>2} {:>5}".format(n, unit[n]))

# define neopixel string
pixels = neopixel.NeoPixel(board.GP28, num_pixels)


'''##### FUNCTIONS ############################################################'''
def pulse_onboard_led(count):
    for n in range(0,count):
        onboard_led(True)
        time.sleep(0.1)
        onboard_led(False)
        time.sleep(0.1)


def onboard_led(state):
    Onboard_LED.value = state


def pulse_pin_low(pin, duration):
    pin.value = False
    time.sleep(duration)
    pin.value = True


def pulse_pin_high(pin, duration):
    pin.value = True
    time.sleep(duration)
    pin.value = False


def set_pin_low(pin):
    pin.value = False


def set_pin_high(pin):
    pin.value = True


def pulse_trigger(duration, indent, interval=0):
    if interval != 0:
        print("{}pulse the trigger for {} seconds, interval {}".format(indent, duration, interval))
    else:
        print("{}pulse the trigger for {} seconds".format(indent, duration))
    pulse_pin_low(trigger, duration)
    time.sleep(1)


def pulse_reset(duration, delay, indent):
    if do_reset:
        print("{}pulse the reset for {} seconds".format(indent, duration), end="")
        pulse_pin_low(reset, duration)
    else:
        print("{}no reset issued".format(indent), end="")
    print("{}delay for {} seconds".format(indent, delay))
    time.sleep(delay)


def pulse_pixels(color, duration):
    pixels.fill(pixel_off)
    for n in range(0, num_pixels):
        pixels[n] = color
    time.sleep(duration)
    pixels.fill(pixel_off)


def restore_pixels(this_array):
    for n in range(0, len(this_array)):
        pixels[n] = this_array[n]


def set_pixel(n, color):
    pixels[n] = color


def set_pixels(tag):
    for n in range(1, boards+1, 1):  # set pixels from dict
        set_pixel(n-1, WDT[n][tag])


def pixel_test(color):
    for n in range(0, num_pixels):
        set_pixel(n, color)
        time.sleep(0.1)
        set_pixel(n, pixel_off)


if board_count > 0:
    '''### TEST CODE ############################################################'''
    print("\n///////////////////////////// TESTING {:>2} BOARDS /////////////////////////////////".format(board_count))
    # test the pixels
    pulse_pixels(dim_red, 1)
    pulse_pixels(dim_green, 1)
    pulse_pixels(dim_blue, 1)
    pixels.fill(pixel_off)
    pulse_onboard_led(10)
    time.sleep(1)
    for n in range(0, num_pixels):  # give a countdown via pixels
        pixels[n] = dim_green
        time.sleep(1)
        pixels[n] = pixel_off

    default_pixels = [barely_blue, barely_blue, barely_blue, barely_blue, barely_blue, barely_blue, barely_blue, barely_blue, barely_blue, barely_blue]

    if run_test1:
        ##### TIMEOUT TEST
        print("\n===== WDT TIMEOUT TEST ==========================================================")
        print("   RC is {} seconds, progress_increment is {} seconds, count_maximum is {}, letting the wdt timeout without retriggering" \
            .format(RC, progress_increment, count_maximum))

        restore_pixels(default_pixels)

        max_loops = 3                      # how many samples do we want?
        loop = 0                           # how many samples so far
        trigger_interval = count_maximum   # how long to wait for WDT(s) to time out ... was int(RC * 1.25)
        continue_testing = True            # our loop exit flag
        seconds = 0                        # essentially our seconds elapsed count

        print("   PREPARE FOR TESTING: reset wdt and apply trigger")
        pulse_reset(reset_duration, 2, "   ")
        pulse_trigger(trigger_duration, "   ", trigger_interval)
        print("   BEGIN TESTING: collect the initial output state(s) for last_state")
        for n in range(1, boards+1, 1):  # last_state = wdt_output.value
            if unit[n-1]:
                WDT[n]['last_state'] = WDT[n]['input_pin'].value

        messages = []
        print("   .", end="")
        while continue_testing:
            for n in range(1, boards+1, 1):  # check for boards timing out
                if unit[n-1]:
                    WDT[n]['this_state'] = WDT[n]['input_pin'].value
                    if WDT[n]['last_state'] and not WDT[n]['this_state']:  # we have a high-to-low transition ----____
                        if seconds < WDT[n]['wdt_minimum']: WDT[n]['wdt_minimum'] = seconds # remember last minimum
                        if seconds > WDT[n]['wdt_maximum']: WDT[n]['wdt_maximum'] = seconds # remember last maximum
                        WDT[n]['test1_timed_out'] = True
                    WDT[n]['last_state'] = WDT[n]['this_state']  # update last_state with this_state

            if seconds >= count_maximum:
                loop += 1
                seconds = -1
                pulse_trigger(trigger_duration, "   ", trigger_interval)
                print("   ", end="")
            if loop < max_loops:  # keep chuggin
                time.sleep(1)  # tick off a second
                seconds += 1
                if (seconds % progress_increment) == 0:
                    print(".", end="")
                    pulse_pixels(dim_yellow, 0.01)
                    restore_pixels(default_pixels)
            else: break #  we're done

        time.sleep(10)
        # dump results
        print("\n   TEST RESULTS")
        for n in range(1, boards+1, 1):
            if unit[n-1]:
                if WDT[n]['wdt_minimum'] >= passing_interval:
                    WDT[n]['test1_status'] = 'PASS                 '
                    WDT[n]['test1_pixel'] = dim_green
                if WDT[n]['wdt_minimum'] >= wdt_minimum:
                    WDT[n]['test1_status'] = 'FAIL, never timed out'
                    WDT[n]['test1_pixel'] = dim_red
                if WDT[n]['wdt_minimum'] < passing_interval:
                    WDT[n]['test1_status'] = 'FAIL, timeout short  '
                    WDT[n]['test1_pixel'] = dim_red

                print("   unit {:>2}: test1_status {}, wdt_minimum {:>3}, wdt_maximum {:>3}, timed_out {}". \
                format(n, WDT[n]['test1_status'], WDT[n]['wdt_minimum'], WDT[n]['wdt_maximum'], WDT[n]['test1_timed_out']))
            else:
                WDT[n]['test1_pixel'] = pixel_off
        print("")

    if run_test2:
        ##### RETRIGGER TEST
        print("\n===== WDT RETRIGGER TEST ========================================================")
        print("   RC is {} seconds, progress_increment is {} seconds, count_maximum is {}, retrigger_start {}...retriggering" \
        .format(RC, progress_increment, count_maximum, retrigger_start))

        max_loops = 3                      # how many samples do we want?
        loop = 0                           # how many samples so far
        #trigger_interval = int(passing_interval*0.6)   # how long to wait for WDT(s) to time out
        trigger_interval = int(passing_interval*retrigger_start)   # how long to wait for WDT(s) to time out
        continue_testing = True            # our loop exit flag
        seconds = 0                        # essentially our seconds elapsed count

        print("   PREPARE FOR TESTING: passing_interval {}, starting trigger_interval {}".format(passing_interval, trigger_interval))
        pulse_reset(reset_duration, 2, "   ")
        reset.value = True  # tie it high
        print("   BEGIN TESTING: collect the initial output state(s) for last_state")
        for n in range(1, boards+1, 1):  # last_state = wdt_output.value
            if unit[n-1]:
                WDT[n]['last_state'] = WDT[n]['input_pin'].value

        # print("", end="")
        while continue_testing:
            if seconds == 0:  # retrigger
                pulse_trigger(trigger_duration, "   ", trigger_interval)
                print("   ", end="")
            time.sleep(1)
            seconds += 1
            if (seconds % progress_increment) == 0:
                print(".", end="")
                pulse_pixels(dim_yellow, 0.01)
                set_pixels('test1_pixel')
            for n in range(1, boards+1, 1):  # this_state = wdt_output.value
                if unit[n-1]:
                    WDT[n]['this_state'] = WDT[n]['input_pin'].value
                    if WDT[n]['last_state'] and not WDT[n]['this_state']:  # timeout ----____
                        WDT[n]['test2_timed_out'] = True
                        WDT[n]['wdt_minimum'] = seconds
                        if seconds < passing_interval:
                            WDT[n]['test2_status'] = 'FAIL'
                    WDT[n]['last_state'] = WDT[n]['this_state']
            if seconds >= trigger_interval:  # it is the end of the trigger_interval
                seconds = 0
                loop += 1
                print(" {}, loop {}".format(trigger_interval, loop))
                if loop >= max_loops:       # it is the end of the loops
                    loop = 0
                    trigger_interval += interval_increment   # either max or slightly above
                    diff = trigger_interval - passing_interval
                    if diff <= 0:           # negative or zero, keep testing
                        pass
                    else:
                        if diff < interval_increment:  # we're barely above, this will be the last set of loops
                            trigger_interval = passing_interval  # we're at the last testing interval
                        else:
                            continue_testing = False   # testing is complete

        time.sleep(10)
        # dump results
        print("\n   TEST RESULTS")
        for n in range(1, boards+1, 1):
            if unit[n-1]:
                if WDT[n]['test2_timed_out']:
                    WDT[n]['test2_status'] = 'FAIL, retrigger error'
                    WDT[n]['test2_pixel'] = dim_red
                else:
                    if WDT[n]['wdt_minimum'] == count_maximum:
                        WDT[n]['test2_status'] = 'FAIL, never times out'
                        WDT[n]['test2_pixel'] = dim_red
                    else:
                        WDT[n]['test2_status'] = 'PASS                 '
                        WDT[n]['test2_pixel'] = dim_green
                print("   unit {:>2}: test2_status {}, wdt_minimum {:>3}, wdt_maximum {:>3}, timed_out {}". \
                format(n, WDT[n]['test2_status'], WDT[n]['wdt_minimum'], WDT[n]['wdt_maximum'], WDT[n]['test2_timed_out']))
            else:
    			WDT[n]['test2_pixel'] = pixel_off

        print("")

    if run_test1 and run_test2:
        ##### FINAL RESULTS
        for i in range(0, 10 ,1):
            time.sleep(2)
            set_pixels('test1_pixel')
            time.sleep(1)
            set_pixels('test2_pixel')

        for n in range(1, boards+1, 1):
            if unit[n-1]:
                if (WDT[n]['test1_pixel'] == dim_green) and (WDT[n]['test2_pixel'] == dim_green):
                    WDT[n]['composite_pixel'] = dim_green
                elif (WDT[n]['test1_pixel'] == dim_red) and (WDT[n]['test2_pixel'] == dim_red):
                    WDT[n]['composite_pixel'] = dim_red
                else:
                    WDT[n]['composite_pixel'] = dim_yellow
            else:
                WDT[n]['composite_pixel'] = pixel_off

        set_pixels('composite_pixel')

        for n in range(1, boards+1, 1):
            if unit[n-1]:
                print("unit {}: {}".format(n, WDT[n]))
else:
    pulse_pixels(dim_red, 1)

pulse_onboard_led(100)

# Turn on the onboard LED to indicate we're finished
onboard_led(True)