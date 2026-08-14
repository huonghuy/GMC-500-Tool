r"""Helper module for communicating with the GQ-GMC 500+ Geiger Counter.

This returns:
  - test_serial,  checks serial port communication
  - send_command,  send command to device
  - list_ports, list all available serial ports
  - power_up, powers up the device
  - get_version, reads the model and firmware version of the device
  - get_serial, reads the serial number of the device
  - get_cpm, reads the counts per minute from the device
  - get_voltage, read the voltage of the battery
  - power_off, power off the device
  - read_datetime, reads date and time from device
  - set_datetime, sets date and time of device
  - parse history file and export to csv
"""

import datetime
import struct
import serial
import serial.tools.list_ports
import time
import logging
import pandas as pd
import sys

# set parameters
DEFAULT_BAUD_RATE = 115200
DEFAULT_PORT = ''  # set at runtime from list_ports() or set_port(); platform-specific
DEFAULT_DATA_BITS = 8
DEFAULT_PARITY = 0
DEFAULT_STOP_BIT = 1
DEFAULT_TIMEOUT = 1
DEFAULT_BIN_FILE = 'log_'
DEFAULT_CSV_FILE = 'gq-gmc-500-log.csv'
DEFAULT_FLASH_SIZE = 1_048_576
EOL = '\n'

default_port: str = DEFAULT_PORT

# Crate and configure logger, append logs on every run
logging.basicConfig(filename='geigerlog.log', filemode='a', format='%(asctime)s %(message)s')
logger = logging.getLogger()  # Create logging object
logger.setLevel(logging.DEBUG)


def test_serial(test_port=None) -> str:
    """
    Test if serial connection is functioning
    :param test_port: serial port name ('COM5' on Windows, '/dev/cu.*' on macOS/Linux)
    :returns: Text message success or error
    """
    if test_port is None:
        test_port = default_port
    if not test_port:
        msg: str = 'Error: No serial port selected. Choose a port and press Set Port.'
        logger.error(msg)
        return msg
    try:
        # print(f'Testing port {test_port}\n')
        ser = serial.Serial(test_port, DEFAULT_BAUD_RATE)
        msg: str = f'Serial port functioning'
        ser.close()
    except serial.SerialException as e:
        msg: str = f'Error: {e}'
        logger.error(msg)
    return msg


def send_command(command: bytes, b_len: int) -> bytes:
    """
    Send a command to the device
    :param command: as bytes
    :param b_len: length of bytes
    :returns: the device response as bytes
    :raises serial.SerialException: if the port cannot be opened or the write/read fails
    """
    global default_port
    ser_test = test_serial(default_port)
    if "Error" in ser_test:
        logger.error(f'Error occurred! Check serial connection: {ser_test}')
        raise serial.SerialException(ser_test.removeprefix('Error: '))
    with serial.Serial(default_port, DEFAULT_BAUD_RATE, bytesize=DEFAULT_DATA_BITS, timeout=DEFAULT_TIMEOUT) as ser:
        try:
            ser.write(command)
            ans = ser.read(b_len)
        except (OSError, serial.SerialException) as e:
            logger.error(f'Error {e}')
            raise serial.SerialException(f'Communication failed: {e}') from e
        return ans


def list_ports(symlinks=True) -> list:
    """
    Return all available serial ports, and pre-select a likely USB-serial device.

    Port names are taken from pyserial's ``device`` attribute so they are valid on the
    host platform as-is: 'COM5' on Windows, '/dev/cu.usbserial-1140' on macOS/Linux.
    """
    global default_port
    try:
        port_list = serial.tools.list_ports.comports(include_links=symlinks)
    except Exception as e:
        logger.error(f'Error getting port list {e}')
        return []
    port_list = sorted(port_list, key=lambda item: item.device)
    for item in port_list:
        # The GMC-500+ shows up through a USB-serial bridge; the exact wording of the
        # description varies by driver ('USB Serial', 'USB-SERIAL CH340', ...).
        if 'usb' in (item.description or '').lower():
            default_port = item.device
            logger.info(f'Default Port set to: {default_port}')
            break
    return [item.device for item in port_list]


def set_port(port: str) -> str:
    """
    Set the serial port used by all subsequent commands.
    :param port: port name as returned by list_ports()
    :returns: confirmation message
    """
    global default_port
    default_port = port
    logger.info(f'Port set to: {default_port}')
    return f'Port set to: {default_port}'


def power_up() -> str:
    """Power on the device"""
    try:
        send_command(b'<POWERON>>', 0)
        msg = f'Device activated'
        logger.info(f'Device activated')
    except FileNotFoundError as e:
        msg = f'Device not found, check serial port first'
        logger.warning(f'Device not found, check serial port first.')
    return msg


def get_version() -> str:
    """
    Read the model and firmware version of the device
    :returns: Model and version as string
    """
    ver = send_command(b'<GETVER>>', 15)
    return f'Geiger Counter Version: {ver.decode()}'


def get_serial() -> str:
    """
    Read the serial number of the device
    :returns: Sertial number as string
    """
    serial = send_command(b'<GETSERIAL>>', 7)
    serial_number = serial.replace(b'\r', b'').decode()
    return f'The serial number is: {serial_number}'


def get_cpm() -> str:
    """
    Read the CPM counts per minute
    :returns: Counts per minute as string
    """
    raw_cpm = send_command(b'<GETCPM>>', 4)
    cpm = int(raw_cpm[2:4].hex(), 16)
    return f'Current CPM are: {cpm}'


def get_voltage() -> str:
    """
    Read the voltage of the battery
    :returns:  voltage of battery as string.
    """
    voltage = send_command(b'<GETVOLT>>', 5).decode()
    return f'Battery voltage: {voltage}'


def power_off() -> str:
    """
    Power off the device
    :returns: Message of success
    """
    send_command(b'<POWEROFF>>', 0)
    return f'Device is powering off'


def read_datetime() -> str:
    """
    Return date and time in decimal or hexadecimal from device
    :returns: String with date and time from device
    """
    raw_datetime = send_command(b'<GETDATETIME>>', 7)
    # short version using the struct library
    # struct.unpack() converts the strings of binary representations to their original form according to the
    # specified format. The return type is always a tuple.
    # (year, month, day, hour, minute, second, dummy) = struct.unpack(">BBBBBBB", raw_datetime)
    (year, month, day, hour, minute, second, dummy) = struct.unpack(">7B", raw_datetime)
    return f'device date and time are: {day:02d}-{month:02d}-{year:02d}  {hour:02d}:{minute:02d}:{second:02d}'


def set_datetime() -> str:
    """
    Set the device time and date to the system time and date.
    :returns: local date and time
    """
    today = datetime.datetime.now()
    day = int(today.strftime("%d"))
    month = int(today.strftime("%m"))
    year = int(today.strftime("%y"))
    hour = int(today.strftime("%H"))
    minute = int(today.strftime("%M"))
    second = int(today.strftime("%S"))
    cmd = struct.pack('>BBBBBB', year, month, day, hour, minute, second)
    send_command(b'<SETDATETIME' + cmd + b'>>', 1)
    return f'local date and time are:  {day:02d}-{month:02d}-{year:02d}  {hour:02d}:{minute:02d}:{second:02d}'


def get_datetime() -> str:
    """
    Get current system date and time and return it
    :return: date and time as YYMMDD_HH_MM_SS
    """
    today = datetime.datetime.now()
    return today.strftime("%y%m%d_%H_%M_%S")


def date_to_unix(str_date) -> datetime:
    """
    Convert date + time in str format to unix format.
    :param str_date: date and time as string
    :return: unix timestamp
    """
    timestamp = time.mktime(datetime.datetime.strptime(str_date, "%Y-%m-%d %H:%M:%S").timetuple())
    return timestamp


def hexlify(data) -> str:
    """Return justified right, two characters as hexadecimal upper"""
    return ' '.join(f'{c:0>2X}' for c in data)


def create_record_time(data):
    """
    Create timestamp from part of bin file data and return timestamp in datetime format.
    :param data: a slice from the bin file
    :return: record_time (datetime)
    """
    year = data[3]  # year in hex without thousands
    month = data[4]  # month in hex
    day = data[5]  # day in hex
    hour = data[6]  # hours in hex
    minute = data[7]  # minutes in hex
    second = data[8]  # seconds in hex
    # 0x55 and 0XAA are the end of the sequence marker
    # create timestamp and append to list
    rec_time = f"20{year:02d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
    timestamp = datetime.datetime.strptime(rec_time, "%Y-%m-%d %H:%M:%S")
    return timestamp


def get_save_type(save_type) -> list:
    """
    Determine the saved data type and return it as string.
    Saved data types are every second, every minute or every hour.\n
    The respective intervals are 1s, 60s, and 3600s.
    :param save_type:
    :return: list(save_type, save_interval)
    """
    if save_type == 0:
        save_text = 'history saving deactivated'
        save_intval = 0
    elif save_type == 1:
        save_text = 'Every Second'
        save_intval = 1
    elif save_type == 2:
        save_text = 'Every Minute'
        save_intval = 60
    elif save_type == 3:
        save_text = 'Every Hour'
        save_intval = 3600
    elif save_type == 4:
        save_text = 'Every Second if exceeding threshold'
        save_intval = 1
    elif save_type == 5:
        save_text = 'Every Minute if exceeding threshold'
        save_intval = 60
    else:
        # Do not abort the whole export (and, from the GUI, the app) over one odd byte.
        save_text = f'Unknown save interval: {save_type} (allowed is: 0, 1, 2, 3, 4, 5)'
        save_intval = 1
        logger.warning(save_text)
    return [save_text, save_intval]


def bin_to_csv(in_file='20231007_17_19_34.bin', out_file='20231007_17_19_34.csv'):
    """
    Read history bin file and parse the data. Then write timestamp, counts per minute and counts per second in a
    csv file.

    The device can record counts per minute or counts per second.
    :param in_file:
    :param out_file:
    :return:
    """
    logger.info(f'Reading file {in_file} for parsing')
    with open(in_file, 'rb') as file:
        record = file.read()
    # 0xFF marks the erased/unwritten tail of the flash; nothing beyond it is data.
    record = record.rstrip(b'\xff')

    segments = _split_segments(record)
    rows = []
    for start_time, save_type, counts in segments:
        rows.extend(_counts_to_rows(start_time, save_type, counts))

    column_names = ['DateTime', 'Type', 'CPM'] + [f'# {x} CPS' for x in range(1, 61)]
    parsed_df = pd.DataFrame(rows, columns=column_names)
    write_csv(final_df=parsed_df, out_file=out_file)
    msg = f'Finished parsing, csv export done. {len(segments)} blocks -> {len(parsed_df)} rows.'
    logger.info(msg)
    return msg


def _split_segments(record) -> list:
    """
    Split the raw history into (timestamp, save_type, counts) segments.

    On-disk layout, confirmed against a GMC-500+ Re 2.53 dump: a 12-byte header
    ``55 AA 00 YY MM DD HH MM SS 55 AA 01`` followed by one count byte per sample
    interval, until the next header. In per-second mode the device emits a header
    every 180 s, giving the characteristic 192-byte record.
    """
    segments = []
    current = None  # (timestamp, save_type, [counts])
    last_save_type = 1  # per-second logging until the file says otherwise
    i = 0
    end = len(record)
    while i < end:
        if record[i] == 0x55 and i + 2 < end and record[i + 1] == 0xAA:
            tag = record[i + 2]
            if tag in (0x00, 0x05):
                # 0x05 carries a 4-byte preamble before the date bytes
                base = i + 4 if tag == 0x05 else i
                stamp = _read_timestamp(record, base)
                if stamp is not None:
                    i = base + 9  # past 55 AA 00 + the six date bytes
                    # A 55 AA <n> marker follows the date. Normally n is the save mode
                    # (01 = every second). In stretches where the device stamps every
                    # single second, n varies per record and is not a mode - keep the
                    # last real mode there, but always consume the marker so that 0x55
                    # and 0xAA can never be mistaken for counts.
                    if record[i:i + 2] == b'\x55\xaa' and i + 2 < end:
                        if record[i + 2] in (1, 2, 3):
                            last_save_type = record[i + 2]
                        i += 3
                    current = (stamp, last_save_type, [])
                    segments.append(current)
                    continue
            elif tag == 0x01 and i + 4 < end:
                # [55][AA][01][DH][DL]: a single count that did not fit in one byte
                if current is not None:
                    current[2].append(record[i + 3] * 256 + record[i + 4])
                i += 5
                continue
            elif tag == 0x02 and i + 3 < end:
                # ASCII note: [55][AA][02][len][text...]
                i += 4 + record[i + 3]
                continue
            elif tag in (0x03, 0x04):
                i += 4
                continue
            else:
                # An unrecognised marker: skip the 55 AA <tag> triplet rather than
                # letting 0x55/0xAA be recorded as counts of 85 and 170.
                logger.debug(f'skipping unknown marker 55 AA {tag:02X} at {i}')
                i += 3
                continue
        if current is not None:
            current[2].append(record[i])
        i += 1
    return segments


def _read_timestamp(record, base):
    """Return the datetime at ``base``, or None if those bytes are not a valid date."""
    if base + 8 >= len(record):
        return None
    try:
        return datetime.datetime(2000 + record[base + 3], record[base + 4], record[base + 5],
                                 record[base + 6], record[base + 7], record[base + 8])
    except ValueError:
        return None  # ordinary count data that happens to look like a marker


def _counts_to_rows(start_time, save_type, counts) -> list:
    """Chunk one segment's counts into per-minute rows: [DateTime, Type, CPM, 60x CPS]."""
    save_txt, save_interval = get_save_type(save_type)
    if save_interval == 0:
        return []
    rows = []
    per_row = 60 if save_interval == 1 else 1  # per-second data groups 60 samples to a minute
    for offset in range(0, len(counts), per_row):
        block = counts[offset:offset + per_row]
        row_time = start_time + datetime.timedelta(seconds=offset * save_interval)
        # pad short trailing blocks so every row has the same width
        padded = list(block) + [None] * (60 - len(block))
        rows.append([row_time, save_txt, sum(block)] + padded)
    return rows


def write_csv(final_df, out_file):
    """Write the parsed data to a csv file"""
    # Add a title row above the data. Keep the column header flush left, otherwise the
    # leading whitespace becomes part of the first column name. newline='' stops the
    # line endings pandas emits from being translated a second time on Windows.
    with open(out_file, 'w', newline='') as fp:
        fp.write('GMC-500+ Data Tool\n')
        fp.write(final_df.to_csv(index=False))
    return f'Parsed BIN file and wrote data to file.'


if __name__ == "__main__":
    pass
