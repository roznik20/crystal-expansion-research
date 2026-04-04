#Need to change datalogger -> oscilloscope

from moku.instruments import MultiInstrument, Datalogger, FrequencyResponseAnalyzer

#===============================

#HARD-CODED SECTION

#-------------------------------

MOKU_SERIAL       = "MokuGo-008036.local"
STREAM_DT         = 10           #datalogger
SAMPLE_RATE       = 5            #datalogger

SWEEP_START_HZ    = 1_000        # start frequency (Hz)
SWEEP_END_HZ      = 1_000_000    # stop  frequency (Hz)
SWEEP_POINTS      = 512          # number of frequency points
SWEEP_AMPLITUDE   = 0.5          # stimulus amplitude (Vpp)
OUTPUT_CHANNEL    = 1            # Moku output channel for the stimulus

#===============================



mim = MultiInstrument(MOKU_SERIAL, platform_id=2, Force_connect=True)

try:
    
    #Configure MultiInstrument mode
    dl = mim.set_instrument(1, Datalogger)
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

    #Configure datalogger
    mim.set_frontend(channel=1, coupling='DC', impedance='1MOhm', range='1Vpp')
    dl.set_acquisition_mode(mode='Normal')

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
    dl.start_streaming(duration = STREAM_DT, sample_rate = SAMPLE_RATE)

    #Data processing
    while True:
        data = dl.get_stream_data()
        frame = fra.get_data()

        #from frame extract the resonant frequency
        #for data logger, convert voltage to temperature and export to csv
        #append resonant frequency column to data, export table as csv file


except Exception as e:
    if str(e) == "End of stream":
        print("Streaming session complete!")
    else:
        mim.relinquish_ownership()
        raise e

finally:
    mim.set_power_supply(1, enable=False)
    mim.set_power_supply(2, enable=False)
    mim.relinquish_ownership()