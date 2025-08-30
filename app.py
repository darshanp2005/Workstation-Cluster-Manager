# app.py
# A single script that can run as either a master server or a slave client.
# Use the command-line argument --role to specify its function.

import socketio
import eventlet
import psutil
import subprocess
import argparse
import logging
import time
import os
import threading
from flask import Flask, render_template_string, request

# Configure logging for clear output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Shared Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # project root (where app.py lives)
SHARED_DIRECTORY = os.path.join(BASE_DIR, "shared")    # points to ./shared folder
SERVER_ADDRESS = "0.0.0.0"  # Listen on all interfaces
SERVER_PORT = 5000
HEALTH_REPORT_INTERVAL = 5  # seconds

# HTML template for the simple web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cluster Task Submitter</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f0f2f5; color: #333; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: auto; background-color: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        h1, h2 { color: #2c3e50; }
        form { display: flex; flex-direction: column; gap: 10px; }
        input[type="text"], input[type="number"] { padding: 12px; border-radius: 8px; border: 1px solid #ccc; font-size: 16px; }
        button { padding: 12px; border-radius: 8px; border: none; background-color: #3498db; color: white; font-size: 16px; cursor: pointer; transition: background-color 0.3s ease; }
        button:hover { background-color: #2980b9; }
        .form-group { margin-bottom: 20px; }
        #message { margin-top: 20px; padding: 15px; border-radius: 8px; background-color: #e8f5e9; color: #1b5e20; border: 1px solid #c8e6c9; }
        pre { background-color: #f4f4f4; padding: 10px; border-radius: 8px; white-space: pre-wrap; word-wrap: break-word; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Cluster Task Submitter</h1>
        <h2>Submit a Generic Command</h2>
        <form action="/submit_command" method="post">
            <label for="command">Command:</label>
            <input type="text" id="command" name="command" placeholder="e.g., python3 dummy_task.py" required>
            <button type="submit">Submit Command</button>
        </form>
        <hr style="margin: 40px 0;">
        <h2>Submit a Distributed Job</h2>
        <p>Use {task_id} as a placeholder in the command to specify the batch, frame, or scene number.</p>
        <form action="/submit_job" method="post">
            <div class="form-group">
                <label for="job_name">Job Name:</label>
                <input type="text" id="job_name" name="job_name" value="render_job" required>
            </div>
            <div class="form-group">
                <label for="job_command">Job Command:</label>
                <input type="text" id="job_command" name="job_command" placeholder="e.g., python3 render_video.py --frame {task_id}" required>
            </div>
            <div class="form-group">
                <label for="num_tasks">Number of Tasks (Frames/Batches):</label>
                <input type="number" id="num_tasks" name="num_tasks" value="5" min="1" required>
            </div>
            <button type="submit">Start Distributed Job</button>
        </form>
        {% if message %}
        <div id="message">{{ message }}</div>
        {% endif %}
    </div>
</body>
</html>
"""

# --- Server (Master) Logic ---
def run_server(host, port):
    logging.info("Starting the master server...")
    sio = socketio.Server(async_mode='eventlet')
    app = Flask(__name__)
    app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)

    connected_clients = {}
    ongoing_jobs = {}

    @app.route('/')
    def index():
        return render_template_string(HTML_TEMPLATE)

    @app.route('/submit_command', methods=['POST'])
    def submit_command():
        command = request.form['command']
        logging.info(f"Received new generic command: '{command}'")

        available_clients = {
            sid: data for sid, data in connected_clients.items()
            if data['cpu_percent'] < 80 and data['mem_percent'] < 90
        }
        
        if available_clients:
            least_loaded_sid = min(available_clients, key=lambda sid: available_clients[sid]['tasks_running'])
            client_to_assign = connected_clients[least_loaded_sid]

            task_payload = {
                'task_name': f"user_command_{int(time.time())}",
                'command': command
            }
            
            logging.info(f"Assigning command '{task_payload['task_name']}' to client {least_loaded_sid} ({client_to_assign['host']})")
            sio.emit('task', task_payload, room=least_loaded_sid)
            
            client_to_assign['tasks_running'] += 1
            message = f"Command '{task_payload['task_name']}' has been submitted to client {least_loaded_sid}."
        else:
            message = "No available clients to assign the task to. Please try again later."
        
        return render_template_string(HTML_TEMPLATE, message=message)
        
    @app.route('/submit_job', methods=['POST'])
    def submit_job():
        job_name = request.form['job_name']
        job_command_template = request.form['job_command']
        num_tasks = int(request.form['num_tasks'])
        job_id = f"{job_name}_{int(time.time())}"
        
        logging.info(f"Received new distributed job: '{job_id}' with {num_tasks} tasks.")
        ongoing_jobs[job_id] = {'total_tasks': num_tasks, 'completed_tasks': 0, 'status': 'in-progress'}

        for i in range(num_tasks):
            available_clients = {
                sid: data for sid, data in connected_clients.items()
                if data['cpu_percent'] < 80 and data['mem_percent'] < 90
            }
            
            if not available_clients:
                logging.warning(f"No available clients for job {job_id}. Tasks will be queued.")
                break

            least_loaded_sid = min(available_clients, key=lambda sid: available_clients[sid]['tasks_running'])
            client_to_assign = connected_clients[least_loaded_sid]
            
            command = job_command_template.replace('{task_id}', str(i + 1))
            task_payload = {
                'task_name': f"task_{i+1}of{num_tasks}",
                'command': command,
                'job_id': job_id
            }

            logging.info(f"Assigning task {i+1} of job {job_id} to client {least_loaded_sid} ({client_to_assign['host']})")
            sio.emit('task', task_payload, room=least_loaded_sid)
            client_to_assign['tasks_running'] += 1

        message = f"Distributed job '{job_id}' with {num_tasks} tasks has been started."
        return render_template_string(HTML_TEMPLATE, message=message)

    @sio.event
    def connect(sid, environ):
        client_host = environ.get('REMOTE_ADDR')
        logging.info(f"Client connected: {sid} from {client_host}")
        connected_clients[sid] = {'host': client_host, 'cpu_percent': 0, 'mem_percent': 0, 'tasks_running': 0}
        logging.info(f"Total clients connected: {len(connected_clients)}")

    @sio.event
    def disconnect(sid):
        if sid in connected_clients:
            del connected_clients[sid]
            logging.warning(f"Client disconnected: {sid}")
            logging.info(f"Total clients connected: {len(connected_clients)}")

    @sio.event
    def health_report(sid, data):
        if sid in connected_clients:
            connected_clients[sid].update({
                'cpu_percent': data['cpu_percent'],
                'mem_percent': data['mem_percent'],
                'tasks_running': data['tasks_running']
            })
            logging.info(f"Health report from {connected_clients[sid]['host']} ({sid}): CPU={data['cpu_percent']}%, Memory={data['mem_percent']}%")

    @sio.event
    def task_result(sid, data):
        logging.info(f"Task result received from {connected_clients[sid]['host']} ({sid}) for task '{data['task_name']}':")
        logging.info(f"Status: {data['status']}")
        logging.info(f"Output: \n{data['output']}")
        logging.info(f"Duration: {data['duration']:.2f} seconds")
        
        job_id = data.get('job_id')
        if job_id and job_id in ongoing_jobs:
            ongoing_jobs[job_id]['completed_tasks'] += 1
            completed = ongoing_jobs[job_id]['completed_tasks']
            total = ongoing_jobs[job_id]['total_tasks']
            logging.info(f"Job '{job_id}' progress: {completed}/{total} tasks completed.")
            if completed >= total:
                ongoing_jobs[job_id]['status'] = 'completed'
                logging.info(f"Job '{job_id}' is complete!")
        
        if sid in connected_clients:
            connected_clients[sid]['tasks_running'] -= 1

    eventlet.wsgi.server(eventlet.listen((host, port)), app)

# --- Client (Slave) Logic ---
def run_client(server_url):
    logging.info(f"Starting the slave client and connecting to {server_url}...")
    sio = socketio.Client()
    tasks_running = 0

    @sio.event
    def connect():
        logging.info("Connected to server.")
        sio.emit('health_report', get_health_report())

    @sio.event
    def disconnect():
        logging.warning("Disconnected from server.")

    @sio.event
    def task(data):
        nonlocal tasks_running
        tasks_running += 1
        task_name = data.get('task_name')
        command = data.get('command')
        job_id = data.get('job_id')
        logging.info(f"Received task '{task_name}'. Executing command: {command}")
        execute_task(task_name, command, job_id)
        
    def execute_task(task_name, command, job_id=None):
        nonlocal tasks_running
        start_time = time.time()
        try:
            result = subprocess.run(
                command, 
                shell=True,
                capture_output=True,
                text=True,
                check=True,
                cwd=SHARED_DIRECTORY
            )
            status = "success"
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]\n{result.stderr}"
        except FileNotFoundError:
            status = "error"
            output = "Command not found or shared directory not mounted."
        except subprocess.CalledProcessError as e:
            status = "error"
            output = f"Command failed with error code {e.returncode}:\n{e.stderr}"
        except Exception as e:
            status = "error"
            output = f"An unexpected error occurred: {str(e)}"
        finally:
            tasks_running -= 1
            duration = time.time() - start_time
            sio.emit('task_result', {
                'task_name': task_name,
                'status': status,
                'output': output,
                'duration': duration,
                'job_id': job_id
            })

    def get_health_report():
        return {
            'cpu_percent': psutil.cpu_percent(),
            'mem_percent': psutil.virtual_memory().percent,
            'tasks_running': tasks_running
        }

    def send_health_report():
        while True:
            if sio.connected:
                sio.emit('health_report', get_health_report())
            eventlet.sleep(HEALTH_REPORT_INTERVAL)

    eventlet.spawn(send_health_report)
    
    try:
        sio.connect(server_url)
        sio.wait()
    except socketio.exceptions.ConnectionError as e:
        logging.error(f"Failed to connect to server at {server_url}: {e}")
    except KeyboardInterrupt:
        logging.info("Client stopped by user.")
    finally:
        sio.disconnect()

# --- Main Entry Point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distributed Cluster Manager")
    parser.add_argument('--role', required=True, choices=['server', 'client'],
                        help="The role of this node: 'server' or 'client'.")
    parser.add_argument('--server-host', default='127.0.0.1',
                        help="Host of the server (only for client role).")
    parser.add_argument('--server-port', default=SERVER_PORT, type=int,
                        help="Port of the server.")

    args = parser.parse_args()

    if args.role == 'server':
        run_server(SERVER_ADDRESS, args.server_port)
    elif args.role == 'client':
        server_url = f"http://{args.server_host}:{args.server_port}"
        run_client(server_url)
