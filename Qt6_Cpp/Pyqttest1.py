import sys
import io
import json
from datetime import datetime
from pathlib import Path

import pyvisa
from PIL import Image
from PyQt6 import QtCore, QtGui, QtWidgets


# =========================================================================
# HARDWARE / BACKEND LAYER (Manages all VISA & SCPI communications)
# =========================================================================
class Scope:
    def __init__(self):
        self.rm = pyvisa.ResourceManager("@py")
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
        self.scope.write(f":CHANnel{channel}:DISPlay ON")

        print(f"Setting Channel {channel} coupling to {coupling}...")
        self.scope.write(f":CHANnel{channel}:COUPling {coupling}")

    def configure_probe(self, channel: int, attenuation: str):
        """Sets the probe ratio of the specified analog channel Accepted arguments : {0.001|0.002|0.005|0.01|0.02|
        0.05|0.1|0.2|0.5|1|2|5|10|20|50|
        100|200|500|1000|2000|5000|
        10000|20000|50000}
        """
        print(f"Ensuring Channel {channel} is ON...")
        self.scope.write(f":CHANnel{channel}:DISPlay ON")

        print(f"Setting Channel {channel} probe attenuation to {attenuation}...")
        self.scope.write(f":CHANnel{channel}:PROBe {attenuation}")

    def toggle_invert(self, channel: int):
        """Turns on or off the waveform invert for the specified channel , Accpeted arguments : 1|ON , 0|OFF"""
        print(f"Ensuring Channel {channel} is ON...")
        self.scope.write(f":CHANnel{channel}:DISPlay ON")

        current_status = self.query_raw(f":CHANnel{channel}:INVert?").strip()
        if current_status in ["1", "ON"]:
            new_status = "OFF"
        else:
            new_status = "ON"

        print(f"Setting Channel {channel} toggle invert {new_status}...")
        self.scope.write(f":CHANnel{channel}:INVert {new_status}")

    def voltage_scale(self, channel: int, scale: float):
        """Sets the vertical scale of the specified channel. Its default unit is V/div"""
        print(f"Ensuring Channel {channel} is ON...")
        self.scope.write(f":CHANnel{channel}:DISPlay ON")

        print(f"Setting Channel {channel} configure vertical scale to {scale}...")
        self.scope.write(f":CHANnel{channel}:SCAle {scale}")

    def trigger_level(self, level: float):
        """Sets or queries the trigger level of Edge trigger. The unit is the same as that of
        current amplitude of the selected source."""
        if self.scope:
            print(f"Setting trigger level to {level}V...")
            self.scope.write(f":TRIGger:PULSe:LEVel {level}")

    def set_trigger_sweep(self, mode):
        """Sets trigger sweep mode (AUTO, NORMAL, or SINGLE)."""
        if self.scope:
            self.scope.write(f":TRIGger:SWEep {mode.upper()}")

    def trigger_autoset(self):
        """Triggers the oscilloscope Autoset function."""
        print("Executing Autoset...")
        if self.scope:
            self.scope.write(":AUToset")
            self.scope.query("*OPC?")

    def set_trigger_source(self, source="CHAN1"):
        """
        Sets the edge trigger source.
        Accepted arguments: 'CHAN1', 'CHAN2', 'CHAN3', 'CHAN4', 'EXT'
        """
        if self.scope:
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
        if self.scope:
            print(f"Configure horizontal time scale to {scale} s/div...")
            self.scope.write(f":TIMebase:SCALe {scale}")

    def capture_screenshot(self):
        """Capture a PNG screenshot from a DHO800 series oscilloscope."""
        if not self.scope:
            raise RuntimeError("No instrument connected.")

        old_timeout = self.scope.timeout
        try:
            self.scope.timeout = 10000
            png_data = self.scope.query_binary_values(":DISPlay:SNAP?", datatype='B', container=bytes)

            if not png_data.startswith(b"\x89PNG"):
                raise RuntimeError("Returned data stream does not contain a valid PNG magic header.")
            return png_data
        finally:
            self.scope.timeout = old_timeout

    def save_png(self, data, directory="."):
        """Saves binary PNG data to storage disk with a systematic timestamp name format."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)

        filename = folder / f"dho814_{timestamp}.png"
        filename.write_bytes(data)
        return filename


# =========================================================================
# USER INTERFACE LAYER (Manages only layout updates and user clicks)
# =========================================================================
class ScopeApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rigol Oscilloscope Controller")
        self.resize(1600, 1400)
        self.oscilloscope = None
        self.live_view_running = False
        self.active_channel = 1

        # ---------Fonts--------- #
        self.channel_font = QtGui.QFont("Candara Light", 14, QtGui.QFont.Weight.Bold)
        self.default_font = QtGui.QFont("Yu Gothic UI Semilight", 12, QtGui.QFont.Weight.Bold)
        self.button_font = QtGui.QFont("Yu Gothic UI Semilight", 8, QtGui.QFont.Weight.Bold)

        self.setStyleSheet("""
            QMainWindow { background-color: #303030; }
            QWidget { background-color: #303030; color: #ffffff; }
            QGroupBox {
                border: 1px solid #555555;
                border-radius: 4px;
                margin-top: 12px;
                background-color: #303030;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
            QLabel { background-color: #1e1e1e; color: #ffffff; padding: 2px; }
            QLineEdit { background-color: #1a1a1a; color: #00ff00; border: 1px solid #555555; }
            QComboBox { background-color: #1e1e1e; color: #ffffff; }
        """)
        radio_style = ("""
        QRadioButton {
            color: black;
        }
        QRadioButton:checked {
            color: yellow;
            font-weight: bold;
        }
        """)

        # ---Central / Main Container---
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QHBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # ---Left-Side Container 80%---
        self.left_column = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(self.left_column)
        left_layout.setContentsMargins(5, 5, 5, 5)

        # ---Right-Side Container 20%---
        self.right_column = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(self.right_column)
        right_layout.setContentsMargins(5, 5, 5, 5)

        main_layout.addWidget(self.left_column, 4)
        main_layout.addWidget(self.right_column, 1)

        # ----Set Terminal Frame---- #
        self.terminal_frame = QtWidgets.QGroupBox("Terminal")
        self.terminal_frame.setFont(self.channel_font)
        terminal_layout = QtWidgets.QVBoxLayout(self.terminal_frame)
        left_layout.addWidget(self.terminal_frame)

        # ------------Live View / Terminal Frame--------- #
        self.live_view_container = QtWidgets.QLabel()
        self.live_view_container.setFixedSize(1110, 480)
        self.live_view_container.setStyleSheet("background-color: black;")
        self.live_view_container.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        terminal_layout.addWidget(self.live_view_container, 0, QtCore.Qt.AlignmentFlag.AlignLeft)

        self.bottomtaskbar_frame = QtWidgets.QWidget()
        bottom_grid = QtWidgets.QGridLayout(self.bottomtaskbar_frame)
        terminal_layout.addWidget(self.bottomtaskbar_frame)

        # -----Setup Elements-------- #
        self.lbl_volt_div_ch1 = QtWidgets.QLabel("VOLT/DIVIDE")
        self.lbl_volt_div_ch1.setFont(self.button_font)
        self.volt_div = QtWidgets.QComboBox()
        self.volt_div.setFont(self.button_font)
        self.volt_div.addItems(['100 mV', '200 mV', '500 mV', '1 V', '2 V', '10 V'])
        self.volt_div.currentIndexChanged.connect(self.change_volt_div)

        self.lbl_coupling = QtWidgets.QLabel("COUPLING")
        self.lbl_coupling.setFont(self.button_font)
        self.coup_channel = QtWidgets.QComboBox()
        self.coup_channel.setFont(self.button_font)
        self.coup_channel.addItems(['AC', 'DC', 'GND'])
        self.coup_channel.currentIndexChanged.connect(self.change_coupling)

        self.lbl_probe_conf = QtWidgets.QLabel("PROBE")
        self.lbl_probe_conf.setFont(self.button_font)
        self.probe_config_channel = QtWidgets.QComboBox()
        self.probe_config_channel.setFont(self.button_font)
        self.probe_config_channel.addItems(['X0.1', 'X0.2', 'X0.5', 'X1', 'X2', 'X5', 'X10'])
        self.probe_config_channel.currentIndexChanged.connect(self.probe_setting)

        # ----Channel radio buttons---- #
        self.rad_ch1 = QtWidgets.QRadioButton("Configure CH1")
        self.rad_ch2 = QtWidgets.QRadioButton("Configure CH2")
        self.rad_ch3 = QtWidgets.QRadioButton("Configure CH3")
        self.rad_ch4 = QtWidgets.QRadioButton("Configure CH4")
        for rb in (self.rad_ch1, self.rad_ch2, self.rad_ch3, self.rad_ch4):
            rb.setFont(self.button_font)
            rb.setStyleSheet(radio_style)
        self.rad_ch1.setChecked(True)

        self.channel_group = QtWidgets.QButtonGroup(self)
        self.channel_group.addButton(self.rad_ch1, 1)
        self.channel_group.addButton(self.rad_ch2, 2)
        self.channel_group.addButton(self.rad_ch3, 3)
        self.channel_group.addButton(self.rad_ch4, 4)
        self.channel_group.idClicked.connect(self.set_active_channel)

        self.btn_invert = QtWidgets.QPushButton("INVERT")
        self.btn_invert.setFont(self.button_font)
        self.btn_invert.setStyleSheet(
            "QPushButton { background-color: #d8cf48; color: #3c0854; border: 0; }"
            "QPushButton:hover { background-color: #f2e640; color: #230332; }"
        )
        self.btn_invert.setEnabled(False)
        self.btn_invert.clicked.connect(self.invert_signal)

        # -----Log frame and setup------- #
        self.terminal_log = QtWidgets.QTextEdit()
        self.terminal_log.setReadOnly(True)
        self.terminal_log.setStyleSheet("background-color: #000000; color: #00FF00;")
        self.terminal_log.setFont(QtGui.QFont("Courier New", 10))
        self.terminal_log.setMinimumWidth(500)
        self.terminal_log.setMinimumHeight(150)

        # -----CHECKBOX FOR CHANNELS----------- #
        bottom_grid.addWidget(self.rad_ch1, 0, 0)
        bottom_grid.addWidget(self.rad_ch2, 1, 0)
        bottom_grid.addWidget(self.rad_ch3, 2, 0)
        bottom_grid.addWidget(self.rad_ch4, 3, 0)

        # ----Invert Button------ #
        bottom_grid.addWidget(self.btn_invert, 1, 1)

        # ------VOLT/DIV DROPDOWN MENUS------- #
        bottom_grid.addWidget(self.lbl_volt_div_ch1, 0, 1)
        bottom_grid.addWidget(self.volt_div, 0, 2)

        # ------COUPLING DROPDOWN MENUS------- #
        bottom_grid.addWidget(self.lbl_coupling, 2, 1)
        bottom_grid.addWidget(self.coup_channel, 2, 2)

        # ------PROBE SET DROPDOWN MENUS------- #
        bottom_grid.addWidget(self.lbl_probe_conf, 3, 1)
        bottom_grid.addWidget(self.probe_config_channel, 3, 2)

        # ------Log box------- #
        bottom_grid.addWidget(self.terminal_log, 0, 3, 4, 3)

        # ============= RIGHT COLUMN ============= #

        # Horizontal
        self.horizontal_frame = QtWidgets.QGroupBox("Horizontal Configure")
        self.horizontal_frame.setStyleSheet("QGroupBox::title { color: #C99C0A; }")
        h_layout = QtWidgets.QGridLayout(self.horizontal_frame)
        right_layout.addWidget(self.horizontal_frame)

        self.lbl_tdiv = QtWidgets.QLabel("TIME/DIV")
        self.lbl_tdiv.setFont(self.button_font)
        self.drop_time_div = QtWidgets.QComboBox()
        self.drop_time_div.setFont(self.button_font)
        self.drop_time_div.addItems(['100 us', '200 us', '500 us', '1 ms', '2 ms', '5 ms', '10 ms'])
        self.drop_time_div.currentIndexChanged.connect(self.time_divide_configure)

        h_layout.addWidget(self.lbl_tdiv, 0, 0)
        h_layout.addWidget(self.drop_time_div, 1, 0, 1, 2)

        # Trigger
        self.trigger_frame = QtWidgets.QGroupBox("Trigger Configure")
        self.trigger_frame.setStyleSheet("QGroupBox::title { color: #B9CF0D; }")
        t_layout = QtWidgets.QGridLayout(self.trigger_frame)
        right_layout.addWidget(self.trigger_frame)

        self.lbl_trg_source = QtWidgets.QLabel("SOURCE")
        self.lbl_trg_source.setFont(self.button_font)
        self.drop_trig_source = QtWidgets.QComboBox()
        self.drop_trig_source.setFont(self.button_font)
        self.drop_trig_source.addItems(['CH1', 'CH2', 'CH3', 'CH4', 'NONE'])
        self.drop_trig_source.currentIndexChanged.connect(self.change_trigger_source)

        self.lbl_trg_slope = QtWidgets.QLabel("SLOPE")
        self.lbl_trg_slope.setFont(self.button_font)
        self.drop_trig_slope = QtWidgets.QComboBox()
        self.drop_trig_slope.setFont(self.button_font)
        self.drop_trig_slope.addItems(['RISING', 'FALLING', 'BOTH'])
        self.drop_trig_slope.currentIndexChanged.connect(self.change_trigger_slope)

        self.lbl_trg_coupling = QtWidgets.QLabel("COUPLING")
        self.lbl_trg_coupling.setFont(self.button_font)
        self.drop_trig_coup = QtWidgets.QComboBox()
        self.drop_trig_coup.setFont(self.button_font)
        self.drop_trig_coup.addItems(['AC', 'DC', 'LFR', 'HFR'])
        self.drop_trig_coup.setCurrentIndex(1)
        self.drop_trig_coup.currentIndexChanged.connect(self.change_trigger_coupling)

        self.lbl_levels_trig = QtWidgets.QLabel("TRIGGER LEVEL")
        self.lbl_levels_trig.setFont(self.button_font)
        self.level_trig_input = QtWidgets.QLineEdit("0")
        self.level_trig_input.setFont(self.button_font)
        self.btn_sendleveltrg = QtWidgets.QPushButton("APPLY")
        self.btn_sendleveltrg.setFont(self.button_font)
        self.btn_sendleveltrg.setStyleSheet(
            "QPushButton { background-color: #b9c847; color: #000000; border: 0; }"
            "QPushButton:hover { background-color: #b9bf8e; }"
        )
        self.btn_sendleveltrg.setEnabled(False)
        self.btn_sendleveltrg.clicked.connect(self.send_level_trig)

        # -------- Trigger Source----------- #
        t_layout.addWidget(self.lbl_trg_source, 0, 0)
        t_layout.addWidget(self.drop_trig_source, 1, 0, 1, 2)

        # -------- Trigger Slope----------- #
        t_layout.addWidget(self.lbl_trg_slope, 0, 3)
        t_layout.addWidget(self.drop_trig_slope, 1, 3, 1, 2)

        # -------- Trigger Coupling----------- #
        t_layout.addWidget(self.lbl_trg_coupling, 0, 5)
        t_layout.addWidget(self.drop_trig_coup, 1, 5, 1, 2)

        # ----Trigger Level------ #
        t_layout.addWidget(self.lbl_levels_trig, 2, 0, 1, 2)
        t_layout.addWidget(self.level_trig_input, 3, 0, 1, 2)
        t_layout.addWidget(self.btn_sendleveltrg, 3, 2, 1, 2)

        # Home / System Control Frame
        self.system_frame = QtWidgets.QGroupBox("Start & Stop / SCPI Commands")
        self.system_frame.setStyleSheet("QGroupBox::title { color: #1CC209; }")
        s_layout = QtWidgets.QGridLayout(self.system_frame)
        right_layout.addWidget(self.system_frame)

        self.btn_connect = QtWidgets.QPushButton("CONNECT")
        self.btn_connect.setFont(self.button_font)
        self.btn_connect.setStyleSheet(
            "QPushButton { background-color: #2ecc71; color: #ffffff; border: 0; }"
            "QPushButton:hover { background-color: #27ae60; }"
        )
        self.btn_connect.clicked.connect(self.connect_scope)

        self.btn_disconnect = QtWidgets.QPushButton("DISCONNECT")
        self.btn_disconnect.setFont(self.button_font)
        self.btn_disconnect.setStyleSheet(
            "QPushButton { background-color: #d53f3d; color: #000000; border: 0; }"
            "QPushButton:hover { background-color: #c70805; }"
        )
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.clicked.connect(self.disconnect_scope)

        self.btn_sendcmd = QtWidgets.QPushButton("SEND COMMANDS")
        self.btn_sendcmd.setFont(self.button_font)
        self.btn_sendcmd.setStyleSheet(
            "QPushButton { background-color: #4594de; color: #000000; border: 0; }"
            "QPushButton:hover { background-color: #086ecd; }"
        )
        self.btn_sendcmd.setEnabled(False)
        self.btn_sendcmd.clicked.connect(self.send_scpi_command)

        self.lbl_scpi = QtWidgets.QLabel("SCPI COMMANDS")
        self.lbl_scpi.setFont(self.button_font)

        self.ip_input = QtWidgets.QLineEdit("*IDN")
        self.ip_input.setFont(self.button_font)

        self.txt_idn_display = QtWidgets.QLineEdit("Scope: Not Connected")
        self.txt_idn_display.setFont(self.default_font)
        self.txt_idn_display.setReadOnly(True)

        self.btn_start = QtWidgets.QPushButton("RUN")
        self.btn_start.setFont(self.button_font)
        self.btn_start.setStyleSheet(
            "QPushButton { background-color: #2ecc71; color: #ffffff; border: 0; }"
            "QPushButton:hover { background-color: #27ae60; }"
        )
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.scope_run)

        self.btn_stop = QtWidgets.QPushButton("STOP")
        self.btn_stop.setFont(self.button_font)
        self.btn_stop.setStyleSheet(
            "QPushButton { background-color: #d53f3d; color: #000000; border: 0; }"
            "QPushButton:hover { background-color: #c70805; }"
        )
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.scope_stop)

        self.lbl_mode = QtWidgets.QLabel("MODE")
        self.lbl_mode.setFont(self.button_font)
        self.drop_trig_mode = QtWidgets.QComboBox()
        self.drop_trig_mode.setFont(self.button_font)
        self.drop_trig_mode.addItems(['AUTO', 'NORMAL', 'SINGLE'])
        self.drop_trig_mode.currentIndexChanged.connect(self.change_mode)

        # ------------ Row 0 Layout ----------------- #
        s_layout.addWidget(self.btn_connect, 0, 0)
        s_layout.addWidget(self.btn_disconnect, 0, 1)
        s_layout.addWidget(self.lbl_scpi, 0, 2)
        s_layout.addWidget(self.ip_input, 0, 2)
        s_layout.addWidget(self.btn_sendcmd, 0, 3)

        # ------------ Row 1 Layout ----------------- #
        s_layout.addWidget(self.txt_idn_display, 1, 0, 1, 4)

        # ------------ Row 2 Layout ----------------- #
        s_layout.addWidget(self.btn_start, 2, 0)
        s_layout.addWidget(self.btn_stop, 2, 1)
        s_layout.addWidget(self.lbl_mode, 2, 2)
        s_layout.addWidget(self.drop_trig_mode, 2, 2, 1, 2)

        # Storage Frame
        self.storage_frame = QtWidgets.QGroupBox("Storage and Etc.")
        self.storage_frame.setStyleSheet("QGroupBox::title { color: #C446EE; }")
        st_layout = QtWidgets.QGridLayout(self.storage_frame)
        right_layout.addWidget(self.storage_frame)

        self.btn_screenshot = QtWidgets.QPushButton("CAPTURE SCREENSHOT")
        self.btn_screenshot.setFont(self.button_font)
        self.btn_screenshot.setStyleSheet(
            "QPushButton { background-color: #9b59b6; color: #ffffff; border: 0; }"
            "QPushButton:hover { background-color: #8e44ad; }"
        )
        self.btn_screenshot.setEnabled(False)
        self.btn_screenshot.clicked.connect(self.take_screenshot)

        self.btn_autoset = QtWidgets.QPushButton("AUTOSET")
        self.btn_autoset.setFont(self.button_font)
        self.btn_autoset.setStyleSheet(
            "QPushButton { background-color: #080808; color: #1274e4; border: 0; }"
            "QPushButton:hover { background-color: #000000; color: #044fa4; }"
        )
        self.btn_autoset.setEnabled(False)
        self.btn_autoset.clicked.connect(self.autoset_command)

        self.btn_live_view = QtWidgets.QPushButton("START LIVE VIEW")
        self.btn_live_view.setFont(self.button_font)
        self.btn_live_view.setStyleSheet(
            "QPushButton { background-color: #3498db; color: #ffffff; border: 0; }"
        )
        self.btn_live_view.setEnabled(False)
        self.btn_live_view.clicked.connect(self.toggle_live_view)

        self.btn_log_clear = QtWidgets.QPushButton("CLEAR LOG MESSAGE")
        self.btn_log_clear.setFont(self.button_font)
        self.btn_log_clear.setStyleSheet(
            "QPushButton { background-color: #32D9C0; color: #000000; border: 0; }"
            "QPushButton:hover { background-color: #8DE0D4; }"
        )
        self.btn_log_clear.clicked.connect(self.clear_log_terminal)

        st_layout.addWidget(self.btn_screenshot, 0, 0)
        st_layout.addWidget(self.btn_autoset, 1, 0)
        st_layout.addWidget(self.btn_live_view, 2, 0)
        st_layout.addWidget(self.btn_log_clear, 0, 1)

        # ----Live view refresh timer (replaces tk root.after loop)---- #
        self.live_view_timer = QtCore.QTimer(self)
        self.live_view_timer.timeout.connect(self.update_live_view)

        # Presets Frame
        self.preset_frame = QtWidgets.QGroupBox("Presets")
        self.preset_frame.setStyleSheet("QGroupBox::title { color: #E67E22; }")
        p_layout = QtWidgets.QGridLayout(self.preset_frame)
        right_layout.addWidget(self.preset_frame)

        self.presets_file = Path("presets.json")

        self.lbl_preset_name = QtWidgets.QLabel("PRESET NAME")
        self.lbl_preset_name.setFont(self.button_font)
        self.preset_name_input = QtWidgets.QLineEdit()
        self.preset_name_input.setFont(self.button_font)
        self.preset_name_input.setPlaceholderText("e.g. My Setup 1")

        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.setFont(self.button_font)
        self.preset_combo.currentTextChanged.connect(self.on_preset_selected)

        self.btn_save_preset = QtWidgets.QPushButton("SAVE")
        self.btn_save_preset.setFont(self.button_font)
        self.btn_save_preset.setStyleSheet(
            "QPushButton { background-color: #E67E22; color: #000000; border: 0; }"
            "QPushButton:hover { background-color: #F39C12; }"
        )
        self.btn_save_preset.clicked.connect(self.save_preset)

        self.btn_load_preset = QtWidgets.QPushButton("LOAD")
        self.btn_load_preset.setFont(self.button_font)
        self.btn_load_preset.setStyleSheet(
            "QPushButton { background-color: #27AE60; color: #ffffff; border: 0; }"
            "QPushButton:hover { background-color: #2ECC71; }"
        )
        self.btn_load_preset.clicked.connect(self.load_preset)

        self.btn_delete_preset = QtWidgets.QPushButton("DELETE")
        self.btn_delete_preset.setFont(self.button_font)
        self.btn_delete_preset.setStyleSheet(
            "QPushButton { background-color: #C0392B; color: #ffffff; border: 0; }"
            "QPushButton:hover { background-color: #E74C3C; }"
        )
        self.btn_delete_preset.clicked.connect(self.delete_preset)

        p_layout.addWidget(self.lbl_preset_name, 0, 0, 1, 2)
        p_layout.addWidget(self.preset_name_input, 1, 0, 1, 2)
        p_layout.addWidget(self.btn_save_preset, 1, 2)

        p_layout.addWidget(self.preset_combo, 2, 0, 1, 2)
        p_layout.addWidget(self.btn_load_preset, 2, 2)
        p_layout.addWidget(self.btn_delete_preset, 3, 2)

        self.refresh_preset_list()

        right_layout.addStretch(1)
    # ==========================================
    # EVENT LOGIC METHODS (Clean UI Layer)
    # ==========================================
    def log_to_terminal(self, title: str, message: str = None):
        if message is None:
            message = title
            title = None

        timestamp = datetime.now().strftime("%H:%M:%S")
        if title:
            self.terminal_log.append(f"[{timestamp}] {title}: {message}")
        else:
            self.terminal_log.append(f"[{timestamp}] {message}")
        self.terminal_log.verticalScrollBar().setValue(
            self.terminal_log.verticalScrollBar().maximum()
        )

    def clear_log_terminal(self):
        self.terminal_log.clear()

    def set_active_channel(self, channel_id):
        self.active_channel = channel_id

    def connect_scope(self):
        """Initializes backend class and updates buttons."""
        self.btn_connect.setText("SEARCHING...")
        self.btn_connect.setEnabled(False)
        QtWidgets.QApplication.processEvents()

        try:
            self.oscilloscope = Scope()
            idn_str = self.oscilloscope.get_idn()

            self.log_to_terminal("Success", f"Connected to Rigol Scope: {idn_str}")
            self.btn_connect.setText("CONNECTED")
            self.btn_connect.setStyleSheet("QPushButton { background-color: #27ae60; color: #ffffff; border: 0; }")
            self.btn_disconnect.setEnabled(True)
            self.btn_sendcmd.setEnabled(True)
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(True)
            self.btn_screenshot.setEnabled(True)
            self.btn_autoset.setEnabled(True)
            self.btn_live_view.setEnabled(True)
            self.btn_invert.setEnabled(True)
            self.btn_sendleveltrg.setEnabled(True)

            self.txt_idn_display.setText(f"Connected: {idn_str}")

        except Exception as e:
            self.log_to_terminal("Error", f"Failed to connect: {e}")
            self.btn_connect.setText("CONNECT")
            self.btn_connect.setStyleSheet("QPushButton { background-color: #2ecc71; color: #ffffff; border: 0; }")
            self.btn_connect.setEnabled(True)
            self.oscilloscope = None
            self.txt_idn_display.setText("Connection Error!")

    def disconnect_scope(self):
        if self.oscilloscope:
            self.oscilloscope.disconnect()
            self.oscilloscope = None

        self.log_to_terminal("Disconnected", "Session cleanly terminated.")
        self.btn_connect.setText("CONNECT")
        self.btn_connect.setStyleSheet("QPushButton { background-color: #2ecc71; color: #ffffff; border: 0; }")
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.btn_sendcmd.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_screenshot.setEnabled(False)
        self.btn_autoset.setEnabled(False)
        self.live_view_running = False
        self.live_view_timer.stop()
        self.btn_live_view.setEnabled(False)
        self.btn_live_view.setText("START LIVE VIEW")
        self.btn_live_view.setStyleSheet("QPushButton { background-color: #3498db; color: #ffffff; border: 0; }")
        self.btn_invert.setEnabled(False)
        self.btn_sendleveltrg.setEnabled(False)
        self.txt_idn_display.setText("Scope : Not Connect")

    def send_scpi_command(self):
        if not self.oscilloscope:
            self.log_to_terminal("No Connection", "Connect to the scope first!")
            return

        command = self.ip_input.text().strip()
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

    def change_mode(self, index=None):
        """
            Changed mode into AUTO , NORMAL , SINGLE
        """
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return

        selected_mode = self.drop_trig_mode.currentText()
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

            QtWidgets.QMessageBox.information(
                self, "Screenshot Saved", f"Successfully saved: {saved_path.resolve()}"
            )
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

    def change_trigger_source(self, index=None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return

        selected_source = self.drop_trig_source.currentText()
        try:
            if selected_source == "NONE":
                self.oscilloscope.set_trigger_source("EXT")
                self.log_to_terminal("Successfully", f"Oscilloscope changed trigger source into: {selected_source} !")
            else:
                self.oscilloscope.set_trigger_source(selected_source)
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set trigger mode: {e}")

    def change_trigger_slope(self, index=None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return

        selected_slope = self.drop_trig_slope.currentText()
        try:
            self.oscilloscope.set_trigger_slope(selected_slope)
            self.log_to_terminal("Successfully", f"Oscilloscope sets the edge trigger into: {selected_slope} !")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set trigger mode: {e}")

    def change_trigger_coupling(self, index=None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return

        selected_coup = self.drop_trig_coup.currentText()
        try:
            self.oscilloscope.set_trigger_coupling(selected_coup)
            self.log_to_terminal("Successfully", f"Oscilloscope set the trigger coupling into: {selected_coup} !")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set trigger mode: {e}")

    def change_volt_div(self, index=None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return

        selected_display = self.volt_div.currentText()
        volt_map = {
            '100 mV': '0.1',
            '200 mV': '0.2',
            '500 mV': '0.5',
            '1 V': '1.0',
            '2 V': '2.0',
            '10 V': '10.0'
        }
        mapping_volt_value = volt_map.get(selected_display, 1.0)

        selected_channel = self.active_channel

        try:
            self.oscilloscope.voltage_scale(int(selected_channel), float(mapping_volt_value))
            self.log_to_terminal("Successfully", f"Oscilloscope Channel{selected_channel} vertical scale sets into: {mapping_volt_value} !")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set vertical scale: {e}")

    def change_coupling(self, index=None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return

        selected_display = self.coup_channel.currentText()
        selected_channel = self.active_channel

        try:
            self.oscilloscope.configure_coupling(int(selected_channel), selected_display)
            self.log_to_terminal("Successfully", f"Oscilloscope Channel{selected_channel} copuling modes into: {selected_display} !")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set vertical scale: {e}")

    def invert_signal(self):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return

        selected_channel = self.active_channel
        try:
            self.oscilloscope.toggle_invert(int(selected_channel))
            self.log_to_terminal("Successfully", f"Oscilloscope Channel{selected_channel} inverted!")

        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to send RUN command: {e}")

    def time_divide_configure(self, index=None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return

        selected_display = self.drop_time_div.currentText()
        time_map = {
            '100 us': 0.0001, '200 us': 0.0002, '500 us': 0.0005, '1 ms': 0.001,
            '2 ms': 0.002, '5 ms': 0.005, '10 ms': 0.010
        }
        mapping_time_value = time_map.get(selected_display, 0.001)
        try:
            self.oscilloscope.time_scale(float(mapping_time_value))
            self.log_to_terminal("Successfully", f"Oscilloscope horizontal scale sets into: {mapping_time_value} !")
        except Exception as e:
            self.log_to_terminal("SCPI Error", f"Failed to set horizontal scale: {e}")

    def probe_setting(self, index=None):
        if not self.oscilloscope:
            self.log_to_terminal("Error", "Oscilloscope is not connected!")
            return

        selected_display = self.probe_config_channel.currentText()
        selected_channel = self.active_channel

        probe_map = {
            'X0.1': '0.1',
            'X0.2': '0.2',
            'X0.5': '0.5',
            'X1': '1',
            'X2': '2',
            'X5': '5',
            'X10': '10',
        }

        attenuation_value = probe_map.get(selected_display, '1')

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

        levels_trg = self.level_trig_input.text().strip()
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
            self.btn_live_view.setText("STOP LIVE VIEW")
            self.btn_live_view.setStyleSheet("QPushButton { background-color: #e74c3c; color: #ffffff; border: 0; }")
            self.live_view_timer.start(500)
        else:
            self.btn_live_view.setText("START LIVE VIEW")
            self.btn_live_view.setStyleSheet("QPushButton { background-color: #3498db; color: #ffffff; border: 0; }")
            self.live_view_timer.stop()

    def update_live_view(self):
        if not self.live_view_running or not self.oscilloscope:
            return

        try:
            png_bytes = self.oscilloscope.capture_screenshot()
            img = Image.open(io.BytesIO(png_bytes))

            target_w = self.live_view_container.width()
            target_h = self.live_view_container.height()
            if target_w > 1 and target_h > 1:
                img.thumbnail((target_w, target_h), Image.LANCZOS)

            img = img.convert("RGB")
            qimage = QtGui.QImage(
                img.tobytes(), img.width, img.height, img.width * 3, QtGui.QImage.Format.Format_RGB888
            )
            pixmap = QtGui.QPixmap.fromImage(qimage)
            self.live_view_container.setPixmap(pixmap)
        except Exception as e:
            print(f"Live view frame failed: {e}")

    def closeEvent(self, event):
        """Ensure the instrument connection is released on window close."""
        self.live_view_timer.stop()
        if self.oscilloscope:
            try:
                self.oscilloscope.disconnect()
            except Exception:
                pass
        event.accept()

    def gather_current_settings(self):
        """Snapshot all current dropdown/radio states into a dict."""
        return {
            "active_channel": self.active_channel,
            "volt_div": self.volt_div.currentText(),
            "coupling": self.coup_channel.currentText(),
            "probe": self.probe_config_channel.currentText(),
            "time_div": self.drop_time_div.currentText(),
            "trig_source": self.drop_trig_source.currentText(),
            "trig_slope": self.drop_trig_slope.currentText(),
            "trig_coupling": self.drop_trig_coup.currentText(),
            "trig_level": self.level_trig_input.text(),
            "trig_mode": self.drop_trig_mode.currentText(),
        }

    def apply_settings(self, settings: dict, send_to_scope: bool = True):
        """Apply a settings dict back to the UI, optionally pushing to the scope."""
        # Select the right channel radio button first
        channel = settings.get("active_channel", 1)
        btn = self.channel_group.button(channel)
        if btn:
            btn.setChecked(True)
            self.active_channel = channel

        # Block signals while restoring UI so we don't spam SCPI writes per-field,
        # then optionally push everything at once at the end.
        widgets_map = [
            (self.volt_div, "volt_div"),
            (self.coup_channel, "coupling"),
            (self.probe_config_channel, "probe"),
            (self.drop_time_div, "time_div"),
            (self.drop_trig_source, "trig_source"),
            (self.drop_trig_slope, "trig_slope"),
            (self.drop_trig_coup, "trig_coupling"),
            (self.drop_trig_mode, "trig_mode"),
        ]
        for widget, key in widgets_map:
            if key in settings:
                widget.blockSignals(True)
                widget.setCurrentText(settings[key])
                widget.blockSignals(False)

        if "trig_level" in settings:
            self.level_trig_input.setText(settings["trig_level"])

        if send_to_scope and self.oscilloscope:
            try:
                self.change_volt_div()
                self.change_coupling()
                self.probe_setting()
                self.time_divide_configure()
                self.change_trigger_source()
                self.change_trigger_slope()
                self.change_trigger_coupling()
                self.change_mode()
                self.send_level_trig()
            except Exception as e:
                self.log_to_terminal("Preset Error", f"Failed applying to scope: {e}")

    def load_presets_from_disk(self):
        if self.presets_file.exists():
            try:
                return json.loads(self.presets_file.read_text())
            except Exception as e:
                self.log_to_terminal("Preset Error", f"Corrupt presets file: {e}")
        return {}

    def refresh_preset_list(self):
        presets = self.load_presets_from_disk()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItems(sorted(presets.keys()))
        self.preset_combo.blockSignals(False)

    def save_preset(self):
        name = self.preset_name_input.text().strip()
        if not name:
            self.log_to_terminal("Preset", "Enter a name before saving.")
            return

        presets = self.load_presets_from_disk()
        presets[name] = self.gather_current_settings()
        self.presets_file.write_text(json.dumps(presets, indent=2))

        self.refresh_preset_list()
        self.preset_combo.setCurrentText(name)
        self.log_to_terminal("Preset Saved", f"'{name}' saved successfully.")

    def load_preset(self):
        name = self.preset_combo.currentText()
        if not name:
            self.log_to_terminal("Preset", "No preset selected.")
            return

        presets = self.load_presets_from_disk()
        settings = presets.get(name)
        if not settings:
            self.log_to_terminal("Preset Error", f"'{name}' not found.")
            return

        self.apply_settings(settings)
        self.log_to_terminal("Preset Loaded", f"'{name}' applied.")

    def delete_preset(self):
        name = self.preset_combo.currentText()
        if not name:
            return

        presets = self.load_presets_from_disk()
        if name in presets:
            del presets[name]
            self.presets_file.write_text(json.dumps(presets, indent=2))
            self.refresh_preset_list()
            self.log_to_terminal("Preset Deleted", f"'{name}' removed.")

    def on_preset_selected(self, name):
        """Optional: preview the name in the input box when selecting from the list."""
        if name:
            self.preset_name_input.setText(name)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = ScopeApp()
    window.log_to_terminal("Welcome to Rigol GUI PyQt6 using python!")
    window.log_to_terminal("Oscilloscope type required: DHO800++")
    window.show()
    sys.exit(app.exec())