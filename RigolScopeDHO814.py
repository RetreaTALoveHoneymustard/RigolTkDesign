import tkinter as tk
from tkinter import ttk , messagebox , font as tkfont , scrolledtext
import pyvisa
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageTk
import io

# =========================================================================
# HARDWARE / BACKEND LAYER (Manages all VISA & SCPI communications)
# =========================================================================
class Scope:
    def __init__(self):
        self.rm = pyvisa.ResourceManager("@py")
        # FIXED: Changed self.instrument to self.scope to match ScopeApp expectations
        self.scope = self.find_rigol_instrument()

    def find_rigol_instrument(self):
        """Find the first RIGOL oscilloscope."""
        resources = self.rm.list_resources()
        usb_resources = [r for r in resources if r.startswith("USB")]
        if not usb_resources:
            raise RuntimeError("No USB VISA instruments found.")
        
        print("Searching for RIGOL oscilloscope...")
        for resource in usb_resources:
            try:
                scope = self.rm.open_resource(resource)
                scope.timeout = 3000
                idn = scope.query("*IDN?").strip()
                print(f"{resource}")
                print(f" {idn}")
                if "RIGOL" in idn.upper():
                    print("\nUsing:", resource)
                    return scope
                scope.close()
            except Exception as ex:
                print(f" {ex}")
                
        raise RuntimeError("No RIGOL oscilloscope found.")
    
    def get_idn(self):
        """Queries and returns the *IDN identity string."""
        if self.scope:
            return self.scope.query("*IDN?").strip()
        return "Not Connected"

    def write_raw(self, scpi_command):
        """Allows fallback custom raw SCPI writes."""
        if self.scope:
            self.scope.write(scpi_command)

    def query_raw(self, scpi_command):
        """Allows fallback custom raw SCPI queries."""
        if self.scope:
            return self.scope.query(scpi_command).strip()
        return ""

    def run(self):
        """Puts the scope into continuous capture execution."""
        if self.scope:
            self.scope.write(":RUN")

    def stop(self):
        """Freezes the scope acquisition state."""
        if self.scope:
            self.scope.write(":STOP")

    def configure_coupling(self, channel: int, coupling: str):
        """Sets the coupling mode of the specified channel AC , DC , GND"""
        print(f"Ensuring Channel {channel} is ON...")
        self.scope.write(f":CHANnel{channel}:DISPlay ON") # Turns the channel graphics on

        print(f"Setting Channel {channel} coupling to {coupling}...")
        self.scope.write(f":CHANnel{channel}:COUPling {coupling}")

    def configure_probe(self, channel: int, attenuation: str):
        """Sets the probe ratio of the specified analog channel Accepted arguments : {0.001|0.002|0.005|0.01|0.02|
        0.05|0.1|0.2|0.5|1|2|5|10|20|50|
        100|200|500|1000|2000|5000|
        10000|20000|50000}
        """
        print(f"Ensuring Channel {channel} is ON...")
        self.scope.write(f":CHANnel{channel}:DISPlay ON") # Turns the channel graphics on
        
        print(f"Setting Channel {channel} probe attenuation to {attenuation}...")
        self.scope.write(f":CHANnel{channel}:PROBe {attenuation}")

    def toggle_invert(self, channel: int):
        """Turns on or off the waveform invert for the specified channel , Accpeted arguments : 1|ON , 0|OFF"""
        print(f"Ensuring Channel {channel} is ON...")
        self.scope.write(f":CHANnel{channel}:DISPlay ON") # Turns the channel graphics on

        
        current_status = self.query_raw(f":CHANnel{channel}:INVert?").strip()
        if current_status in ("1", "ON"):
            new_status = "OFF"
        else:
            new_status = "ON"
        
        print(f"Setting Channel {channel} toggle invert {new_status}...")
        self.scope.write(f":CHANnel{channel}:INVert {new_status}")

    def voltage_scale(self, channel: int, scale: float):
        """Sets the vertical scale of the specified channel. Its default unit is V/div"""
        print(f"Ensuring Channel {channel} is ON...")
        self.scope.write(f":CHANnel{channel}:DISPlay ON") # Turns the channel graphics on
        
        print(f"Setting Channel {channel} configure vertical scale to {scale}...")
        self.scope.write(f":CHANnel{channel}:SCAle {scale}")

    def trigger_level(self, level: float):
        """Sets or queries the trigger level of Edge trigger. The unit is the same as that of
        current amplitude of the selected source."""
        print(f"Setting trigger level to {level}V...")
        self.scope.write(f":TRIGger:PULSe:LEVel {level}")

    def set_trigger_sweep(self, mode):
        """Sets trigger sweep mode (AUTO, NORMAL, or SINGLE)."""
        if self.scope:
            # Rigol sweep parameter accepts lowercase or uppercase modes directly
            self.scope.write(f":TRIGger:SWEep {mode.upper()}")
    
    def trigger_autoset(self):
        """Triggers the oscilloscope Autoset function."""
        print("Executing Autoset...")
        self.scope.write(":AUToset")
        self.scope.query("*OPC?") # Waits until the autoset operation is complete

    def set_trigger_source(self, source="CHAN1"):
        """
        Sets the edge trigger source.
        Accepted arguments: 'CHAN1', 'CHAN2', 'CHAN3', 'CHAN4', 'EXT'
        """
        if self.scope:
            # Reformat string slightly to ensure Rigol expected syntax matching
            src = source.upper()
            if src.startswith("CH"):
                src = src.replace("CH", "CHAN")
            self.scope.write(f":TRIGger:EDGe:SOURce {src}")

    def set_trigger_slope(self, slope="POSitive"):
        """
        Sets the edge trigger slope direction.
        Accepted arguments: 'POSitive' (Rising), 'NEGative' (Falling), 'RFALl' (Both)
        """
        if self.scope:
            slp = slope.upper()
            if slp in ["RISING", "POS"]:
                slp = "POSitive"
            elif slp in ["FALLING", "NEG"]:
                slp = "NEGative"
            elif slp in ["BOTH", "RFAL"]:
                slp = "RFALl"
                
            self.scope.write(f":TRIGger:EDGe:SLOPe {slp}")

    def set_trigger_coupling(self, coupling="DC"):
        """
        Sets the trigger signal coupling.
        Accepted arguments: 'AC', 'DC', 'LFR' (Low Freq Reject), 'HFR' (High Freq Reject)
        """
        if self.scope:
            self.scope.write(f":TRIGger:COUPling {coupling.upper()}")

    def disconnect(self):
        """Close the instrument and VISA resource manager."""
        if hasattr(self, 'scope') and self.scope is not None:
            self.scope.close()
            self.scope = None
            print("Instrument disconnected.")
            
        if hasattr(self, 'rm') and self.rm is not None:
            self.rm.close()
            self.rm = None
            print("Resource Manager closed.")

    def time_scale(self, scale: float):
        """
        Configures the horizontal time base scale (seconds per division).
        """
        print(f"Configure horizontal time scale to {scale} s/div...")
        self.scope.write(f":TIMebase:SCALe {scale}")

    def capture_screenshot(self):
        """Capture a PNG screenshot from a DHO800 series oscilloscope."""
        if not self.scope:
            raise RuntimeError("No instrument connected.")
            
        old_timeout = self.scope.timeout
        try:
            self.scope.timeout = 10000  # Expand timeout window for image transfer data block
            png_data = self.scope.query_binary_values(":DISPlay:SNAP?", datatype='B', container=bytes)
            
            if not png_data.startswith(b"\x89PNG"):
                raise RuntimeError("Returned data stream does not contain a valid PNG magic header.")
            return png_data
        finally:
            self.scope.timeout = old_timeout

    def save_png(self, data, directory="."):
        """Saves binary PNG data to storage disk with a systematic timestamp name format."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Ensure target folder directory exists smoothly
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        
        filename = folder / f"dho800_{timestamp}.png"
        filename.write_bytes(data)
        return filename

# =========================================================================
# USER INTERFACE LAYER (Manages only layout updates and user clicks)
# =========================================================================
class ScopeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Rigol Oscilloscope Controller")
        self.root.geometry("1600x1400")
        self.oscilloscope = None
        self.live_view_running = False
        self.channel_font = tkfont.Font(family="Candara Light", size=14, weight="bold")
        self.default_font = tkfont.Font(family="Yu Gothic UI Semilight", size="12",weight="bold")
        self.button_font = tkfont.Font(family="Yu Gothic UI Semilight", size="8", weight="bold")
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("Default.TLabelframe", background="#303030")
        self.style.configure("Horizontal.TLabelframe.Label", background="#303030",foreground="#C99C0A",font=self.default_font)
        self.style.configure("Trigger.TLabelframe.Label", background="#303030",foreground="#B9CF0D",font=self.default_font)
        self.style.configure("System.TLabelframe.Label", background="#303030",foreground="#1CC209",font=self.default_font)
        self.style.configure("Storage.TLabelframe.Label", background="#303030",foreground="#C446EE",font=self.default_font)


        # ---Main Container---
        self.main_container = ttk.Frame(root, padding="10")
        self.main_container.pack(fill=tk.BOTH, expand=True)
        self.main_container.grid_columnconfigure(0, weight=4)
        self.main_container.grid_columnconfigure(1, weight=1) 
        self.main_container.grid_rowconfigure(0, weight=1)
    
        #---Left-Side Container 80%---
        self.left_column = ttk.Frame(self.main_container, padding="5")
        self.left_column.grid(row=0, column=0, sticky="nsew")
        
        self.left_column.grid_rowconfigure(0, weight=1)
        self.left_column.grid_columnconfigure(0, weight=1)
        
        #----Set Terminal Frame----#
        terminal_label = ttk.Label(self.left_column, text="Terminal", font=self.channel_font)
        self.terminal_frame = ttk.LabelFrame(self.left_column, labelwidget=terminal_label)
        self.terminal_frame.grid(row=0, column=0, pady=5, sticky="nsew")

        self.terminal_frame.grid_rowconfigure(0,weight=6)
        self.terminal_frame.grid_rowconfigure(1,weight=4)
        self.terminal_frame.grid_columnconfigure(0, weight=1)

        # --- Inside bottom_task Frame Layout ---
        # Fixed-size container that will NOT grow to fit its contents
        self.live_view_container = tk.Frame(self.terminal_frame, bg="black")
        self.live_view_container.grid(row=0, column=0, sticky="nsew")
        self.live_view_container.config(width=800, height=480)
        self.live_view_container.grid_propagate(False)  # <-- key line: lock the size

        self.live_view_label = tk.Label(self.live_view_container, bg="black")
        self.live_view_label.pack(fill="both", expand=True)

        self.bottomtaskbar_frame = ttk.Frame(self.terminal_frame,padding=5,style="Default.TLabelframe")
        self.bottomtaskbar_frame.grid(row=1,sticky="nsew")
        self.bottomtaskbar_frame.grid_rowconfigure(0, weight=1)
        self.bottomtaskbar_frame.grid_columnconfigure(0, weight=1)
        self.active_channel = tk.IntVar(value=1)

        self.lbl_volt_div_ch1 = tk.Label(
            self.bottomtaskbar_frame, text="VOLT/DIVIDE", font=self.button_font,
            fg="#ffffff", bg="#1e1e1e"
        )
        self.volt_div_var = tk.StringVar()
        self.volt_div = ttk.Combobox(
            self.bottomtaskbar_frame, textvariable=self.volt_div_var,
            font=self.button_font, state="readonly"
        )
        self.lbl_coupling = tk.Label(
            self.bottomtaskbar_frame, text="COUPLING", font=self.button_font,
            fg="#ffffff", bg="#1e1e1e"
        )
        self.coupling_channel_var = tk.StringVar()
        self.coup_channel = ttk.Combobox(
            self.bottomtaskbar_frame, textvariable=self.coupling_channel_var,
            font=self.button_font, state="readonly"
        )
        self.lbl_probe_conf = tk.Label(
            self.bottomtaskbar_frame, text="PROBE", font=self.button_font,
            fg="#ffffff", bg="#1e1e1e"
        )
        self.probe_channel_var = tk.StringVar()
        self.probe_config_channel = ttk.Combobox(
            self.bottomtaskbar_frame, textvariable=self.probe_channel_var,
            font=self.button_font, state="readonly"
        )
        self.rad_ch1 = tk.Radiobutton(
            self.bottomtaskbar_frame, text="Configure CH1", 
            variable=self.active_channel, value=1,
            font=self.button_font
        )

        self.rad_ch2 = tk.Radiobutton(
            self.bottomtaskbar_frame, text="Configure CH2", 
            variable=self.active_channel, value=2,
            font=self.button_font
        )

        self.rad_ch3 = tk.Radiobutton(
            self.bottomtaskbar_frame, text="Configure CH3", 
            variable=self.active_channel, value=3,
            font=self.button_font
        )

        self.rad_ch4 = tk.Radiobutton(
            self.bottomtaskbar_frame, text="Configure CH4", 
            variable=self.active_channel, value=4,
            font=self.button_font
        )
        self.btn_invert = tk.Button(
            self.bottomtaskbar_frame, text="INVERT", font=self.button_font,
            bg="#d8cf48", fg="#3c0854", activebackground="#f2e640", activeforeground="#230332",
            bd=0 , command=self.invert_signal , state="disabled"
        )
        # The actual terminal frame container aligned nicely via Grid layout
        text_container_frame = tk.Frame(self.bottomtaskbar_frame, bg="#000000", bd=1, relief="solid")
        text_container_frame.grid(column=3, row=1, rowspan=4, columnspan=3, sticky="nsew", pady=10)

        # Make the container frame itself expandable
        text_container_frame.grid_rowconfigure(0, weight=1)
        text_container_frame.grid_columnconfigure(0, weight=1)

        self.terminal_log = scrolledtext.ScrolledText(
            text_container_frame,
            wrap="word",
            bg="#000000",
            fg="#00FF00",
            insertbackground="white",
            font=("Courier New", 10),
            state="disabled",
            width=75,   # characters wide
            height=10   # lines tall
        )
        self.terminal_log.grid(row=0, column=0, sticky="nsew")

        #-----CHECKBOX FOR CHANNELS-----------
        self.rad_ch1.grid(column=0, row=1, padx=5, pady=5, sticky="w")
        self.rad_ch2.grid(column=0, row=2, padx=5, pady=5, sticky="w")
        self.rad_ch3.grid(column=0, row=3, padx=5, pady=5, sticky="w")
        self.rad_ch4.grid(column=0, row=4, padx=5, pady=5, sticky="w")

        self.btn_invert.grid(column=1 , row=2 , padx=5 , pady=5 , ipadx = 5 , ipady =5 , sticky="w")

        self.lbl_volt_div_ch1.grid(column=1, row=1, padx=5, pady=(2, 22), sticky="w") 
        self.volt_div['values'] = ('100 mV','200 mV','500 mV','1 V', '2 V', '10 V')
        self.volt_div.current(0)
        self.volt_div.grid(column=1, row=1, columnspan=2, padx=5, pady=(50,10), sticky="ew")
        self.volt_div.bind("<<ComboboxSelected>>", self.change_volt_div)
        self.lbl_coupling.grid(column=1, row=3 ,padx=5, pady=(2, 22), sticky="w") 
        self.coup_channel['values'] = ('AC','DC','GND')
        self.coup_channel.current(0)
        self.coup_channel.grid(column=1, row=3, columnspan=2, padx=5, pady=(50,10), sticky="ew")
        self.coup_channel.bind("<<ComboboxSelected>>", self.change_coupling)
        self.lbl_probe_conf.grid(column=1, row=4 ,padx=5, pady=(2, 22), sticky="w") 
        self.probe_config_channel['values'] = ('X0.1','X0.2','X0.5','X1','X2','X5','X10')
        self.probe_config_channel.current(0)
        self.probe_config_channel.grid(column=1, row=4, columnspan=2, padx=5, pady=(50,10), sticky="ew")
        self.probe_config_channel.bind("<<ComboboxSelected>>", self.probe_setting)


        #---Right-Side Container 20%---
        self.right_column = ttk.Frame(self.main_container, padding="5")
        self.right_column.grid(row=0, column=1, sticky="nsew")
        
        for r in range(4):
            self.right_column.grid_rowconfigure(r, weight=1)
        self.right_column.grid_columnconfigure(0, weight=1)

        # Horizontal
        horizontal_config_label = ttk.Label(self.right_column, text="Horizontal Configure",style="Horizontal.TLabelframe.Label")
        self.horizontal_frame = ttk.LabelFrame(self.right_column, labelwidget=horizontal_config_label,style="Default.TLabelframe")
        self.horizontal_frame.grid(row=0, column=0, pady=5, sticky="nsew")

        self.lbl_tdiv = tk.Label(
            self.horizontal_frame, text="TIME/DIV", font=self.button_font,
            fg="#ffffff", bg="#1e1e1e"
        )

        self.time_divide_var = tk.StringVar()
        self.drop_time_div= ttk.Combobox(
            self.horizontal_frame, textvariable=self.time_divide_var,
            font=self.button_font, state="readonly"
        )

        self.lbl_tdiv.grid(column=0, row=0, padx=5, pady=(2, 22), sticky="w") 
        self.drop_time_div['values'] = ('100 us', '200 us', '500 us','1 ms','2 ms','5 ms','10 ms')
        self.drop_time_div.current(0)
        self.drop_time_div.grid(column=0, row=0, columnspan=2, padx=5, pady=(50,10), sticky="ew")
        self.drop_time_div.bind("<<ComboboxSelected>>", self.time_divide_configure)


        # Trigger
        trigger_config_label = ttk.Label(self.right_column, text="Trigger Configure", font=self.default_font,style="Trigger.TLabelframe.Label")
        self.trigger_frame = ttk.LabelFrame(self.right_column, labelwidget=trigger_config_label,style="Default.TLabelframe")
        self.trigger_frame.grid(row=1, column=0, pady=5, sticky="nsew")

        self.lbl_trg_source = tk.Label(
            self.trigger_frame, text="SOURCE", font=self.button_font,
            fg="#ffffff", bg="#1e1e1e"
        )
        self.trigger_source_var = tk.StringVar()
        self.drop_trig_source = ttk.Combobox(
            self.trigger_frame, textvariable=self.trigger_source_var,
            font=self.button_font, state="readonly"
        )
        self.lbl_trg_slope = tk.Label(
            self.trigger_frame, text="SLOPE", font=self.button_font,
            fg="#ffffff", bg="#1e1e1e"
        )
        self.trigger_slope_var = tk.StringVar()
        self.drop_trig_slope = ttk.Combobox(
            self.trigger_frame, textvariable=self.trigger_slope_var,
            font=self.button_font, state="readonly"
        )
        self.lbl_trg_coupling = tk.Label(
            self.trigger_frame, text="COUPLING", font=self.button_font,
            fg="#ffffff", bg="#1e1e1e"
        )
        self.trigger_coup_var = tk.StringVar()
        self.drop_trig_coup = ttk.Combobox(
            self.trigger_frame, textvariable=self.trigger_coup_var,
            font=self.button_font, state="readonly"
        )
        self.lbl_levels_trig = tk.Label(
            self.trigger_frame, text="TRIGGER LEVEL", font=self.button_font,
            fg="#ffffff", bg="#1e1e1e"
        )
        self.btn_sendleveltrg = tk.Button(
            self.trigger_frame, text="APPLY", font=self.button_font,
            bg="#b9c847", fg="#000000", activebackground="#b9bf8e", activeforeground="#000000",
            bd=0, state="disabled", command=self.send_level_trig
        )

        #-------- Trigger Source-----------#
        self.lbl_trg_source.grid(column=0, row=0, padx=5, pady=(2, 22), sticky="w") 
        self.drop_trig_source['values'] = ('CH1', 'CH2', 'CH3','CH4','NONE')
        self.drop_trig_source.current(0)
        self.drop_trig_source.grid(column=0, row=0, columnspan=2, padx=5, pady=(50,10), sticky="ew")
        self.drop_trig_source.bind("<<ComboboxSelected>>", self.change_trigger_source)

        #-------- Trigger Slope-----------#
        self.lbl_trg_slope.grid(column=3, row=0, padx=5, pady=(2, 22), sticky="w") 
        self.drop_trig_slope['values'] = ('RISING', 'FALLING', 'BOTH')
        self.drop_trig_slope.current(0)
        self.drop_trig_slope.grid(column=3, row=0, columnspan=2, padx=5, pady=(50,10), sticky="ew")
        self.drop_trig_slope.bind("<<ComboboxSelected>>", self.change_trigger_slope)

        #-------- Trigger Coupling-----------#
        self.lbl_trg_coupling.grid(column=5, row=0, padx=5, pady=(2, 22), sticky="w") 
        self.drop_trig_coup['values'] = ('AC', 'DC', 'LFR','HFR')
        self.drop_trig_coup.current(1)
        self.drop_trig_coup.grid(column=5, row=0, columnspan=2, padx=5, pady=(50,10), sticky="ew")
        self.drop_trig_coup.bind("<<ComboboxSelected>>", self.change_trigger_coupling)

        #----Trigger Level------#
        self.lbl_levels_trig.grid(column=0,row=1,columnspan=2,sticky="ew",padx =5)
        self.level_trig_input = tk.Entry(self.trigger_frame, font=self.button_font)
        self.level_trig_input.insert(0,"0") 
        self.level_trig_input.grid(column=0,row=1,columnspan=2,sticky="ew",padx =5,pady=(50,10))
        self.btn_sendleveltrg.grid(column=2,row=1,ipadx=5,ipady=5,sticky="ew",padx=5,pady=(50,10),columnspan=2)



        # Home / System Control Frame
        home_config_label = ttk.Label(self.right_column, text="Start & Stop / SCPI Commands", font=self.default_font,style="System.TLabelframe.Label")
        self.system_frame = ttk.LabelFrame(self.right_column, labelwidget=home_config_label,style="Default.TLabelframe")
        self.system_frame.grid(row=2, column=0, pady=5, sticky="nsew")
        
        for r in range(4): # Set up columns
            self.system_frame.grid_columnconfigure(r, weight=1)
        self.system_frame.grid_rowconfigure(0, weight=4)
        self.system_frame.grid_rowconfigure(1, weight=2)    
        self.system_frame.grid_rowconfigure(2, weight=4)

        # Widgets Inside System Frame
        self.btn_connect = tk.Button(
            self.system_frame, text="CONNECT", font=self.button_font,
            bg="#2ecc71", fg="#ffffff", activebackground="#27ae60", activeforeground="#ffffff",
            bd=0, command=self.connect_scope
        )

        self.btn_disconnect = tk.Button(
            self.system_frame, text="DISCONNECT", font=self.button_font,
            bg="#d53f3d", fg="#000000", activebackground="#c70805", activeforeground="#000000",
            bd=0, state="disabled", command=self.disconnect_scope
        )

        self.btn_sendcmd = tk.Button(
            self.system_frame, text="SEND COMMANDS", font=self.button_font,
            bg="#4594de", fg="#000000", activebackground="#086ecd", activeforeground="#000000",
            bd=0, state="disabled", command=self.send_scpi_command
        )

        self.lbl_scpi = tk.Label(
            self.system_frame, text="SCPI COMMANDS", font=self.button_font,
            fg="#ffffff", bg="#1e1e1e"
        )

        self.txt_idn_display = tk.Entry(
            self.system_frame, font=self.default_font,
            bg="#1a1a1a", fg="#00ff00", bd=1, relief="solid"
        )

        self.btn_start = tk.Button(
            self.system_frame, text="RUN", font=self.button_font,
            bg="#2ecc71", fg="#ffffff", activebackground="#27ae60", activeforeground="#ffffff",
            bd=0, state="disabled", command=self.scope_run
        )

        self.btn_stop = tk.Button(
            self.system_frame, text="STOP", font=self.button_font,
            bg="#d53f3d", fg="#000000", activebackground="#c70805", activeforeground="#000000",
            bd=0, state="disabled", command=self.scope_stop
        )

        self.mode_var = tk.StringVar()
        self.drop_trig_mode = ttk.Combobox(
            self.system_frame, textvariable=self.mode_var,
            font=self.button_font, state="readonly"
        )

        self.lbl_mode = tk.Label(
            self.system_frame, text="MODE", font=self.button_font,
            fg="#ffffff", bg="#1e1e1e"
        )

        #------------ Row 0 Layout -----------------#
        self.ip_input = tk.Entry(self.system_frame, font=self.button_font)
        self.ip_input.insert(0, "*IDN") 
        self.btn_connect.grid(column=0, row=0, padx=5, pady=5, ipadx=5, ipady=5, sticky="ew")
        self.btn_disconnect.grid(column=1, row=0, padx=5, pady=5, ipadx=5, ipady=5, sticky="ew")
        self.lbl_scpi.grid(column=2, row=0, padx=5, pady=(2, 22), sticky="w") 
        self.ip_input.grid(column=2, row=0, padx=5, pady=(20, 5), ipadx=40, sticky="ew")
        self.btn_sendcmd.grid(column=3, row=0, padx=5, pady=5, ipadx=5, ipady=5, sticky="ew")
        
        #------------ Row 1 Layout -----------------#
        self.txt_idn_display.grid(column=0, row=1, columnspan=4, padx=10, pady=5, sticky="ew")
        self.txt_idn_display.insert(0, "Scope: Not Connected")
        self.txt_idn_display.config(state="readonly")
        
        #------------ Row 2 Layout -----------------#
        self.btn_start.grid(column=0, row=2, padx=5, pady=5, ipadx=5, ipady=5, sticky="ew")
        self.btn_stop.grid(column=1, row=2, padx=5, pady=5, ipadx=5, ipady=5, sticky="ew")
        self.lbl_mode.grid(column=2, row=2, padx=5, pady=(2, 45), sticky="w") 
        self.drop_trig_mode['values'] = ('AUTO', 'NORMAL', 'SINGLE')
        self.drop_trig_mode.current(0)
        self.drop_trig_mode.grid(column=2, row=2, columnspan=2, padx=5, pady=5, sticky="ew")
        self.drop_trig_mode.bind("<<ComboboxSelected>>", self.change_mode)

        # Storage Frame
        storage_config_label = ttk.Label(self.right_column, text="Storage and Etc.",style="Storage.TLabelframe.Label")
        self.storage_frame = ttk.LabelFrame(self.right_column, labelwidget=storage_config_label,style="Default.TLabelframe")
        self.storage_frame.grid(row=3, column=0, pady=5, sticky="nsew")

        self.btn_live_view = tk.Button(
            self.storage_frame, text="START LIVE VIEW", font=self.button_font,
            bg="#3498db", fg="#ffffff", bd=0, state="disabled",command=self.toggle_live_view
        )
        self.btn_live_view.grid(column=0, row=2, padx=10, pady=10, ipadx=5, ipady=5, sticky="ew")

        self.btn_screenshot = tk.Button(
            self.storage_frame, text="CAPTURE SCREENSHOT", font=self.button_font,
            bg="#9b59b6", fg="#ffffff", activebackground="#8e44ad", activeforeground="#ffffff",
            bd=0, state="disabled", command=self.take_screenshot
        )
        self.btn_autoset = tk.Button(
            self.storage_frame, text="AUTOSET", font=self.button_font,
            bg="#080808", fg="#1274e4", activebackground="#000000", activeforeground="#044fa4",
            bd=0, state="disabled", command=self.autoset_command
        )
        self.btn_log_clear = tk.Button(
            self.storage_frame, text="CLEAR LOG MESSAGE", font=self.button_font,
            bg="#32D9C0", fg="#000000", activebackground="#8DE0D4", activeforeground="#000000",
            bd=0, state="normal", command=self.clear_log_terminal
        )
        self.btn_screenshot.grid(column=0, row=0, padx=10, pady=10, ipadx=5, ipady=5, sticky="ew")
        self.btn_autoset.grid(column=0, row=1, padx=10, pady=10, ipadx=5, ipady=5, sticky="ew")
        self.btn_live_view.grid(column=0, row=2, padx=10, pady=10, ipadx=5, ipady=5, sticky="ew")
        self.btn_log_clear.grid(column=1, row=0, padx=10, pady=10, ipadx=5, ipady=5, sticky="ew")
        
        


    # ==========================================
    # EVENT LOGIC METHODS (Clean UI Layer)
    # ==========================================
    def log_to_terminal(self, title: str, message: str = None):
        if message is None:
            message = title
            title = None

        self.terminal_log.config(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        if title:
            self.terminal_log.insert(tk.END, f"[{timestamp}] {title}: {message}\n")
        else:
            self.terminal_log.insert(tk.END, f"[{timestamp}] {message}\n")
        self.terminal_log.see(tk.END)
        self.terminal_log.config(state="disabled")

    def clear_log_terminal(self):
        self.terminal_log.config(state="normal")
        self.terminal_log.delete(1.0, tk.END)
        self.terminal_log.config(state="disabled") 

    def connect_scope(self):
        """Initializes backend class and updates buttons."""
        self.btn_connect.config(text="SEARCHING...", state="disabled")
        self.root.update()
        
        try:
            self.oscilloscope = Scope()
            idn_str = self.oscilloscope.get_idn() # Pure OOP abstraction call!
            
            self.log_to_terminal("Success", f"Connected to Rigol Scope: {idn_str}")
            self.btn_connect.config(text="CONNECTED", bg="#27ae60")
            self.btn_disconnect.config(state="normal")
            self.btn_sendcmd.config(state="normal")
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="normal")
            self.btn_screenshot.config(state="normal")
            self.btn_autoset.config(state="normal")
            self.btn_live_view.config(state="normal")
            self.btn_invert.config(state="normal")
            self.btn_sendleveltrg.config(state="normal")
            
            self.txt_idn_display.config(state="normal")      
            self.txt_idn_display.delete(0, tk.END)             
            self.txt_idn_display.insert(0, f"Connected: {idn_str}") 
            self.txt_idn_display.config(state="readonly")     
            
        except Exception as e:
            self.log_to_terminal("Error", f"Failed to connect: {e}")
            self.btn_connect.config(text="CONNECT", bg="#2ecc71", state="normal")
            self.oscilloscope = None
            self.txt_idn_display.config(state="normal")
            self.txt_idn_display.delete(0, tk.END)
            self.txt_idn_display.insert(0, "Connection Error!")
            self.txt_idn_display.config(state="readonly")

    def disconnect_scope(self):
        if self.oscilloscope:
            self.oscilloscope.disconnect()
            self.oscilloscope = None
            
        self.log_to_terminal("Disconnected", "Session cleanly terminated.")
        self.btn_connect.config(text="CONNECT", bg="#2ecc71", state="normal")
        self.btn_disconnect.config(state="disabled")
        self.btn_sendcmd.config(state="disabled")
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="disabled")
        self.btn_screenshot.config(state="disabled")
        self.btn_autoset.config(state="disabled")
        self.live_view_running = False
        self.btn_live_view.config(state="disabled", text="START LIVE VIEW", bg="#3498db")
        self.btn_invert.config(state="disabled")
        self.btn_sendleveltrg.config(state="disabled")
        self.txt_idn_display.config(state="normal")
        self.txt_idn_display.delete(0, tk.END)             
        self.txt_idn_display.insert(0, "Scope : Not Connect") 
        self.txt_idn_display.config(state="readonly")

    def send_scpi_command(self):
        if not self.oscilloscope:
            self.log_to_terminal("No Connection", "Connect to the scope first!")
            return
            
        command = self.ip_input.get().strip()
        if not command:
            return
            
        try:
            if "?" in command:
                response = self.oscilloscope.query_raw(command)
                self.log_to_terminal("Query Response", f"Sent: {command} Received: {response}")
            else:
                self.oscilloscope.write_raw(command)
                self.log_to_terminal("Command Sent", f"Successfully wrote: {command}")
        except Exception as e:
            self.log_to_terminal("Command Error", f"Execution failed: {e}")

    def scope_run(self):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return
        try:
            self.oscilloscope.run()
            self.log_to_terminal("Successfully", "Oscilloscope is running now!")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to send RUN command: {e}")

    def scope_stop(self):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return 
        try:
            self.oscilloscope.stop()
            self.log_to_terminal("Successfully", "Oscilloscope is stopping!")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to send STOP command: {e}")

    def change_mode(self, event=None):
        """
            Changed mode into AUTO , NORMAL , SINGLE
        """
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return
        
        selected_mode = self.mode_var.get()
        try:
            self.oscilloscope.set_trigger_sweep(selected_mode)
            self.log_to_terminal("Successfully", f"Oscilloscope changed trigger mode into: {selected_mode} !")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set trigger mode: {e}")
    
    def take_screenshot(self):
        """Action routine triggered by clicking the layout button."""
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return
            
        try:
            image_data = self.oscilloscope.capture_screenshot()
            saved_path = self.oscilloscope.save_png(image_data, directory="./screenshots")
            
            messagebox.showinfo("Screenshot Saved", f"Successfully saved: {saved_path.resolve()}")
        except Exception as e:
            self.log_to_terminal("Capture Error", f"Failed to take screenshot: {e}")
    
    def autoset_command(self):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return 
        try:
            self.oscilloscope.trigger_autoset()
            self.log_to_terminal("Successfully", "Oscilloscope Autosetting now!")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to send AUTOSET command: {e}")

    def change_trigger_source(self, event=None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return
    
        selected_source = self.trigger_source_var.get()
        try:
            if selected_source == "NONE":
                self.oscilloscope.set_trigger_source("EXT") 
                self.log_to_terminal("Successfully", f"Oscilloscope changed trigger source into: {selected_source} !")
            else:
                self.oscilloscope.set_trigger_source(selected_source)
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set trigger mode: {e}")

    def change_trigger_slope(self, event=None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return
    
        selected_slope = self.trigger_slope_var.get()
        try:
            self.oscilloscope.set_trigger_slope(selected_slope)
            self.log_to_terminal("Successfully", f"Oscilloscope sets the edge trigger into: {selected_slope} !")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set trigger mode: {e}")

    def change_trigger_coupling(self, event=None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return
    
        selected_coup = self.trigger_coup_var.get()
        try:
            self.oscilloscope.set_trigger_coupling(selected_coup)
            self.log_to_terminal("Successfully", f"Oscilloscope set the trigger coupling into: {selected_coup} !")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set trigger mode: {e}")
    
    def change_volt_div(self, event = None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return
            
        selected_display = self.volt_div.get()
        volt_map = {
            '100 mV' : '0.1',
            '200 mV' : '0.2',
            '500 mV': '0.5',
            '1 V': '1.0',
            '2 V': '2.0',
            '10 V': '10.0'
        }
        mapping_volt_value = volt_map.get(selected_display, 1.0)

        selected_channel = self.active_channel.get()
        
        try:
            self.oscilloscope.voltage_scale(int(selected_channel),float(mapping_volt_value))
            self.log_to_terminal("Successfully", f"Oscilloscope Channel{selected_channel} vertical scale sets into: {mapping_volt_value} !")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set vertical scale: {e}")

    def change_coupling(self, event = None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return
            
        selected_display = self.coup_channel.get()
        selected_channel = self.active_channel.get()
        
        try:
            self.oscilloscope.configure_coupling(int(selected_channel),selected_display)
            self.log_to_terminal("Successfully", f"Oscilloscope Channel{selected_channel} copuling modes into: {selected_display} !")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set vertical scale: {e}")
    
    def invert_signal(self):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return
        
        selected_channel = self.active_channel.get()
        try:
            self.oscilloscope.toggle_invert(int(selected_channel))
            self.log_to_terminal("Successfully", f"Oscilloscope Channel{selected_channel} inverted!")

        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to send RUN command: {e}")
    
    def time_divide_configure(self, event=None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return
            
        selected_display = self.drop_time_div.get()
        time_map = {
           '100 us' : 0.0001 , '200 us' : 0.0002, '500 us': 0.0005 ,'1 ms': 0.001,'2 ms': 0.002,'5 ms':0.005,'10 ms' : 0.010
        }
        mapping_time_value = time_map.get(selected_display, 0.001)
        try:
            self.oscilloscope.time_scale(float(mapping_time_value))
            self.log_to_terminal("Successfully", f"Oscilloscope horizontal scale sets into: {mapping_time_value} !")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set horizontal scale: {e}")
        
    def probe_setting(self, event=None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return

        selected_display = self.probe_config_channel.get()
        selected_channel = self.active_channel.get()

        probe_map = {
            'X0.1': '0.1',
            'X0.2': '0.2',
            'X0.5': '0.5',
            'X1':   '1',
            'X2':   '2',
            'X5':   '5',
            'X10':  '10',
        }

        attenuation_value = probe_map.get(selected_display,'1')

        if attenuation_value is None:
            self.log_to_terminal("Error", f"Unknown probe setting: {selected_display}")
            return

        try:
            self.oscilloscope.configure_probe(int(selected_channel), attenuation_value)
            self.log_to_terminal("Successfully", f"Oscilloscope Channel{selected_channel} probe sets into: {selected_display} !")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set probe attenuation: {e}")

    def send_level_trig(self):
        if not self.oscilloscope:
            self.log_to_terminal("No Connection", "Connect to the scope first!")
            return
            
        levels_trg = self.level_trig_input.get().strip()
        if not levels_trg:
            return
            
        try:
            self.oscilloscope.trigger_level(float(levels_trg))
            self.log_to_terminal("Successfully", f"Oscilloscope trigger level changed: {levels_trg} !")
        except Exception as e:
            self.log_to_terminal("Command Error", f"Execution failed: {e}")
    
    def toggle_live_view(self):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return

        self.live_view_running = not self.live_view_running
        if self.live_view_running:
            self.btn_live_view.config(text="STOP LIVE VIEW", bg="#e74c3c")
            self.update_live_view()
        else:
            self.btn_live_view.config(text="START LIVE VIEW", bg="#3498db")

    def update_live_view(self):
        if not self.live_view_running or not self.oscilloscope:
            return

        try:
            png_bytes = self.oscilloscope.capture_screenshot()
            img = Image.open(io.BytesIO(png_bytes))

            target_w = self.live_view_container.winfo_width()
            target_h = self.live_view_container.winfo_height()
            if target_w > 1 and target_h > 1:
                img.thumbnail((target_w, target_h), Image.LANCZOS)

            photo = ImageTk.PhotoImage(img)
            self.live_view_label.config(image=photo)
            self.live_view_label.image = photo
        except Exception as e:
            print(f"Live view frame failed: {e}")

        self.root.after(500, self.update_live_view)

if __name__ == "__main__":
    root = tk.Tk()
    app = ScopeApp(root)
    app.log_to_terminal("Welcome to Rigol GUI Tkinter using python!")
    app.log_to_terminal("Oscilloscope type required: DHO800++")
    root.mainloop()