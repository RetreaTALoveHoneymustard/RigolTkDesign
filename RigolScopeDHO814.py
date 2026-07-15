import tkinter as tk
from tkinter import ttk , messagebox , font as tkfont
import numpy as np
import time
import pyvisa
from datetime import datetime
from pathlib import Path

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

class Scope:
    def __init__(self):
        self.rm = pyvisa.ResourceManager("@py")
        self.instrument = self.find_rigol_instrument()

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
    
    def disconnect(self):
        """Close the instrument and VISA resource manager."""
        # This will now work perfectly because self.scope was defined in __init__
        if hasattr(self, 'scope') and self.scope is not None:
            self.scope.close()
            self.scope = None
            print("Instrument disconnected.")
            
        if hasattr(self, 'rm') and self.rm is not None:
            self.rm.close()
            self.rm = None
            print("Resource Manager closed.")

class ScopeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Rigol Oscilloscope Controller")
        self.root.geometry("1600x1400")
        self.oscilloscope = None
        self.channel_font = tkfont.Font(family="Candara Light",size=14,weight="bold")
        self.default_font = tkfont.Font(family="Yu Gothic UI Semilight", size ="12")
        self.button_font = tkfont.Font(family="Yu Gothic UI Semilight", size ="8",weight="bold")
        
        # ---Main Container---
        self.main_container = ttk.Frame(root, padding="10")# Main Container creater
        self.main_container.pack(fill=tk.BOTH, expand=True)
        self.main_container.grid_columnconfigure(0, weight=4)#make column that exceed 80% of all column pixels
        self.main_container.grid_columnconfigure(1, weight=1) #make column that exceed 20% of all column pixels
        self.main_container.grid_rowconfigure(0, weight=1)#make row(1) 
        #---Main Container---
        
        #---Left-Side Container 80% of all Main Container---
        self.left_column = ttk.Frame(self.main_container, padding="5")
        self.left_column.grid(row=0, column=0, sticky="nsew")
        
        # Create the 4 Sidebar Block Frames
        for i in range(4):
            self.left_column.grid_rowconfigure(i, weight=1)
        self.left_column.grid_columnconfigure(0, weight=1)

        # Create the 4 Sidebar Block Frames
        #//CH1 CONTAINER//
        ch1_title_label = ttk.Label(self.left_column, text="Channel 1", font=self.channel_font)#Create a custom Label 
        self.ch1_frame = ttk.LabelFrame(self.left_column, labelwidget=ch1_title_label)#Pass into a LabelFrame with labelwidget to avoid a conflict
        self.ch1_frame.grid(row=0, column=0, pady=5, sticky="nsew")#Provide coordinate and nsew for widget fits all directions (north south east west)

        #//CH2 CONTAINER//
        ch2_title_label = ttk.Label(self.left_column, text="Channel 2", font=self.channel_font)#Create a custom Label 
        self.ch2_frame = ttk.LabelFrame(self.left_column, labelwidget=ch2_title_label)#Pass into a LabelFrame with labelwidget to avoid a conflict
        self.ch2_frame.grid(row=1, column=0, pady=5, sticky="nsew")#Provide coordinate and nsew for widget fits all directions (north south east west)

        #//CH3 CONTAINER//
        ch3_title_label = ttk.Label(self.left_column, text="Channel 3", font=self.channel_font)
        self.ch3_frame = ttk.LabelFrame(self.left_column, labelwidget=ch3_title_label)
        self.ch3_frame.grid(row=2, column=0, pady=5, sticky="nsew")

        #//CH4 CONTAINER//
        ch4_title_label = ttk.Label(self.left_column, text="Channel 4", font=self.channel_font)
        self.ch4_frame = ttk.LabelFrame(self.left_column, labelwidget=ch4_title_label)
        self.ch4_frame.grid(row=3, column=0, pady=5, sticky="nsew")
        #---Left-Side Container 80% of all Main Container---

        #---Right-Side Container 20% of all Main Container---
        self.right_column = ttk.Frame(self.main_container, padding="5")
        self.right_column.grid(row=0, column=1, sticky="nsew")
        
        # Configure 4 rows for the sidebar blocks
        for r in range(4):
            self.right_column.grid_rowconfigure(r, weight=1)
        self.right_column.grid_columnconfigure(0, weight=1)

        # Create the 4 Sidebar Block Frames
        #//Horizontal_Figure CONTAINER//
        horizontal_config_label = ttk.Label(self.right_column, text="Horizontal Configure", font=self.default_font)
        self.horizontal_frame = ttk.LabelFrame(self.right_column, labelwidget=horizontal_config_label)
        self.horizontal_frame.grid(row=0, column=0, pady=5, sticky="nsew")

        #//Trigger Container//
        trigger_config_label = ttk.Label(self.right_column, text="Trigger Configure", font=self.default_font)
        self.trigger_frame = ttk.LabelFrame(self.right_column, labelwidget=trigger_config_label)
        self.trigger_frame.grid(row=1, column=0, pady=5, sticky="nsew")

        #//Home Container//
        home_config_label = ttk.Label(self.right_column, text="Start & Stop / SCPI Commands", font=self.default_font)
        self.system_frame = ttk.LabelFrame(self.right_column, labelwidget=home_config_label)
        self.system_frame.grid(row=2, column=0, pady=5, sticky="nsew")
        
        # Configure 3 rows for the sidebar blocks
        for r in range(3):
            self.system_frame.grid_columnconfigure(r, weight=1)
        self.system_frame.grid_rowconfigure(0, weight=4)
        self.system_frame.grid_rowconfigure(1, weight=2)    
        self.system_frame.grid_rowconfigure(2, weight=4)


        self.btn_connect = tk.Button(
        self.system_frame,                     #Where the button lives (parent frame)
        text="CONNECT",                     #The text displayed on the button
        font=self.button_font,             #custom "Yu Gothic UI Semilight" font
        bg="#2ecc71",                     #Background color
        fg="#ffffff",                     #Text color
        activebackground="#27ae60",       #Color when the user clicks it
        activeforeground="#ffffff",       #Text color when clicked
        bd=0,                               #Border width (0 makes it flat)
        command=self.connect_scope    #The function to run when clicked
        )

        self.btn_disconnect = tk.Button(
        self.system_frame,                 
        text="DISCONNECT",                  
        font=self.button_font,            
        bg="#d53f3d",                   
        fg="#000000",                     
        activebackground="#c70805",      
        activeforeground="#000000",       
        bd=0,
        command=self.disconnect_scope                               
        )

        self.btn_sendcmd = tk.Button(
        self.system_frame,                  
        text="SEND COMMANDS",                    
        font=self.button_font,           
        bg="#4594de",                     
        fg="#000000",                  
        activebackground="#086ecd",       
        activeforeground="#000000",       
        bd=0,
        command=self.send_scpi_command                               
        )

        self.lbl_scpi = tk.Label(
            self.system_frame,
            text="SCPI COMMANDS",
            font=self.button_font,
            fg="#ffffff",     
            bg="#1e1e1e"            
        )

        # Create a text box for the IDN display
        self.txt_idn_display = tk.Entry(
            self.system_frame, 
            font=self.default_font,
            bg="#1a1a1a",
            fg="#00ff00", 
            bd=1,
            relief="solid"
        )

        self.btn_start = tk.Button(
        self.system_frame,                     #Where the button lives (parent frame)
        text="RUN",                     #The text displayed on the button
        font=self.button_font,             #custom "Yu Gothic UI Semilight" font
        bg="#2ecc71",                     #Background color
        fg="#ffffff",                     #Text color
        activebackground="#27ae60",       #Color when the user clicks it
        activeforeground="#ffffff",       #Text color when clicked
        bd=0,                               #Border width (0 makes it flat)
        command=self.scope_run   #The function to run when clicked
        )

        self.btn_stop = tk.Button(
        self.system_frame,                 
        text="STOP",                  
        font=self.button_font,            
        bg="#d53f3d",                   
        fg="#000000",                     
        activebackground="#c70805",      
        activeforeground="#000000",       
        bd=0,
        command=self.scope_stop                               
        )

        self.trigger_mode_var = tk.StringVar()
        
        self.drop_trig_mode = ttk.Combobox(
            self.system_frame, 
            textvariable=self.trigger_mode_var,
            font=self.button_font,
            state="readonly" # Prevents user from typing custom text
        )

        self.lbl_mode = tk.Label(
            self.system_frame,
            text="MODE",
            font=self.button_font,
            fg="#ffffff",     
            bg="#1e1e1e"            
        )

        #------------ Row 0 -----------------#
        self.ip_input = tk.Entry(self.system_frame, font=self.button_font)
        self.ip_input.insert(0, "*IDN") 
        self.btn_connect.grid(column=0, row=0, padx=5, pady=5, ipadx=5, ipady=5, sticky="ew")
        self.btn_disconnect.grid(column=1, row=0, padx=5, pady=5, ipadx=5, ipady=5, sticky="ew")
        self.lbl_scpi.grid(column=2, row=0, padx=5, pady=(2, 22), sticky="w") 
        self.ip_input.grid(column=2, row=0, padx=5, pady=(20, 5), ipadx=40, sticky="ew")
        self.btn_sendcmd.grid(column=3, row=0, padx=5, pady=5, ipadx=5, ipady=5, sticky="ew")
        #------------ Row 1 -----------------#
        self.txt_idn_display.grid(column=0, row=1, columnspan=4,padx = 10, sticky="ew")
        self.txt_idn_display.insert(0, "Scope: Not Connected")
        self.txt_idn_display.config(state="readonly")
        #------------ Row 2 -----------------#
        self.btn_start.grid(column=0, row=2, padx=5, pady=5, ipadx=5, ipady=5, sticky="ew")
        self.btn_stop.grid(column=1, row=2, padx=5, pady=5, ipadx=5, ipady=5, sticky="ew")
        self.lbl_mode.grid(column=2, row=2, padx=5, pady=(2, 45), sticky="w") 
        self.drop_trig_mode['values'] = ('AUTO', 'NORMAL', 'SINGLE')
        self.drop_trig_mode.current(0)
        self.drop_trig_mode.grid(column=2, row=2, columnspan=2, padx=5, pady=5, sticky="ew")
        self.drop_trig_mode.bind("<<ComboboxSelected>>", self.change_trigger_mode)


        #//Storage Container//
        storage_config_label = ttk.Label(self.right_column, text="Storage", font=self.default_font)
        self.storage_frame = ttk.LabelFrame(self.right_column, labelwidget=storage_config_label)
        self.storage_frame.grid(row=3, column=0, pady=5, sticky="nsew")
         #---Right-Side Container 20% of all Main Container---

    # ==========================================
    # VISA BACKEND INTERACTION METHODS
    # ==========================================

    def connect_scope(self):
        """Initializes the Scope backend class and handles connection feedback."""
        self.btn_connect.config(text="SEARCHING...", state="disabled")
        self.root.update()
        
        try:
            # Instantiate our backend class (will trigger auto-discovery)
            self.oscilloscope = Scope()
            
            # Fetch identification string
            idn_str = self.oscilloscope.scope.query("*IDN?").strip()
            
            # UI Updates on success
            messagebox.showinfo("Success", f"Connected to Rigol Scope:\n{idn_str}")
            self.btn_connect.config(text="CONNECTED", bg="#27ae60")
            self.btn_disconnect.config(state="normal")
            self.btn_sendcmd.config(state="normal")
            self.txt_idn_display.config(state="normal")       # 1. Unlock it
            self.txt_idn_display.delete(0, tk.END)             # 2. Clear old text
            self.txt_idn_display.insert(0, f"Connected: {idn_str}") # 3. Put IDN inside
            self.txt_idn_display.config(state="readonly")     # 4. Lock it again
            
        except Exception as e:
            # Revert UI state on failure
            messagebox.showerror("Error", f"Failed to connect:\n{e}")
            self.btn_connect.config(text="CONNECT", bg="#2ecc71", state="normal")
            self.oscilloscope = None
            self.txt_idn_display.config(state="normal")
            self.txt_idn_display.delete(0, tk.END)
            self.txt_idn_display.insert(0, "Connection Error!")
            self.txt_idn_display.config(state="readonly")

    def disconnect_scope(self):
        """Safely disconnects from the device and reverts UI controls."""
        if self.oscilloscope:
            self.oscilloscope.disconnect()
            self.oscilloscope = None
            
        messagebox.showinfo("Disconnected", "Session cleanly terminated.")
        self.btn_connect.config(text="CONNECT", bg="#2ecc71", state="normal")
        self.btn_disconnect.config(state="disabled")
        self.btn_sendcmd.config(state="disabled")

    def send_scpi_command(self):
        """Reads a command from the entry box and sends it to the instrument."""
        if not self.oscilloscope or not self.oscilloscope.scope:
            messagebox.showerror("No Connection", "Connect to the scope first!")
            return
            
        command = self.ip_input.get().strip()
        if not command:
            return
            
        try:
            # If it's a query command containing '?', read a response
            if "?" in command:
                response = self.oscilloscope.scope.query(command).strip()
                messagebox.showinfo("Query Response", f"Sent: {command}\n\nReceived: {response}")
            else:
                self.oscilloscope.scope.write(command)
                messagebox.showinfo("Command Sent", f"Successfully wrote:\n{command}")
        except Exception as e:
            messagebox.showerror("Command Error", f"Execution failed:\n{e}")

    def scope_run(self):
        if not self.oscilloscope or not self.oscilloscope.scope:
            messagebox.showerror("Error", "Oscilloscope is not connected!")
            return
        try:
            self.oscilloscope.scope.write(":RUN")
        except Exception as e:
            messagebox.showerror("SCPI Error", f"Failed to send RUN command:\n{e}")

    def scope_stop(self):
        if not self.oscilloscope or not self.oscilloscope.scope:
            messagebox.showerror("Error", "Oscilloscope is not connected!")
            return 
        try:
            self.oscilloscope.scope.write(":STOP")
        except Exception as e:
            messagebox.showerror("SCPI Error", f"Failed to send STOP command:\n{e}")

    def change_trigger_mode(self, event=None):
        if not self.oscilloscope or not self.oscilloscope.scope:
            messagebox.showerror("Error", "Oscilloscope is not connected!")
            return
        selected_mode = self.trigger_mode_var.get()
        
        try:
            scpi_command = f":TRIGger:SWEep {selected_mode}"
            self.oscilloscope.scope.write(scpi_command)         
        except Exception as e:
            messagebox.showerror("SCPI Error", f"Failed to set trigger mode:\n{e}")


# --- Main Block ---
if __name__ == "__main__":
    root = tk.Tk()
    app = ScopeApp(root)
    root.mainloop()
