import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta
import threading
import time
import os
import sys
from pynput import mouse, keyboard
import pyscreenshot as ImageGrab
import requests
import io
from PIL import ImageGrab 
import numpy as np  
import signal
import atexit
import random

# Database Configuration
db_config = {
    'host': '194.59.164.11',
    'user': 'u980535601_tracking',
    'password': '*6EyNH3GNMq',  # Replace with your MySQL password
    'database': 'u980535601_tracking'
}


# Global variables
punch_in_time = None
punch_out_time = None
break_timer_running = False
work_timer_running = False
work_elapsed_time = 0
break_elapsed_time = 0
last_activity_time = time.time()
activity_check_interval = 1  # seconds
inactivity_timeout = 180  # seconds
screenshot_interval = 2461

stop_work_timer_running = False
stop_work_timer_thread = None
stop_work_elapsed_time = 0
stop_reason = None

break_taken = None
break_stop = None


# Hardcoded employee information
emp_email = "anuj@iraveta.com"
emp_id = "EMP0083"

work_timer_thread = None
break_timer_thread = None

# Functions for timers
def update_work_timer():
    """Update the work timer using after()."""
    global work_elapsed_time, work_timer_running
    if work_timer_running:
        work_elapsed_time += 1
        work_timer_label.config(text=f"{str(timedelta(seconds=work_elapsed_time))}")
        root.after(1000, update_work_timer)

def update_break_timer():
    """Update the break timer using after()."""
    global break_elapsed_time, break_timer_running
    if break_timer_running:
        break_elapsed_time += 1
        break_timer_label.config(text=f"{str(timedelta(seconds=break_elapsed_time))}")
        root.after(1000, update_break_timer)

def start_work_timer():
    """Start the work timer."""
    global work_timer_running, work_timer_thread
    if not work_timer_running and work_timer_thread is None:
        work_timer_running = True
        work_timer_thread = threading.Thread(target=update_work_timer, daemon=True)
        work_timer_thread.start()

def stop_work_timer():
    """Stop the work timer."""
    global work_timer_running, work_timer_thread
    work_timer_running = False
    if work_timer_thread is not None:
        work_timer_thread.join()  # Ensure the work timer thread stops before continuing
    work_timer_thread = None  # Reset the thread flag

def start_break_timer():
    """Start the break timer."""
    global break_timer_running, break_timer_thread
    if not break_timer_running and break_timer_thread is None:
        stop_work_timer()  # Stop work timer
        break_timer_running = True
        break_timer_thread = threading.Thread(target=update_break_timer, daemon=True)
        break_timer_thread.start()

def stop_break_timer():
    """Stop the break timer."""
    global break_timer_running, break_timer_thread
    break_timer_running = False
    if break_timer_thread is not None:
        break_timer_thread.join()  # Ensure the break timer thread stops before continuing
    break_timer_thread = None  # Reset the thread flag
    start_work_timer()  # Resume work timer



def capture_and_upload_screenshot(reason):
    try:
        # Capture the screenshot
        screenshot = ImageGrab.grab()
        image_stream = io.BytesIO()
        screenshot.save(image_stream, format='PNG')  # Save screenshot to memory
        image_stream.seek(0)

        # Upload the screenshot
        upload_url = "https://pashine.com.au/tracking/upload.php"
        response = requests.post(
            upload_url,
            files={'screenshot': ('screenshot.png', image_stream, 'image/png')},  # Match the server's expected input name
            data={
                'reason': reason,
                'emp_email': emp_email,  # Include the hardcoded email
                'emp_id': emp_id      # Include the hardcoded employee ID
            },
            headers={'User-Agent': 'EmployeeMonitoringSystem/1.0'}
        )

        # Process server response
        if response.status_code == 200:
            try:
                server_response = response.json()  # Expect JSON from the server
                if server_response.get('status') == 'success':
                    print(f"Screenshot uploaded successfully. Server message: {server_response.get('message')}")
                else:
                    print(f"Upload failed. Server response: {server_response.get('message', 'No message provided.')}")
            except ValueError:
                print(f"Upload failed. Invalid JSON response from server: {response.text}")
        else:
            print(f"Failed to upload screenshot. Status code: {response.status_code}")
            print(f"Response: {response.text}")

    except Exception as e:
        print(f"Error capturing or uploading screenshot: {e}")



# Function to send status to the server
def send_status_to_server():
    global work_timer_running, break_timer_running, last_activity_time, stop_work_timer_running, stop_reason

    status_url = "https://pashine.com.au/tracking/status.php"  # Replace with your server's endpoint
    status_headers = {'User-Agent': 'EmployeeMonitoringSystem/1.0'}
    status_interval = 10  # Send status every 10 seconds

    def status_updater():
        while True:
            # Determine the current status
            if break_timer_running:
                status = "Break"
            if stop_work_timer_running:
                status = stop_reason
            elif time.time() - last_activity_time > inactivity_timeout:
                status = "Inactive"
            elif work_timer_running:
                status = "Active"
            else:
                status = "Inactive"

            # Send the status to the server
            try:
                response = requests.post(
                    status_url,
                    data={'email': emp_email, 'id': emp_id, 'status': status},
                    headers=status_headers
                )

                if response.status_code == 200:
                    print(f"Status '{status}' sent successfully for {emp_email} ({emp_id}).")
                else:
                    print(f"Failed to send status. Server response: {response.text}")
            except Exception as e:
                print(f"Error sending status: {e}")

            # Wait before sending the next status
            time.sleep(status_interval)

    # Start the status updater in a separate thread
    threading.Thread(target=status_updater, daemon=True).start()


# Confirmation Dialog
def confirm_action(action):
    return messagebox.askyesno("Confirmation", f"Are you sure you want to {action}?")

    # Function to fetch commands from the server
    def fetch_command():
        """Fetch the latest command from the server."""
        try:
            server_url = "https://pashine.com.au/tracking/command.php"  # Replace with your actual endpoint
            response = requests.get(server_url)
            if response.status_code == 200:
                data = response.json()  # Expect a JSON response
                if 'command' in data:
                    return data['command']
            else:
                print(f"Failed to fetch command. Status code: {response.status_code}")
        except Exception as e:
            print(f"Error fetching command: {e}")
        return None

    # Function to handle periodic command checking
    def command_listener():
        """Periodically check for server commands."""
        while True:
            time.sleep(10)  # Check every 10 seconds
            command = fetch_command()
            if command == "request_screenshot":
                print("Screenshot request received from the server.")
                capture_and_upload_screenshot("server_request")

    # Add the command listener as a background thread
    threading.Thread(target=command_listener, daemon=True).start()

# Database Functions

def save_all_data():
    global punch_in_time, punch_out_time, work_elapsed_time, break_elapsed_time, emp_id, emp_email

    if not punch_in_time:
        messagebox.showwarning("Warning", "No data to save. Please punch in first.")
        return

    if not punch_out_time:
        punch_out_time = datetime.now()

    # Prepare data for sending to the server
    total_work_time = str(timedelta(seconds=work_elapsed_time))
    total_break_time = str(timedelta(seconds=break_elapsed_time))
    record_date = punch_in_time.date().isoformat()  # Format date as YYYY-MM-DD

    # Data to send to the server
    data = {
        'emp_id': emp_id,
        'emp_email': emp_email,
        'punch_in_time': punch_in_time.isoformat(),
        'punch_out_time': punch_out_time.isoformat(),
        'total_work_time': total_work_time,
        'total_break_time': total_break_time,
        'record_date': record_date
    }

    try:
        # Send data to the server
        response = requests.post("https://pashine.com.au/tracking/save_tracking_data.php", data=data)
        response_data = response.json()

        # Handle server response
        if response.status_code == 200 and response_data.get('status') == 'success':
            messagebox.showinfo("Success", response_data.get('message', 'Data saved successfully.'))
            # Restart the application after successful save
            os.execl(sys.executable, sys.executable, *sys.argv)
        else:
            messagebox.showerror("Error", f"Failed to save data: {response_data.get('message', 'Unknown error')}")
    except requests.RequestException as e:
        print(f"Request error: {e}")
        messagebox.showerror("Error", f"Failed to connect to the server: {e}")


def save_all_data_silent():
    global punch_in_time, punch_out_time, work_elapsed_time, break_elapsed_time, emp_id, emp_email

    if not punch_in_time:
        messagebox.showwarning("Warning", "No data to save. Please punch in first.")
        return

    # Prepare data for sending to the server
    total_work_time = str(timedelta(seconds=work_elapsed_time))
    total_break_time = str(timedelta(seconds=break_elapsed_time))
    record_date = punch_in_time.date().isoformat()  # Format date as YYYY-MM-DD

    # Handle punch_out_time if it is None
    punch_out_time_value = punch_out_time.isoformat() if punch_out_time else None

    # Data to send to the server
    data = {
        'emp_id': emp_id,
        'emp_email': emp_email,
        'punch_in_time': punch_in_time.isoformat(),
        'punch_out_time': punch_out_time_value,
        'total_work_time': total_work_time,
        'total_break_time': total_break_time,
        'record_date': record_date
    }

    try:
        # Send data to the server
        response = requests.post("https://pashine.com.au/tracking/save_tracking_data.php", data=data)
        response_data = response.json()
        # Handle server response
        if response.status_code == 200 and response_data.get('status') == 'success':
            print("Data saved successfully.")
        else:
            messagebox.showerror("Error", f"Failed to save data: {response_data.get('message', 'Unknown error')}")
    except requests.RequestException as e:
        print(f"Request error: {e}")
        messagebox.showerror("Error", f"Failed to connect to the server: {e}")

def save_all_break_data():
    global break_taken, break_stop, emp_id, break_elapsed_time, emp_email

    # Ensure break_taken and break_stop are set
    if not break_taken or not break_stop:
        print("Error: Break start or stop time is missing.")  # Debugging print
        messagebox.showerror("Error", "Break start or stop time is missing.")
        return

    # Prepare data for sending to the server
    total_break_time = str(timedelta(seconds=break_elapsed_time))
    record_date = punch_in_time.date().isoformat()  # Format date as YYYY-MM-DD

    # Data to send to the server
    data = {
        'emp_id': emp_id,
        'emp_email': emp_email,
        'break_taken': break_taken.isoformat(),
        'break_stop': break_stop.isoformat(),
        'total_break_time': total_break_time,
        'record_date': record_date
    }

    try:
        # Send data to the server
        response = requests.post("https://pashine.com.au/tracking/save_break_data.php", data=data)
        response_data = response.json()

        # Handle server response
        if response.status_code == 200 and response_data.get('status') == 'success':
            print("Break data saved successfully.")
        else:
            messagebox.showerror("Error", f"Failed to save data: {response_data.get('message', 'Unknown error')}")
    except requests.RequestException as e:
        print(f"Request error: {e}")
        messagebox.showerror("Error", f"Failed to connect to the server: {e}")

# Main Functions
def punch_in():
    if not confirm_action("punch in"):
        return
    global punch_in_time, punch_out_time, work_elapsed_time
    punch_in_time = datetime.now()
    punch_out_time = None
    punch_in_label.config(text=f"Punch In Time: {punch_in_time.strftime('%d-%m-%Y %H:%M:%S')}")
    punch_out_label.config(text="Punch Out Time: None")
    punch_in_button.config(state=tk.DISABLED)
    punch_out_button.config(state=tk.NORMAL)
    break_button.config(state=tk.NORMAL)
    stop_work_button.config(state=tk.NORMAL)
    work_elapsed_time = 0
    save_all_data_silent()
    start_work_timer()


def punch_out():
    global work_timer_running, punch_out_time, break_timer_running
    if break_timer_running:
        messagebox.showwarning("Warning", "Please complete your break before punching out.")
        return
    if not confirm_action("punch out"):
        return
    if punch_in_time is not None:
        stop_work_timer()
        stop_break_timer()
        work_timer_running = False
        break_timer_running = False
        punch_out_time = datetime.now()
        punch_out_label.config(text=f"Punch Out Time: {punch_out_time.strftime('%d-%m-%Y %H:%M:%S')}")
        punch_in_button.config(state=tk.DISABLED)
        punch_out_button.config(state=tk.DISABLED)
        break_button.config(state=tk.DISABLED)
        stop_break_button.config(state=tk.DISABLED)
        stop_work_button.config(state=tk.DISABLED)
        save_button.config(state=tk.NORMAL)  # Enable save button
        data = (emp_email, emp_id, punch_in_time, punch_out_time, work_elapsed_time, break_elapsed_time)
        print(f"Punch out data: {data}")
        stop_all_threads()
        save_all_data()


def stop_all_threads():
    """
    Ensure that no timer-related threads remain running.
    This function halts all background activity to prevent issues like 2x speed.
    """
    global work_timer_running, break_timer_running

    # Stop the work and break timers if running
    if work_timer_running:
        stop_work_timer()
    if break_timer_running:
        stop_break_timer()

    # Reset thread flags
    work_timer_running = False
    break_timer_running = False


def take_a_break():
    if not confirm_action("take a break"):
        return
    global break_timer_running, break_taken, break_elapsed_time
    if not break_timer_running:
        stop_work_timer()
        break_elapsed_time = 0  # Reset break elapsed time
        break_taken = datetime.now()  # Set break start time
        print(f"Break started at: {break_taken}")  # Debugging print
        start_break_timer()
        break_button.config(state=tk.DISABLED)
        stop_break_button.config(state=tk.NORMAL)
        stop_work_button.config(state=tk.DISABLED)
        resume_work_button.config(state=tk.DISABLED)
        save_all_data_silent()  # Save current work data silently


def stop_break():
    if not confirm_action("stop the break"):
        return
    global break_timer_running, break_stop
    if break_timer_running:
        stop_break_timer()
        break_stop = datetime.now()  # Set break stop time
        print(f"Break stopped at: {break_stop}")  # Debugging print
        break_button.config(state=tk.NORMAL)
        stop_break_button.config(state=tk.DISABLED)
        stop_work_button.config(state=tk.NORMAL)
        resume_work_button.config(state=tk.DISABLED)
        save_all_data_silent()  # Save current work data silently
        save_all_break_data()  # Save break data

def handle_exit_signal(signum, frame):
    print("System is shutting down. Saving data...")
    save_all_data()

# Register signal handlers and exit hooks
signal.signal(signal.SIGTERM, handle_exit_signal)  # Termination signal
signal.signal(signal.SIGINT, handle_exit_signal)   # Interrupt signal (e.g., Ctrl+C)
atexit.register(save_all_data)

# Activity Monitoring
def on_activity():
    global last_activity_time
    last_activity_time = time.time()

def show_alert():
    """Display a high-priority alert asking the user to confirm their presence."""
    def close_alert():
        alert.destroy()

    # Create the alert window
    alert = tk.Tk()
    alert.title("Inactivity Detected")
    alert.geometry("300x150")  # Set the window size
    alert.attributes("-topmost", True)  # Keep the window on top
    alert.protocol("WM_DELETE_WINDOW", lambda: None)  # Disable the close button

    # Get screen width and height
    screen_width = alert.winfo_screenwidth()
    screen_height = alert.winfo_screenheight()

    # Calculate position to center the window
    window_width = 300
    window_height = 150
    position_x = (screen_width // 2) - (window_width // 2)
    position_y = (screen_height // 2) - (window_height // 2)

    # Set the window's position
    alert.geometry(f"{window_width}x{window_height}+{position_x}+{position_y}")

    # Make the window modal
    alert.grab_set()  # Prevent interaction with other windows

    # Create the label and button
    label = tk.Label(alert, text="Please Confirm: Are you here?", font=("Arial", 12))
    label.pack(pady=20)

    yes_button = tk.Button(alert, text="Yes, I am here", command=close_alert, font=("Arial", 10))
    yes_button.pack(pady=10)

    alert.mainloop()  # Start the Tkinter event loop
# Activity Monitoring with Punch-In, Break, and Punch-Out Check
def monitor_activity():
    def check_activity():
        global work_timer_running, last_activity_time, break_timer_running, punch_in_time, punch_out_time

        while True:
            # If punch-in hasn't been done, don't monitor activity
            if punch_in_time is None:
                time.sleep(activity_check_interval)
                continue

            # If punch-out is done, stop the monitoring activity
            if punch_out_time is not None:
                break


            time.sleep(activity_check_interval)

            # If break timer is running, skip the activity check
            if break_timer_running:
                continue  # Skip checking activity if break is active

            if  stop_work_timer_running:
                continue  # Skip checking activity if break is active

            # If no activity for the specified timeout, pause work timer
            if time.time() - last_activity_time > inactivity_timeout:
                if work_timer_running:
                    stop_work_timer()
                    capture_and_upload_screenshot("inactivity")
                    print("Work timer paused due to inactivity.")
                    show_alert()
            else:
                # Only resume work timer if it's not running
                if not work_timer_running:  # Only resume if it's not running
                    start_work_timer()
                    print("Work timer resumed after activity.")

    threading.Thread(target=check_activity, daemon=True).start()

# Function to stop work
def stop_work():
    global stop_work_timer_running, stop_work_elapsed_time, stop_reason

    if work_timer_running:
        stop_work_timer()  # Stop the work timer
        stop_work_timer_running = True
        stop_work_elapsed_time = 0

        # Popup to collect reason for stopping work
        popup = tk.Toplevel(root)
        popup.title("Reason for Stopping Work")
        popup.geometry("300x200")
        popup.configure(bg="#c8d6e5")
        popup.transient(root)
        popup.grab_set()

        def save_reason():
            global stop_reason
            stop_reason = reason_entry.get().strip()
            if not stop_reason:
                messagebox.showwarning("Warning", "Please provide a reason for stopping work.")
                return
            popup.destroy()
            # Start tracking stop work time
            stop_work_label.config(text=f"Reason: {stop_reason}\nTime: {str(timedelta(seconds=stop_work_elapsed_time))}")
            threading.Thread(target=update_stop_work_timer, args=(stop_reason,), daemon=True).start()

        reason_label = tk.Label(popup, text="Reason:", font=("Helvetica", 12), bg="#c8d6e5")
        reason_label.pack(pady=10)
        reason_entry = tk.Entry(popup, font=("Helvetica", 12), width=25)
        reason_entry.pack(pady=10)
        save_button = tk.Button(popup, text="Save", font=("Helvetica", 12), command=save_reason, bg="#10ac84", fg="white")
        save_button.pack(pady=20)
        stop_work_button.config(state=tk.DISABLED)
        resume_work_button.config(state=tk.NORMAL)
        break_button.config(state=tk.DISABLED)
        stop_break_button.config(state=tk.DISABLED)


# Function to update stop work timer
def update_stop_work_timer(reason):
    global stop_work_elapsed_time, stop_work_timer_running
    while stop_work_timer_running:
        time.sleep(1)
        stop_work_elapsed_time += 1
        stop_work_label.config(text=f"Reason: {reason}\nTime: {str(timedelta(seconds=stop_work_elapsed_time))}")

# Function to resume work
def resume_work():
    global stop_work_timer_running, stop_work_elapsed_time

    if stop_work_timer_running:
        # Stop the stop-work timer
        stop_work_timer_running = False

        # Send the stopped time and reason to the server
        data = {
            "emp_email": emp_email,
            "emp_id": emp_id,
            "reason": stop_reason,
            "date_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_stopped_time": str(timedelta(seconds=stop_work_elapsed_time))
        }

        try:
            response = requests.post("https://pashine.com.au/tracking/meetingsave.php", data=data)
            if response.status_code == 200:
                print("Stopped work data sent successfully:", response.text)
            else:
                print("Failed to send stopped work data. Response:", response.text)
        except Exception as e:
            print(f"Error sending stopped work data: {e}")

        # Reset the label and resume work
        stop_work_label.config(text="Reason: None\nTime: 00:00:00")
        stop_work_button.config(state=tk.NORMAL)
        resume_work_button.config(state=tk.DISABLED)
        break_button.config(state=tk.NORMAL)
        stop_break_button.config(state=tk.DISABLED)
        start_work_timer()


# Screenshot Timer
def screenshot_timer():
    while work_timer_running:
        time.sleep(screenshot_interval)
        capture_and_upload_screenshot("hourly")

listener_mouse = mouse.Listener(on_click=lambda x, y, button, pressed: on_activity())
listener_keyboard = keyboard.Listener(on_press=lambda key: on_activity())
listener_mouse.start()
listener_keyboard.start()

def prevent_close():
    # Display a warning message when the user tries to close the window
    messagebox.showwarning("Warning", "You cannot close this window.")
    # Do nothing to prevent the window from closing

# Initialize GUI
root = tk.Tk()
root.title("Iraveta Marketing Solutions")
root.geometry("400x600")
root.protocol("WM_DELETE_WINDOW", prevent_close)
root.configure(bg="#c8d6e5")  # LCD-like background color

# Digital clock-style font
DIGITAL_FONT = ("Courier", 18, "bold")

# GUI Elements
header_label = tk.Label(root, text="Iraveta Marketing Solution", font=("Helvetica", 16, "bold"), bg="#c8d6e5", fg="#222f3e")
header_label.pack(pady=10)

punch_in_label = tk.Label(root, text="Punch In Time: None", font=("Helvetica", 12), bg="#c8d6e5", fg="#222f3e")
punch_in_label.pack(pady=5)

punch_out_label = tk.Label(root, text="Punch Out Time: None", font=("Helvetica", 12), bg="#c8d6e5", fg="#222f3e")
punch_out_label.pack(pady=5)

# GUI Elements for Stop and Resume Work




work_timer_label = tk.Label(root, text="00:00:00", font=DIGITAL_FONT, bg="#576574", fg="#ffffff", width=15, relief="sunken", bd=2)
work_timer_label.pack(pady=10)

break_timer_label = tk.Label(root, text="00:00:00", font=DIGITAL_FONT, bg="#576574", fg="#ffffff", width=15, relief="sunken", bd=2)
break_timer_label.pack(pady=10)

stop_work_label = tk.Label(root, text="Reason: None\nTime: 00:00:00", font=DIGITAL_FONT, bg="#c8d6e5", fg="#222f3e", justify="left")
stop_work_label.pack(pady=10)

button_frame = tk.Frame(root, bg="#c8d6e5")
button_frame.pack(pady=20)

punch_in_button = tk.Button(button_frame, text="Punch In", font=("Helvetica", 12), command=punch_in, bg="#10ac84", fg="white", width=15)
punch_in_button.grid(row=0, column=0, padx=10, pady=5)

punch_out_button = tk.Button(button_frame, text="Punch Out", font=("Helvetica", 12), state=tk.DISABLED, command=punch_out, bg="#ee5253", fg="white", width=15)
punch_out_button.grid(row=0, column=1, padx=10, pady=5)

break_button = tk.Button(button_frame, text="Take a Break", font=("Helvetica", 12), state=tk.DISABLED, command=take_a_break, bg="#ff9f43", fg="white", width=15)
break_button.grid(row=1, column=0, padx=10, pady=5)

stop_break_button = tk.Button(button_frame, text="Stop Break", font=("Helvetica", 12), state=tk.DISABLED, command=stop_break, bg="#1e90ff", fg="white", width=15)
stop_break_button.grid(row=1, column=1, padx=10, pady=5)

stop_work_button = tk.Button(button_frame, text="Physical Work", font=("Helvetica", 12), state=tk.DISABLED,command=stop_work, bg="#ff6b6b", fg="white", width=15)
stop_work_button.grid(row=2, column=0, padx=10, pady=5)

resume_work_button = tk.Button(button_frame, text="Resume PC Work", font=("Helvetica", 12), command=resume_work, state=tk.DISABLED, bg="#54a0ff", fg="white", width=15)
resume_work_button.grid(row=2, column=1, padx=10, pady=5)

save_button = tk.Button(button_frame, text="Save All Data", font=("Helvetica", 12), command=save_all_data, bg="#2ecc71", fg="white", width=15)
save_button.grid(row=3, column=0, columnspan=2, padx=10, pady=5)

# Start monitoring activity
monitor_activity()

send_status_to_server()

# Run the GUI loop
root.mainloop()
