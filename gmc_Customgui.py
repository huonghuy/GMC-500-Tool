import sys
import customtkinter
import tkinter as tk
from tkinter.filedialog import askopenfilename
from tkinter.filedialog import asksaveasfilename
from tkinter import messagebox
import os
import gmc_tools
from pathlib import Path
import logging
import struct

DEFAULT_FLASH_SIZE = 1_048_576

# Crate and configure logger, append logs on every run
logging.basicConfig(filename='geigerlog.log', filemode='a', format='%(asctime)s %(message)s')
logger = logging.getLogger()  # Create logging object
logger.setLevel(logging.DEBUG)

# Set color theme for gui
customtkinter.set_default_color_theme("dark-blue")  # Themes: "blue" (standard), "green", "dark-blue"


# Create main app window
class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        self.bar = None
        self.init_ui()

    # Display errors in widget
    @staticmethod
    def show_error(exc, val, tb, *args):
        logger.error(f'{exc.__name__}: {val}')
        messagebox.showerror(title='Error', message=str(val))

    # Override internal function to show errors
    tk.Tk.report_callback_exception = show_error

    # Create functions to be called by the UI
    def set_port(self):
        """Set and display chosen serial port"""
        chosen = self.om1.get()
        if not chosen or chosen == "Select Port First":
            self.status.set('No port selected.')
            return
        self.port.set(chosen)
        self.status.set(gmc_tools.set_port(chosen))
        return

    def get_version(self):
        """Get software version from device"""
        self.status.set(gmc_tools.get_version())

    def get_serial_number(self):
        """Get serial number from device"""
        self.status.set(gmc_tools.get_serial())

    def get_cpm(self):
        """Get CPM from device"""
        self.status.set(gmc_tools.get_cpm())

    def get_battery(self):
        """Get battery voltage"""
        self.status.set(gmc_tools.get_voltage())

    @staticmethod
    def power_on():
        """Power on the device"""
        gmc_tools.power_up()

    @staticmethod
    def power_off():
        """Power off the device"""
        gmc_tools.power_off()

    def read_date(self):
        """Read date and time from device"""
        self.status.set(gmc_tools.read_datetime())

    def set_date(self):
        self.status.set(gmc_tools.set_datetime())

    def end_program(self):
        self.destroy()
        sys.exit(0)

    def get_history(self, data_length=4096) -> str:
        """Read all history data from the internal flash memory and write it to a bin file.
        The GQ GMC-500+ Geiger Counter has 1MB Flash Memory.

        COMMAND:
            <SPIR[A2][A1][A0][L1][L0]>>
        A2,A1,A0 are three bytes address data, from MSB to LSB.  The L1,L0 are the data length requested.  L1 is high
        byte of 16 bit integer and L0 is low byte.
        The length normally not exceed 4096 bytes in each request.

        Writes:
            The history data in raw byte array to file with name 20YYMMDD_HH_MM_SS.bin.

        Comment:
            The minimum address is 0, and maximum address value is the size of the flash memory of the GQ GMC
            Geiger counter. Check the user manual for particular model flash size.

        Firmware supported:  GMC-300 Re.2.0x, Re.2.10 or later

        MSB = most significant bit
        LSB = least significant bit
        :param data_length: int, default 4096
        :returns: string message
        """
        out_file = f'GMC-500-History-20{gmc_tools.get_datetime()}.bin'  # create filename
        files = [('Binary file', '*.BIN'),
                 ('Binary file', '*.bin')]
        out_path = asksaveasfilename(filetypes=files, defaultextension='.BIN',
                                     initialdir=os.getcwd(),
                                     initialfile=out_file)
        if not out_path:  # user cancelled the save dialog
            self.status.set('History read cancelled.')
            return 'History read cancelled.'
        self.status.set('Reading history ...')
        record = b''
        # set the number of times a page from flash memory will be read
        num_of_runs = int(DEFAULT_FLASH_SIZE / data_length)

        # send history request to device
        for i in range(num_of_runs):
            # pack address into 4 bytes, big endian for transmission as MSB to LSB; then clip 1st bye = high byte
            # struck.pack with ">" uses big endian ordering
            # start at address 0: the first page holds the oldest records and the first timestamp
            address = data_length * i
            ad = struct.pack(">I", address)[1:]
            # pack data_length into 2 byes, big endian; use all bytes
            dl = struct.pack(">H", data_length)
            logger.info(f'{i:>3}: requesting data length: {data_length:5d} (0x{dl[0]:02x}{dl[1]:02x}) address: '
                        f'{address:5d} (0x{ad[0]:02x}{ad[1]:02x}{ad[2]:02x})')
            status_msg = f'Reading block {i + 1:>3} of {num_of_runs}'
            self.status.set(status_msg)
            self.update()
            data_page = gmc_tools.send_command(b'<SPIR' + ad + dl + b'>>', data_length)
            record = record + data_page
        if record:
            msg = f"received: {len(record):5d}"
            logger.info(msg)
        else:
            msg = "ERROR: No data received"
            logger.error(msg)
            self.status.set(msg)
            return msg
        # write history in binary file
        with open(out_path, 'wb') as f_out:
            f_out.write(record)
        self.status.set(f'Data export complete {msg} bytes')
        return f'\nData export complete {msg} bytes'

    def parse_history(self):
        """Load history file, parse and export to csv"""
        data = [('BIN File(*.bin)', '*.bin')]
        hist_path = askopenfilename(filetypes=data)
        if not hist_path:  # user cancelled the open dialog
            self.status.set('Parse cancelled.')
            return
        file_path = Path(hist_path)
        out_path = file_path.with_suffix(".csv")
        self.status.set(gmc_tools.bin_to_csv(in_file=hist_path, out_file=out_path))

    # Create and initialize UI
    def init_ui(self):
        self.title("GMC-500+ Tool")
        self.geometry("600x750")
        self.status = tk.StringVar()
        self.status.set(os.getcwd())
        self.port = tk.StringVar(value="No Port Selected")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.button_frame = MyButtonFrame(self)
        self.button_frame.grid(row=1, column=0, padx=10, pady=(10, 0), sticky="nsw")

        self.output_frame = MyOutputFrame(self)
        self.output_frame.grid(row=1, column=1, padx=10, pady=(10, 0), sticky="nse")

        # Setting up variables
        self.status = customtkinter.StringVar()
        self.status.set(os.getcwd())
        self.port = customtkinter.StringVar()
        self.port.set("No Port Selected")

        # Create serial port chooser
        self.port_values = [item for item in gmc_tools.list_ports()]
        self.om1 = customtkinter.CTkOptionMenu(master=self, values=self.port_values)
        self.om1.set("Select Port First")
        self.om1.grid(row=0, column=0, padx=20, pady=10, sticky="ew", columnspan=2)

        # Create status bar
        self.statusbar = customtkinter.CTkLabel(master=self, textvariable=self.status)
        self.statusbar.grid(row=15, column=0, pady=10, padx=5, columnspan=2)

        self.portbar = customtkinter.CTkLabel(master=self, textvariable=self.port)
        self.portbar.grid(row=16, column=0, pady=10, padx=5, columnspan=2)


class MyOutputFrame(customtkinter.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        self.info_txt = ("GMC-500+ Tool\n"
                         "\n"
                         "All functions should be self explanatory. \n\n"
                         "First you need to select and set the serial port to use.\n\n"
                         "You can read from and write to the device without turning"
                         "it on,\n\n"
                         "Set Date&Time - writes the system time to the device.\n\n"
                         "Get History - reads the collected data from the device and\nwrites it into a BIN-file.\n\n"
                         "Parse History - loads a BIN file, parses the data and writes\nit into a CSV-file. "
                         "It takes a while to read 1MB of data from the\ndevice through a serial connection.\n"
                         "You can see the progress in the status below.")

        # Create Textbox
        self.textbox = customtkinter.CTkTextbox(master=self, width=400, height=570, corner_radius=0)
        self.textbox.grid(row=1, column=0, columnspan=1, sticky="nsew")
        self.textbox.insert("0.0", self.info_txt)


class MyButtonFrame(customtkinter.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        # Create buttons
        self.set_btn = customtkinter.CTkButton(self, text="Set Port", command=master.set_port)
        self.set_btn.grid(row=2, column=0, padx=20, pady=10, sticky="w", columnspan=2)

        self.pw_btn = customtkinter.CTkButton(self, text="Power Up Device", command=master.power_on)
        self.pw_btn.grid(row=3, column=0, padx=20, pady=10, sticky="w", columnspan=2)

        self.vn_btn = customtkinter.CTkButton(self, text="Get Version", command=master.get_version)
        self.vn_btn.grid(row=4, column=0, padx=20, pady=10, sticky="w", columnspan=2)

        self.sn_btn = customtkinter.CTkButton(self, text="Get Serial Number", command=master.get_serial_number)
        self.sn_btn.grid(row=5, column=0, padx=20, pady=10, sticky="w", columnspan=2)

        self.cpm_btn = customtkinter.CTkButton(self, text="Read CPM", command=master.get_cpm)
        self.cpm_btn.grid(row=6, column=0, padx=20, pady=10, sticky="w", columnspan=2)

        self.vo_btn = customtkinter.CTkButton(self, text="Get Battery Voltage", command=master.get_battery)
        self.vo_btn.grid(row=7, column=0, padx=20, pady=10, sticky="w", columnspan=2)

        self.td_btn = customtkinter.CTkButton(self, text="Get Date&Time", command=master.read_date)
        self.td_btn.grid(row=8, column=0, padx=20, pady=10, sticky="w", columnspan=2)

        self.std_btn = customtkinter.CTkButton(self, text="Set Date&Time", command=master.set_date)
        self.std_btn.grid(row=9, column=0, padx=20, pady=10, sticky="w", columnspan=2)

        self.hist_btn = customtkinter.CTkButton(self, text="Get History", command=master.get_history)
        self.hist_btn.grid(row=10, column=0, padx=20, pady=10, sticky="w", columnspan=2)

        self.std_btn = customtkinter.CTkButton(self, text="Parse History", command=master.parse_history)
        self.std_btn.grid(row=11, column=0, padx=20, pady=10, sticky="w", columnspan=2)

        self.std_btn = customtkinter.CTkButton(self, text="Power Off", command=master.power_off)
        self.std_btn.grid(row=12, column=0, padx=20, pady=10, sticky="w", columnspan=2)

        self.exit_btn = customtkinter.CTkButton(self, text="Quit", command=master.end_program)
        self.exit_btn.grid(row=13, column=0, padx=20, pady=10, sticky="w", columnspan=2)


if __name__ == "__main__":
    app = App()
    app.mainloop()
