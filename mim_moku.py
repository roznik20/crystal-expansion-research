import numpy as np
import datetime
from moku.instruments import MultiInstrument, Oscilloscope, FrequencyResponseAnalyzer
from moku_script import ensure_csv, append_row, voltage_to_temperature_C, find_resonant_frequency

#===============================

#HARD-CODED SECTION

#-------------------------------

MOKU_SERIAL       = "MokuGo-008036.local"
THERMO_CHANNEL    = 1
STREAM_DT         = 10           #datalogger
SAMPLE_RATE       = 5            #datalogger

SWEEP_START_HZ    = 1_000        # start frequency (Hz)
SWEEP_END_HZ      = 1_000_000    # stop  frequency (Hz)
SWEEP_POINTS      = 512          # number of frequency points
SWEEP_DURATION    = SWEEP_POINTS * 2e-3
SWEEP_AMPLITUDE   = 0.5          # stimulus amplitude (Vpp)
OUTPUT_CHANNEL    = 1            # Moku output channel for the stimulus

OUTPUT_CSV        = "resonance_log.csv"
CSV_FIELDS = ["run", "time", "resonant_frequency_hz", "temperature_C"]

#thermo calibration constants
CAL_COEFFS  = np.array([-4.467737406588116, 30.398833920002193, 487.48348434479993, -400.91916238202316])
CAL_T_MEAN  = 230.23333333333335   # K
CAL_T_STD   = 54.100921639305014   # K
CAL_T_MIN_K = 133.14999999999998   # K
CAL_T_MAX_K = 298.15               # K

#===============================

def read_thermo_volt(osc_inst,channel):
    data = osc_inst.get_data(wait_complete=True)
    samples = data[f"ch{channel}"]
    return float(np.mean(samples))


mim = MultiInstrument(MOKU_SERIAL, platform_id=2, force_connect=True)

#Configure csv file
ensure_csv(OUTPUT_CSV)
run = 1
print(f"Logging to '{OUTPUT_CSV}'. Press Ctrl+C to stop.\n")

try:
    
    #Configure MultiInstrument mode
    osc = mim.set_instrument(1, Oscilloscope)
    fra = mim.set_instrument(2, FrequencyResponseAnalyzer)

    connections = [
        dict(source='Input2', destination='Slot1InA'),
        dict(source='Slot2OutA', destination='Output1'),
        dict(source='Input1', destination='Slot2InA')
    ]

    mim.set_connections(connections=connections)

    #power for AD595 thermocouple
    mim.set_power_supply(1, enable=True, voltage=-5, current=0.1)
    mim.set_power_supply(2, enable=True, voltage=10, current=0.1)

    #Configure oscilloscope
    osc.set_timebase(-0.05, 0.05)

    #Configure FRA
    fra.set_sweep(
        start_frequency=SWEEP_START_HZ,
        stop_frequency=SWEEP_END_HZ,
        num_points=SWEEP_POINTS,
        averaging_time=2e-3
    )
    fra.set_output(1, amplitude=SWEEP_AMPLITUDE)

    #Start collecting data
    fra.start_sweep()

    #Data processing
    while True:
        print(f"Run {run}")
        #recording with oscillsocope
        print("  Reading thermocouple voltage ...")
        voltage_V   = read_thermo_volt(THERMO_CHANNEL)
        try:
            temperature = voltage_to_temperature_C(voltage_V, CAL_COEFFS, CAL_T_MEAN, CAL_T_STD,
                                                    CAL_T_MIN_K, CAL_T_MAX_K)
        except ValueError as e:
            print(f"  Warning: {e}")
            temperature = float('nan')
            
        print(f"  → {voltage_V * 1000:.2f} mV  =  {temperature:.2f} °C")
        
        #recording with FRA
        try:
            sweep_data = fra.get_data(wait_complete = True)
        except Exception as e:
            fra.start_sweep()
            sweep_data = fra.get_data(wait_complete=True)

        #logging the data in the csv file
        frequencies = sweep_data["ch1"]["frequency"]
        gains_db    = sweep_data["ch1"]["magnitude"]
        resonant_hz = find_resonant_frequency(frequencies, gains_db)
        timestamp   = datetime.datetime.now().isoformat(timespec="seconds")

        print(f"  → resonant frequency: {resonant_hz:.1f} Hz\n")

        append_row(OUTPUT_CSV, {
            "run":                   run,
            "time":                  timestamp,
            "resonant_frequency_hz": resonant_hz,
            "temperature_C":         round(temperature, 3),
        })

        run += 1

except KeyboardInterrupt:
    # Catches the Ctrl+C and exits cleanly without a giant red error
    print("\nExperiment stopped by user. Saving and disconnecting...")

except Exception as e:
    print(f"\nAn error occurred: {e}")
    raise e

finally:
    mim.set_power_supply(1, enable=False)
    mim.set_power_supply(2, enable=False)
    mim.relinquish_ownership()